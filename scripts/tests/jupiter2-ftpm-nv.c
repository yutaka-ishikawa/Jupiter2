#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/syscall.h>
#include <unistd.h>

/* TPM 2.0 commands for NV index 0x01500020 with empty owner authorization. */
static const uint8_t nv_define[] = {
    0x80, 0x02, 0x00, 0x00, 0x00, 0x2d, 0x00, 0x00, 0x01, 0x2a,
    0x40, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x09, 0x40, 0x00,
    0x00, 0x09, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x0e, 0x01, 0x50, 0x00, 0x20, 0x00, 0x0b, 0x00, 0x02, 0x00,
    0x02, 0x00, 0x00, 0x00, 0x04,
};

static const uint8_t nv_read[] = {
    0x80, 0x02, 0x00, 0x00, 0x00, 0x23, 0x00, 0x00, 0x01, 0x4e,
    0x40, 0x00, 0x00, 0x01, 0x01, 0x50, 0x00, 0x20, 0x00, 0x00,
    0x00, 0x09, 0x40, 0x00, 0x00, 0x09, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x04, 0x00, 0x00,
};

static const uint8_t nv_seed[] = {
    0x80, 0x02, 0x00, 0x00, 0x00, 0x27, 0x00, 0x00, 0x01, 0x37,
    0x40, 0x00, 0x00, 0x01, 0x01, 0x50, 0x00, 0x20, 0x00, 0x00,
    0x00, 0x09, 0x40, 0x00, 0x00, 0x09, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x04, 0x54, 0x45, 0x53, 0x54, 0x00, 0x00,
};

static uint32_t be32(const uint8_t *p)
{
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 |
	   (uint32_t)p[2] << 8 | p[3];
}

static int exchange(const uint8_t *cmd, size_t size, uint8_t *reply)
{
    int fd = open("/dev/tpmrm0", O_RDWR);
    ssize_t n;

    if (fd < 0) {
	return -errno;
    }
    errno = 0;
    n = write(fd, cmd, size);
    if (n == (ssize_t)size) {
	n = read(fd, reply, 4096);
    } else if (n >= 0) {
	n = -EPROTO;
    }
    if (n < 0) {
	if (n == -1 && errno) {
	    n = -errno;
	}
    } else if (n < 10 || be32(reply + 2) != (uint32_t)n) {
	n = -EPROTO;
    }
    close(fd);
    return n;
}

static int test_command(const char *label, const uint8_t *cmd, size_t size,
			uint8_t *reply)
{
    int n = exchange(cmd, size, reply);

    if (n < 0) {
	fprintf(stderr, "%s transport error: %d\n", label, n);
    } else {
	printf("%s TPM_RC=0x%08x\n", label, be32(reply + 6));
    }
    return n < 0 || be32(reply + 6) ? -1 : n;
}

#define RUN(cmd) test_command(#cmd, cmd, sizeof(cmd), reply)

static pid_t start_supplicant(void)
{
    pid_t pid = fork();

    if (!pid) {
	execl("/tee-supplicant", "tee-supplicant", (char *)NULL);
	_exit(127);
    }
    sleep(1);
    return pid;
}

/* The REE FS uses flat files named dirf.db and hexadecimal object numbers. */
static int export_storage(void)
{
    DIR *dir = opendir("/var/lib/tee");
    struct dirent *entry;
    unsigned int files = 0;

    if (!dir) {
	return -1;
    }
    while ((entry = readdir(dir))) {
	const char *name = entry->d_name;
	FILE *file;
	unsigned char data[128];
	size_t count;
	size_t i;
	int fd;

	if (entry->d_type != DT_REG) {
	    continue;
	}
	if (strcmp(name, "dirf.db") &&
	    strspn(name, "0123456789abcdef") != strlen(name)) {
	    closedir(dir);
	    return -1;
	}
	fd = openat(dirfd(dir), name, O_RDONLY);
	file = fd < 0 ? NULL : fdopen(fd, "rb");
	if (!file) {
	    if (fd >= 0) {
		close(fd);
	    }
	    closedir(dir);
	    return -1;
	}
	printf("NV_FILE %s\n", name);
	while ((count = fread(data, 1, sizeof(data), file))) {
	    char hex[sizeof(data) * 2 + 1];
	    static const char digits[] = "0123456789abcdef";

	    for (i = 0; i < count; i++) {
		hex[2 * i] = digits[data[i] >> 4];
		hex[2 * i + 1] = digits[data[i] & 15];
	    }
	    hex[2 * count] = '\0';
	    printf("NV_HEX %s\n", hex);
	}
	if (ferror(file)) {
	    fclose(file);
	    closedir(dir);
	    return -1;
	}
	fclose(file);
	puts("NV_END");
	files++;
    }
    closedir(dir);
    if (!files) {
	return -1;
    }
    printf("NV_EXPORT files=%u\n", files);
    return 0;
}

static int run_test(const char *mode)
{
    uint8_t reply[4096];
    int fd;
    int rc;

    if (start_supplicant() <= 0) {
	return -1;
    }
    fd = open("/tpm_ftpm_tee.ko", O_RDONLY);
    if (fd < 0) {
	return -1;
    }
    rc = syscall(SYS_finit_module, fd, "", 0);
    close(fd);
    if (rc) {
	return -1;
    }
    if (!strcmp(mode, "seed")) {
	if (RUN(nv_define) < 0 || RUN(nv_seed) < 0 || export_storage()) {
	    return -1;
	}
    }
    if (!strcmp(mode, "empty")) {
	rc = exchange(nv_read, sizeof(nv_read), reply);
	/* TPM_RC_HANDLE on the second handle, the NV index. */
	if (rc != 10 || be32(reply + 6) != 0x28b) {
	    fprintf(stderr, "empty TPM reply size=%d rc=%#x\n",
		    rc, rc < 10 ? 0 : be32(reply + 6));
	    return -1;
	}
	puts("NV_EMPTY TPM_RC=0x0000028b");
    } else if (RUN(nv_read) != 25 || reply[14] || reply[15] != 4 ||
	       memcmp(reply + 16, "TEST", 4)) {
	return -1;
    }
    return 0;
}

int main(int argc, char **argv)
{
    int fd;
    int rc;
    const char *mode = argv[argc - 1];

    if (mount("devtmpfs", "/dev", "devtmpfs", 0, NULL)) {
	return 1;
    }
    fd = open("/dev/kmsg", O_WRONLY);
    if (fd < 0 || dup2(fd, STDOUT_FILENO) < 0 ||
	dup2(fd, STDERR_FILENO) < 0) {
	return 1;
    }
    close(fd);
    setvbuf(stdout, NULL, _IOLBF, 0);
    if (argc < 2 || (strcmp(mode, "seed") && strcmp(mode, "read") &&
		     strcmp(mode, "empty"))) {
	printf("NV_RESULT invalid mode argc=%d last=%s\n", argc, mode);
    } else {
	rc = run_test(mode);
	printf("NV_RESULT %s %s\n", mode, rc ? "FAIL" : "PASS");
    }
    reboot(RB_POWER_OFF);
    return 1;
}
