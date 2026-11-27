/* SPDX-License-Identifier: BSD-2-Clause
 * K3 compatibility boundary for Keystone PMP shootdowns.
 * No remote PMP operation may be reported as complete without per-hart ACK.
 * This stage intentionally refuses all global updates; the authenticated
 * event mailbox and offline-hart generation replay are not yet connected.
 */
#include <sbi/sbi_error.h>
#include <sbi/sbi_console.h>
#include "ipi.h"
#include "k3_pmp_sync_state.h"

#include <sbi/sbi_scratch.h>
#include <sbi/riscv_asm.h>
#include <sbi/riscv_barrier.h>
#include <sbi/sbi_hsm.h>
#include <sbi/sbi_timer.h>
#include <sbi/sbi_ecall_interface.h>
#include <sbi/sbi_error.h>
#include "k3_pmp_ipi_transport.h"
#include "pmp.h"
#include "k3_hsm_stop_gate.h"
#include "k3_hsm_start_policy.h"

/* Functions are in vendor OpenSBI and share the same HSM/PMP gate
 * during admission/finish/cancel. No second unlocked admission window. */
extern int sbi_hsm_k3_e2_start_reserve(unsigned int hartindex);
extern int sbi_hsm_k3_e2_classify_target(unsigned int hartindex, int hsm_state);
extern int sbi_hsm_k3_e2_start_cancel(unsigned int hartindex);
extern int sbi_hsm_k3_e2_finish_and_mark_started(unsigned int hartindex);
static struct k3_hsm_stop_gate k3_global_hsm_gate;
static unsigned int k3_sync_poisoned;
static uint64_t k3_sync_generation;
static struct k3_hsm_start_policy k3_start_policy;

/* Protected by k3_start_policy.gate. Multiple OP-TEE harts may run. */
static unsigned int k3_optee_harts;
static bool k3_pmp_update_reserved;
static bool k3_enclave_update_reserved;

int k3_keystone_enclave_update_begin(void)
{
    int rc = SBI_EINVALID_STATE;

    while (k3_policy_lock(&k3_start_policy)) {
	cpu_relax();
    }
    if (!k3_optee_harts && !k3_enclave_update_reserved &&
	!k3_pmp_update_reserved) {
	k3_enclave_update_reserved = true;
	rc = 0;
    }
    k3_policy_unlock(&k3_start_policy);
    return rc;
}

void k3_keystone_enclave_update_end(void)
{
    while (k3_policy_lock(&k3_start_policy)) {
	cpu_relax();
    }
    k3_enclave_update_reserved = false;
    k3_policy_unlock(&k3_start_policy);
}

bool k3_keystone_optee_active(unsigned int hartindex)
{
    bool active;

    if (hartindex >= 16U) {
	return false;
    }
    while (k3_policy_lock(&k3_start_policy)) {
	cpu_relax();
    }
    active = k3_optee_harts & (1U << hartindex);
    k3_policy_unlock(&k3_start_policy);
    return active;
}

int k3_keystone_optee_enter(unsigned int hartindex)
{
    unsigned int bit;
    int rc = SBI_EFAIL;

    if (hartindex >= 16U) {
	return SBI_EINVAL;
    }
    bit = 1U << hartindex;
    while (k3_policy_lock(&k3_start_policy)) {
	cpu_relax();
    }
    if (!__atomic_load_n(&k3_sync_poisoned, __ATOMIC_ACQUIRE) &&
	!(k3_optee_harts & bit)) {
	if (k3_pmp_update_reserved || k3_enclave_update_reserved) {
	    rc = SBI_EINVALID_STATE;
	} else {
	    k3_optee_harts |= bit;
	    rc = 0;
	}
    }
    k3_policy_unlock(&k3_start_policy);
    return rc;
}

void k3_keystone_optee_leave(unsigned int hartindex)
{
    while (k3_policy_lock(&k3_start_policy)) {
	cpu_relax();
    }
    k3_optee_harts &= ~(1U << hartindex);
    k3_policy_unlock(&k3_start_policy);
}

/* Explicit initialization during verified cold boot ONLY; not in the
 * production SM startup path until PMP ownership and HSM replay are proven. */
