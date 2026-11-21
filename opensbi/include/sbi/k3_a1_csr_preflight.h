/* SPDX-License-Identifier: BSD-2-Clause */
/* K3 A1-E: read-only local PMP shape preflight, NOT an ownership proof.
 * This is deliberately conservative. Hardware capabilities, CSR snapshots,
 * cross-Hart agreement, address-specific priorities and M-mode holds still
 * require independent verification before any PMP write or S-mode entry.
 */
#ifndef __K3_A1_CSR_PREFLIGHT_H__
#define __K3_A1_CSR_PREFLIGHT_H__
#include <stdint.h>
#include <sbi/k3_pmp_contract.h>
#define K3_A1_CSR_MAX K3_PMP_COMMON_REGS
#define K3_A1_CSR_A 0x18U
#define K3_A1_CSR_NAPOT 0x18U
#define K3_A1_CSR_RWX 0x07U
#define K3_A1_CSR_LOCK 0x80U
/* Bit meanings from RISC-V Smepmp mseccfg, not an extension-presence test. */
#define K3_A1_CSR_MSECCFG_POLICY 0x07U

enum k3_a1_preflight_result {
    K3_A1_PF_OK = 0,
    K3_A1_PF_BAD_INPUT = -1,
    K3_A1_PF_ACTIVE_SMEPMP = -2,
    K3_A1_PF_NO_GLOBAL_ALLOW = -3,
    K3_A1_PF_SHADOWED = -4,
    K3_A1_PF_LOCKED = -5,
    K3_A1_PF_NO_SLOTS = -6,
    K3_A1_PF_AMBIGUOUS = -7
};

struct k3_a1_csr_measured_entry {
    uint64_t prot, addr;
    unsigned int log2len;
};

struct k3_a1_csr_measured {
    unsigned int count, granularity;
    unsigned int pmp_addrbits; /* implemented PMPADDR bits, not RV64 XLEN */
    unsigned int mseccfg_valid;
    uint64_t mseccfg;
    struct k3_a1_csr_measured_entry entry[K3_PMP_MAX_REGS];
};

struct k3_a1_local_candidate {
    unsigned int old_allow, fallback;
    uint16_t firmware_entries, free_keystone_entries;
};

/* This gate only establishes structural suitability of a *local* legacy-PMP
 * image. No caller may treat PF_OK as permission to transfer ownership.
 * If anything is ambiguous, reject and preserve the existing build gate.
 */
/* verified_root_locks is valid only after a full domain-derived CSR
 * readback on this Hart. A caller-supplied mask alone is not evidence.
 * The default wrapper below authorizes no locks at all.
 */
