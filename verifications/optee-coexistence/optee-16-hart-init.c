/* SPDX-License-Identifier: BSD-2-Clause */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdio.h>
#include <sched.h>
#include <unistd.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <tee_client_api.h>
#include "protocol.h"

static int check_ta(unsigned int cpu)
{
    TEEC_Context ctx;
    TEEC_Session session;
    const TEEC_UUID uuid = COEXISTENCE_TA_UUID;
    TEEC_Operation op = {0};
    uint32_t origin = 0;
    TEEC_Result rc;
    int passed = 0;
    cpu_set_t affinity;

    CPU_ZERO(&affinity);
    CPU_SET(cpu, &affinity);
    if (sched_setaffinity(0, sizeof(affinity), &affinity) ||
	sched_getcpu() != (int)cpu) {
	perror("CPU affinity");
	return 1;
    }
    rc = TEEC_InitializeContext(NULL, &ctx);
    printf("TEEC_InitializeContext: %#x\n", rc);
    if (rc != TEEC_SUCCESS) {
	goto done;
    }
    rc = TEEC_OpenSession(&ctx, &session, &uuid, TEEC_LOGIN_PUBLIC,
			  NULL, NULL, &origin);
    printf("TEEC_OpenSession: %#x origin=%u\n", rc, origin);
    if (rc != TEEC_SUCCESS) {
	goto finish;
    }
    op.paramTypes = TEEC_PARAM_TYPES(TEEC_VALUE_INOUT, TEEC_NONE,
				     TEEC_NONE, TEEC_NONE);
    op.params[0].value.a = 41;
    rc = TEEC_InvokeCommand(&session, COEXISTENCE_CMD_INCREMENT, &op, &origin);
    if (rc == TEEC_SUCCESS && op.params[0].value.a == 42 &&
	op.params[0].value.b == COEXISTENCE_TA_MARKER) {
	passed = 1;
	printf("PASS: CPU %u OP-TEE TA response verified\n", cpu);
    } else {
	printf("FAIL: TA result=%#x origin=%u value=%u marker=%#x\n",
	       rc, origin, op.params[0].value.a, op.params[0].value.b);
    }
    TEEC_CloseSession(&session);
finish:
    TEEC_FinalizeContext(&ctx);
done:
    return !passed;
}

int main(void)
{
    int log;
    unsigned int cpu;
    int failed = 0;
    long online = sysconf(_SC_NPROCESSORS_ONLN);

    setvbuf(stdout, NULL, _IONBF, 0);
    if (mount("devtmpfs", "/dev", "devtmpfs", 0, NULL)) {
	perror("devtmpfs");
	goto stop;
    }
    log = open("/dev/kmsg", O_WRONLY);
    if (log >= 0) {
	dup2(log, STDOUT_FILENO);
	dup2(log, STDERR_FILENO);
	if (log > STDERR_FILENO) {
	    close(log);
	}
    }
    printf("OP-TEE test: online CPUs=%ld\n", online);
    if (online != 16) {
	goto stop;
    }
    for (cpu = 0; cpu < 16; cpu++) {
	failed |= check_ta(cpu);
    }
    if (!failed) {
	printf("PASS: OP-TEE TA calls on all 16 CPUs\n");
	reboot(RB_POWER_OFF);
    }
stop:
    for (;;) {
	pause();
    }
}