int k3_pmp_sync_initialize(void)
{
  int rc = k3_pmp_ipi_transport_register();
  if (rc) return rc;
  rc = k3_pmp_ipi_transport_bind_apply(k3_pmp_apply_verified);
  if (rc) k3_pmp_ipi_transport_unregister();
  return rc;
}

int send_and_sync_pmp_ipi(int region_idx, int type, uint8_t perm)
{
  struct k3_pmp_ipi_request request;
  unsigned long mask = 0;
  u32 i;

  int rc = SBI_ENOTSUPP;
  if (__atomic_load_n(&k3_sync_poisoned, __ATOMIC_ACQUIRE)) return SBI_EFAIL;
  if (k3_hsm_gate_acquire(&k3_global_hsm_gate))
    return SBI_EINVALID_STATE;
  /* Only STOPPED may be excluded; unexpected HSM states fail closed.
   * Any excluded Hart missing a PMP generation cannot start until replay. */
  if (sbi_scratch_last_hartindex() >= sizeof(unsigned long) * 8) goto done;
  for (i = 0; i <= sbi_scratch_last_hartindex(); i++) {
    u32 hartid = sbi_hartindex_to_hartid(i);
    unsigned int state = __sbi_hsm_hart_get_state(i);
    if (!sbi_hartindex_to_scratch(i) || hartid >= sizeof(unsigned long)*8 ||
        i >= 16U /* K3 supports at most 16 hart indices */) goto done;
    /* E2: verified STOPPED quarantine is NOT an ACK, but may be
     * excluded while future starts are blocked by the same gate. */
    if (state == SBI_HSM_STATE_STOPPED) {
      if (sbi_hsm_k3_e2_classify_target(i,0)!=0) goto done;
      continue;
    }
    if (state != SBI_HSM_STATE_STARTED ||
        sbi_hsm_k3_e2_classify_target(i,1)!=1) goto done;
    if (hartid != csr_read(CSR_MHARTID)) mask |= 1UL << hartid;
  }
  if (++k3_sync_generation == 0) goto done;
  request.generation = k3_sync_generation;
  request.region = region_idx;
  request.operation = type;
  request.permissions = perm;
  rc = mask ? k3_pmp_ipi_transport_send(mask, 0, &request) : 0;
  if (!rc) rc = k3_pmp_apply_verified(region_idx, type, perm);
  /* Do not publish offline generations: HSM Start requires authoritatively
   * verified inactive protection. Such a publisher is not wired yet. */
done:
  if (rc) __atomic_store_n(&k3_sync_poisoned, 1, __ATOMIC_RELEASE);
  k3_hsm_gate_release(&k3_global_hsm_gate);
  return rc;
}

/* Verified boot-only admission for the standard initial HSM Start path.
 * At this point the cold Hart's root PMP and SM local initialization are
 * complete, but CREATE is unavailable until all 16 local Hart bits arrive.
 * Never transition back to INACTIVE after any dynamic PMP generation. */
int k3_keystone_allow_initial_hsm_starts(void)
{
  int rc = SBI_EINVALID_STATE;
  if (!k3_pmp_partition_is_prepared() ||
      __atomic_load_n(&k3_sync_poisoned, __ATOMIC_ACQUIRE) ||
      __atomic_load_n(&k3_sync_generation, __ATOMIC_ACQUIRE))
    return rc;
  if (k3_hsm_gate_acquire(&k3_global_hsm_gate)) return rc;
  if (!k3_policy_lock(&k3_start_policy)) {
    if (!k3_start_policy.inflight &&
        k3_start_policy.protection == K3_PMP_ACTIVE &&
        k3_pmp_ipi_transport_is_ready()) {
      rc = k3_policy_set_protection_locked(&k3_start_policy,
                                            K3_PMP_INACTIVE) ?
                                           SBI_EINVALID_STATE : 0;
    }
    k3_policy_unlock(&k3_start_policy);
  }
  k3_hsm_gate_release(&k3_global_hsm_gate);
  return rc;
}

int k3_pmp_sync_healthy(void)
{
  return !__atomic_load_n(&k3_sync_poisoned, __ATOMIC_ACQUIRE) &&
         k3_pmp_ipi_transport_is_ready();
}

/* Called immediately before STARTED -> STOP_PENDING. Busy means a PMP
 * update is in flight: HSM must reject STOP, not race with target capture.
 * Stage 177 does not authorize a stopped hart to resume without replay. */
