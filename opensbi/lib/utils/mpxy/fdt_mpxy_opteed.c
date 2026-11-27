/*
 * SPDX-License-Identifier: BSD-2-Clause
 *
 * Copyright (c) 2024 Intel Corporation. All rights reserved.
 */

#include <sbi/sbi_error.h>
#include <sbi/k3_measured_boot.h>
#include <sbi/sbi_heap.h>
#include <sbi/sbi_hart.h>
#include <sbi/sbi_mpxy.h>
#include <libfdt.h>
#include <sbi_utils/fdt/fdt_helper.h>
#include <sbi_utils/mpxy/fdt_mpxy.h>
#include <sbi/sbi_domain.h>
#include <sbi/sbi_console.h>

#if __riscv_xlen == 64
#define SHMEM_PHYS_ADDR(_hi, _lo) (_lo)
#elif __riscv_xlen == 32
#define SHMEM_PHYS_ADDR(_hi, _lo) (((u64)(_hi) << 32) | (_lo))
#else
#error "Undefined XLEN"
#endif

#define INVALID_ADDR		(-1U)
#define IS_SHMEM_ADDR_VALID(ms) \
		((ms) && (ms)->shmem.shmem_addr_lo != INVALID_ADDR && \
		 (ms)->shmem.shmem_addr_hi != INVALID_ADDR)

/** Get hart shared memory base address */
static inline void *hart_shmem_base(struct hart_mpxy_state *ms)
{
	return (void *)(unsigned long)SHMEM_PHYS_ADDR(ms->shmem.shmem_addr_hi,
						ms->shmem.shmem_addr_lo);
}

/** SPD TEE MPXY Message IDs */
enum mpxy_opteed_message_id {
	OPTEED_MSG_COMMUNICATE = 0x01,
	OPTEED_MSG_COMPLETE = 0x02,
};

struct abi_entry_vectors {
	uint32_t yield_abi_entry;
	uint32_t fast_abi_entry;
};

struct abi_entry_vectors *entry_vector_table = NULL;

#define ABI_ENTRY_TYPE_FAST		1
#define FUNCID_TYPE_SHIFT		31
#define FUNCID_TYPE_MASK		0x1
#define GET_ABI_ENTRY_TYPE(id)		(((id) >> FUNCID_TYPE_SHIFT) & \
					 FUNCID_TYPE_MASK)

/* Defined in optee_os/core/arch/riscv/include/tee/teeabi_opteed.h */
#define TEEABI_OPTEED_RETURN_ENTRY_DONE 0xBE000000
#define TEEABI_OPTEED_RETURN_ON_DONE 0xBE000001

static char opteed_domain_name[64];
static struct sbi_domain *tdomain, *udomain;

static int opteed_domain_setup(const void *fdt, int nodeoff,
			       const struct fdt_match *match)
{
	const u32 *prop_instance;
	int len, offset;

	prop_instance = fdt_getprop(fdt, nodeoff, "opensbi-domain-instance", &len);
	if (!prop_instance || len < 4)
		return SBI_EINVAL;

	offset = fdt_node_offset_by_phandle(fdt, fdt32_to_cpu(*prop_instance));
	if (offset < 0)
		return SBI_EINVAL;

	strncpy(opteed_domain_name, fdt_get_name(fdt, offset, NULL),
		sizeof(opteed_domain_name));
	opteed_domain_name[sizeof(opteed_domain_name) - 1] = '\0';

	return 0;
}

static struct sbi_domain *__get_tdomain(void)
{
	struct sbi_domain *dom = NULL;
	sbi_domain_for_each(dom) {
		if (!sbi_strcmp(dom->name, opteed_domain_name)) {
			return dom;
		}
	}

	return NULL;
}

static struct sbi_domain *__get_udomain(void)
{
	struct sbi_domain *dom = NULL;
	sbi_domain_for_each(dom) {
		if (!sbi_strcmp(dom->name, "untrusted-domain")) {
			return dom;
		}
	}

	return NULL;
}

static int sbi_ecall_tee_domain_enter(unsigned long entry_point, bool try_lock)
{
    int rc;

    rc = sbi_domain_context_set_mepc(tdomain, entry_point);
    if (rc) {
	return rc;
    }
    return sbi_domain_context_enter(tdomain, try_lock);
}

