/* SPDX-License-Identifier: BSD-2-Clause
 * Purpose: real S-mode guest for the real K3 QEMU + OpenSBI + SM boot path.
 * Starts secondary Harts via SBI HSM and counts actual S-mode arrivals.
 * No mocked SBI/CSR/PMP and no production function is copied here.
 * This is not Linux, an Enclave test, or an isolation proof.
 */
.option norelax
.section .text.init,"ax"
.balign 4
.global _start
_start:
    la sp, stacks
    li t0, 8192
    add sp, sp, t0
    mv s2, a0
    li s0, 0
    li s3, 0
start_next:
    beq s0, s2, skip_boot_hart
    mv a0, s0
    la a1, secondary
    li a2, 0
    li a6, 0
    li a7, 0x48534d
    ecall
    bnez a0, failed
    addi s3, s3, 1
    rdtime s4
    li t0, 240000000
    add s4, s4, t0
wait_one:
    la t0, arrivals
    ld t1, 0(t0)
    beq t1, s3, skip_boot_hart
    rdtime t0
    bltu t0, s4, wait_one
    j failed
skip_boot_hart:
    addi s0, s0, 1
    li t0, 16
    bltu s0, t0, start_next
    j passed
failed:
    la s1, fail_message
    j print_message
passed:
    la s1, pass_message
print_message:
    lbu a0, 0(s1)
    beqz a0, shutdown
    li a7, 1
    ecall
    addi s1, s1, 1
    j print_message
shutdown:
    li a0, 0
    li a1, 0
    li a6, 0
    li a7, 0x53525354
    ecall
stop:
    wfi
    j stop
.balign 4
secondary:
    la t0, arrivals
    li t1, 1
    amoadd.d.aqrl zero, t1, (t0)
    j stop
.section .rodata,"a"
pass_message:
    .asciz "PMP-HSM-SMOKE: all 16 Harts reached S-mode\n"
fail_message:
    .asciz "PMP-HSM-SMOKE: FAIL\n"
.section .bss,"aw",@nobits
.balign 4096
arrivals:
    .zero 8
.balign 16
stacks:
    .zero 8192
