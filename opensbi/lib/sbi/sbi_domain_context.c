/*
 * SPDX-License-Identifier: BSD-2-Clause
 *
 * Copyright (c) IPADS@SJTU 2023. All rights reserved.
 */

#include <sbi/sbi_error.h>
#include <sbi/riscv_locks.h>
#include <sbi/riscv_asm.h>
#include <sbi/sbi_console.h>
#include <sbi/sbi_hsm.h>
#include <sbi/sbi_hart.h>
#include <sbi/sbi_heap.h>
#include <sbi/sbi_scratch.h>
#include <sbi/sbi_string.h>
#include <sbi/sbi_domain.h>
#include <sbi/sbi_domain_context.h>
#include <sbi/sbi_trap.h>

/** Context representation for a hart within a domain */
struct hart_context {
	/** Trap-related states such as GPRs, mepc, and mstatus */
	struct sbi_trap_context trap_ctx;

	/** Supervisor status register */
	unsigned long sstatus;
	/** Supervisor interrupt enable register */
	unsigned long sie;
	/** Supervisor trap vector base address register */
	unsigned long stvec;
	/** Supervisor scratch register for temporary storage */
	unsigned long sscratch;
	/** Supervisor exception program counter register */
	unsigned long sepc;
	/** Supervisor cause register */
	unsigned long scause;
	/** Supervisor trap value register */
	unsigned long stval;
	/** Supervisor interrupt pending register */
	unsigned long sip;
	/** Supervisor address translation and protection register */
	unsigned long satp;
	/** Counter-enable register */
	unsigned long scounteren;
	/** Supervisor environment configuration register */
	unsigned long senvcfg;

	/** Reference to the owning domain */
	struct sbi_domain *dom;
	/** Previous context (caller) to jump to during context exits */
	struct hart_context *prev_ctx;
	/** Is context initialized and runnable */
	bool initialized;
};

struct domain_context_priv {
	/** Contexts for possible HARTs indexed by hartindex */
	struct hart_context *hartindex_to_context_table[SBI_HARTMASK_MAX_BITS];
};

static struct sbi_domain_data dcpriv = {
	.data_size = sizeof(struct domain_context_priv),
};

static inline struct hart_context *hart_context_get(struct sbi_domain *dom,
						    u32 hartindex)
{
	struct domain_context_priv *dcp = sbi_domain_data_ptr(dom, &dcpriv);

	return (dcp && hartindex < SBI_HARTMASK_MAX_BITS) ?
		dcp->hartindex_to_context_table[hartindex] : NULL;
}

static void hart_context_set(struct sbi_domain *dom, u32 hartindex,
			     struct hart_context *hc)
{
	struct domain_context_priv *dcp = sbi_domain_data_ptr(dom, &dcpriv);

	if (dcp && hartindex < SBI_HARTMASK_MAX_BITS)
		dcp->hartindex_to_context_table[hartindex] = hc;
}

/** Macro to obtain the current hart's context pointer */
#define hart_context_thishart_get()					\
	hart_context_get(sbi_domain_thishart_ptr(),			\
			 current_hartindex())

/**
 * Switches the HART context from the current domain to the target domain.
 * This includes changing domain assignments and reconfiguring PMP, as well
 * as saving and restoring CSRs and trap states.
 *
 * @param ctx pointer to the current HART context
 * @param dom_ctx pointer to the target domain context
 * @param set_caller whether to record the current context as the caller
 * @param try_lock whether to acquire both assignment locks without waiting
 *
 * @return 0 on success or an SBI error before committing the switch
 */
