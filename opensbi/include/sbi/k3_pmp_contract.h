/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef __K3_PMP_CONTRACT_H__
#define __K3_PMP_CONTRACT_H__

/* Hardware inventory is per Hart. Allocation is common across all Harts. */
#define K3_PMP_COMMON_REGS 16U
#define K3_PMP_MAX_REGS 32U

static inline int k3_pmp_count_supported(unsigned int count)
{
#ifdef K3_QEMU_PMP16
    return count == K3_PMP_COMMON_REGS;
#else
    return count == K3_PMP_COMMON_REGS || count == K3_PMP_MAX_REGS;
#endif
}
#endif
