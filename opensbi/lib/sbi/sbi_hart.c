/*
 * SPDX-License-Identifier: BSD-2-Clause
 *
 * Copyright (c) 2019 Western Digital Corporation or its affiliates.
 *
 * Authors:
 *   Anup Patel <anup.patel@wdc.com>
 */

#include <sbi/riscv_asm.h>
#include <sbi/riscv_barrier.h>
#include <sbi/riscv_encoding.h>
#include <sbi/riscv_fp.h>
#include <sbi/sbi_bitops.h>
#include <sbi/sbi_console.h>
#include <sbi/sbi_domain.h>
#include <sbi/sbi_csr_detect.h>
#include <sbi/sbi_error.h>
#include <sbi/sbi_hart.h>
#include <sbi/k3_measured_boot.h>
#include <sbi/sbi_math.h>
#include <sbi/sbi_platform.h>
#include <sbi/sbi_pmu.h>
#include <sbi/sbi_string.h>
#include <sbi/sbi_trap.h>
#include <sbi/sbi_hfence.h>
#include <spacemit/k3/core_common.h>

extern void __sbi_expected_trap(void);
extern void __sbi_expected_trap_hext(void);

void (*sbi_hart_expected_trap)(void) = &__sbi_expected_trap;

static unsigned long hart_features_offset;

static void mstatus_init(struct sbi_scratch *scratch)
{
	int cidx;
	unsigned long mstatus_val = 0;
	unsigned int mhpm_mask = sbi_hart_mhpm_mask(scratch);
	uint64_t mhpmevent_init_val = 0;
	uint64_t menvcfg_val, mstateen_val;

	/* Enable FPU */
	if (misa_extension('D') || misa_extension('F'))
		mstatus_val |=  MSTATUS_FS;

	/* Enable Vector context */
	if (misa_extension('V'))
		mstatus_val |=  MSTATUS_VS;

	csr_write(CSR_MSTATUS, mstatus_val);

	/* Disable user mode usage of all perf counters except default ones (CY, TM, IR) */
	if (misa_extension('S') &&
	    sbi_hart_priv_version(scratch) >= SBI_HART_PRIV_VER_1_10)
		csr_write(CSR_SCOUNTEREN, 7);

	/**
	 * OpenSBI doesn't use any PMU counters in M-mode.
	 * Supervisor mode usage for all counters are enabled by default
	 * But counters will not run until mcountinhibit is set.
	 */
	if (sbi_hart_priv_version(scratch) >= SBI_HART_PRIV_VER_1_10)
		csr_write(CSR_MCOUNTEREN, -1);

	/* All programmable counters will start running at runtime after S-mode request */
	if (sbi_hart_priv_version(scratch) >= SBI_HART_PRIV_VER_1_11)
		csr_write(CSR_MCOUNTINHIBIT, 0xFFFFFFF8);

	/**
	 * The mhpmeventn[h] CSR should be initialized with interrupt disabled
	 * and inhibited running in M-mode during init.
	 */
	mhpmevent_init_val |= (MHPMEVENT_OF | MHPMEVENT_MINH);
	for (cidx = 0; cidx <= 28; cidx++) {
		if (!(mhpm_mask & 1 << (cidx + 3)))
			continue;
#if __riscv_xlen == 32
		csr_write_num(CSR_MHPMEVENT3 + cidx,
			       mhpmevent_init_val & 0xFFFFFFFF);
		if (sbi_hart_has_extension(scratch, SBI_HART_EXT_SSCOFPMF))
			csr_write_num(CSR_MHPMEVENT3H + cidx,
				      mhpmevent_init_val >> BITS_PER_LONG);
#else
		csr_write_num(CSR_MHPMEVENT3 + cidx, mhpmevent_init_val);
#endif
	}

	if (sbi_hart_has_extension(scratch, SBI_HART_EXT_SMSTATEEN)) {
		mstateen_val = csr_read(CSR_MSTATEEN0);
#if __riscv_xlen == 32
		mstateen_val |= ((uint64_t)csr_read(CSR_MSTATEEN0H)) << 32;
#endif
		mstateen_val |= SMSTATEEN_STATEN;
		mstateen_val |= SMSTATEEN0_CONTEXT;
		mstateen_val |= SMSTATEEN0_HSENVCFG;

		if (sbi_hart_has_extension(scratch, SBI_HART_EXT_SMAIA))
			mstateen_val |= (SMSTATEEN0_AIA | SMSTATEEN0_IMSIC);
		else
			mstateen_val &= ~(SMSTATEEN0_AIA | SMSTATEEN0_IMSIC);

		if (sbi_hart_has_extension(scratch, SBI_HART_EXT_SMAIA) ||
		    sbi_hart_has_extension(scratch, SBI_HART_EXT_SMCSRIND))
			mstateen_val |= (SMSTATEEN0_SVSLCT);
		else
			mstateen_val &= ~(SMSTATEEN0_SVSLCT);

		csr_write(CSR_MSTATEEN0, mstateen_val);
#if __riscv_xlen == 32
		csr_write(CSR_MSTATEEN0H, mstateen_val >> 32);
#endif
	}

	if (sbi_hart_priv_version(scratch) >= SBI_HART_PRIV_VER_1_12) {
		menvcfg_val = csr_read(CSR_MENVCFG);
#if __riscv_xlen == 32
		menvcfg_val |= ((uint64_t)csr_read(CSR_MENVCFGH)) << 32;
#endif

		/* Disable double trap by default */
		menvcfg_val &= ~ENVCFG_DTE;

#define __set_menvcfg_ext(__ext, __bits)				\
		if (sbi_hart_has_extension(scratch, __ext))		\
			menvcfg_val |= __bits;

		/*
		 * Enable access to extensions if they are present in the
		 * hardware or in the device tree.
		 */

		__set_menvcfg_ext(SBI_HART_EXT_ZICBOZ, ENVCFG_CBZE)
		__set_menvcfg_ext(SBI_HART_EXT_ZICBOM, ENVCFG_CBCFE)
		__set_menvcfg_ext(SBI_HART_EXT_ZICBOM,
				  ENVCFG_CBIE_INV << ENVCFG_CBIE_SHIFT)
#if __riscv_xlen > 32
		__set_menvcfg_ext(SBI_HART_EXT_SVPBMT, ENVCFG_PBMTE)
#endif
		__set_menvcfg_ext(SBI_HART_EXT_SSTC, ENVCFG_STCE)
		__set_menvcfg_ext(SBI_HART_EXT_SMCDELEG, ENVCFG_CDE);
		__set_menvcfg_ext(SBI_HART_EXT_SVADU, ENVCFG_ADUE);

#undef __set_menvcfg_ext

		/*
		 * When both Svade and Svadu are present in DT, the default scheme for managing
		 * the PTE A/D bits should use Svade. Check Svadu before Svade extension to ensure
		 * that the ADUE bit is cleared when the Svade support are specified.
		 */

		if (sbi_hart_has_extension(scratch, SBI_HART_EXT_SVADE))
			menvcfg_val &= ~ENVCFG_ADUE;

		csr_write(CSR_MENVCFG, menvcfg_val);
#if __riscv_xlen == 32
		csr_write(CSR_MENVCFGH, menvcfg_val >> 32);
#endif

		/* Enable S-mode access to seed CSR */
		if (sbi_hart_has_extension(scratch, SBI_HART_EXT_ZKR)) {
			csr_set(CSR_MSECCFG, MSECCFG_SSEED);
			csr_clear(CSR_MSECCFG, MSECCFG_USEED);
		}
	}

	/* Disable all interrupts */
	csr_write(CSR_MIE, 0);

	/* Disable S-mode paging */
	if (misa_extension('S'))
		csr_write(CSR_SATP, 0);
}

static int fp_init(struct sbi_scratch *scratch)
{
#ifdef __riscv_flen
	int i;
#endif

	if (!misa_extension('D') && !misa_extension('F'))
		return 0;

	if (!(csr_read(CSR_MSTATUS) & MSTATUS_FS))
		return SBI_EINVAL;

#ifdef __riscv_flen
	for (i = 0; i < 32; i++)
		init_fp_reg(i);
	csr_write(CSR_FCSR, 0);
#endif

	return 0;
}

static int delegate_traps(struct sbi_scratch *scratch)
{
	const struct sbi_platform *plat = sbi_platform_ptr(scratch);
	unsigned long interrupts, exceptions;

	if (!misa_extension('S'))
		/* No delegation possible as mideleg does not exist */
		return 0;

	/* Send M-mode interrupts and most exceptions to S-mode */
	interrupts = MIP_SSIP | MIP_STIP | MIP_SEIP;
	interrupts |= sbi_pmu_irq_bit();

	exceptions = (1U << CAUSE_MISALIGNED_FETCH) | (1U << CAUSE_BREAKPOINT) |
		     (1U << CAUSE_USER_ECALL);
	if (sbi_platform_has_mfaults_delegation(plat))
		exceptions |= (1U << CAUSE_FETCH_PAGE_FAULT) |
			      (1U << CAUSE_LOAD_PAGE_FAULT) |
			      (1U << CAUSE_STORE_PAGE_FAULT) |
			      (1U << CAUSE_SW_CHECK_EXCP);

	/*
	 * If hypervisor extension available then we only handle hypervisor
	 * calls (i.e. ecalls from HS-mode) in M-mode.
	 *
	 * The HS-mode will additionally handle supervisor calls (i.e. ecalls
	 * from VS-mode), Guest page faults and Virtual interrupts.
	 */
	if (misa_extension('H')) {
		exceptions |= (1U << CAUSE_VIRTUAL_SUPERVISOR_ECALL);
		exceptions |= (1U << CAUSE_FETCH_GUEST_PAGE_FAULT);
		exceptions |= (1U << CAUSE_LOAD_GUEST_PAGE_FAULT);
		exceptions |= (1U << CAUSE_VIRTUAL_INST_FAULT);
		exceptions |= (1U << CAUSE_STORE_GUEST_PAGE_FAULT);
	}

	csr_write(CSR_MIDELEG, interrupts);
	csr_write(CSR_MEDELEG, exceptions);

	return 0;
}

void sbi_hart_delegation_dump(struct sbi_scratch *scratch,
			      const char *prefix, const char *suffix)
{
	if (!misa_extension('S'))
		/* No delegation possible as mideleg does not exist*/
		return;

	sbi_printf("%sMIDELEG%s: 0x%" PRILX "\n",
		   prefix, suffix, csr_read(CSR_MIDELEG));
	sbi_printf("%sMEDELEG%s: 0x%" PRILX "\n",
		   prefix, suffix, csr_read(CSR_MEDELEG));
}

unsigned int sbi_hart_mhpm_mask(struct sbi_scratch *scratch)
{
	struct sbi_hart_features *hfeatures =
			sbi_scratch_offset_ptr(scratch, hart_features_offset);

	return hfeatures->mhpm_mask;
}

unsigned int sbi_hart_pmp_count(struct sbi_scratch *scratch)
{
	struct sbi_hart_features *hfeatures =
			sbi_scratch_offset_ptr(scratch, hart_features_offset);

	return hfeatures->pmp_count;
}

unsigned int sbi_hart_pmp_log2gran(struct sbi_scratch *scratch)
{
	struct sbi_hart_features *hfeatures =
			sbi_scratch_offset_ptr(scratch, hart_features_offset);

	return hfeatures->pmp_log2gran;
}

unsigned int sbi_hart_pmp_addrbits(struct sbi_scratch *scratch)
{
	struct sbi_hart_features *hfeatures =
			sbi_scratch_offset_ptr(scratch, hart_features_offset);

	return hfeatures->pmp_addr_bits;
}

unsigned int sbi_hart_mhpm_bits(struct sbi_scratch *scratch)
{
	struct sbi_hart_features *hfeatures =
			sbi_scratch_offset_ptr(scratch, hart_features_offset);

	return hfeatures->mhpm_bits;
}

/* Smepmp-only setup must not be compiled in Keystone builds. */
#ifndef CONFIG_K3_KEYSTONE_SM
/*
 * Returns Smepmp flags for a given domain and region based on permissions.
 */
static unsigned int sbi_hart_get_smepmp_flags(struct sbi_scratch *scratch,
					      struct sbi_domain *dom,
					      struct sbi_domain_memregion *reg)
{
	unsigned int pmp_flags = 0;