static int switch_to_next_domain_context(struct hart_context *ctx,
					 struct hart_context *dom_ctx,
					 bool set_caller, bool try_lock)
{
    u32 hartindex = current_hartindex();
    struct sbi_scratch *scratch = sbi_scratch_thishart_ptr();
    struct sbi_trap_context *trap_ctx = sbi_trap_get_context(scratch);
    struct sbi_domain *current_dom, *target_dom;
#if defined(CONFIG_K3_KEYSTONE_SM) && K3_PMP_BOOT_TRACE
    bool trace_handoff;
#endif
#ifdef CONFIG_K3_KEYSTONE_SM
    int rc;
#else
    unsigned int pmp_count = sbi_hart_pmp_count(scratch);
#endif

    if (!ctx || !dom_ctx || ctx == dom_ctx || !trap_ctx) {
	return SBI_EINVAL;
    }
    current_dom = ctx->dom;
    target_dom = dom_ctx->dom;
#if defined(CONFIG_K3_KEYSTONE_SM) && K3_PMP_BOOT_TRACE
    trace_handoff = !set_caller && !ctx->initialized &&
	current_dom == sbi_hart_keystone_optee_domain() &&
	current_hartid() == current_dom->boot_hartid;
    if (trace_handoff) {
	sbi_printf("K3 OP-TEE handoff: hart=%u target=%s initialized=%d\n",
		   current_hartid(), target_dom->name, dom_ctx->initialized);
    }
#endif

    /* A retryable entry must acquire both locks before changing domains. */
    if (try_lock) {
	if (!spin_trylock(&current_dom->assigned_harts_lock)) {
	    return SBI_EINVALID_STATE;
	}
	if (!spin_trylock(&target_dom->assigned_harts_lock)) {
	    spin_unlock(&current_dom->assigned_harts_lock);
	    return SBI_EINVALID_STATE;
	}
    }

#ifdef CONFIG_K3_KEYSTONE_SM
    /* Update only the OpenSBI-owned fixed slots before publishing the
     * new domain. On error the source retains its existing context.
     */
    rc = sbi_hart_keystone_switch_optee_pmp(target_dom);
#if K3_PMP_BOOT_TRACE
    if (trace_handoff) {
	sbi_printf("K3 OP-TEE handoff: PMP rc=%d\n", rc);
    }
#endif
    if (rc) {
	if (try_lock) {
	    spin_unlock(&target_dom->assigned_harts_lock);
	    spin_unlock(&current_dom->assigned_harts_lock);
	}
	return rc;
    }
#endif

    if (set_caller) {
	dom_ctx->prev_ctx = ctx;
    }

    /* Assign current hart to target domain */
    if (!try_lock) {
	spin_lock(&current_dom->assigned_harts_lock);
    }
#ifdef CONFIG_K3_KEYSTONE_SM
    if (set_caller && dom_ctx->initialized &&
	current_dom == sbi_hart_keystone_optee_host()) {
	sbi_hartmask_set_hartindex(hartindex, &current_dom->optee_caller_harts);
    }
#endif
    sbi_hartmask_clear_hartindex(hartindex, &current_dom->assigned_harts);
    if (!try_lock) {
	spin_unlock(&current_dom->assigned_harts_lock);
    }

    sbi_update_hartindex_to_domain(hartindex, target_dom);

    if (!try_lock) {
	spin_lock(&target_dom->assigned_harts_lock);
    }
#ifdef CONFIG_K3_KEYSTONE_SM
    sbi_hartmask_clear_hartindex(hartindex, &target_dom->optee_caller_harts);
#endif
    sbi_hartmask_set_hartindex(hartindex, &target_dom->assigned_harts);
    spin_unlock(&target_dom->assigned_harts_lock);
    if (try_lock) {
	spin_unlock(&current_dom->assigned_harts_lock);
    }

#if defined(CONFIG_K3_KEYSTONE_SM) && K3_PMP_BOOT_TRACE
    if (trace_handoff) {
	sbi_printf("K3 OP-TEE handoff: domain assignment complete\n");
    }
#endif

    /* Generic domains retain the full PMP reconfiguration path. */
#ifndef CONFIG_K3_KEYSTONE_SM
	for (int i = 0; i < pmp_count; i++) {
		pmp_disable(i);
	}
	sbi_hart_pmp_configure(scratch);
#endif

	/* Save current CSR context and restore target domain's CSR context */
	ctx->sstatus	= csr_swap(CSR_SSTATUS, dom_ctx->sstatus);
	ctx->sie	= csr_swap(CSR_SIE, dom_ctx->sie);
	ctx->stvec	= csr_swap(CSR_STVEC, dom_ctx->stvec);
	ctx->sscratch	= csr_swap(CSR_SSCRATCH, dom_ctx->sscratch);
	ctx->sepc	= csr_swap(CSR_SEPC, dom_ctx->sepc);
	ctx->scause	= csr_swap(CSR_SCAUSE, dom_ctx->scause);
	ctx->stval	= csr_swap(CSR_STVAL, dom_ctx->stval);
	ctx->sip	= csr_swap(CSR_SIP, dom_ctx->sip);
	ctx->satp	= csr_swap(CSR_SATP, dom_ctx->satp);
#ifdef CONFIG_K3_KEYSTONE_SM
    __asm__ __volatile__("sfence.vma" ::: "memory");
#endif
	if (sbi_hart_priv_version(scratch) >= SBI_HART_PRIV_VER_1_10)
		ctx->scounteren = csr_swap(CSR_SCOUNTEREN, dom_ctx->scounteren);
	if (sbi_hart_priv_version(scratch) >= SBI_HART_PRIV_VER_1_12)
		ctx->senvcfg	= csr_swap(CSR_SENVCFG, dom_ctx->senvcfg);

	/* Save current trap state and restore target domain's trap state */
	sbi_memcpy(&ctx->trap_ctx, trap_ctx, sizeof(*trap_ctx));
	sbi_memcpy(trap_ctx, &dom_ctx->trap_ctx, sizeof(*trap_ctx));

	/* Mark current context structure initialized because context saved */
	ctx->initialized = true;

    /* If target domain context is not initialized or runnable */
    if (!dom_ctx->initialized) {
	if (current_hartid() == target_dom->boot_hartid) {
#if defined(CONFIG_K3_KEYSTONE_SM) && K3_PMP_BOOT_TRACE
	    if (trace_handoff) {
		sbi_printf("K3 OP-TEE handoff: switch mode next=%#lx mode=%lu\n",
			   target_dom->next_addr, target_dom->next_mode);
	    }
#endif
	    sbi_hart_switch_mode(target_dom->boot_hartid, target_dom->next_arg1,
				 target_dom->next_addr, target_dom->next_mode,
				 false);
	} else {
#ifdef CONFIG_K3_KEYSTONE_SM
	    sbi_hsm_optee_boot_stop(scratch);
#else
	    sbi_hsm_hart_stop(scratch, true);
#endif
	}
    }
    return 0;
}