int k3_keystone_hsm_stop_begin(void)
{
  if (__atomic_load_n(&k3_sync_poisoned, __ATOMIC_ACQUIRE)) return SBI_EFAIL;
  return k3_hsm_gate_acquire(&k3_global_hsm_gate) ? SBI_EINVALID_STATE : 0;
}

void k3_keystone_hsm_stop_end(void)
{
  k3_hsm_gate_release(&k3_global_hsm_gate);
}

#define K3_HSM_GATE_TIMEOUT_MS 100

static bool k3_hsm_try_gate(void *gate)
{
    return !k3_hsm_gate_acquire(gate);
}

static int k3_hsm_acquire_gate(bool retry)
{
    if (k3_hsm_try_gate(&k3_global_hsm_gate)) {
	return 0;
    }
    if (!retry || !sbi_timer_get_device()) {
	return SBI_EINVALID_STATE;
    }
    if (!sbi_timer_waitms_until(k3_hsm_try_gate, &k3_global_hsm_gate,
			       K3_HSM_GATE_TIMEOUT_MS)) {
	return SBI_ETIMEDOUT;
    }
    return 0;
}

/* Called by vendor HSM before STOPPED -> START_PENDING, under the same gate
 * as STOP and all PMP broadcast. Stage 178 denies a missed-generation start.
 * The next stage must implement replay before permitting admission. */
int k3_keystone_hsm_start_begin(unsigned int hartindex, bool boot_start)
{
    int rc;

    if (hartindex >= 16U) {
	return SBI_EINVAL;
    }
    if (__atomic_load_n(&k3_sync_poisoned, __ATOMIC_ACQUIRE)) {
	return SBI_EFAIL;
    }
    /* At boot, another hart may be completing its initial HSM Start. */
    if (k3_hsm_acquire_gate(boot_start)) {
	return SBI_EINVALID_STATE;
    }
    if (__atomic_load_n(&k3_sync_poisoned, __ATOMIC_ACQUIRE)) {
	k3_hsm_gate_release(&k3_global_hsm_gate);
	return SBI_EFAIL;
    }
    if (k3_policy_lock(&k3_start_policy)) {
	k3_hsm_gate_release(&k3_global_hsm_gate);
	return SBI_EINVALID_STATE;
    }
    rc = k3_policy_begin_hart_locked(&k3_start_policy, hartindex);
    if (!rc && sbi_hsm_k3_e2_start_reserve(hartindex)) {
	/* Both reservations are changed inside one global exclusion gate. */
	(void)k3_policy_finish_hart_locked(&k3_start_policy, hartindex);
	rc = SBI_EINVALID_STATE;
    }
    k3_policy_unlock(&k3_start_policy);
    k3_hsm_gate_release(&k3_global_hsm_gate);
    return rc ? SBI_EINVALID_STATE : 0;
}
/* Boot handoff can quarantine a hart only before dynamic PMP updates. */
int k3_keystone_hsm_boot_stop_begin(void)
{
    if (k3_hsm_gate_acquire(&k3_global_hsm_gate)) {
	return SBI_EALREADY;
    }
    if (k3_start_policy.protection != K3_PMP_INACTIVE ||
	k3_sync_generation ||
	__atomic_load_n(&k3_sync_poisoned, __ATOMIC_ACQUIRE)) {
	k3_hsm_gate_release(&k3_global_hsm_gate);
	return SBI_EDENIED;
    }
    return 0;
}