	if (SBI_DOMAIN_MEMREGION_IS_SHARED(reg->flags)) {
		/* Read only for both M and SU modes */
		if (SBI_DOMAIN_MEMREGION_IS_SUR_MR(reg->flags))
			pmp_flags = (PMP_L | PMP_R | PMP_W | PMP_X);

		/* Execute for SU but Read/Execute for M mode */
		else if (SBI_DOMAIN_MEMREGION_IS_SUX_MRX(reg->flags))
			/* locked region */
			pmp_flags = (PMP_L | PMP_W | PMP_X);

		/* Execute only for both M and SU modes */
		else if (SBI_DOMAIN_MEMREGION_IS_SUX_MX(reg->flags))
			pmp_flags = (PMP_L | PMP_W);

		/* Read/Write for both M and SU modes */
		else if (SBI_DOMAIN_MEMREGION_IS_SURW_MRW(reg->flags))
			pmp_flags = (PMP_W | PMP_X);

		/* Read only for SU mode but Read/Write for M mode */
		else if (SBI_DOMAIN_MEMREGION_IS_SUR_MRW(reg->flags))
			pmp_flags = (PMP_W);
	} else if (SBI_DOMAIN_MEMREGION_M_ONLY_ACCESS(reg->flags)) {
		/*
		 * When smepmp is supported and used, M region cannot have RWX
		 * permissions on any region.
		 */
		if ((reg->flags & SBI_DOMAIN_MEMREGION_M_ACCESS_MASK)
		    == SBI_DOMAIN_MEMREGION_M_RWX) {
			sbi_printf("%s: M-mode only regions cannot have"
				   "RWX permissions\n", __func__);
			return 0;
		}

		/* M-mode only access regions are always locked */
		pmp_flags |= PMP_L;

		if (reg->flags & SBI_DOMAIN_MEMREGION_M_READABLE)
			pmp_flags |= PMP_R;
		if (reg->flags & SBI_DOMAIN_MEMREGION_M_WRITABLE)
			pmp_flags |= PMP_W;
		if (reg->flags & SBI_DOMAIN_MEMREGION_M_EXECUTABLE)
			pmp_flags |= PMP_X;
	} else if (SBI_DOMAIN_MEMREGION_SU_ONLY_ACCESS(reg->flags)) {
		if (reg->flags & SBI_DOMAIN_MEMREGION_SU_READABLE)
			pmp_flags |= PMP_R;
		if (reg->flags & SBI_DOMAIN_MEMREGION_SU_WRITABLE)
			pmp_flags |= PMP_W;
		if (reg->flags & SBI_DOMAIN_MEMREGION_SU_EXECUTABLE)
			pmp_flags |= PMP_X;
	}

	return pmp_flags;
}

static void sbi_hart_smepmp_set(struct sbi_scratch *scratch,
				struct sbi_domain *dom,
				struct sbi_domain_memregion *reg,
				unsigned int pmp_idx,
				unsigned int pmp_flags,
				unsigned int pmp_log2gran,
				unsigned long pmp_addr_max)
{
	unsigned long pmp_addr = reg->base >> PMP_SHIFT;

	if (pmp_log2gran <= reg->order && pmp_addr < pmp_addr_max) {
		pmp_set(pmp_idx, pmp_flags, reg->base, reg->order);
	} else {
#if 0
		sbi_printf("Can not configure pmp for domain %s because"
			   " memory region address 0x%lx or size 0x%lx "
			   "is not in range.\n", dom->name, reg->base,
			   reg->order);
#endif
	}
}

static int sbi_hart_smepmp_configure(struct sbi_scratch *scratch,
				     unsigned int pmp_count,
				     unsigned int pmp_log2gran,
				     unsigned long pmp_addr_max)
{
	struct sbi_domain_memregion *reg;
	struct sbi_domain *dom = sbi_domain_thishart_ptr();
	unsigned int pmp_idx, pmp_flags;

	/*
	 * Set the RLB so that, we can write to PMP entries without
	 * enforcement even if some entries are locked.
	 */
	csr_set(CSR_MSECCFG, MSECCFG_RLB);

	/* Disable the reserved entry */
	pmp_disable(SBI_SMEPMP_RESV_ENTRY);

	/* Program M-only regions when MML is not set. */
	pmp_idx = 0;
	sbi_domain_for_each_memregion(dom, reg) {
		/* Skip reserved entry */
		if (pmp_idx == SBI_SMEPMP_RESV_ENTRY)
			pmp_idx++;
		if (pmp_count <= pmp_idx)
			break;

		/* Skip shared and SU-only regions */
		if (!SBI_DOMAIN_MEMREGION_M_ONLY_ACCESS(reg->flags)) {
			pmp_idx++;
			continue;
		}

		pmp_flags = sbi_hart_get_smepmp_flags(scratch, dom, reg);
		if (!pmp_flags)
			return 0;

		sbi_hart_smepmp_set(scratch, dom, reg, pmp_idx++, pmp_flags,
				    pmp_log2gran, pmp_addr_max);
	}

	/* Set the MML to enforce new encoding */
	csr_set(CSR_MSECCFG, MSECCFG_MML);

	/* Program shared and SU-only regions */
	pmp_idx = 0;
	sbi_domain_for_each_memregion(dom, reg) {
		/* Skip reserved entry */
		if (pmp_idx == SBI_SMEPMP_RESV_ENTRY)
			pmp_idx++;
		if (pmp_count <= pmp_idx)
			break;

		/* Skip M-only regions */
		if (SBI_DOMAIN_MEMREGION_M_ONLY_ACCESS(reg->flags)) {
			pmp_idx++;
			continue;
		}

		pmp_flags = sbi_hart_get_smepmp_flags(scratch, dom, reg);
		if (!pmp_flags)
			return 0;

		sbi_hart_smepmp_set(scratch, dom, reg, pmp_idx++, pmp_flags,
				    pmp_log2gran, pmp_addr_max);
	}

	/*
	 * All entries are programmed.
	 * Keep the RLB bit so that dynamic mappings can be done.
	 */

	return 0;
}

#endif /* !CONFIG_K3_KEYSTONE_SM */

#ifdef CONFIG_K3_KEYSTONE_SM
#include <sbi/k3_keystone_boot_slots.h>
#include "k3_pico_itx_pmp.h"
/* Diagnostic only: enabled by K3_PMP_BOOT_TRACE=1 at build time. */
#if defined(K3_PMP_BOOT_TRACE) && K3_PMP_BOOT_TRACE
#define K3_PMP_TRACE(...) sbi_printf("[K3-PMP] " __VA_ARGS__)
#else
#define K3_PMP_TRACE(...) do { } while (0)
#endif
/* The domain remains the source of access policy. Only the adjacent,
 * unlocked firmware RX/RW pair may share one hardware deny entry when
 * legacy PMP gives both entries exactly the same effective permissions.
 * No domain record is removed, and no locked or MMIO entry is folded.
 */
static bool k3_root_is_global_allow(const struct sbi_domain_memregion *r)
{
    return r->base == 0 && r->order == __riscv_xlen &&
	(r->flags & SBI_DOMAIN_MEMREGION_SU_ACCESS_MASK) ==
	SBI_DOMAIN_MEMREGION_SU_ACCESS_MASK &&
	!(r->flags & SBI_DOMAIN_MEMREGION_ENF_PERMISSIONS);
}

static unsigned long k3_root_pmp_permissions(const struct sbi_domain_memregion *r)
{
    unsigned long prot = 0;

    if (r->flags & SBI_DOMAIN_MEMREGION_ENF_PERMISSIONS) {
	prot |= PMP_L;
    }
    if (r->flags & SBI_DOMAIN_MEMREGION_SU_READABLE) {
	prot |= PMP_R;
    }
    if (r->flags & SBI_DOMAIN_MEMREGION_SU_WRITABLE) {
	prot |= PMP_W;
    }
    if (r->flags & SBI_DOMAIN_MEMREGION_SU_EXECUTABLE) {
	prot |= PMP_X;
    }
    return prot;
}

struct k3_root_pmp_layout {
    struct k3_boot_pmp_plan slots;
    const struct sbi_domain_memregion *region[K3_BOOT_PMP_COUNT];
    const struct sbi_domain_memregion *fallback;
    const struct sbi_domain_memregion *folded;
    const struct sbi_domain_memregion *carrier;
    const struct sbi_domain_memregion *utm_guard;
    unsigned int regular;
    bool pico_itx;
};

enum k3_pmp_layout_kind {
    K3_PMP_LAYOUT_ROOT,
    K3_PMP_LAYOUT_COEXIST,
    K3_PMP_LAYOUT_PICO_ITX,
};

struct k3_pmp_entry {
    const struct sbi_domain_memregion *region;
    unsigned long permissions;
};

struct k3_optee_pmp_policy {
    struct k3_pmp_entry entries[K3_BOOT_PMP_COUNT];
    unsigned int switch_mask;
    unsigned int retarget_mask;
};

static const struct sbi_domain *k3_optee_host;
static const struct sbi_domain *k3_optee_tee;
static enum k3_pmp_layout_kind k3_optee_layout;
static bool k3_optee_shared_fallback;
static bool k3_optee_has_utm_guard;
static unsigned int k3_optee_retarget_mask;

/* The DCIU window remains denied while the host's all-range entry is open. */
static const struct sbi_domain_memregion k3_dciu_guard = {
    .base = 0xd8440000UL,
    .order = 16,
    .flags = SBI_DOMAIN_MEMREGION_MMIO,
};

static bool k3_region_matches(const struct sbi_domain_memregion *region,
			      const struct sbi_domain_memregion *expected)
{
    return region->base == expected->base && region->order == expected->order &&
	region->flags == expected->flags;
}

static bool k3_region_overlaps(const struct sbi_domain_memregion *reg,
			       unsigned long base, unsigned long size)
{
    return reg->order >= __riscv_xlen ||
	(base <= reg->base ? reg->base - base < size :
	 base - reg->base < (1UL << reg->order));
}

static bool k3_pico_itx_aia_region(const struct sbi_domain_memregion *reg)
{
    unsigned int i;

    for (i = 0; i < array_size(k3_pico_itx_aia); i++) {
	if (k3_region_matches(reg, &k3_pico_itx_aia[i])) {
	    return true;
	}
    }
    return false;
}

static bool k3_root_firmware_pair(const struct sbi_scratch *scratch,
				  const struct sbi_domain_memregion *rx)
{
    const struct sbi_domain_memregion *rw = rx + 1;

    /* Adjacency is essential: removing RX must not expose an intervening
     * higher-priority rule. Exact flags exclude L, MMIO and S/U grants.
     * The caller rejects active Smepmp policy before using this proof.
     */
    if (rx->flags != (SBI_DOMAIN_MEMREGION_M_READABLE |
		      SBI_DOMAIN_MEMREGION_M_EXECUTABLE) ||
	rw->flags != (SBI_DOMAIN_MEMREGION_M_READABLE |
		      SBI_DOMAIN_MEMREGION_M_WRITABLE) ||
	rx->base != scratch->fw_start || rw->base != rx->base ||
	rx->order >= rw->order || rw->order >= __riscv_xlen) {
	return false;
    }
    if ((1UL << rx->order) != scratch->fw_rw_offset ||
	scratch->fw_size <= scratch->fw_rw_offset ||
	scratch->fw_size > (1UL << rw->order)) {
	return false;
    }
    return k3_root_pmp_permissions(rx) == 0 &&
	k3_root_pmp_permissions(rw) == 0;
}

static int k3_root_pmp_layout_build(struct sbi_scratch *scratch,
				    const struct sbi_domain *dom,
				    unsigned int count, unsigned int gran,
				    unsigned long addr_max,
				    struct k3_root_pmp_layout *layout,
				    bool trace_regions,
				    enum k3_pmp_layout_kind kind)
{
    struct sbi_domain_memregion *reg;
    unsigned int i, broad = 0;
    bool allow_shared = kind != K3_PMP_LAYOUT_ROOT;
    bool share_fallback;

