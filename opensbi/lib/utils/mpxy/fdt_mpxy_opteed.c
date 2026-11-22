/*
 * SPDX-License-Identifier: BSD-2-Clause
 *
 * Copyright (c) 2024 Intel Corporation. All rights reserved.
 */

#include <sbi/sbi_error.h>
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
#define TEEABI_OPTEED_RETURN_CALL_DONE 0xBE000000

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

static int sbi_ecall_tee_domain_enter(unsigned long entry_point)
{
    int rc;

    rc = sbi_domain_context_set_mepc(tdomain, entry_point);
    if (rc) {
	return rc;
    }
    return sbi_domain_context_enter(tdomain);
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

    /*
     * Reject traffic before touching either domain's state until the
     * Keystone-owned PMP transition is available.
     */
#ifdef CONFIG_K3_KEYSTONE_SM
    return SBI_ENOTSUPP;
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

	entry_point = (ulong)&entry_vector_table->yield_abi_entry;
	if (GET_ABI_ENTRY_TYPE(words[0]) == ABI_ENTRY_TYPE_FAST) {
	    entry_point = (ulong)&entry_vector_table->fast_abi_entry;
	}
	sbi_memcpy(hart_shmem_base(ms), msgbuf, msg_len);
	return sbi_ecall_tee_domain_enter(entry_point);
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
	if (!IS_SHMEM_ADDR_VALID(ms)) {
	    if (words[0] == TEEABI_OPTEED_RETURN_CALL_DONE) {
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

static int mpxy_opteed_init(const void *fdt, int nodeoff,
			    const struct fdt_match *match)
{
	struct sbi_mpxy_channel *channel;
	const fdt32_t *val;
	u32 channel_id;
	int rc, len, i;

	/* Setup domain for OP-TEE dispatcher */
	rc = opteed_domain_setup(fdt, nodeoff, match);
	if (rc)
		return rc;

	tdomain = __get_tdomain();
	udomain = __get_udomain();

#ifdef CONFIG_K3_KEYSTONE_SM
    rc = sbi_hart_keystone_check_optee_pmp(sbi_scratch_thishart_ptr(),
					  udomain, tdomain);
    if (rc) {
	sbi_printf("K3 OP-TEE PMP: fixed slot plan rejected (%d)\n", rc);
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
