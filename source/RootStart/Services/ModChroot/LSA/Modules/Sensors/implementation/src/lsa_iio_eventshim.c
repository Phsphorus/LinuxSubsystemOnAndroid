#define _GNU_SOURCE

#include <errno.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include <stdint.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/un.h>

#include <linux/iio/events.h>


#define LSA_EVENT_SOCKET \
    "/run/lsa-iio/events.sock"


static bool
lsa_iio_name(
    int fd,
    char *name,
    size_t size
)
{
    char procpath[64];
    char target[512];

    snprintf(
        procpath,
        sizeof(procpath),
        "/proc/self/fd/%d",
        fd
    );

    ssize_t n = readlink(
        procpath,
        target,
        sizeof(target) - 1
    );

    if (n < 0)
        return false;

    target[n] = '\0';

    const char *base = strrchr(
        target,
        '/'
    );

    base = base ? base + 1 : target;

    if (
        strncmp(
            base,
            "iio:device",
            10
        ) != 0
    )
        return false;

    size_t base_len = strlen(base);

    if (base_len + 1 > size)
        return false;

    memcpy(
        name,
        base,
        base_len + 1
    );

    return true;
}


static int
lsa_try_event_fd(
    const char *device,
    int *event_fd
)
{
    int s = socket(
        AF_UNIX,
        SOCK_STREAM | SOCK_CLOEXEC,
        0
    );

    if (s < 0)
        return 0;

    struct sockaddr_un addr;

    memset(
        &addr,
        0,
        sizeof(addr)
    );

    addr.sun_family = AF_UNIX;

    snprintf(
        addr.sun_path,
        sizeof(addr.sun_path),
        "%s",
        LSA_EVENT_SOCKET
    );

    if (
        connect(
            s,
            (struct sockaddr *)&addr,
            sizeof(addr)
        ) < 0
    ) {
        close(s);
        return 0;
    }

    char request[64];

    int len = snprintf(
        request,
        sizeof(request),
        "%s\n",
        device
    );

    if (
        len <= 0 ||
        len >= (int)sizeof(request)
    ) {
        close(s);
        return 0;
    }

    if (
        send(
            s,
            request,
            (size_t)len,
            MSG_NOSIGNAL
        ) != len
    ) {
        close(s);
        return 0;
    }

    char reply[3];

    ssize_t got = recv(
        s,
        reply,
        sizeof(reply),
        MSG_WAITALL
    );

    if (
        got != 3 ||
        memcmp(
            reply,
            "OK\n",
            3
        ) != 0
    ) {
        close(s);
        return 0;
    }

    *event_fd = s;

    return 1;
}


/*
 * ABI-level ioctl interposer.
 *
 * Linux passes the optional third ioctl argument in the normal
 * third argument word/register. For a true two-argument ioctl the
 * value is unspecified, but such commands ignore it in the kernel.
 *
 * This avoids reading a nonexistent C vararg while preserving pointer
 * and integer ioctl arguments bit-for-bit.
 */
int
ioctl(
    int fd,
    unsigned long request,
    unsigned long arg
)
{
    if (request == IIO_GET_EVENT_FD_IOCTL) {

        int *event_fd =
            (int *)(uintptr_t)arg;

        if (!event_fd) {
            errno = EFAULT;
            return -1;
        }

        char device[64];

        if (
            lsa_iio_name(
                fd,
                device,
                sizeof(device)
            )
        ) {
            if (
                lsa_try_event_fd(
                    device,
                    event_fd
                )
            )
                return 0;
        }
    }

    return (int)syscall(
        SYS_ioctl,
        fd,
        request,
        arg
    );
}