    sbi_memset(layout, 0, sizeof(*layout));
    layout->pico_itx = kind == K3_PMP_LAYOUT_PICO_ITX;
    if (!dom || !dom->regions || !k3_pmp_count_supported(count)) {
	return SBI_ENOTSUPP;
    }
    if (sbi_hart_has_extension(scratch, SBI_HART_EXT_SMEPMP) &&
	(csr_read(CSR_MSECCFG) & (MSECCFG_MML | MSECCFG_MMWP | MSECCFG_RLB))) {
	return SBI_EDENIED;
    }

    sbi_domain_for_each_memregion(dom, reg) {
	if (trace_regions) {
	    K3_PMP_TRACE("region base=0x%lx order=%lu flags=0x%lx pmp=0x%lx\n",
			 reg->base, reg->order, reg->flags,
			 k3_root_pmp_permissions(reg));
	}
	/* Even a folded record must be representable. This optimization
	 * must not hide malformed or below-grain domain metadata.
	 */
	if (reg->order > __riscv_xlen || gran > reg->order ||
	    (reg->base >> PMP_SHIFT) >= addr_max) {
	    K3_PMP_TRACE(
		"REJECT unrepresentable region base=0x%lx order=%lu gran=%u\n",
		reg->base, reg->order, gran);
	    return SBI_ENOTSUPP;
	}
	if (k3_root_is_global_allow(reg)) {
	    if (layout->pico_itx && reg->flags != SBI_DOMAIN_MEMREGION_SU_RWX) {
		return SBI_EDENIED;
	    }
	    layout->fallback = reg;
	    broad++;
	    continue;
	}
	if (allow_shared && k3_region_matches(reg, &k3_dciu_guard)) {
	    if (layout->utm_guard) {
		return SBI_EDENIED;
	    }
	    layout->utm_guard = reg;
	    continue;
	}
	if (!layout->folded && k3_root_firmware_pair(scratch, reg)) {
	    layout->folded = reg;
	    layout->carrier = reg + 1;
	    if (trace_regions) {
		K3_PMP_TRACE(
		    "share firmware deny base=0x%lx order=%lu via order=%lu\n",
		    reg->base, reg->order, layout->carrier->order);
	    }
	    continue;
	}
	if (layout->pico_itx) {
	    if (k3_pico_itx_aia_region(reg)) {
		continue;
	    }
	    for (i = 0; i < K3_PICO_ITX_PMP_FIXED_COUNT; i++) {
		if (k3_region_matches(reg, &k3_pico_itx_host[i])) {
		    break;
		}
	    }
	    if (i == K3_PICO_ITX_PMP_FIXED_COUNT || layout->region[i]) {
		sbi_printf("K3 Pico-ITX PMP: unexpected host region "
			   "base=0x%lx order=%lu flags=0x%lx\n",
			   reg->base, reg->order, reg->flags);
		return SBI_EDENIED;
	    }
	    layout->region[i] = reg;
	    layout->regular++;
	    continue;
	}
	if (layout->regular >= K3_BOOT_FALLBACK) {
	    return SBI_ENOTSUPP;
	}
	layout->region[layout->regular++] = reg;
    }

    share_fallback = allow_shared &&
	layout->regular == K3_BOOT_FALLBACK - K3_BOOT_SHARED_MIN_KEYSTONE;
    if (layout->pico_itx &&
	(!share_fallback || !layout->utm_guard || !layout->carrier)) {
	sbi_printf("K3 Pico-ITX PMP: incomplete host layout\n");
	return SBI_EDENIED;
    }
    if (layout->utm_guard) {
	if (!share_fallback) {
	    return SBI_EDENIED;
	}
	for (i = 0; i < layout->regular; i++) {
	    if (k3_region_overlaps(layout->region[i], k3_dciu_guard.base,
				   1UL << k3_dciu_guard.order)) {
		return SBI_EDENIED;
	    }
	}
    }
    if (k3_boot_plan_slots(count, layout->regular, broad, share_fallback,
			   &layout->slots)) {
	K3_PMP_TRACE(
	    "REJECT root PMP capacity/order regular=%u broad=%u count=%u\n",
	    layout->regular, broad, count);
	return SBI_ENOTSUPP;
    }
    return 0;
}

bool sbi_hart_keystone_optee_overlaps(unsigned long base, unsigned long size)
{
    const struct sbi_domain_memregion *reg;

    if (!k3_optee_tee || !size) {
	return false;
    }
    sbi_domain_for_each_memregion(k3_optee_tee, reg) {
	if (!(reg->flags & SBI_DOMAIN_MEMREGION_SU_ACCESS_MASK)) {
	    continue;
	}
	if (k3_region_overlaps(reg, base, size)) {
	    return true;
	}
    }
    return false;
}

/*
 * QEMU layout for the K3 GEU model. The Linux deny covers the whole window.
 * OP-TEE gets only the GEU page and its closed fallback protects the rest.
 * The registered domains must agree with these firmware-owned definitions.
 */
static int k3_qemu_geu_pmp_slot(const struct k3_root_pmp_layout *layout,
				const struct sbi_domain *tee,
				const struct sbi_domain_memregion *geu,
				unsigned int gran)
{
    static const struct sbi_domain_memregion guard = {
	.base = 0xf0700000UL,
	.order = 14,
	.flags = SBI_DOMAIN_MEMREGION_MMIO,
    };
    static const struct sbi_domain_memregion grant = {
	.base = 0xf0702000UL,
	.order = 12,
	.flags = SBI_DOMAIN_MEMREGION_MMIO | SBI_DOMAIN_MEMREGION_SU_READABLE |
		 SBI_DOMAIN_MEMREGION_SU_WRITABLE,
    };
    const struct sbi_domain_memregion *reg;
    unsigned int i, slot;
    unsigned long size = 1UL << guard.order;

    if (layout->slots.keystone_mask != K3_BOOT_SHARED_SM_MASK ||
	gran > grant.order || !k3_region_matches(geu, &grant)) {
	return SBI_EDENIED;
    }
    for (slot = 0; slot < layout->regular; slot++) {
	if (k3_region_matches(layout->region[slot], &guard)) {
	    break;
	}
    }
    if (slot == layout->regular) {
	return SBI_EDENIED;
    }

    /* Reject any competing rule over the window in either state. */
    for (i = 0; i < layout->regular; i++) {
	if (i != slot && k3_region_overlaps(layout->region[i], guard.base, size)) {
	    return SBI_EDENIED;
	}
    }
    sbi_domain_for_each_memregion(tee, reg) {
	if (reg != geu && k3_region_overlaps(reg, guard.base, size)) {
	    return SBI_EDENIED;
	}
    }
    return slot;
}

static int k3_pico_itx_optee_plan(struct sbi_scratch *scratch,
				 const struct k3_root_pmp_layout *layout,
				 const struct sbi_domain *tee,
				 struct k3_optee_pmp_policy *policy)
{
    const struct sbi_domain_memregion *reg, *host;
    unsigned int i;
    unsigned int gran = sbi_hart_pmp_log2gran(scratch);
    unsigned int bits = sbi_hart_pmp_addrbits(scratch);

    sbi_domain_for_each_memregion(tee, reg) {
	if (k3_pico_itx_aia_region(reg) ||
	    k3_region_matches(reg, layout->folded)) {
	    continue;
	}
	for (i = 0; i < K3_PICO_ITX_PMP_FIXED_COUNT; i++) {
	    host = layout->region[i];
	    /* Inherited root memory is fixed by the host layout. */
	    if ((host->flags & (SBI_DOMAIN_MEMREGION_M_ACCESS_MASK |
				SBI_DOMAIN_MEMREGION_ENF_PERMISSIONS)) &&
		k3_region_matches(reg, host)) {
		break;
	    }
	    if (k3_region_matches(reg, &k3_pico_itx_optee[i])) {
		if (policy->entries[i].region || gran > reg->order ||
		    ((reg->base + (1UL << reg->order) - 1) >> PMP_SHIFT) >=
		    (1UL << bits)) {
		    return SBI_EDENIED;
		}
		policy->entries[i].region = reg;
		policy->entries[i].permissions = k3_root_pmp_permissions(reg);
		policy->switch_mask |= 1U << i;
		if (host->base != reg->base || host->order != reg->order) {
		    policy->retarget_mask |= 1U << i;
		}
		break;
	    }
	}
	if (i == K3_PICO_ITX_PMP_FIXED_COUNT) {
	    sbi_printf("K3 Pico-ITX PMP: unexpected OP-TEE region "
		       "base=0x%lx order=%lu flags=0x%lx\n",
		       reg->base, reg->order, reg->flags);
	    return SBI_EDENIED;
	}
    }
    for (i = 0; i < K3_PICO_ITX_PMP_FIXED_COUNT; i++) {
	if (k3_pico_itx_optee[i].order && !policy->entries[i].region) {
	    sbi_printf("K3 Pico-ITX PMP: missing OP-TEE slot %u\n", i);
	    return SBI_EDENIED;
	}
    }
    policy->switch_mask |= 1U << K3_BOOT_SHARED_UTM;
    return 0;
}

static int k3_optee_pmp_plan(struct sbi_scratch *scratch,
			    const struct k3_root_pmp_layout *layout,
			    const struct sbi_domain *tee,
			    bool allow_qemu_geu,
			    struct k3_optee_pmp_policy *policy)
{
    const struct sbi_domain_memregion *reg, *slot;
    unsigned int i;
    int geu_slot;

    sbi_memset(policy, 0, sizeof(*policy));
    if (layout->pico_itx) {
	return k3_pico_itx_optee_plan(scratch, layout, tee, policy);
    }
    sbi_domain_for_each_memregion(tee, reg) {
	if (!(reg->flags & SBI_DOMAIN_MEMREGION_SU_ACCESS_MASK)) {
	    continue;
	}
	if (reg->flags & SBI_DOMAIN_MEMREGION_ENF_PERMISSIONS) {
	    return SBI_EDENIED;
	}
	if (layout->utm_guard &&
	    k3_region_overlaps(reg, k3_dciu_guard.base,
			       1UL << k3_dciu_guard.order)) {
	    return SBI_EDENIED;
	}
	for (i = 0; i < layout->regular; i++) {
	    slot = layout->region[i];
	    if (slot->base == reg->base && slot->order == reg->order &&
		!((slot->flags ^ reg->flags) & SBI_DOMAIN_MEMREGION_MMIO)) {
		break;
	    }
	}
	if (i == layout->regular && allow_qemu_geu) {
	    geu_slot = k3_qemu_geu_pmp_slot(layout, tee, reg,
					  sbi_hart_pmp_log2gran(scratch));
	    if (geu_slot < 0) {
		return geu_slot;
	    }
	    i = geu_slot;
	    policy->retarget_mask |= 1U << i;
	}
	if (i == layout->regular || (policy->switch_mask & (1U << i))) {
	    return SBI_EDENIED;
	}
	slot = layout->region[i];
	if (slot == layout->carrier ||
	    (slot->flags & (SBI_DOMAIN_MEMREGION_M_ACCESS_MASK |
			    SBI_DOMAIN_MEMREGION_ENF_PERMISSIONS))) {
	    return SBI_EDENIED;
	}
	policy->entries[i].region = reg;
	policy->entries[i].permissions = k3_root_pmp_permissions(reg);
	policy->switch_mask |= 1U << i;
    }
    if (!policy->switch_mask) {
	return SBI_EINVAL;
    }
    if (layout->utm_guard) {
	policy->switch_mask |= 1U << K3_BOOT_SHARED_UTM;
    }
    return 0;
}

/* The first PMP entry covering any log byte must cover the whole log. */
static int k3_check_measured_boot_pmp(const struct k3_root_pmp_layout *layout,
				     const struct k3_pmp_entry *tee)
{
    unsigned int i;

    for (i = 0; i < layout->regular; i++) {
	const struct sbi_domain_memregion *reg = layout->region[i];
	unsigned long end = reg->order >= __riscv_xlen ? ~0UL :
			    reg->base | ((1UL << reg->order) - 1);

	if (reg->base >= K3_MB_LOG_BASE + K3_MB_LOG_CAPACITY ||
	    end < K3_MB_LOG_BASE) {
	    continue;
	}
	if (reg->base != K3_MB_PRIVATE_BASE ||
	    reg->order != K3_MB_PRIVATE_ORDER ||
	    k3_root_pmp_permissions(reg) || !(tee[i].permissions & PMP_R) ||
	    !tee[i].region || tee[i].region->base != reg->base ||
	    tee[i].region->order != reg->order) {
	    return SBI_EDENIED;
	}
	return 0;
    }
    return SBI_EDENIED;
}

