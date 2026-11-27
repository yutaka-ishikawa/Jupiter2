/* SPDX-License-Identifier: BSD-2-Clause */
/* K3 deterministic 16-PMP boot slot layout.
 * Every effective root mapping (denies and grants) precedes Keystone slots;
 * the caller preserves domain metadata and proves any shared hardware entry;
 * the root-domain universal S/U allow is always index 15.
 * This is a slot plan, not a substitute for hardware CSR readback.
 */
#ifndef __K3_KEYSTONE_BOOT_SLOTS_H__
#define __K3_KEYSTONE_BOOT_SLOTS_H__
#include <stdbool.h>
#include <stdint.h>
#include <sbi/k3_pmp_contract.h>
#define K3_BOOT_PMP_COUNT K3_PMP_COMMON_REGS
#define K3_BOOT_FALLBACK 15U
#define K3_BOOT_MIN_KEYSTONE 3U
#define K3_BOOT_SHARED_SM_MASK 0x6000U
#define K3_BOOT_SHARED_MIN_KEYSTONE 2U

struct k3_boot_pmp_plan {
    uint16_t opensbi_mask;
    uint16_t keystone_mask;
    uint8_t firmware_entries;
    uint8_t fallback_index;
};

static inline int k3_boot_plan_slots(unsigned int pmp_count,
				     unsigned int firmware_entries,
				     unsigned int broad_allow_entries,
				     bool share_fallback,
				     struct k3_boot_pmp_plan *out)
{
    unsigned int i;
    unsigned int min_keystone = share_fallback ? K3_BOOT_SHARED_MIN_KEYSTONE :
						K3_BOOT_MIN_KEYSTONE;
    uint16_t reserved = (uint16_t)(1U << K3_BOOT_FALLBACK);
    if (!out || !k3_pmp_count_supported(pmp_count) || !firmware_entries ||
	broad_allow_entries != 1U ||
	firmware_entries + min_keystone > K3_BOOT_FALLBACK) {
	return -1;
    }
    for (i = 0; i < firmware_entries; i++) {
	reserved |= (uint16_t)(1U << i);
    }
    out->firmware_entries = (uint8_t)firmware_entries;
    out->fallback_index = K3_BOOT_FALLBACK;
    out->opensbi_mask = reserved;
    out->keystone_mask = (uint16_t)(0xffffU & ~reserved);
    return 0;
}
#endif
