/* SPDX-License-Identifier: BSD-2-Clause */

#include <sbi/riscv_io.h>
#include <sbi/riscv_locks.h>
#include <sbi/sbi_bitops.h>
#include <sbi/sbi_domain.h>
#include <sbi/sbi_error.h>
#include <sbi/sbi_hart.h>
#include "k3_pico_itx_mmio.h"

#define K3_MPMU 0xd4050000UL
#define K3_APMU_AES 0xd4282868UL
#define K3_APBC2 0xf0610000UL
#define K3_DCIU 0xd8440000UL
#define K3_GEU 0xf0702800UL

struct k3_clock_rule {
    unsigned long addr;
    u32 host_mask;
    u32 tee_mask;
    u32 tee_value;
};

#define HOST_CLOCK(addr, mask) { (addr), (mask), 0, 0 }
#define SHARED_CLOCK(addr, host, tee, val) \
    { (addr), (host), (tee), (val) }
#define DMA_CONTROL(offset) \
    SHARED_CLOCK(K3_DCIU + (offset), 0, BIT(0), BIT(0))

/* Linux and U-Boot CCU fields. OP-TEE supplies the shared clock settings
 * during initialization. Host writes merge only the host-owned fields.
 */
#define MPMU_HOST_GATES \
    (BIT(0) | BIT(1) | BIT(2) | BIT(3) | BIT(4) | BIT(6) | BIT(7) | \
     BIT(8) | BIT(10) | BIT(11) | BIT(12) | BIT(13) | BIT(14) | BIT(15) | \
     BIT(16) | BIT(18) | BIT(19) | BIT(21))
#define MPMU_UART_DIV (GENMASK(28, 16) | GENMASK(12, 0))
#define MPMU_I2S_SELECT \
    (GENMASK(2, 0) | GENMASK(6, 4) | BIT(8) | GENMASK(14, 12) | \
     GENMASK(18, 16) | GENMASK(22, 20))

static const struct k3_clock_rule clock_rules[] = {
    HOST_CLOCK(K3_MPMU + 0x008, BIT(29)),	/* FCCR */
    HOST_CLOCK(K3_MPMU + 0x010, 0),		/* PLL status */
    HOST_CLOCK(K3_MPMU + 0x014, MPMU_UART_DIV),
    HOST_CLOCK(K3_MPMU + 0x040, GENMASK(26, 0) | GENMASK(31, 30)),
    HOST_CLOCK(K3_MPMU + 0x044, ~0U),		/* I2S clock fields */
    HOST_CLOCK(K3_MPMU + 0x200, GENMASK(2, 0)),	/* Watchdog clock/reset */
    HOST_CLOCK(K3_MPMU + 0x210, BIT(0) | BIT(2)),	/* RCPU IPC clock/reset */
    SHARED_CLOCK(K3_MPMU + 0x1024, MPMU_HOST_GATES, BIT(5), BIT(5)),
    HOST_CLOCK(K3_MPMU + 0x1050, GENMASK(1, 0)),	/* APB mux */
    HOST_CLOCK(K3_MPMU + 0x10b0, MPMU_UART_DIV),
    HOST_CLOCK(K3_MPMU + 0x1100, ~0U),		/* I2S dividers */
    HOST_CLOCK(K3_MPMU + 0x1104, ~0U),
    HOST_CLOCK(K3_MPMU + 0x1108, ~0U),
    HOST_CLOCK(K3_MPMU + 0x110c, ~0U),
    HOST_CLOCK(K3_MPMU + 0x1110, ~0U),
    HOST_CLOCK(K3_MPMU + 0x1114, MPMU_I2S_SELECT),

    /* The vendor AES initialization programs one exact clock/reset value. */
    SHARED_CLOCK(K3_APMU_AES, 0, ~0U, 0x1cff003f),

    HOST_CLOCK(K3_APBC2 + 0x00, 0),		/* Secure UART clock status */
    HOST_CLOCK(K3_APBC2 + 0x04, 0),		/* Secure SPI clock status */
    HOST_CLOCK(K3_APBC2 + 0x08, GENMASK(6, 4) | GENMASK(2, 0)),
    SHARED_CLOCK(K3_APBC2 + 0x0c, 0, BIT(7) | GENMASK(2, 0), 0x83),
    HOST_CLOCK(K3_APBC2 + 0x10, 0),		/* Secure timer clock status */
    HOST_CLOCK(K3_APBC2 + 0x1c, 0),		/* Secure GPIO clock status */

    /* Keep the interfaces initialized by OP-TEE available for IOPMP. */
    DMA_CONTROL(0x204), DMA_CONTROL(0x208), DMA_CONTROL(0x20c),
    DMA_CONTROL(0x210), DMA_CONTROL(0x214), DMA_CONTROL(0x218),
    DMA_CONTROL(0x21c), DMA_CONTROL(0x220), DMA_CONTROL(0x224),
    DMA_CONTROL(0x228), DMA_CONTROL(0x22c), DMA_CONTROL(0x230),
    DMA_CONTROL(0x234), DMA_CONTROL(0x238),
    HOST_CLOCK(K3_DCIU + 0x244, BIT(0)),		/* TCM pipe clocks */
    HOST_CLOCK(K3_DCIU + 0x248, BIT(0)),
};