/* Called once by the OPTEED driver before any S-mode entry. */
int sbi_hart_keystone_check_optee_pmp(struct sbi_scratch *scratch,
				    const struct sbi_domain *host,
				    const struct sbi_domain *tee,
				    bool measured_boot,
				    enum sbi_k3_optee_pmp_profile profile)
{
    struct k3_root_pmp_layout layout;
    struct k3_optee_pmp_policy tee_policy;
    enum k3_pmp_layout_kind kind = profile == SBI_K3_OPTEE_PMP_PICO_ITX ?
	K3_PMP_LAYOUT_PICO_ITX : K3_PMP_LAYOUT_COEXIST;
    unsigned int bits, i;
    int rc;

    if (!host || !tee || host == tee || k3_optee_host ||
	(sbi_domain_thishart_ptr() != host && sbi_domain_thishart_ptr() != tee)) {
	return SBI_EINVAL;
    }
    bits = sbi_hart_pmp_addrbits(scratch);
    if (!bits || bits >= __riscv_xlen) {
	return SBI_ENOTSUPP;
    }
    rc = k3_root_pmp_layout_build(scratch, host,
				  sbi_hart_pmp_count(scratch),
				  sbi_hart_pmp_log2gran(scratch),
				  (1UL << bits) - 1, &layout, true, kind);
    if (rc) {
	return rc;
    }
    rc = k3_optee_pmp_plan(scratch, &layout, tee,
			   profile == SBI_K3_OPTEE_PMP_QEMU, &tee_policy);
    if (rc) {
	return rc;
    }
    if (layout.slots.keystone_mask == K3_BOOT_SHARED_SM_MASK) {
	for (i = 0; i < layout.regular; i++) {
	    unsigned long prot = k3_root_pmp_permissions(layout.region[i]);

	    if ((prot & PMP_L) && (prot & (PMP_R | PMP_W | PMP_X))) {
		return SBI_EDENIED;
	    }
	}
    }

    if (measured_boot) {
	rc = k3_check_measured_boot_pmp(&layout, tee_policy.entries);
	if (rc) {
	    return rc;
	}
	sbi_printf("K3 measured boot: fixed event log PMP plan verified\n");
    }

    k3_optee_host = host;
    k3_optee_tee = tee;
    k3_optee_layout = kind;
    k3_optee_shared_fallback =
	layout.slots.keystone_mask == K3_BOOT_SHARED_SM_MASK;
    k3_optee_has_utm_guard = layout.utm_guard != NULL;
    k3_optee_retarget_mask = tee_policy.retarget_mask;
    sbi_printf("K3 OP-TEE PMP: fixed=0x%x Keystone=0x%x fallback=%u\n",
	       tee_policy.switch_mask, layout.slots.keystone_mask,
	       layout.slots.fallback_index);
    return 0;
}

bool sbi_hart_keystone_shared_fallback(void)
{
    return k3_optee_shared_fallback;
}

bool sbi_hart_keystone_has_utm_guard(void)
{
    return k3_optee_has_utm_guard;
}

void sbi_hart_keystone_trace_pmp(enum k3_pmp_trace_state state)
{
#if defined(K3_PMP_BOOT_TRACE) && K3_PMP_BOOT_TRACE
    static const char *const state_names[] = {
	[K3_PMP_TRACE_BOOT_HOST] = "boot-host",
	[K3_PMP_TRACE_HOST] = "host",
	[K3_PMP_TRACE_OPTEE] = "optee",
	[K3_PMP_TRACE_ENCLAVE] = "enclave",
    };
    static unsigned int last_mask[SBI_HARTMASK_MAX_BITS][K3_PMP_TRACE_STATE_COUNT];
    struct sbi_scratch *scratch = sbi_scratch_thishart_ptr();
    unsigned int count, i, hartindex;
    unsigned long prot, base, order;
    unsigned int active = 0;

    if (!k3_optee_shared_fallback) {
	return;
    }
    count = sbi_hart_pmp_count(scratch);
    for (i = 0; i < count; i++) {
	if (pmp_get(i, &prot, &base, &order)) {
	    K3_PMP_TRACE("shared readback failed hart=%lu slot=%u\n",
			 csr_read(CSR_MHARTID), i);
	    return;
	}
	if (prot & PMP_A) {
	    active |= 1U << i;
	}
    }
    hartindex = current_hartindex();
    if (last_mask[hartindex][state] == active) {
	return;
    }
    last_mask[hartindex][state] = active;
    K3_PMP_TRACE("shared CSR hart=%lu state=%s implemented=%u gran=%u "
		 "active=%u mask=0x%x\n", csr_read(CSR_MHARTID), state_names[state], count,
		 sbi_hart_pmp_log2gran(scratch), __builtin_popcount(active), active);
    if (k3_optee_has_utm_guard) {
	if (pmp_get(K3_BOOT_SHARED_UTM, &prot, &base, &order)) {
	    K3_PMP_TRACE("shared readback failed hart=%lu slot=%u\n",
			 csr_read(CSR_MHARTID), K3_BOOT_SHARED_UTM);
	    return;
	}
	K3_PMP_TRACE("UTM CSR hart=%lu state=%s slot=%u base=0x%lx "
		     "order=%lu prot=0x%lx\n", csr_read(CSR_MHARTID),
		     state_names[state], K3_BOOT_SHARED_UTM, base, order, prot);
    }
    for (i = 0; i < K3_BOOT_FALLBACK; i++) {
	if (!(k3_optee_retarget_mask & (1U << i))) {
	    continue;
	}
	if (pmp_get(i, &prot, &base, &order)) {
	    K3_PMP_TRACE("shared readback failed hart=%lu slot=%u\n",
			 csr_read(CSR_MHARTID), i);
	    return;
	}
	K3_PMP_TRACE("retarget CSR hart=%lu state=%s slot=%u base=0x%lx "
		     "order=%lu prot=0x%lx\n", csr_read(CSR_MHARTID),
		     state_names[state], i, base, order, prot);
    }
#else
    (void)state;
#endif
}

static int k3_pmp_check_entry(unsigned int index,
			      const struct k3_pmp_entry *entry,
			      unsigned int full_range_order)
{
    const struct sbi_domain_memregion *reg = entry->region;
    unsigned long prot, base, order;
    int rc;

    rc = pmp_get(index, &prot, &base, &order);
    if (rc) {
	return rc;
    }
    if (!reg) {
	return prot ? SBI_EFAIL : 0;
    }
    if (prot != (PMP_A_NAPOT | entry->permissions) || base != reg->base ||
	(reg->order == __riscv_xlen ? order < full_range_order :
	 order != reg->order)) {
	return SBI_EFAIL;
    }
    return 0;
}

static int k3_pmp_write_checked(unsigned int index,
				const struct k3_pmp_entry *entry,
				unsigned int full_range_order)
{
    const struct sbi_domain_memregion *reg = entry->region;
    int rc;

    if (reg) {
	rc = pmp_set(index, entry->permissions, reg->base, reg->order);
    } else {
	rc = pmp_disable(index);
    }
    if (rc) {
	return rc;
    }
    return k3_pmp_check_entry(index, entry, full_range_order);
}

/* Keep fallback closed while updating earlier slots. This function is used
 * for both applying a policy and restoring the verified source policy.
 */
static int k3_pmp_policy_apply(const struct k3_pmp_entry policy[K3_BOOT_PMP_COUNT],
			       unsigned int available, unsigned int moving,
			       unsigned int full_range_order)
{
    const struct k3_pmp_entry disabled = {0};
    const struct k3_pmp_entry closed = {
	.region = policy[K3_BOOT_FALLBACK].region,
    };
    unsigned int i;
    int rc;

    rc = k3_pmp_write_checked(K3_BOOT_FALLBACK, &closed, full_range_order);
    if (rc) {
	return rc;
    }
    for (i = 0; i < K3_BOOT_FALLBACK; i++) {
	if (!(available & (1U << i))) {
	    continue;
	}
	/* Do not carry the old address matching mode across an address write. */
	if ((moving & (1U << i)) && policy[i].region) {
	    rc = k3_pmp_write_checked(i, &disabled, full_range_order);
	    if (rc) {
		return rc;
	    }
	}
	rc = k3_pmp_write_checked(i, &policy[i], full_range_order);
	if (rc) {
	    return rc;
	}
    }
    if (policy[K3_BOOT_FALLBACK].permissions) {
	rc = k3_pmp_write_checked(K3_BOOT_FALLBACK, &policy[K3_BOOT_FALLBACK],
				  full_range_order);
    }
    return rc;
}

static int k3_pmp_policy_verify(const struct k3_pmp_entry policy[K3_BOOT_PMP_COUNT],
				unsigned int available, unsigned int full_range_order)
{
    unsigned int i;
    int rc;

    available |= 1U << K3_BOOT_FALLBACK;
    for (i = 0; i < K3_BOOT_PMP_COUNT; i++) {
	if (!(available & (1U << i))) {
	    continue;
	}
	rc = k3_pmp_check_entry(i, &policy[i], full_range_order);
	if (rc) {
	    return rc;
	}
    }
    return 0;
}

static int k3_pmp_policy_transition(
	struct sbi_scratch *scratch, unsigned int available,
	const struct k3_pmp_entry source[K3_BOOT_PMP_COUNT],
	const struct k3_pmp_entry target[K3_BOOT_PMP_COUNT])
{
    const struct sbi_domain_memregion *fallback =
	source[K3_BOOT_FALLBACK].region;
    unsigned int full_range_order, i, moving = 0;
    int rc;

    if (csr_read(CSR_MSTATUS) & (MSTATUS_MIE | MSTATUS_MPRV)) {
	K3_PMP_TRACE("domain transition rejected mstatus=0x%lx\n",
		     csr_read(CSR_MSTATUS));
	return SBI_EDENIED;
    }
    if (available >= (1U << K3_BOOT_FALLBACK) || !fallback ||
	target[K3_BOOT_FALLBACK].region != fallback ||
	fallback->base || fallback->order != __riscv_xlen) {
	return SBI_EINVAL;
    }
    if ((source[K3_BOOT_FALLBACK].permissions |
	 target[K3_BOOT_FALLBACK].permissions) & PMP_L) {
	return SBI_EDENIED;
    }
    full_range_order = sbi_hart_pmp_addrbits(scratch) + PMP_SHIFT;
    rc = k3_pmp_policy_verify(source, available, full_range_order);
    if (rc) {
	return rc;
    }


    /* Every entry we write must be restorable on a failed transition. */
    for (i = 0; i < K3_BOOT_FALLBACK; i++) {
	const struct sbi_domain_memregion *from = source[i].region;
	const struct sbi_domain_memregion *to = target[i].region;

	if (!(available & (1U << i))) {
	    continue;
	}
	if ((source[i].permissions | target[i].permissions) & PMP_L) {
	    return SBI_EDENIED;
	}
	if (from != to && (!from || !to || from->base != to->base ||
			   from->order != to->order)) {
	    moving |= 1U << i;
	}
    }

    rc = k3_pmp_policy_apply(target, available, moving, full_range_order);
    if (rc && k3_pmp_policy_apply(source, available, moving, full_range_order)) {
	sbi_printf("K3 domain PMP: unable to restore source policy\n");
	sbi_hart_hang();
    }
    __asm__ __volatile__("sfence.vma" ::: "memory");
    return rc;
}

