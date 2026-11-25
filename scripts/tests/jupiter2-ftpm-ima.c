#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#define IMA_PATH "/sys/kernel/security/ima/"

static int prepare(void)
{
    int status;
    int fd;
    int rc;
    pid_t child;

    if (mount("devtmpfs", "/dev", "devtmpfs", 0, NULL)) {
	return 1;
    }
    fd = open("/dev/kmsg", O_RDWR);
    if (fd < 0 || dup2(fd, STDIN_FILENO) < 0 ||
	dup2(fd, STDOUT_FILENO) < 0 || dup2(fd, STDERR_FILENO) < 0) {
	return 1;
    }
    if (fd > STDERR_FILENO) {
	close(fd);
    }
    child = fork();
    if (!child) {
	execl("/tee-supplicant", "tee-supplicant", "-d", (char *)NULL);
	_exit(127);
    }
    if (child < 0 || waitpid(child, &status, 0) != child ||
	!WIFEXITED(status) || WEXITSTATUS(status)) {
	fprintf(stderr, "IMA prep: supplicant failed\n");
	return 1;
    }
    fd = open("/tpm_ftpm_tee.ko", O_RDONLY);
    if (fd < 0) {
	return 1;
    }
    rc = syscall(SYS_finit_module, fd, "", 0);
    if (rc) {
	perror("IMA prep: finit_module");
    } else if ((rc = access("/dev/tpmrm0", F_OK))) {
	perror("IMA prep: /dev/tpmrm0");
    }
    close(fd);
    return rc != 0;
}

static int read_pcr(const char *label)
{
    static const uint8_t request[] = {
	0x80, 0x01, 0, 0, 0, 20, 0, 0, 0x01, 0x7e,
	0, 0, 0, 1, 0, 0x0b, 3, 0, 4, 0,
    };
    uint8_t reply[256];
    int fd = open("/dev/tpmrm0", O_RDWR);
    ssize_t n;
    int i;

    if (fd < 0) {
	return -1;
    }
    n = write(fd, request, sizeof(request));
    if (n == sizeof(request)) {
	n = read(fd, reply, sizeof(reply));
    }
    close(fd);
    if (n != 62 || memcmp(reply + 6, "\0\0\0\0", 4) ||
	memcmp(reply + 14, "\0\0\0\1\0\x0b\3\0\4\0\0\0\0\1\0\x20", 16)) {
	return -1;
    }
    printf("IMA_PCR_%s ", label);
    for (i = 30; i < n; i++) {
	printf("%02x", reply[i]);
    }
    puts("");
    return 0;
}

static int suite(int late)
{
    static const char policy[] =
	"measure func=FILE_CHECK mask=MAY_READ fsmagic=0x858458f6\n";
    char line[4096];
    FILE *measurements;
    int fd;
    int found = 0;

    if (mount("securityfs", "/sys/kernel/security", "securityfs", 0, NULL)) {
	perror("securityfs");
	return 1;
    }
    fd = open(IMA_PATH "policy", O_WRONLY);
    if (fd < 0 || write(fd, policy, sizeof(policy) - 1) != sizeof(policy) - 1 ||
	close(fd)) {
	perror("IMA policy");
	return 1;
    }
    if (read_pcr("BEFORE")) {
	return 1;
    }
    fd = open("/ima-probe", O_RDONLY);
    if (fd < 0 || read(fd, line, sizeof(line)) <= 0 || close(fd) ||
	read_pcr("AFTER")) {
	return 1;
    }
    measurements = fopen(late ? IMA_PATH "ascii_runtime_measurements" :
			 IMA_PATH "ascii_runtime_measurements_sha256", "r");
    if (!measurements) {
	perror("IMA SHA256 log");
	return 1;
    }
    while (fgets(line, sizeof(line), measurements)) {
	if (strstr(line, " /ima-probe\n")) {
	    printf("IMA_MEASUREMENT %s", line);
	    found++;
	}
    }
    fclose(measurements);
    return found != 1;
}

int main(int argc, char **argv)
{
    int fd;
    int rc;

    int late = argc > 1 && !strcmp(argv[argc - 1], "late");

    if (!strcmp(argv[0], "/ima-ftpm-prepare")) {
	return prepare();
    }
    if (late && prepare()) {
	reboot(RB_POWER_OFF);
	return 1;
    }
    fd = open("/dev/kmsg", O_WRONLY);
    if (fd < 0 || dup2(fd, STDOUT_FILENO) < 0 || dup2(fd, STDERR_FILENO) < 0) {
	return 1;
    }
    close(fd);
    setvbuf(stdout, NULL, _IOLBF, 0);
    rc = suite(late);
    printf("IMA_GUEST_RESULT=%d\n", rc);
    reboot(RB_POWER_OFF);
    return rc;
}