static inline int
k3_a1_preflight_local_with_root_locks(const struct k3_a1_csr_measured *m,
				      struct k3_a1_local_candidate *out,
				      uint16_t verified_root_locks)
{
    unsigned int i, old = K3_A1_CSR_MAX, fallback;
    uint16_t fw = 0, free_mask = 0, actual_locks = 0;

    if (!m || !out || !k3_pmp_count_supported(m->count) ||
	m->granularity > 64 || m->pmp_addrbits == 0 || m->pmp_addrbits > 62) {
	return K3_A1_PF_BAD_INPUT;
    }
#ifdef K3_QEMU_PMP16
    if (m->count != 16U) {
	return K3_A1_PF_BAD_INPUT;
    }
#endif
    if (m->mseccfg_valid && (m->mseccfg & K3_A1_CSR_MSECCFG_POLICY)) {
	return K3_A1_PF_ACTIVE_SMEPMP;
    }
    /* Extra entries are not allocator capacity. Reject active rules and
     * locks, including TOR locks on the preceding PMPADDR, without writes.
     */
    for (i = K3_PMP_COMMON_REGS; i < m->count; i++) {
	if ((m->entry[i].prot & ~0x07ULL) != 0) {
	    return K3_A1_PF_BAD_INPUT;
	}
    }
    for (i = 0; i < K3_PMP_COMMON_REGS; i++) {
	const struct k3_a1_csr_measured_entry *e = &m->entry[i];
	unsigned int mode = (unsigned int)e->prot & K3_A1_CSR_A;

	if (e->prot & ~(uint64_t)0xffU) {
	    return K3_A1_PF_BAD_INPUT;
	}
	if (mode != 0 && mode != 0x08U && mode != 0x10U && mode != 0x18U) {
	    return K3_A1_PF_BAD_INPUT;
	}
	if (e->prot & K3_A1_CSR_LOCK) {
	    if (!mode) {
		return K3_A1_PF_LOCKED;
	    }
	    actual_locks |= (uint16_t)(1U << i);
	}
	/* Accept full physical PMP coverage, not only RV64 order 64. */
	if (mode == K3_A1_CSR_NAPOT && e->addr == 0 &&
	    e->log2len >= m->pmp_addrbits + 2U &&
	    ((unsigned int)e->prot & K3_A1_CSR_RWX) == K3_A1_CSR_RWX) {
	    if (old != K3_A1_CSR_MAX) {
		return K3_A1_PF_AMBIGUOUS;
	    }
	    if (e->prot & K3_A1_CSR_LOCK) {
		return K3_A1_PF_LOCKED;
	    }
	    old = i;
	}
    }
    if (actual_locks != verified_root_locks) {
	return K3_A1_PF_LOCKED;
    }
    if (old == K3_A1_CSR_MAX) {
	return K3_A1_PF_NO_GLOBAL_ALLOW;
    }
    if (old == K3_PMP_COMMON_REGS - 1U) {
	unsigned int seen_free = 0;

	for (i = 0; i < old; i++) {
	    const struct k3_a1_csr_measured_entry *e = &m->entry[i];

	    if (e->prot & K3_A1_CSR_A) {
		if (seen_free) {
		    return K3_A1_PF_SHADOWED;
		}
		fw |= (uint16_t)(1U << i);
	    } else {
		seen_free = 1;
		free_mask |= (uint16_t)(1U << i);
	    }
	}
	if (!fw || __builtin_popcount((unsigned int)free_mask) < 3) {
	    return K3_A1_PF_NO_SLOTS;
	}
	out->old_allow = old;
	out->fallback = old;
	out->firmware_entries = fw;
	out->free_keystone_entries = free_mask;
	return K3_A1_PF_OK;
    }
    /* Root locks are authorized only in the canonical last-fallback
     * layout. Retain the stricter legacy alternative for other callers.
     */
    if (verified_root_locks) {
	return K3_A1_PF_LOCKED;
    }
    for (i = 0; i < old; i++) {
	const struct k3_a1_csr_measured_entry *e = &m->entry[i];

	if (!((unsigned int)e->prot & K3_A1_CSR_A) ||
	    (e->prot & K3_A1_CSR_RWX)) {
	    return K3_A1_PF_SHADOWED;
	}
	fw |= (uint16_t)(1U << i);
    }
    if (!fw) {
	return K3_A1_PF_SHADOWED;
    }
    for (i = old + 1; i < K3_PMP_COMMON_REGS; i++) {
	const struct k3_a1_csr_measured_entry *e = &m->entry[i];

	if ((e->prot & K3_A1_CSR_A) || (e->prot & K3_A1_CSR_LOCK)) {
	    return K3_A1_PF_NO_SLOTS;
	}
	free_mask |= (uint16_t)(1U << i);
    }
    fallback = K3_PMP_COMMON_REGS - 1;
    if (fallback <= old + 2 ||
	__builtin_popcount((unsigned int)free_mask) < 3) {
	return K3_A1_PF_NO_SLOTS;
    }
    out->old_allow = old;
    out->fallback = fallback;
    out->firmware_entries = fw;
    out->free_keystone_entries = free_mask;
    return K3_A1_PF_OK;
}

static inline int k3_a1_preflight_local(const struct k3_a1_csr_measured *m,
					struct k3_a1_local_candidate *out)
{
    return k3_a1_preflight_local_with_root_locks(m, out, 0);
}
#endif