static int k3_optee_pmp_switch_policy(struct sbi_scratch *scratch,
				      const struct k3_root_pmp_layout *layout,
				      bool enter)
{
    struct k3_pmp_entry host[K3_BOOT_PMP_COUNT] = {0};
    struct k3_optee_pmp_policy tee;
    unsigned long prot, addr, order;
    unsigned int i;
    int rc;

    rc = k3_optee_pmp_plan(scratch, layout, k3_optee_tee,
			   k3_optee_retarget_mask != 0, &tee);
    if (rc) {
	return rc;
    }
    if (tee.retarget_mask != k3_optee_retarget_mask ||
	(layout->utm_guard != NULL) != k3_optee_has_utm_guard) {
	return SBI_EDENIED;
    }
    for (i = 0; i < layout->regular; i++) {
	host[i].region = layout->region[i];
	host[i].permissions = k3_root_pmp_permissions(layout->region[i]);
	if (!(tee.switch_mask & (1U << i)) &&
	    (host[i].permissions & (PMP_R | PMP_W | PMP_X))) {
	    return SBI_EDENIED;
	}
    }
    for (i = 0; i < K3_BOOT_PMP_COUNT; i++) {
	if (!(layout->slots.keystone_mask & (1U << i))) {
	    continue;
	}
	if (i == K3_BOOT_SHARED_UTM && layout->utm_guard) {
	    continue;
	}
	rc = pmp_get(i, &prot, &addr, &order);
	if (rc || ((prot & PMP_A) && (prot & (PMP_R | PMP_W | PMP_X)))) {
	    K3_PMP_TRACE("OP-TEE transition rejected Keystone slot=%u prot=0x%lx rc=%d\n",
			 i, prot, rc);
	    return SBI_EDENIED;
	}
    }
    host[K3_BOOT_SHARED_UTM].region = layout->utm_guard;
    host[K3_BOOT_FALLBACK].region = layout->fallback;
    host[K3_BOOT_FALLBACK].permissions = k3_root_pmp_permissions(layout->fallback);
    tee.entries[K3_BOOT_FALLBACK].region = layout->fallback;

    return k3_pmp_policy_transition(scratch, tee.switch_mask,
				    enter ? host : tee.entries,
				    enter ? tee.entries : host);
}

/* Keep the SM-owned full-range OS entry off while OP-TEE runs. */
static int k3_optee_pmp_switch_with_os_slot(
	struct sbi_scratch *scratch, const struct k3_root_pmp_layout *layout,
	bool enter)
{
    extern int k3_keystone_check_os_pmp(bool enabled);
    extern int k3_keystone_set_os_pmp(bool enabled);
    int rc;

    if (k3_optee_shared_fallback) {
	return k3_optee_pmp_switch_policy(scratch, layout, enter);
    }

    if (csr_read(CSR_MSTATUS) & (MSTATUS_MIE | MSTATUS_MPRV) ||
	k3_keystone_check_os_pmp(enter)) {
	return SBI_EDENIED;
    }

    if (enter && k3_keystone_set_os_pmp(false)) {
	rc = SBI_EFAIL;
    } else {
	rc = k3_optee_pmp_switch_policy(scratch, layout, enter);
    }

    if ((enter && rc) || (!enter && !rc)) {
	/* The Linux policy is active before restoring its OS entry. */
	if (k3_keystone_set_os_pmp(true)) {
	    sbi_printf("K3 OP-TEE PMP: OS entry restoration failed\n");
	    sbi_hart_hang();
	}
    }
    __asm__ __volatile__("sfence.vma" ::: "memory");
    return rc;
}

/* Only the trusted domain-context path may call this. Domain assignment
 * and CPU state still belong to the caller until the CSR update succeeds.
 */
int sbi_hart_keystone_switch_optee_pmp(const struct sbi_domain *target)
{
    extern int cpu_is_enclave_context(void);
    const struct sbi_domain *source = sbi_domain_thishart_ptr();
    struct sbi_scratch *scratch = sbi_scratch_thishart_ptr();
    struct k3_root_pmp_layout layout;
    unsigned int bits;
    bool enter;
    int rc;

    if (!k3_optee_host || !k3_optee_tee) {
	return SBI_ENOTSUPP;
    }
    enter = source == k3_optee_host && target == k3_optee_tee;
    if ((!enter && !(source == k3_optee_tee && target == k3_optee_host)) ||
	!sbi_hartmask_test_hartindex(current_hartindex(), target->possible_harts) ||
	cpu_is_enclave_context()) {
	return SBI_EDENIED;
    }
    bits = sbi_hart_pmp_addrbits(scratch);
    if (!bits || bits >= __riscv_xlen) {
	return SBI_ENOTSUPP;
    }
    /* Resolve the Linux allocation even when returning from OP-TEE. */
    rc = k3_root_pmp_layout_build(scratch, k3_optee_host,
				  sbi_hart_pmp_count(scratch),
				  sbi_hart_pmp_log2gran(scratch),
				  (1UL << bits) - 1, &layout, false, k3_optee_layout);
    if (rc) {
	return rc;
    }
    rc = sbi_hart_keystone_verify_extra_pmp(scratch);
    if (rc) {
	return rc;
    }
    rc = k3_optee_pmp_switch_with_os_slot(scratch, &layout, enter);
    if (!rc) {
	sbi_hart_keystone_trace_pmp(enter ? K3_PMP_TRACE_OPTEE : K3_PMP_TRACE_HOST);
    }
    return rc;
}

int sbi_hart_keystone_switch_enclave_pmp(bool enter)
{
    struct sbi_scratch *scratch = sbi_scratch_thishart_ptr();
    struct k3_root_pmp_layout layout;
    struct k3_pmp_entry host[K3_BOOT_PMP_COUNT] = {0};
    struct k3_pmp_entry enclave[K3_BOOT_PMP_COUNT] = {0};
    unsigned int bits, i, available = 0;
    int rc;

    if (!k3_optee_shared_fallback ||
	sbi_domain_thishart_ptr() != k3_optee_host ||
	(csr_read(CSR_MSTATUS) & (MSTATUS_MIE | MSTATUS_MPRV))) {
	return SBI_EDENIED;
    }
    bits = sbi_hart_pmp_addrbits(scratch);
    if (!bits || bits >= __riscv_xlen) {
	return SBI_ENOTSUPP;
    }
    rc = sbi_hart_keystone_verify_extra_pmp(scratch);
    if (rc) {
	return rc;
    }
    rc = k3_root_pmp_layout_build(scratch, k3_optee_host,
				  sbi_hart_pmp_count(scratch),
				  sbi_hart_pmp_log2gran(scratch),
				  (1UL << bits) - 1, &layout, false, k3_optee_layout);
    if (rc) {
	return rc;
    }
    for (i = 0; i < layout.regular; i++) {
	host[i].region = layout.region[i];
	host[i].permissions = k3_root_pmp_permissions(layout.region[i]);
	if (host[i].permissions & (PMP_R | PMP_W | PMP_X)) {
	    if (!layout.pico_itx || i != K3_PICO_ITX_I2C_SLOT) {
		enclave[i].region = layout.region[i];
	    }
	    available |= 1U << i;
	}
    }
    if (layout.utm_guard) {
	host[K3_BOOT_SHARED_UTM].region = layout.utm_guard;
	available |= 1U << K3_BOOT_SHARED_UTM;
    }
    host[K3_BOOT_FALLBACK].region = layout.fallback;
    host[K3_BOOT_FALLBACK].permissions = k3_root_pmp_permissions(layout.fallback);
    enclave[K3_BOOT_FALLBACK].region = layout.fallback;

    /* Entry rollback can reach here after the host policy was restored. */
    if (!enter && !k3_pmp_policy_verify(host, available, bits + PMP_SHIFT)) {
	return 0;
    }
    return k3_pmp_policy_transition(scratch, available, enter ? host : enclave,
				    enter ? enclave : host);
}

const struct sbi_domain *sbi_hart_keystone_optee_host(void)
{
    return k3_optee_host;
}

const struct sbi_domain *sbi_hart_keystone_optee_domain(void)
{
    return k3_optee_tee;
}

bool sbi_hart_keystone_pico_itx(void)
{
    return k3_optee_tee && k3_optee_layout == K3_PMP_LAYOUT_PICO_ITX;
}

/* Keystone admits the Linux layout before installing the S-mode policy. */
int sbi_hart_keystone_optee_boot_policy(struct sbi_scratch *scratch)
{
    struct k3_root_pmp_layout layout;
    unsigned int bits;
    int rc;

    if (!k3_optee_tee || sbi_domain_thishart_ptr() != k3_optee_tee) {
	return 0;
    }
    bits = sbi_hart_pmp_addrbits(scratch);
    if (!bits || bits >= __riscv_xlen) {
	return SBI_ENOTSUPP;
    }
    rc = k3_root_pmp_layout_build(scratch, k3_optee_host,
				  sbi_hart_pmp_count(scratch),
				  sbi_hart_pmp_log2gran(scratch),
				  (1UL << bits) - 1, &layout, true, k3_optee_layout);
    if (rc) {
	return rc;
    }
    rc = k3_optee_pmp_switch_with_os_slot(scratch, &layout, true);
    if (!rc) {
	sbi_hart_keystone_trace_pmp(K3_PMP_TRACE_OPTEE);
    }
    return rc;
}

/* Exercise both directions with lower privilege modes stopped. */
static int k3_optee_pmp_boot_check(struct sbi_scratch *scratch,
				   const struct k3_root_pmp_layout *layout)
{
    int rc;

    if (!k3_optee_tee || k3_optee_host != sbi_domain_thishart_ptr()) {
	return 0;
    }
    rc = k3_optee_pmp_switch_policy(scratch, layout, true);
    if (rc) {
	return rc;
    }
    rc = k3_optee_pmp_switch_policy(scratch, layout, false);
    if (!rc) {
	K3_PMP_TRACE("OP-TEE fixed-slot round trip PASS hart=%lu\n",
		     csr_read(CSR_MHARTID));
    }
    return rc;
}

static int k3_root_pmp_layout_verify(struct sbi_scratch *scratch,
				     const struct k3_root_pmp_layout *layout,
				     unsigned short *locked_mask)
{
    const struct sbi_domain_memregion *reg;
    unsigned long prot, addr, len, expected;
    unsigned int i, required_order;
    unsigned short locks = 0;
    int rc;

    *locked_mask = 0;
    required_order = sbi_hart_pmp_addrbits(scratch) + PMP_SHIFT;
    rc = sbi_hart_keystone_verify_extra_pmp(scratch);
    if (rc) {
	return rc;
    }
    for (i = 0; i < K3_BOOT_PMP_COUNT; i++) {
	rc = pmp_get(i, &prot, &addr, &len);
	if (rc) {
	    return rc;
	}
	if (i < layout->regular) {
	    reg = layout->region[i];
	} else if (i == K3_BOOT_SHARED_UTM && layout->utm_guard) {
	    reg = layout->utm_guard;
	} else if (i == layout->slots.fallback_index) {
	    reg = layout->fallback;
	} else {
	    if (prot & ~(PMP_R | PMP_W | PMP_X)) {
		K3_PMP_TRACE("FAIL nonfree Keystone slot=%u prot=0x%lx\n", i,
			     prot);
		return SBI_EFAIL;
	    }
	    continue;
	}

	expected = k3_root_pmp_permissions(reg);
	if (prot != (PMP_A_NAPOT | expected) || addr != reg->base ||
	    (reg == layout->fallback ? len < required_order :
	     len != reg->order)) {
	    K3_PMP_TRACE("FAIL root readback slot=%u prot=0x%lx expected=0x%lx "
			 "addr=0x%lx len=%lu\n",
			 i, prot, expected, addr, len);
	    return SBI_EFAIL;
	}
	if (reg == layout->carrier) {
	    /* The actual carrier was read back, not just assumed present.
	     * Together with adjacency and equal unlocked deny permissions,
	     * its coverage proves the omitted hardware RX record as well.
	     */
	    if (!layout->folded || prot & (PMP_R | PMP_W | PMP_X | PMP_L) ||
		addr != layout->folded->base || len < layout->folded->order) {
		return SBI_EFAIL;
	    }
	    K3_PMP_TRACE("verified shared firmware deny slot=%u base=0x%lx\n",
			 i, addr);
	}
	if (prot & PMP_L) {
	    locks |= (unsigned short)(1U << i);
	}
    }
    *locked_mask = locks;
    return 0;
}

/* Read-only verification for the later admission gate. Reconstruct the
 * same canonical root layout and verify ALL entries, including free slots.
 * Only this trusted result may authorize locks in the CSR shape preflight.
 */
