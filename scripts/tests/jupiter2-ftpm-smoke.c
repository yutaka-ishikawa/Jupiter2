#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <unistd.h>

#include <tee_client_api.h>

static int test_ftpm(void)
{
    const TEEC_UUID uuid = {
	0xbc50d971, 0xd4c9, 0x42c4,
	{ 0x82, 0xcb, 0x34, 0x3f, 0xb7, 0xf3, 0x78, 0x96 }
    };
    /* TPM2_GetRandom(16), TPM_ST_NO_SESSIONS. */
    uint8_t command[] = {
	0x80, 0x01, 0x00, 0x00, 0x00, 0x0c, 0x00, 0x00, 0x01, 0x7b,
	0x00, 0x10
    };
    uint8_t response[4096] = { 0 };
    TEEC_Operation op = { 0 };
    TEEC_Context ctx;
    TEEC_Session session;
    uint32_t origin = 0;
    TEEC_Result result;
    unsigned int count;
    unsigned int size;
    int status = EXIT_FAILURE;

    result = TEEC_InitializeContext(NULL, &ctx);
    if (result != TEEC_SUCCESS) {
	fprintf(stderr, "TEEC_InitializeContext: %#x\n", result);
	return status;
    }

    result = TEEC_OpenSession(&ctx, &session, &uuid, TEEC_LOGIN_PUBLIC,
			      NULL, NULL, &origin);
    if (result != TEEC_SUCCESS) {
	fprintf(stderr, "TEEC_OpenSession: %#x origin=%#x\n", result, origin);
	TEEC_FinalizeContext(&ctx);
	return status;
    }

    op.paramTypes = TEEC_PARAM_TYPES(TEEC_MEMREF_TEMP_INPUT,
				     TEEC_MEMREF_TEMP_INOUT, TEEC_NONE,
				     TEEC_NONE);
    op.params[0].tmpref.buffer = command;
    op.params[0].tmpref.size = sizeof(command);
    op.params[1].tmpref.buffer = response;
    op.params[1].tmpref.size = sizeof(response);
    result = TEEC_InvokeCommand(&session, 0, &op, &origin);
    if (result != TEEC_SUCCESS) {
	fprintf(stderr, "TEEC_InvokeCommand: %#x origin=%#x\n", result, origin);
    } else {
	size = (unsigned int)response[2] << 24 |
	       (unsigned int)response[3] << 16 |
	       (unsigned int)response[4] << 8 | response[5];
	count = (unsigned int)response[10] << 8 | response[11];
	if (response[0] == 0x80 && response[1] == 0x01 &&
	    !response[6] && !response[7] && !response[8] && !response[9] &&
	    count == 16 && size == 12 + count) {
	    printf("fTPM PASS: TPM2_GetRandom returned %u bytes\n", count);
	    status = EXIT_SUCCESS;
	} else {
	    fprintf(stderr, "TPM reply: tag=%02x%02x rc=%02x%02x%02x%02x "
		    "size=%u count=%u\n", response[0], response[1], response[6],
		    response[7], response[8], response[9], size, count);
	}
    }
    TEEC_CloseSession(&session);
    TEEC_FinalizeContext(&ctx);
    return status;
}

static int start_supplicant(void)
{
    int status;
    pid_t child;
    int log;

    if (mount("devtmpfs", "/dev", "devtmpfs", 0, NULL)) {
	perror("mount /dev");
	return -1;
    }
    /* The minimal guest keeps the SBI boot console for kernel messages. */
    log = open("/dev/kmsg", O_RDWR);
    if (log < 0) {
	return -1;
    }
    if (dup2(log, STDIN_FILENO) < 0 || dup2(log, STDOUT_FILENO) < 0 ||
	dup2(log, STDERR_FILENO) < 0) {
	return -1;
    }
    if (log > STDERR_FILENO) {
	close(log);
    }
    child = fork();
    if (child < 0) {
	perror("fork");
	return -1;
    }
    if (!child) {
	execl("/tee-supplicant", "tee-supplicant", "-d", (char *)NULL);
	perror("tee-supplicant");
	_exit(EXIT_FAILURE);
    }
    if (waitpid(child, &status, 0) != child ||
	!WIFEXITED(status) || WEXITSTATUS(status)) {
	fprintf(stderr, "tee-supplicant did not start\n");
	return -1;
    }
    return 0;
}

int main(void)
{
    int status = EXIT_FAILURE;

    if (getpid() != 1) {
	return test_ftpm();
    }
    if (!start_supplicant()) {
	status = test_ftpm();
    }
    if (status != EXIT_SUCCESS) {
	fprintf(stderr, "fTPM FAIL\n");
    }
    fflush(stdout);
    reboot(RB_POWER_OFF);
    perror("power off");
    return status;
}