/**
 * Set domain entry point
 * @param dom pointer to domain
 * @param entry_point new entry point of domain
 *
 * @return 0 on success and negative error code on failure
 */
int sbi_domain_context_set_mepc(struct sbi_domain *dom, unsigned long entry_point)
{
	struct hart_context *dom_ctx = hart_context_get(dom, current_hartindex());

	/* Validate the domain context existence */
	if (!dom_ctx)
		return SBI_EINVAL;

	dom_ctx->trap_ctx.regs.mepc = entry_point - 4;

	return 0;
}

int sbi_domain_context_enter(struct sbi_domain *dom, bool try_lock)
{
	struct hart_context *ctx = hart_context_thishart_get();
	struct hart_context *dom_ctx = hart_context_get(dom, current_hartindex());

    return switch_to_next_domain_context(ctx, dom_ctx, true, try_lock);
}

int sbi_domain_context_exit(void)
{
	u32 hartindex = current_hartindex();
	struct sbi_domain *dom;
	struct hart_context *ctx = hart_context_thishart_get();
	struct hart_context *dom_ctx, *tmp;

	/*
	 * If it's first time to call `exit` on the current hart, no
	 * context allocated before. Loop through each domain to allocate
	 * its context on the current hart if valid.
	 */
	if (!ctx) {
		sbi_domain_for_each(dom) {
			if (!sbi_hartmask_test_hartindex(hartindex,
							 dom->possible_harts))
				continue;

			dom_ctx = sbi_zalloc(sizeof(struct hart_context));
			if (!dom_ctx)
				return SBI_ENOMEM;

			/* Bind context and domain */
			dom_ctx->dom = dom;
			hart_context_set(dom, hartindex, dom_ctx);
		}

		ctx = hart_context_thishart_get();
	}

    if (!ctx) {
	return SBI_EINVAL;
    }

	dom_ctx = ctx->prev_ctx;

	/* If no previous caller context */
	if (!dom_ctx) {
		/* Try to find next uninitialized user-defined domain's context */
		sbi_domain_for_each(dom) {
			if (dom == &root || dom == sbi_domain_thishart_ptr())
				continue;

			tmp = hart_context_get(dom, hartindex);
			if (tmp && !tmp->initialized) {
				dom_ctx = tmp;
				break;
			}
		}
	}

	/* Take the root domain context if fail to find */
	if (!dom_ctx)
		dom_ctx = hart_context_get(&root, hartindex);

    return switch_to_next_domain_context(ctx, dom_ctx, false, false);
}

#ifdef CONFIG_K3_KEYSTONE_SM
void sbi_domain_context_raise_host_ssip(const struct sbi_domain *host)
{
	struct hart_context *ctx;

	if (sbi_domain_thishart_ptr() == host) {
		csr_set(CSR_MIP, MIP_SSIP);
		return;
	}

	/* The target hart owns this context. The M-mode interrupt handler
	 * and the domain switch cannot run concurrently on this hart.
	 */
	ctx = hart_context_thishart_get();
	if (ctx && ctx->prev_ctx && ctx->prev_ctx->dom == host) {
		ctx->prev_ctx->sip |= MIP_SSIP;
	}
}
#endif

int sbi_domain_context_init(void)
{
	return sbi_domain_register_data(&dcpriv);
}

void sbi_domain_context_deinit(void)
{
	sbi_domain_unregister_data(&dcpriv);
}