static int sbi_ecall_tee_domain_exit(void)
{
    return sbi_domain_context_exit();
}

static int mpxy_opteed_send_message_withresp(
    struct sbi_mpxy_channel *channel, u32 msg_id, void *msgbuf, u32 msg_len,
    void *respbuf, u32 resp_max_len, unsigned long *resp_len)
{
    u32 hartidx = current_hartindex();
    struct hart_mpxy_state *ms;
    const ulong *words = msgbuf;
    ulong entry_point;
    bool fast, try_lock = false;

#ifdef CONFIG_K3_KEYSTONE_SM
    extern int k3_keystone_optee_enter(unsigned int hartindex);
    extern void k3_keystone_optee_leave(unsigned int hartindex);
    int rc;
#endif
    if (!tdomain || !udomain || tdomain == udomain) {
	return SBI_ENOTSUPP;
    }

    if (msg_id == OPTEED_MSG_COMMUNICATE) {
	if (sbi_domain_thishart_ptr() != udomain) {
	    return SBI_EDENIED;
	}
	if (msg_len != 8 * sizeof(ulong) || !entry_vector_table) {
	    return SBI_EINVAL;
	}
	ms = hart_mpxy_state_get(tdomain, hartidx);
	if (!IS_SHMEM_ADDR_VALID(ms)) {
	    return SBI_EINVAL;
	}

	fast = GET_ABI_ENTRY_TYPE(words[0]) == ABI_ENTRY_TYPE_FAST;
	if (fast) {
	    entry_point = (ulong)&entry_vector_table->fast_abi_entry;
	} else {
	    entry_point = (ulong)&entry_vector_table->yield_abi_entry;
	}
#if defined(CONFIG_PLATFORM_SPACEMIT_K3) && !defined(CONFIG_K3_KEYSTONE_SM)
	/* Linux retries yielding calls when MPXY reports temporary contention. */
	try_lock = !fast;
#endif
#ifdef CONFIG_K3_KEYSTONE_SM
	rc = k3_keystone_optee_enter(hartidx);
	if (rc) {
	    return rc;
	}
#endif
	sbi_memcpy(hart_shmem_base(ms), msgbuf, msg_len);
#ifdef CONFIG_K3_KEYSTONE_SM
	rc = sbi_ecall_tee_domain_enter(entry_point, try_lock);
	if (rc) {
	    k3_keystone_optee_leave(hartidx);
	}
	return rc;
#else
	return sbi_ecall_tee_domain_enter(entry_point, try_lock);
#endif
    }

    if (msg_id == OPTEED_MSG_COMPLETE) {
	if (sbi_domain_thishart_ptr() != tdomain) {
	    return SBI_EDENIED;
	}
	if (msg_len != 5 * sizeof(ulong) || !resp_len ||
	    resp_max_len < msg_len - sizeof(ulong)) {
	    return SBI_EINVAL;
	}
	ms = hart_mpxy_state_get(udomain, hartidx);
#ifdef CONFIG_K3_KEYSTONE_SM
	if (IS_SHMEM_ADDR_VALID(ms)) {
	    rc = sbi_ecall_tee_domain_exit();
	    if (!rc) {
		sbi_memcpy(hart_shmem_base(ms), &words[1], msg_len - sizeof(ulong));
		*resp_len = msg_len - sizeof(ulong);
		k3_keystone_optee_leave(hartidx);
	    }
	    return rc;
	}
	if (current_hartid() != tdomain->boot_hartid) {
	    if (words[0] != TEEABI_OPTEED_RETURN_ON_DONE || words[1]) {
		return SBI_EINVAL;
	    }
	} else if (words[0] != TEEABI_OPTEED_RETURN_ENTRY_DONE || !words[1] ||
	    words[1] % sizeof(u32) ||
	    !sbi_domain_check_addr_range(tdomain, words[1],
		sizeof(*entry_vector_table), PRV_S, SBI_DOMAIN_EXECUTE)) {
	    return SBI_EINVAL;
	}
#endif
	if (!IS_SHMEM_ADDR_VALID(ms)) {
	    if (words[0] == TEEABI_OPTEED_RETURN_ENTRY_DONE) {
		entry_vector_table = (struct abi_entry_vectors *)words[1];
		sbi_printf("Registered OP-TEE entry table: %#lx\n",
			   (ulong)entry_vector_table);
	    }
	} else {
	    /* Skip a0 and transfer the a1 through a4 response. */
	    sbi_memcpy(hart_shmem_base(ms), &words[1], msg_len - sizeof(ulong));
	    *resp_len = msg_len - sizeof(ulong);
	}
	return sbi_ecall_tee_domain_exit();
    }

    sbi_printf("%s: message id %d not supported by channel%d\n",
	       __func__, msg_id, channel->channel_id);
    return SBI_EINVAL;
}