/* Hart-specific finish/cancel: only a matching outstanding reservation is released. */
static int k3_keystone_hsm_release_reservation(unsigned int hartindex,
                                               int completed)
{
  int rc;
  if (hartindex >= 16U) return SBI_EINVAL;
  /* Retry only before touching the ledger or publishing STARTED. */
  rc = k3_hsm_acquire_gate(completed);
  if (rc) {
    return rc;
  }
  if (k3_policy_lock(&k3_start_policy)) {
    __atomic_store_n(&k3_sync_poisoned, 1, __ATOMIC_RELEASE);
    k3_hsm_gate_release(&k3_global_hsm_gate);
    return SBI_EFAIL;
  }
  /* Publish STARTED while holding the gate, so an IPI capture cannot
   * mistake a newly-started Hart for STOPPED or START_PENDING. */
  rc = completed ? sbi_hsm_k3_e2_finish_and_mark_started(hartindex)
                 : sbi_hsm_k3_e2_start_cancel(hartindex);
  if (!rc) rc = k3_policy_finish_hart_locked(&k3_start_policy, hartindex);
  if (rc) __atomic_store_n(&k3_sync_poisoned, 1, __ATOMIC_RELEASE);
  k3_policy_unlock(&k3_start_policy);
  k3_hsm_gate_release(&k3_global_hsm_gate);
  return rc ? SBI_EINVALID_STATE : 0;
}
int k3_keystone_hsm_start_finish(unsigned int hartindex)
{
  return k3_keystone_hsm_release_reservation(hartindex,1);
}
int k3_keystone_hsm_start_cancel(unsigned int hartindex)
{
  return k3_keystone_hsm_release_reservation(hartindex,0);
}
/* ADR-001: PMP-protection lifecycle entry point. All production PMP
 * writers must eventually pass through this common admission gate.
 * UNKNOWN and any PMP update are conservatively treated as protection ACTIVE.
 * No INACTIVE publisher is supplied until a full teardown can be proven. */
int k3_keystone_pmp_transition_begin(void)
{
  int rc;
  if (k3_hsm_gate_acquire(&k3_global_hsm_gate)) return SBI_EINVALID_STATE;
  if (k3_policy_lock(&k3_start_policy)) {
    k3_hsm_gate_release(&k3_global_hsm_gate);
    return SBI_EINVALID_STATE;
  }
  rc = SBI_EINVALID_STATE;
  if (!k3_optee_harts && !k3_pmp_update_reserved) {
    rc = k3_policy_set_protection_locked(&k3_start_policy, K3_PMP_TRANSITION);
    if (!rc) {
	k3_pmp_update_reserved = true;
    }
  }
  k3_policy_unlock(&k3_start_policy);
  k3_hsm_gate_release(&k3_global_hsm_gate);
  return rc ? SBI_EINVALID_STATE : 0;
}

void k3_keystone_pmp_transition_finish(void)
{
  while (k3_policy_lock(&k3_start_policy)) {
    cpu_relax();
  }
  /* Even a successful UNSET does not establish globally inactive PMP.
   * Failure also leaves protection conservatively ACTIVE. */
  if (k3_policy_set_protection_locked(&k3_start_policy, K3_PMP_ACTIVE))
    __atomic_store_n(&k3_sync_poisoned, 1, __ATOMIC_RELEASE);
  k3_pmp_update_reserved = false;
  k3_policy_unlock(&k3_start_policy);
}

/* ADR-001: Assert conservatively that SM protection may be active.
 * Used by SM bootstrap and local enclave PMP switching, NOT as an
 * authorization to enable the incomplete K3 SM integration.
 * The start-admission gate is shared with HSM Start and PMP broadcasts.
 * Never publish INACTIVE from a local PMP operation. */
int k3_keystone_pmp_assert_active(void)
{
  bool already_active;
  int rc;

  /* The broadcast owner holds the HSM gate while waiting for this hart.
   * ACTIVE and TRANSITION already exclude HSM Start; checking those
   * states must neither contend for that gate nor overwrite TRANSITION.
   */
  while (k3_policy_lock(&k3_start_policy)) {
    cpu_relax();
  }
  already_active = !k3_start_policy.inflight &&
      (k3_start_policy.protection == K3_PMP_ACTIVE ||
       k3_start_policy.protection == K3_PMP_TRANSITION);
  k3_policy_unlock(&k3_start_policy);
  if (already_active) {
    return 0;
  }

  if (k3_hsm_gate_acquire(&k3_global_hsm_gate)) return SBI_EINVALID_STATE;
  if (k3_policy_lock(&k3_start_policy)) {
    k3_hsm_gate_release(&k3_global_hsm_gate);
    return SBI_EINVALID_STATE;
  }
  rc = k3_policy_set_protection_locked(&k3_start_policy, K3_PMP_ACTIVE);
  k3_policy_unlock(&k3_start_policy);
  k3_hsm_gate_release(&k3_global_hsm_gate);
  if (rc) __atomic_store_n(&k3_sync_poisoned, 1, __ATOMIC_RELEASE);
  return rc ? SBI_EINVALID_STATE : 0;
}
