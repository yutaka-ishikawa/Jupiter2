#include <fcntl.h>
#include <stdio.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

int main(void)
{
    int fd;
    int status;
    pid_t child;

    if (mount("devtmpfs", "/dev", "devtmpfs", 0, NULL) < 0) {
        perror("mount devtmpfs");
        goto poweroff;
    }

    fd = open("/dev/kmsg", O_WRONLY);
    if (fd >= 0) {
        dup2(fd, STDOUT_FILENO);
        dup2(fd, STDERR_FILENO);
        close(fd);
    }
    fd = open("/keystone-driver.ko", O_RDONLY);
    if (fd < 0 || syscall(SYS_finit_module, fd, "", 0) < 0) {
        perror("load Keystone driver");
        goto poweroff;
    }
    close(fd);

    child = fork();
    if (child == 0) {
        execl("/optee-coexistence", "/optee-coexistence",
              "/hello-native", "/eyrie-rt", "/loader.bin", NULL);
        perror("exec optee-coexistence");
        _exit(127);
    }
    if (child < 0 || waitpid(child, &status, 0) < 0 ||
        !WIFEXITED(status) || WEXITSTATUS(status) != 0)
        fprintf(stderr, "OP-TEE coexistence init: test failed\n");

poweroff:
    fflush(NULL);
    reboot(RB_POWER_OFF);
    for (;;)
        pause();
}