int sbi_hart_keystone_a1_verify_root_pmp(struct sbi_scratch *scratch,
					 unsigned short *locked_mask)
{
    struct k3_root_pmp_layout layout;
    unsigned int bits;
    unsigned long addr_max;
    const struct sbi_domain *domain = sbi_domain_thishart_ptr();
    bool tee_active = domain == k3_optee_tee;
    int rc;

    if (!scratch || !locked_mask) {
	return SBI_EINVAL;
    }
    *locked_mask = 0;
    bits = sbi_hart_pmp_addrbits(scratch);
    if (!bits || bits >= __riscv_xlen) {
	return SBI_ENOTSUPP;
    }
    addr_max = (1UL << bits) - 1;
    rc = k3_root_pmp_layout_build(scratch, tee_active ? k3_optee_host : domain,
				  sbi_hart_pmp_count(scratch),
				  sbi_hart_pmp_log2gran(scratch), addr_max,
				  &layout, true,
				  tee_active || domain == k3_optee_host ?
				  k3_optee_layout : K3_PMP_LAYOUT_ROOT);
    if (rc) {
	return rc;
    }
    return k3_root_pmp_layout_verify(scratch, &layout, locked_mask);
}

static int k3_keystone_root_pmp_configure(struct sbi_scratch *scratch,
					  unsigned int count, unsigned int gran,
					  unsigned long addr_max)
{
    struct k3_root_pmp_layout layout;
    unsigned short locked_mask;
    unsigned int i, free_slots;
    unsigned long prot, addr, len;
    const struct sbi_domain *domain = sbi_domain_thishart_ptr();
    bool tee_active = domain == k3_optee_tee;
    int rc;

    rc = k3_root_pmp_layout_build(scratch, tee_active ? k3_optee_host : domain,
				  count, gran, addr_max, &layout, true,
				  tee_active || domain == k3_optee_host ?
				  k3_optee_layout : K3_PMP_LAYOUT_ROOT);
    if (rc) {
	return rc;
    }
    free_slots = __builtin_popcount((unsigned int)layout.slots.keystone_mask);
    K3_PMP_TRACE(
	"root plan regular=%u opensbi-mask=0x%x keystone-mask=0x%x free=%u\n",
	layout.regular, layout.slots.opensbi_mask, layout.slots.keystone_mask,
	free_slots);

    /* Never overwrite any active or locked entry left by earlier code. */
    for (i = 0; i < count; i++) {
	rc = pmp_get(i, &prot, &addr, &len);
	if (rc || (prot & (PMP_A | PMP_L))) {
	    K3_PMP_TRACE("REJECT preexisting PMP index=%u rc=%d prot=0x%lx\n",
			 i, rc, prot);
	    return SBI_EDENIED;
	}
    }
    for (i = 0; i < layout.regular; i++) {
	rc = pmp_set(i, k3_root_pmp_permissions(layout.region[i]),
		     layout.region[i]->base, layout.region[i]->order);
	if (rc) {
	    return rc;
	}
    }
    if (layout.utm_guard) {
	rc = pmp_set(K3_BOOT_SHARED_UTM, 0, layout.utm_guard->base,
		     layout.utm_guard->order);
	if (rc) {
	    return rc;
	}
    }
    rc = pmp_set(layout.slots.fallback_index,
		 k3_root_pmp_permissions(layout.fallback),
		 layout.fallback->base, layout.fallback->order);
    if (rc) {
	return rc;
    }
    rc = k3_optee_pmp_boot_check(scratch, &layout);
    if (rc) {
	return rc;
    }
    rc = k3_root_pmp_layout_verify(scratch, &layout, &locked_mask);
    if (rc) {
	return rc;
    }
    sbi_printf(
	"K3 PMP: OpenSBI entries=%u fallback=%u Keystone free=%u mask=0x%x\n",
	layout.regular, layout.slots.fallback_index, free_slots,
	layout.slots.keystone_mask);
    K3_PMP_TRACE("root-config PASS hart=%lu implemented=%u common=%u "
		 "extra-off=%u root=%u Keystone-free=%u\n",
		 csr_read(CSR_MHARTID), count, K3_PMP_COMMON_REGS,
		 count - K3_PMP_COMMON_REGS, layout.regular + 1, free_slots);
    sbi_hart_keystone_trace_pmp(K3_PMP_TRACE_BOOT_HOST);
    return 0;
}

#endif

#ifndef CONFIG_K3_KEYSTONE_SM
static int sbi_hart_oldpmp_configure(struct sbi_scratch *scratch,
				     unsigned int pmp_count,
				     unsigned int pmp_log2gran,
				     unsigned long pmp_addr_max)
{
	struct sbi_domain_memregion *reg;
	struct sbi_domain *dom = sbi_domain_thishart_ptr();
	unsigned int pmp_idx = 0;
	unsigned int pmp_flags;
	unsigned long pmp_addr;

	sbi_domain_for_each_memregion(dom, reg) {
		if (pmp_count <= pmp_idx)
			break;

		pmp_flags = 0;

		/*
		 * If permissions are to be enforced for all modes on
		 * this region, the lock bit should be set.
		 */
		if (reg->flags & SBI_DOMAIN_MEMREGION_ENF_PERMISSIONS)
			pmp_flags |= PMP_L;

		if (reg->flags & SBI_DOMAIN_MEMREGION_SU_READABLE)
			pmp_flags |= PMP_R;
		if (reg->flags & SBI_DOMAIN_MEMREGION_SU_WRITABLE)
			pmp_flags |= PMP_W;
		if (reg->flags & SBI_DOMAIN_MEMREGION_SU_EXECUTABLE)
			pmp_flags |= PMP_X;

		pmp_addr = reg->base >> PMP_SHIFT;
		if (pmp_log2gran <= reg->order && pmp_addr < pmp_addr_max) {
			int rc = pmp_set(pmp_idx++, pmp_flags, reg->base, reg->order);
			if (rc)
				return rc;
		} else {
#if 0
			sbi_printf("Can not configure pmp for domain %s because"
				   " memory region address 0x%lx or size 0x%lx "
				   "is not in range.\n", dom->name, reg->base,
				   reg->order);
#endif
		}
	}

	return 0;
}

#endif /* !CONFIG_K3_KEYSTONE_SM */
#ifdef CONFIG_K3_KEYSTONE_SM
/* Once set, OpenSBI must not reprogram PMP through its normal paths.
 * This bit is a preparatory fail-closed gate; production handoff remains
 * disabled pending PMP capability, CSR readback and Hart admission proof.
 */
int sbi_hart_keystone_verify_extra_pmp(struct sbi_scratch *scratch)
{
    unsigned int i, count;
    unsigned long prot, addr, len;
    int rc;

    if (!scratch) {
	return SBI_EINVAL;
    }
    count = sbi_hart_pmp_count(scratch);
    if (!k3_pmp_count_supported(count)) {
	sbi_printf("[K3-PMP] unsupported hart=%lu implemented=%u common=%u\n",
		   csr_read(CSR_MHARTID), count, K3_PMP_COMMON_REGS);
	return SBI_ENOTSUPP;
    }
    for (i = K3_PMP_COMMON_REGS; i < count; i++) {
	rc = pmp_get(i, &prot, &addr, &len);
	if (rc || (prot & (PMP_A | PMP_L))) {
	    sbi_printf(
		"[K3-PMP] extra rejected hart=%lu index=%u rc=%d prot=0x%lx\n",
		csr_read(CSR_MHARTID), i, rc, prot);
	    return SBI_EDENIED;
	}
    }
    return 0;
}

/* K3 A1: collect local CSR facts without modifying PMP state.
 * Unsafe to invoke from ordinary S-mode; it is only callable from M-mode.
 * All-Hart completeness, priority analysis, park and ownership handoff are
 * deliberately NOT inferred from this function's return value. */
int sbi_hart_keystone_a1_read_pmp_snapshot(struct sbi_scratch *scratch,
					   struct k3_a1_local_pmp_snapshot *out)
{
    unsigned int i, count;
    int rc;
    if (!scratch || !out) {
	return SBI_EINVAL;
    }
    count = sbi_hart_pmp_count(scratch);
    if (!k3_pmp_count_supported(count)) {
	return SBI_ENOTSUPP;
    }
    sbi_memset(out, 0, sizeof(*out));
    out->pmp_count = count;
    out->common_count = K3_PMP_COMMON_REGS;
    out->pmp_log2gran = sbi_hart_pmp_log2gran(scratch);
    if (sbi_hart_has_extension(scratch, SBI_HART_EXT_SMEPMP)) {
	out->mseccfg = csr_read(CSR_MSECCFG);
	out->mseccfg_valid = 1;
    }
    for (i = 0; i < count; i++) {
	rc = pmp_get(i, &out->entry[i].prot, &out->entry[i].addr,
		     &out->entry[i].log2len);
	if (rc) {
	    sbi_memset(out, 0, sizeof(*out));
	    return rc;
	}
    }
    return 0;
}

static unsigned long k3_keystone_block_opensbi_pmp;

void sbi_hart_keystone_pmp_block_opensbi(void)
{
	__atomic_store_n(&k3_keystone_block_opensbi_pmp, 1UL, __ATOMIC_RELEASE);
}

bool sbi_hart_keystone_pmp_opensbi_blocked(void)
{
	return __atomic_load_n(&k3_keystone_block_opensbi_pmp,
				       __ATOMIC_ACQUIRE) != 0;
}
#endif

/* Keep normal SBI S-mode buffer access helpers available in all builds.
 * The only excluded behavior in Keystone mode is the Smepmp-specific PMP
 * mutation. Keystone needs no temporary Smepmp PMP mapping.
 */
int sbi_hart_map_saddr(unsigned long addr, unsigned long size)
{
	/* shared R/W access for M and S/U mode */
#ifndef CONFIG_K3_KEYSTONE_SM
	unsigned int pmp_flags = (PMP_W | PMP_X);
	unsigned long order, base = 0;
	struct sbi_scratch *scratch = sbi_scratch_thishart_ptr();
#endif

#ifdef CONFIG_K3_KEYSTONE_SM
	/* No Smepmp temporary mapping is needed in this build mode. */
	(void)addr;
	(void)size;
	return SBI_OK;
#else
	/* If Smepmp is not supported no special mapping is required */
	if (!sbi_hart_has_extension(scratch, SBI_HART_EXT_SMEPMP))
		return SBI_OK;

	if (is_pmp_entry_mapped(SBI_SMEPMP_RESV_ENTRY))
		return SBI_ENOSPC;

	for (order = MAX(sbi_hart_pmp_log2gran(scratch), log2roundup(size));
	     order <= __riscv_xlen; order++) {
		if (order < __riscv_xlen) {
			base = addr & ~((1UL << order) - 1UL);
			if ((base <= addr) &&
			    (addr < (base + (1UL << order))) &&
			    (base <= (addr + size - 1UL)) &&
			    ((addr + size - 1UL) < (base + (1UL << order))))
				break;
		} else {
			return SBI_EFAIL;
		}
	}

	return pmp_set(SBI_SMEPMP_RESV_ENTRY, pmp_flags, base, order);
#endif /* CONFIG_K3_KEYSTONE_SM */
}

int sbi_hart_unmap_saddr(void)
{
#ifndef CONFIG_K3_KEYSTONE_SM
	struct sbi_scratch *scratch = sbi_scratch_thishart_ptr();
#else
	/* Keystone never installs a Smepmp temporary mapping. */
	return SBI_OK;
#endif

#ifndef CONFIG_K3_KEYSTONE_SM
	if (!sbi_hart_has_extension(scratch, SBI_HART_EXT_SMEPMP))
		return SBI_OK;
	return pmp_disable(SBI_SMEPMP_RESV_ENTRY);
#endif
}

#ifdef CONFIG_K3_KEYSTONE_SM
/* The hardware HSM can power down the hart at the end of OP-TEE boot.
 * Configure empty PMP hardware. Any retained entries must pass the caller's
 * existing full layout readback before the hart can enter S-mode.
 */
