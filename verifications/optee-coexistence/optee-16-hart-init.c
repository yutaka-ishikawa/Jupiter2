/* SPDX-License-Identifier: BSD-2-Clause */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdio.h>
#include <sched.h>
#include <unistd.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <tee_client_api.h>
#include "protocol.h"

#define HARTS 16

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
    op.params[0].value.a = 41 + cpu;
    rc = TEEC_InvokeCommand(&session, COEXISTENCE_CMD_INCREMENT, &op, &origin);
    if (rc == TEEC_SUCCESS && op.params[0].value.a == 42 + cpu &&
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

static int check_parallel(void)
{
    int gate[2];
    pid_t children[HARTS];
    unsigned int count = 0;
    int failed = 0;
    unsigned int cpu;
    int status;
    char unused;
    ssize_t released;

    if (pipe(gate)) {
	perror("pipe");
	return 1;
    }
    while (count < HARTS) {
	pid_t child = fork();

	if (child < 0) {
	    perror("fork");
	    failed = 1;
	    break;
	}
	if (child == 0) {
	    close(gate[1]);
	    /* EOF releases the workers once all write descriptors are closed. */
	    released = read(gate[0], &unused, sizeof(unused));
	    close(gate[0]);
	    _exit(released != 0 || check_ta(count));
	}
	children[count++] = child;
    }
    close(gate[0]);
    close(gate[1]);
    for (cpu = 0; cpu < count; cpu++) {
	if (waitpid(children[cpu], &status, 0) != children[cpu] ||
	    !WIFEXITED(status) || WEXITSTATUS(status)) {
	    failed = 1;
	}
    }
    return failed;
}

int main(void)
{
    int log;
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
    if (online == HARTS && !check_parallel()) {
	printf("PASS: parallel OP-TEE TA calls on all 16 CPUs\n");
	reboot(RB_POWER_OFF);
    }
stop:
    for (;;) {
	pause();
    }
}
