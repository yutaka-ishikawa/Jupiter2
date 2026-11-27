/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef K3_PICO_ITX_MMIO_H
#define K3_PICO_ITX_MMIO_H

#include <sbi/sbi_types.h>

/* SBI_ENOENT delegates an existing host PMU AP register to the caller. */
int k3_pico_itx_mmio(unsigned long pa, bool store, u32 *value);

#endif
