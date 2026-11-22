/* SPDX-License-Identifier: BSD-2-Clause */
#include <stdio.h>
#include <sys/mount.h>
#include <sys/utsname.h>
#include <unistd.h>

int main(void)
{
    struct utsname info;
    long cpus;

    if (mount("proc", "/proc", "proc", 0, NULL) ||
	mount("sysfs", "/sys", "sysfs", 0, NULL) || uname(&info)) {
	perror("K3 Linux smoke initialization");
    } else {
	cpus = sysconf(_SC_NPROCESSORS_ONLN);
	printf("K3 Linux userspace reached: %s %s; online harts=%ld\n",
	       info.release, info.machine, cpus);
	fflush(stdout);
    }
    for (;;) {
	pause();
    }
}