int sbi_hart_keystone_optee_restart_pmp(struct sbi_scratch *scratch)
{
    unsigned int count = sbi_hart_pmp_count(scratch);
    unsigned long prot, addr, len;
    unsigned int i;
    int rc;

    for (i = 0; i < count; i++) {
	rc = pmp_get(i, &prot, &addr, &len);
	if (rc) {
	    return rc;
	}
	if (prot & (PMP_A | PMP_L)) {
	    K3_PMP_TRACE("PMP retained on restarted hart=%u\n", current_hartid());
	    return SBI_OK;
	}
    }

    K3_PMP_TRACE("restore PMP on restarted hart=%u\n", current_hartid());
    return sbi_hart_pmp_configure(scratch);
}
#endif

int sbi_hart_pmp_configure(struct sbi_scratch *scratch)
{
#ifdef CONFIG_K3_KEYSTONE_SM
	if (sbi_hart_keystone_pmp_opensbi_blocked()) {
        K3_PMP_TRACE("REJECT blocked Hart=%lu rc=%d\n", csr_read(CSR_MHARTID), SBI_EDENIED);
        return SBI_EDENIED;
    }
#endif

	int rc;
	unsigned int pmp_bits, pmp_log2gran;
	unsigned int pmp_count = sbi_hart_pmp_count(scratch);
	unsigned long pmp_addr_max;

	if (!pmp_count)
		return 0;

	pmp_log2gran = sbi_hart_pmp_log2gran(scratch);
	pmp_bits = sbi_hart_pmp_addrbits(scratch) - 1;
	pmp_addr_max = (1UL << pmp_bits) | ((1UL << pmp_bits) - 1);

#ifdef CONFIG_K3_KEYSTONE_SM
	/*
	 * Keystone selects the legacy PMP initialization path regardless
	 * of hardware Smepmp capability. Do not configure Smepmp policy.
	 * Platform-provided CSR state still requires independent validation.
	 */
	K3_PMP_TRACE("configure-start Hart=%lu count=%u log2gran=%u addrbits=%u\n",
        csr_read(CSR_MHARTID), pmp_count, pmp_log2gran,
        sbi_hart_pmp_addrbits(scratch));
    rc = k3_keystone_root_pmp_configure(scratch, pmp_count,
                                        pmp_log2gran, pmp_addr_max);
    K3_PMP_TRACE("configure-return Hart=%lu rc=%d\n", csr_read(CSR_MHARTID), rc);
#else
	if (sbi_hart_has_extension(scratch, SBI_HART_EXT_SMEPMP))
		rc = sbi_hart_smepmp_configure(scratch, pmp_count,
						pmp_log2gran, pmp_addr_max);
	else
		rc = sbi_hart_oldpmp_configure(scratch, pmp_count,
						pmp_log2gran, pmp_addr_max);
#endif

	/*
	 * As per section 3.7.2 of privileged specification v1.12,
	 * virtual address translations can be speculatively performed
	 * (even before actual access). These, along with PMP traslations,
	 * can be cached. This can pose a problem with CPU hotplug
	 * and non-retentive suspend scenario because PMP states are
	 * not preserved.
	 * It is advisable to flush the caching structures under such
	 * conditions.
	 */
	if (misa_extension('S')) {
		__asm__ __volatile__("sfence.vma");

		/*
		 * If hypervisor mode is supported, flush caching
		 * structures in guest mode too.
		 */
		if (misa_extension('H'))
			__sbi_hfence_gvma_all();
	}

	return rc;
}

int sbi_hart_priv_version(struct sbi_scratch *scratch)
{
	struct sbi_hart_features *hfeatures =
			sbi_scratch_offset_ptr(scratch, hart_features_offset);

	return hfeatures->priv_version;
}

void sbi_hart_get_priv_version_str(struct sbi_scratch *scratch,
				   char *version_str, int nvstr)
{
	char *temp;
	struct sbi_hart_features *hfeatures =
			sbi_scratch_offset_ptr(scratch, hart_features_offset);

	switch (hfeatures->priv_version) {
	case SBI_HART_PRIV_VER_1_10:
		temp = "v1.10";
		break;
	case SBI_HART_PRIV_VER_1_11:
		temp = "v1.11";
		break;
	case SBI_HART_PRIV_VER_1_12:
		temp = "v1.12";
		break;
	default:
		temp = "unknown";
		break;
	}

	sbi_snprintf(version_str, nvstr, "%s", temp);
}

static inline void __sbi_hart_update_extension(
					struct sbi_hart_features *hfeatures,
					enum sbi_hart_extensions ext,
					bool enable)
{
	if (enable)
		__set_bit(ext, hfeatures->extensions);
	else
		__clear_bit(ext, hfeatures->extensions);
}

/**
 * Enable/Disable a particular hart extension
 *
 * @param scratch pointer to the HART scratch space
 * @param ext the extension number to check
 * @param enable new state of hart extension
 */
void sbi_hart_update_extension(struct sbi_scratch *scratch,
			       enum sbi_hart_extensions ext,
			       bool enable)
{
	struct sbi_hart_features *hfeatures =
			sbi_scratch_offset_ptr(scratch, hart_features_offset);

	__sbi_hart_update_extension(hfeatures, ext, enable);
}

/**
 * Check whether a particular hart extension is available
 *
 * @param scratch pointer to the HART scratch space
 * @param ext the extension number to check
 * @returns true (available) or false (not available)
 */
bool sbi_hart_has_extension(struct sbi_scratch *scratch,
			    enum sbi_hart_extensions ext)
{
	struct sbi_hart_features *hfeatures =
			sbi_scratch_offset_ptr(scratch, hart_features_offset);

	if (__test_bit(ext, hfeatures->extensions))
		return true;
	else
		return false;
}

#define __SBI_HART_EXT_DATA(_name, _id) {	\
	.name = #_name,				\
	.id = _id,				\
}

const struct sbi_hart_ext_data sbi_hart_ext[] = {
	__SBI_HART_EXT_DATA(smaia, SBI_HART_EXT_SMAIA),
	__SBI_HART_EXT_DATA(smepmp, SBI_HART_EXT_SMEPMP),
	__SBI_HART_EXT_DATA(smstateen, SBI_HART_EXT_SMSTATEEN),
	__SBI_HART_EXT_DATA(sscofpmf, SBI_HART_EXT_SSCOFPMF),
	__SBI_HART_EXT_DATA(sstc, SBI_HART_EXT_SSTC),
	__SBI_HART_EXT_DATA(zicntr, SBI_HART_EXT_ZICNTR),
	__SBI_HART_EXT_DATA(zihpm, SBI_HART_EXT_ZIHPM),
	__SBI_HART_EXT_DATA(zkr, SBI_HART_EXT_ZKR),
	__SBI_HART_EXT_DATA(smcntrpmf, SBI_HART_EXT_SMCNTRPMF),
	__SBI_HART_EXT_DATA(xandespmu, SBI_HART_EXT_XANDESPMU),
	__SBI_HART_EXT_DATA(zicboz, SBI_HART_EXT_ZICBOZ),
	__SBI_HART_EXT_DATA(zicbom, SBI_HART_EXT_ZICBOM),
	__SBI_HART_EXT_DATA(svpbmt, SBI_HART_EXT_SVPBMT),
	__SBI_HART_EXT_DATA(sdtrig, SBI_HART_EXT_SDTRIG),
	__SBI_HART_EXT_DATA(smcsrind, SBI_HART_EXT_SMCSRIND),
	__SBI_HART_EXT_DATA(smcdeleg, SBI_HART_EXT_SMCDELEG),
	__SBI_HART_EXT_DATA(sscsrind, SBI_HART_EXT_SSCSRIND),
	__SBI_HART_EXT_DATA(ssccfg, SBI_HART_EXT_SSCCFG),
	__SBI_HART_EXT_DATA(svade, SBI_HART_EXT_SVADE),
	__SBI_HART_EXT_DATA(svadu, SBI_HART_EXT_SVADU),
	__SBI_HART_EXT_DATA(smnpm, SBI_HART_EXT_SMNPM),
	__SBI_HART_EXT_DATA(zicfilp, SBI_HART_EXT_ZICFILP),
	__SBI_HART_EXT_DATA(zicfiss, SBI_HART_EXT_ZICFISS),
	__SBI_HART_EXT_DATA(ssdbltrp, SBI_HART_EXT_SSDBLTRP),
};

_Static_assert(SBI_HART_EXT_MAX == array_size(sbi_hart_ext),
	       "sbi_hart_ext[]: wrong number of entries");

/**
 * Get the hart extensions in string format
 *
 * @param scratch pointer to the HART scratch space
 * @param extensions_str pointer to a char array where the extensions string
 *			 will be updated
 * @param nestr length of the features_str. The feature string will be
 *		truncated if nestr is not long enough.
 */
void sbi_hart_get_extensions_str(struct sbi_scratch *scratch,
				 char *extensions_str, int nestr)
{
	struct sbi_hart_features *hfeatures =
			sbi_scratch_offset_ptr(scratch, hart_features_offset);
	int offset = 0, ext = 0;

	if (!extensions_str || nestr <= 0)
		return;
	sbi_memset(extensions_str, 0, nestr);

	for_each_set_bit(ext, hfeatures->extensions, SBI_HART_EXT_MAX) {
		sbi_snprintf(extensions_str + offset,
				 nestr - offset,
				 "%s,", sbi_hart_ext[ext].name);
		offset = offset + sbi_strlen(sbi_hart_ext[ext].name) + 1;
	}

	if (offset)
		extensions_str[offset - 1] = '\0';
	else
		sbi_strncpy(extensions_str, "none", nestr);
}

static unsigned long hart_pmp_get_allowed_addr(void)
{
	unsigned long val = 0;
	struct sbi_trap_info trap = {0};

	csr_write_allowed(CSR_PMPCFG0, &trap, 0);
	if (trap.cause)
		return 0;

	csr_write_allowed(CSR_PMPADDR0, &trap, PMP_ADDR_MASK);
	if (!trap.cause) {
		val = csr_read_allowed(CSR_PMPADDR0, &trap);
		if (trap.cause)
			val = 0;
	}

	return val;
}

static int hart_mhpm_get_allowed_bits(void)
{
	unsigned long val = ~(0UL);
	struct sbi_trap_info trap = {0};
	int num_bits = 0;

	/**
	 * It is assumed that platforms will implement same number of bits for
	 * all the performance counters including mcycle/minstret.
	 */
	csr_write_allowed(CSR_MHPMCOUNTER3, &trap, val);
	if (!trap.cause) {
		val = csr_read_allowed(CSR_MHPMCOUNTER3, &trap);
		if (trap.cause)
			return 0;
	}
	num_bits = sbi_fls(val) + 1;
#if __riscv_xlen == 32
	csr_write_allowed(CSR_MHPMCOUNTER3H, &trap, val);
	if (!trap.cause) {
		val = csr_read_allowed(CSR_MHPMCOUNTER3H, &trap);
		if (trap.cause)
			return num_bits;
	}
	num_bits += sbi_fls(val) + 1;

#endif

	return num_bits;
}