static spinlock_t clock_lock = SPIN_LOCK_INITIALIZER;

static int clock_access(const struct k3_clock_rule *rule, bool tee,
			bool store, u32 *value)
{
    u32 mask = tee ? rule->tee_mask : rule->host_mask;
    volatile void *reg = (volatile void *)rule->addr;
    u32 next, prev;

    if (tee && !mask) {
	return SBI_EDENIED;
    }
    if (store && tee && (*value & mask) != rule->tee_value) {
	return SBI_EDENIED;
    }
    if (store && !mask) {
	/* Clock framework disable and reset requests preserve shared state. */
	return rule->tee_mask ? SBI_OK : SBI_EDENIED;
    }

    spin_lock(&clock_lock);
    mb();
    prev = readl(reg);
    if (store) {
	next = (prev & ~mask) | (*value & mask);
	if (next != prev) {
	    writel(next, reg);
	}
    } else {
	*value = prev;
    }
    mb();
    spin_unlock(&clock_lock);
    return SBI_OK;
}

/* Allow only the public SoC cells and thermal trim from the board DT. */
static const u32 public_bank7[] = {
    0, 0, 0x0ff00000, 0, 0x07fff800, 0xffffe000, 0xffffffff, 0xcfffffff,
};

static int public_efuse(unsigned long pa, bool store, u32 *value)
{
    unsigned long offset = pa - K3_GEU;
    u32 mask = 0;

    if (store) {
	/* The bootloader reloads its public view. OP-TEE already latched
	 * the controller, so leave the physical GEU configuration alone.
	 */
	if (offset == 0x004 &&
	    (*value == 0x0c424000 || *value == 0x0c024000)) {
	    return SBI_OK;
	}
	return SBI_EDENIED;
    }

    if (offset == 0x184) {
	mask = BIT(1);				/* FUSE_READY */
    } else if (offset == 0x120) {
	mask = GENMASK(7, 0);			/* Bank 0 thermal trim */
    } else if (offset >= 0x190 && offset < 0x1b0) {
	mask = public_bank7[(offset - 0x190) / sizeof(u32)];
    } else if (!((offset >= 0x104 && offset < 0x184) ||
		 (offset >= 0x200 && offset < 0x2e0))) {
	return SBI_EDENIED;
    }

    /* U-Boot eagerly reads whole banks. Return zero for fields outside
     * its public view without reading those words from the controller.
     */
    if (mask) {
	mb();
	*value = readl((volatile void *)pa) & mask;
	mb();
    } else {
	*value = 0;
    }
    return SBI_OK;
}

int k3_pico_itx_mmio(unsigned long pa, bool store, u32 *value)
{
    const struct sbi_domain *dom = sbi_domain_thishart_ptr();
    bool tee = dom == sbi_hart_keystone_optee_domain();
    unsigned int i;

    if (pa % sizeof(u32) || (!tee && dom != sbi_hart_keystone_optee_host())) {
	return SBI_EDENIED;
    }
    for (i = 0; i < array_size(clock_rules); i++) {
	if (clock_rules[i].addr == pa) {
	    return clock_access(&clock_rules[i], tee, store, value);
	}
    }
    if (!tee && pa >= K3_GEU && pa < K3_GEU + 0x400) {
	return public_efuse(pa, store, value);
    }

    return tee ? SBI_EDENIED : SBI_ENOENT;
}