#ifdef CONFIG_K3_KEYSTONE_SM
/* K3 OP-TEE's CFG_DTB_MAX_SIZE. The address comes from the linked Core. */
#define K3_OPTEE_BOOT_DTB_SIZE 0x11000UL

static int k3_optee_copy_boot_dtb(const void *fdt, int nodeoff,
				 struct sbi_scratch *scratch, bool required)
{
    const fdt64_t *buffer;
    unsigned long source = (unsigned long)fdt;
    unsigned long dest;
    unsigned int size;
    int len;

    buffer = fdt_getprop(fdt, nodeoff, "spacemit,optee-boot-dtb", &len);
    if (!buffer) {
	return required || len != -FDT_ERR_NOTFOUND ? SBI_EINVAL : 0;
    }
    if (len != 2 * sizeof(*buffer) ||
	fdt64_ld(buffer + 1) != K3_OPTEE_BOOT_DTB_SIZE ||
	sbi_domain_thishart_ptr() != tdomain ||
	current_hartid() != tdomain->boot_hartid ||
	tdomain->next_arg1 != source || scratch->next_arg1 != source ||
	tdomain->next_addr != K3_MB_PRIVATE_BASE) {
	return SBI_EINVAL;
    }
    dest = fdt64_ld(buffer);
    if ((dest & (PAGE_SIZE - 1)) || dest < K3_MB_PRIVATE_BASE + PAGE_SIZE ||
	dest > K3_MB_LOG_BASE - K3_OPTEE_BOOT_DTB_SIZE ||
	!sbi_domain_check_addr_range(tdomain, dest, K3_OPTEE_BOOT_DTB_SIZE,
				     PRV_S, SBI_DOMAIN_READ | SBI_DOMAIN_WRITE) ||
	fdt_check_header(fdt)) {
	return SBI_EDENIED;
    }
    size = fdt_totalsize(fdt);
    if (size > K3_OPTEE_BOOT_DTB_SIZE ||
	!sbi_domain_check_addr_range(udomain, source, size,
				     PRV_S, SBI_DOMAIN_READ) ||
	(source < dest + K3_OPTEE_BOOT_DTB_SIZE && dest < source + size) ||
	fdt_check_full(fdt, size)) {
	return SBI_EINVAL;
    }

    sbi_memset((void *)dest, 0, K3_OPTEE_BOOT_DTB_SIZE);
    sbi_memcpy((void *)dest, fdt, size);
    tdomain->next_arg1 = dest;
    scratch->next_arg1 = dest;
    sbi_printf("K3 OP-TEE boot DTB: %u bytes from 0x%lx to 0x%lx\n",
	       size, source, dest);
    return 0;
}

static int k3_measured_boot_log(const void *fdt, bool *present)
{
    const fdt64_t *address;
    const fdt32_t *length;
    int node;
    int len;
    u32 size;

    *present = false;
    node = fdt_node_offset_by_compatible(fdt, -1, "arm,tpm_event_log");
    if (node == -FDT_ERR_NOTFOUND) {
	return 0;
    }
    if (node < 0 || node != fdt_path_offset(fdt, "/tpm-event-log") ||
	fdt_node_offset_by_compatible(fdt, node, "arm,tpm_event_log") !=
	-FDT_ERR_NOTFOUND) {
	return SBI_EINVAL;
    }
    address = fdt_getprop(fdt, node, "tpm_event_log_sm_addr", &len);
    if (!address || len != sizeof(*address) ||
	fdt64_ld(address) != K3_MB_LOG_BASE) {
	return SBI_EINVAL;
    }
    length = fdt_getprop(fdt, node, "tpm_event_log_size", &len);
    if (!length || len != sizeof(*length)) {
	return SBI_EINVAL;
    }
    size = fdt32_ld(length);
    if (!size || size > K3_MB_LOG_CAPACITY) {
	return SBI_EINVAL;
    }
    *present = true;
    sbi_printf("K3 measured boot: DT event log bytes=%u\n", size);
    return 0;
}
#endif

