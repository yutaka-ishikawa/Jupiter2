/* SPDX-License-Identifier: BSD-2-Clause */
/* QEMU firmware smoke payload: report entry through the real SBI console. */
.section .text
.globl _start
_start:
    la s0, message
1:  lbu a0, 0(s0)
    beqz a0, 2f
    li a7, 1
    ecall
    addi s0, s0, 1
    j 1b
2:  wfi
    j 2b
message:
    .asciz "K3: S-mode handoff reached\n"