static int hart_detect_features(struct sbi_scratch *scratch)
{
	struct sbi_trap_info trap = {0};
	struct sbi_hart_features *hfeatures =
		sbi_scratch_offset_ptr(scratch, hart_features_offset);
	unsigned long val, oldval;
	bool has_zicntr = false;
	int rc;

	/* If hart features already detected then do nothing */
	if (hfeatures->detected)
		return 0;

	/* Clear hart features */
	sbi_memset(hfeatures->extensions, 0, sizeof(hfeatures->extensions));
	hfeatures->pmp_count = 0;
	hfeatures->mhpm_mask = 0;
	hfeatures->priv_version = SBI_HART_PRIV_VER_UNKNOWN;

#define __check_hpm_csr(__csr, __mask) 					  \
	oldval = csr_read_allowed(__csr, &trap);			  \
	if (!trap.cause) {						  \
		csr_write_allowed(__csr, &trap, 1UL);			  \
		if (!trap.cause && csr_swap(__csr, oldval) == 1UL) {	  \
			(hfeatures->__mask) |= 1 << (__csr - CSR_MCYCLE); \
		}							  \
	}

#define __check_hpm_csr_2(__csr, __mask)	 		  \
	__check_hpm_csr(__csr + 0, __mask)	 		  \
	__check_hpm_csr(__csr + 1, __mask)
#define __check_hpm_csr_4(__csr, __mask)	 		  \
	__check_hpm_csr_2(__csr + 0, __mask) 			  \
	__check_hpm_csr_2(__csr + 2, __mask)
#define __check_hpm_csr_8(__csr, __mask)	 		  \
	__check_hpm_csr_4(__csr + 0, __mask) 			  \
	__check_hpm_csr_4(__csr + 4, __mask)
#define __check_hpm_csr_16(__csr, __mask)	 		  \
	__check_hpm_csr_8(__csr + 0, __mask) 			  \
	__check_hpm_csr_8(__csr + 8, __mask)

#define __check_csr(__csr, __rdonly, __wrval, __field, __skip)		\
	oldval = csr_read_allowed(__csr, &trap);			\
	if (!trap.cause) {						\
		if (__rdonly) {						\
			(hfeatures->__field)++;				\
		} else {						\
			csr_write_allowed(__csr, &trap, __wrval);	\
			if (!trap.cause) {				\
				if ((csr_swap(__csr, oldval) & __wrval) == __wrval)	\
					(hfeatures->__field)++;		\
				else					\
					goto __skip;			\
			} else {					\
				goto __skip;				\
			}						\
		}							\
	} else {							\
		goto __skip;						\
	}
#define __check_csr_2(__csr, __rdonly, __wrval, __field, __skip)	\
	__check_csr(__csr + 0, __rdonly, __wrval, __field, __skip)	\
	__check_csr(__csr + 1, __rdonly, __wrval, __field, __skip)
#define __check_csr_4(__csr, __rdonly, __wrval, __field, __skip)	\
	__check_csr_2(__csr + 0, __rdonly, __wrval, __field, __skip)	\
	__check_csr_2(__csr + 2, __rdonly, __wrval, __field, __skip)
#define __check_csr_8(__csr, __rdonly, __wrval, __field, __skip)	\
	__check_csr_4(__csr + 0, __rdonly, __wrval, __field, __skip)	\
	__check_csr_4(__csr + 4, __rdonly, __wrval, __field, __skip)
#define __check_csr_16(__csr, __rdonly, __wrval, __field, __skip)	\
	__check_csr_8(__csr + 0, __rdonly, __wrval, __field, __skip)	\
	__check_csr_8(__csr + 8, __rdonly, __wrval, __field, __skip)
#define __check_csr_32(__csr, __rdonly, __wrval, __field, __skip)	\
	__check_csr_16(__csr + 0, __rdonly, __wrval, __field, __skip)	\
	__check_csr_16(__csr + 16, __rdonly, __wrval, __field, __skip)
#define __check_csr_64(__csr, __rdonly, __wrval, __field, __skip)	\
	__check_csr_32(__csr + 0, __rdonly, __wrval, __field, __skip)	\
	__check_csr_32(__csr + 32, __rdonly, __wrval, __field, __skip)

	/**
	 * Detect the allowed address bits & granularity. At least PMPADDR0
	 * should be implemented.
	 */
	val = hart_pmp_get_allowed_addr();
	if (val) {
		hfeatures->pmp_log2gran = sbi_ffs(val) + 2;
		hfeatures->pmp_addr_bits = sbi_fls(val) + 1;
		/* Detect number of PMP regions. At least PMPADDR0 should be implemented*/
		__check_csr_64(CSR_PMPADDR0, 0, val, pmp_count, __pmp_skip);
	}
__pmp_skip:
	/* Detect number of MHPM counters */
	__check_hpm_csr(CSR_MHPMCOUNTER3, mhpm_mask);
	hfeatures->mhpm_bits = hart_mhpm_get_allowed_bits();
	__check_hpm_csr_4(CSR_MHPMCOUNTER4, mhpm_mask);
	__check_hpm_csr_8(CSR_MHPMCOUNTER8, mhpm_mask);
	__check_hpm_csr_16(CSR_MHPMCOUNTER16, mhpm_mask);

	/**
	 * No need to check for MHPMCOUNTERH for RV32 as they are expected to be
	 * implemented if MHPMCOUNTER is implemented.
	 */
#undef __check_csr_64
#undef __check_csr_32
#undef __check_csr_16
#undef __check_csr_8
#undef __check_csr_4
#undef __check_csr_2
#undef __check_csr


#define __check_priv(__csr, __base_priv, __priv)			\
	val = csr_read_allowed(__csr, &trap);				\
	if (!trap.cause && (hfeatures->priv_version >= __base_priv)) {	\
		hfeatures->priv_version = __priv;			\
	}

	/* Detect if hart supports Priv v1.10 */
	__check_priv(CSR_MCOUNTEREN,
		     SBI_HART_PRIV_VER_UNKNOWN, SBI_HART_PRIV_VER_1_10);
	/* Detect if hart supports Priv v1.11 */
	__check_priv(CSR_MCOUNTINHIBIT,
		     SBI_HART_PRIV_VER_1_10, SBI_HART_PRIV_VER_1_11);
	/* Detect if hart supports Priv v1.12 */
	__check_priv(CSR_MENVCFG,
		     SBI_HART_PRIV_VER_1_11, SBI_HART_PRIV_VER_1_12);

#undef __check_priv_csr

#define __check_ext_csr(__base_priv, __csr, __ext)			\
	if (hfeatures->priv_version >= __base_priv) {			\
		csr_read_allowed(__csr, &trap);				\
		if (!trap.cause)					\
			__sbi_hart_update_extension(hfeatures,		\
						    __ext, true);	\
	}

	/* Counter overflow/filtering is not useful without mcounter/inhibit */
	/* Detect if hart supports sscofpmf */
	__check_ext_csr(SBI_HART_PRIV_VER_1_11,
			CSR_SCOUNTOVF, SBI_HART_EXT_SSCOFPMF);
	/* Detect if hart supports time CSR */
	__check_ext_csr(SBI_HART_PRIV_VER_UNKNOWN,
			CSR_TIME, SBI_HART_EXT_ZICNTR);
	/* Detect if hart has AIA local interrupt CSRs */
	__check_ext_csr(SBI_HART_PRIV_VER_UNKNOWN,
			CSR_MTOPI, SBI_HART_EXT_SMAIA);
	/* Detect if hart supports stimecmp CSR(Sstc extension) */
	__check_ext_csr(SBI_HART_PRIV_VER_1_12,
			CSR_STIMECMP, SBI_HART_EXT_SSTC);
	/* Detect if hart supports mstateen CSRs */
	__check_ext_csr(SBI_HART_PRIV_VER_1_12,
			CSR_MSTATEEN0, SBI_HART_EXT_SMSTATEEN);
	/* Detect if hart supports smcntrpmf */
	__check_ext_csr(SBI_HART_PRIV_VER_1_12,
			CSR_MCYCLECFG, SBI_HART_EXT_SMCNTRPMF);
	/* Detect if hart support sdtrig (debug triggers) */
	__check_ext_csr(SBI_HART_PRIV_VER_UNKNOWN,
			CSR_TSELECT, SBI_HART_EXT_SDTRIG);

#undef __check_ext_csr

	/* Save trap based detection of Zicntr */
	has_zicntr = sbi_hart_has_extension(scratch, SBI_HART_EXT_ZICNTR);

	/* Let platform populate extensions */
	rc = sbi_platform_extensions_init(sbi_platform_thishart_ptr(),
					  hfeatures);
	if (rc)
		return rc;

	/* Zicntr should only be detected using traps */
	__sbi_hart_update_extension(hfeatures, SBI_HART_EXT_ZICNTR,
				    has_zicntr);

	/* Extensions implied by other extensions and features */
	if (hfeatures->mhpm_mask)
		__sbi_hart_update_extension(hfeatures,
					SBI_HART_EXT_ZIHPM, true);

	/* Mark hart feature detection done */
	hfeatures->detected = true;

	/*
	 * On platforms with Smepmp, the previous booting stage must
	 * enter OpenSBI with mseccfg.MML == 0. This allows OpenSBI
	 * to configure it's own M-mode only regions without depending
	 * on the previous booting stage.
	 */
	if (sbi_hart_has_extension(scratch, SBI_HART_EXT_SMEPMP) &&
	    (csr_read(CSR_MSECCFG) & MSECCFG_MML))
		return SBI_EILL;

	return 0;
}

int sbi_hart_reinit(struct sbi_scratch *scratch)
{
	int rc;

	mstatus_init(scratch);

	rc = fp_init(scratch);
	if (rc)
		return rc;

	rc = delegate_traps(scratch);
	if (rc)
		return rc;

	return 0;
}

int sbi_hart_init(struct sbi_scratch *scratch, bool cold_boot)
{
	int rc;

	/*
	 * Clear mip CSR before proceeding with init to avoid any spurious
	 * external interrupts in S-mode.
	 */
	csr_write(CSR_MIP, 0);

	if (cold_boot) {
		if (misa_extension('H'))
			sbi_hart_expected_trap = &__sbi_expected_trap_hext;

		hart_features_offset = sbi_scratch_alloc_offset(
					sizeof(struct sbi_hart_features));
		if (!hart_features_offset)
			return SBI_ENOMEM;
	}

	rc = hart_detect_features(scratch);
	if (rc)
		return rc;

	return sbi_hart_reinit(scratch);
}

void __attribute__((noreturn)) sbi_hart_hang(void)
{
	while (1)
		wfi();
	__builtin_unreachable();
}

void __attribute__((noreturn))
sbi_hart_switch_mode(unsigned long arg0, unsigned long arg1,
		     unsigned long next_addr, unsigned long next_mode,
		     bool next_virt)
{
#if defined(CONFIG_K3_KEYSTONE_SM) && K3_PMP_BOOT_TRACE
    const struct sbi_domain *host = sbi_hart_keystone_optee_host();
#endif
#if __riscv_xlen == 32
	unsigned long val, valH;
#else
	unsigned long val;
#endif

	switch (next_mode) {
	case PRV_M:
		break;
	case PRV_S:
		if (!misa_extension('S'))
			sbi_hart_hang();
		break;
	case PRV_U:
		if (!misa_extension('U'))
			sbi_hart_hang();
		break;
	default:
		sbi_hart_hang();
	}

	val = csr_read(CSR_MSTATUS);
	val = INSERT_FIELD(val, MSTATUS_MPP, next_mode);
	val = INSERT_FIELD(val, MSTATUS_MPIE, 0);
#if __riscv_xlen == 32
	if (misa_extension('H')) {
		valH = csr_read(CSR_MSTATUSH);
		valH = INSERT_FIELD(valH, MSTATUSH_MPV, next_virt);
		csr_write(CSR_MSTATUSH, valH);
	}
#else
	if (misa_extension('H'))
		val = INSERT_FIELD(val, MSTATUS_MPV, next_virt);
#endif
	csr_write(CSR_MSTATUS, val);
	csr_write(CSR_MEPC, next_addr);

	if (next_mode == PRV_S) {
		if (next_virt) {
			csr_write(CSR_VSTVEC, next_addr);
			csr_write(CSR_VSSCRATCH, 0);
			csr_write(CSR_VSIE, 0);
			csr_write(CSR_VSATP, 0);
		} else {
			csr_write(CSR_STVEC, next_addr);
			csr_write(CSR_SSCRATCH, 0);
			csr_write(CSR_SIE, 0);
			csr_write(CSR_SATP, 0);
		}
	} else if (next_mode == PRV_U) {
		if (misa_extension('N')) {
			csr_write(CSR_UTVEC, next_addr);
			csr_write(CSR_USCRATCH, 0);
			csr_write(CSR_UIE, 0);
		}
	}

	csr_write(CSR_TCMCFG, 1);
	csr_set(CSR_MHCR, (1<<0));

#if defined(CONFIG_K3_KEYSTONE_SM) && K3_PMP_BOOT_TRACE
    if (host && sbi_domain_thishart_ptr() == host &&
	current_hartid() == host->boot_hartid &&
	next_addr == host->next_addr && next_mode == PRV_S && !next_virt) {
	sbi_printf("K3 OP-TEE handoff: mret hart=%u next=%#lx arg1=%#lx\n",
		   current_hartid(), next_addr, arg1);
    }
#endif

	register unsigned long a0 asm("a0") = arg0;
	register unsigned long a1 asm("a1") = arg1;
	__asm__ __volatile__("mret" : : "r"(a0), "r"(a1));
	__builtin_unreachable();
}