static int mpxy_opteed_init(const void *fdt, int nodeoff,
			    const struct fdt_match *match)
{
	struct sbi_mpxy_channel *channel;
	const fdt32_t *val;
	u32 channel_id;
	int rc, len, i;
#ifdef CONFIG_K3_KEYSTONE_SM
    bool measured_boot;
    enum sbi_k3_optee_pmp_profile profile;
    const char *model;
#endif

	/* Setup domain for OP-TEE dispatcher */
	rc = opteed_domain_setup(fdt, nodeoff, match);
	if (rc)
		return rc;

	tdomain = __get_tdomain();
	udomain = __get_udomain();

#ifdef CONFIG_K3_KEYSTONE_SM
    rc = k3_measured_boot_log(fdt, &measured_boot);
    if (rc) {
	sbi_printf("K3 measured boot: DT event log rejected (%d)\n", rc);
	return rc;
    }
    profile = !fdt_node_check_compatible(fdt, 0, "riscv-virtio") ?
	SBI_K3_OPTEE_PMP_QEMU : SBI_K3_OPTEE_PMP_LEGACY;
    if (fdt_getprop(fdt, nodeoff, "spacemit,pico-itx-pmp16", &len)) {
	if (len || fdt_node_check_compatible(fdt, 0, "spacemit,k3")) {
	    return SBI_EINVAL;
	}
	model = fdt_getprop(fdt, 0, "model", &len);
	if (!model || !fdt_stringlist_contains(model, len,
					       "spacemit k3 pico itx board")) {
	    return SBI_EINVAL;
	}
	profile = SBI_K3_OPTEE_PMP_PICO_ITX;
    }
    rc = sbi_hart_keystone_check_optee_pmp(sbi_scratch_thishart_ptr(),
					  udomain, tdomain, measured_boot,
					  profile);
    if (rc) {
	sbi_printf("K3 OP-TEE PMP: fixed slot plan rejected (%d)\n", rc);
	return rc;
    }
    rc = k3_optee_copy_boot_dtb(fdt, nodeoff, sbi_scratch_thishart_ptr(),
				profile == SBI_K3_OPTEE_PMP_PICO_ITX);
    if (rc) {
	sbi_printf("K3 OP-TEE boot DTB rejected (%d)\n", rc);
	return rc;
    }
#endif

	val = fdt_getprop(fdt, nodeoff, "riscv,sbi-mpxy-channel-id", &len);
	len = len / sizeof(u32);
	if (val && len) {
		for (i = 0; i < len; i++) {
			/* Allocate context for MPXY channel */
			channel = NULL;
			channel = sbi_zalloc(sizeof(*channel));
			if (!channel)
				return SBI_ENOMEM;
			channel_id = fdt32_to_cpu(val[i]);
			channel->channel_id = channel_id;
			channel->send_message_with_response =
				mpxy_opteed_send_message_withresp;
			channel->attrs.msg_proto_id = SBI_MPXY_MSGPROTO_TEE_ID;
			channel->attrs.msg_data_maxlen = PAGE_SIZE;

			rc = sbi_mpxy_register_channel(channel);
			if (rc) {
				sbi_free(channel);
				return rc;
			}
		}
	} else {
		sbi_panic("Failed to get riscv,sbi-mpxy-channel-id");
	}

	return SBI_SUCCESS;
}

static const struct fdt_match mpxy_opteed_match[] = {
	{ .compatible = "riscv,sbi-mpxy-opteed", .data = NULL },
	{},
};

const struct fdt_driver fdt_mpxy_opteed = {
	.match_table = mpxy_opteed_match,
	.init = mpxy_opteed_init,
	.experimental = true,
};
