/*
 * LSA private mount-namespace launcher.
 *
 * This deliberately does only the two kernel operations needed before any
 * LSA mount is made: create a mount namespace, then make its entire mount
 * tree recursively private.  Android's toybox `unshare -m` leaves inherited
 * shared-propagation flags intact on supported devices, which can otherwise
 * let a chroot /dev tmpfs hide host Binder devices.  The launcher contains no
 * device/vendor policy and execs an explicitly supplied absolute command.
 */
#define _GNU_SOURCE

#include <errno.h>
#include <sched.h>
#include <stdio.h>
#include <string.h>
#include <sys/mount.h>
#include <unistd.h>

static int fail(const char *operation) {
    fprintf(stderr, "lsa-mountns: %s: %s\n", operation, strerror(errno));
    return 1;
}

int main(int argc, char **argv) {
    if (argc < 2 || argv[1][0] == '\0') {
        fprintf(stderr, "usage: %s <absolute-command> [arguments...]\n", argv[0]);
        return 64;
    }
    if (argv[1][0] != '/') {
        fprintf(stderr, "lsa-mountns: command must be an absolute path\n");
        return 64;
    }
    if (unshare(CLONE_NEWNS) != 0) {
        return fail("unshare(CLONE_NEWNS)");
    }
    if (mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL) != 0) {
        return fail("mount(MS_REC|MS_PRIVATE)");
    }
    execv(argv[1], &argv[1]);
    return fail("execv");
}
