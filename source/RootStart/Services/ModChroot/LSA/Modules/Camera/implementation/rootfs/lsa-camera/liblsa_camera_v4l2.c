#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <netinet/in.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/mman.h>
#include <sys/time.h>
#include <unistd.h>

#define LSA_CAMERA_PATH "/dev/video0"
#define LSA_CAMERA_ALIAS "/dev/lsa-camera"
#define LSA_CAMERA_HOST "127.0.0.1"
#define LSA_CAMERA_PORT 8765
#define MAX_CAMERAS 32
#define MAX_BUFFERS 8
#define DEFAULT_WIDTH 960
#define DEFAULT_HEIGHT 1280
#define DEFAULT_SIZEIMAGE (12 * 1024 * 1024)

typedef int (*open_fn)(const char *, int, ...);
typedef int (*openat_fn)(int, const char *, int, ...);
typedef int (*close_fn)(int);
typedef ssize_t (*read_fn)(int, void *, size_t);
typedef int (*ioctl_fn)(int, unsigned long, ...);
typedef void *(*mmap_fn)(void *, size_t, int, int, int, off_t);
typedef int (*munmap_fn)(void *, size_t);

struct camera_buffer {
    unsigned char *address;
    size_t length;
    int queued;
};

struct camera_fd {
    int fd;
    int active;
    unsigned char *frame;
    size_t size;
    size_t offset;
    long frame_generation;
    int frame_ready;
    unsigned int width;
    unsigned int height;
    struct camera_buffer buffers[MAX_BUFFERS];
    unsigned int buffer_count;
    unsigned int sequence;
    int streaming;
};

static struct camera_fd cameras[MAX_CAMERAS];
static open_fn real_open;
static open_fn real_open64;
static openat_fn real_openat;
static openat_fn real_openat64;
static close_fn real_close;
static read_fn real_read;
static ioctl_fn real_ioctl;
static mmap_fn real_mmap;
static mmap_fn real_mmap64;
static munmap_fn real_munmap;

static void resolve_symbols(void) {
    if (!real_open) real_open = (open_fn)dlsym(RTLD_NEXT, "open");
    if (!real_open64) real_open64 = (open_fn)dlsym(RTLD_NEXT, "open64");
    if (!real_openat) real_openat = (openat_fn)dlsym(RTLD_NEXT, "openat");
    if (!real_openat64) real_openat64 = (openat_fn)dlsym(RTLD_NEXT, "openat64");
    if (!real_close) real_close = (close_fn)dlsym(RTLD_NEXT, "close");
    if (!real_read) real_read = (read_fn)dlsym(RTLD_NEXT, "read");
    if (!real_ioctl) real_ioctl = (ioctl_fn)dlsym(RTLD_NEXT, "ioctl");
    if (!real_mmap) real_mmap = (mmap_fn)dlsym(RTLD_NEXT, "mmap");
    if (!real_mmap64) real_mmap64 = (mmap_fn)dlsym(RTLD_NEXT, "mmap64");
    if (!real_munmap) real_munmap = (munmap_fn)dlsym(RTLD_NEXT, "munmap");
}

static int camera_path(const char *path) {
    return path && (!strcmp(path, LSA_CAMERA_PATH) || !strcmp(path, LSA_CAMERA_ALIAS));
}

static struct camera_fd *find_camera(int fd) {
    for (int i = 0; i < MAX_CAMERAS; ++i) if (cameras[i].active && cameras[i].fd == fd) return &cameras[i];
    return NULL;
}

static struct camera_fd *add_camera(int fd) {
    for (int i = 0; i < MAX_CAMERAS; ++i) {
        if (!cameras[i].active) {
            cameras[i].fd = fd;
            cameras[i].active = 1;
            cameras[i].width = DEFAULT_WIDTH;
            cameras[i].height = DEFAULT_HEIGHT;
            cameras[i].frame_generation = -1;
            return &cameras[i];
        }
    }
    return NULL;
}

static void reset_buffers(struct camera_fd *camera) {
    for (unsigned int i = 0; i < MAX_BUFFERS; ++i) {
        if (camera->buffers[i].address) {
            real_munmap(camera->buffers[i].address, camera->buffers[i].length);
        }
    }
    memset(camera->buffers, 0, sizeof(camera->buffers));
    camera->buffer_count = 0;
    camera->streaming = 0;
}

static int connect_frame(long generation) {
    int fd = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return -1;
    struct sockaddr_in address;
    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_port = htons(LSA_CAMERA_PORT);
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (connect(fd, (struct sockaddr *)&address, sizeof(address))) { real_close(fd); return -1; }
    char request[256];
    int length = snprintf(
        request, sizeof(request),
        "GET /frame.jpg?after=%ld HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
        generation
    );
    if (length < 0 || (size_t)length >= sizeof(request)
        || write(fd, request, (size_t)length) != length) {
        real_close(fd);
        return -1;
    }
    return fd;
}

static int fetch_frame(struct camera_fd *camera) {
    int fd = connect_frame(camera->frame_generation);
    if (fd < 0) return -1;
    unsigned char header[8192];
    size_t used = 0;
    int header_end = 0;
    while (used < sizeof(header) - 1) {
        ssize_t got = real_read(fd, header + used, sizeof(header) - 1 - used);
        if (got <= 0) { real_close(fd); return -1; }
        used += (size_t)got;
        header[used] = '\0';
        unsigned char *marker = (unsigned char *)strstr((char *)header, "\r\n\r\n");
        if (marker) { header_end = (int)(marker - header) + 4; break; }
    }
    if (!header_end || strncmp((char *)header, "HTTP/1.0 200", 12) && strncmp((char *)header, "HTTP/1.1 200", 12)) { real_close(fd); errno = EIO; return -1; }
    char *length_field = strcasestr((char *)header, "Content-Length:");
    if (!length_field) { real_close(fd); errno = EIO; return -1; }
    long length = strtol(length_field + 15, NULL, 10);
    if (length <= 0 || length > 32 * 1024 * 1024) { real_close(fd); errno = EIO; return -1; }
    unsigned char *frame = malloc((size_t)length);
    if (!frame) { real_close(fd); errno = ENOMEM; return -1; }
    size_t body = used - (size_t)header_end;
    if (body > (size_t)length) body = (size_t)length;
    memcpy(frame, header + header_end, body);
    while (body < (size_t)length) {
        ssize_t got = real_read(fd, frame + body, (size_t)length - body);
        if (got <= 0) { free(frame); real_close(fd); errno = EIO; return -1; }
        body += (size_t)got;
    }
    char *generation_field = strcasestr((char *)header, "X-LSA-Camera-Generation:");
    char *width_field = strcasestr((char *)header, "X-LSA-Camera-Width:");
    char *height_field = strcasestr((char *)header, "X-LSA-Camera-Height:");
    long generation = generation_field
        ? strtol(generation_field + 24, NULL, 10)
        : camera->frame_generation + 1;
    unsigned long width = width_field ? strtoul(width_field + 19, NULL, 10) : 0;
    unsigned long height = height_field ? strtoul(height_field + 20, NULL, 10) : 0;
    real_close(fd);
    free(camera->frame);
    camera->frame = frame;
    camera->size = (size_t)length;
    camera->offset = 0;
    camera->frame_generation = generation;
    camera->frame_ready = 1;
    if (width > 0 && width <= UINT32_MAX) camera->width = (unsigned int)width;
    if (height > 0 && height <= UINT32_MAX) camera->height = (unsigned int)height;
    return 0;
}

static int open_camera(int flags, mode_t mode) {
    resolve_symbols();
    int fd = real_open("/dev/null", flags & ~(O_CREAT | O_EXCL), mode);
    if (fd < 0) return fd;
    if (!add_camera(fd)) { real_close(fd); errno = EMFILE; return -1; }
    return fd;
}

int open(const char *path, int flags, ...) {
    mode_t mode = 0;
    if (flags & O_CREAT) { va_list args; va_start(args, flags); mode = va_arg(args, mode_t); va_end(args); }
    if (camera_path(path)) return open_camera(flags, mode);
    resolve_symbols();
    return real_open(path, flags, mode);
}

int open64(const char *path, int flags, ...) {
    mode_t mode = 0;
    if (flags & O_CREAT) { va_list args; va_start(args, flags); mode = va_arg(args, mode_t); va_end(args); }
    if (camera_path(path)) return open_camera(flags, mode);
    resolve_symbols();
    return real_open64 ? real_open64(path, flags, mode) : real_open(path, flags, mode);
}

int openat(int dirfd, const char *path, int flags, ...) {
    mode_t mode = 0;
    if (flags & O_CREAT) { va_list args; va_start(args, flags); mode = va_arg(args, mode_t); va_end(args); }
    if (camera_path(path)) return open_camera(flags, mode);
    resolve_symbols();
    return real_openat(dirfd, path, flags, mode);
}

int openat64(int dirfd, const char *path, int flags, ...) {
    mode_t mode = 0;
    if (flags & O_CREAT) { va_list args; va_start(args, flags); mode = va_arg(args, mode_t); va_end(args); }
    if (camera_path(path)) return open_camera(flags, mode);
    resolve_symbols();
    return real_openat64 ? real_openat64(dirfd, path, flags, mode) : real_openat(dirfd, path, flags, mode);
}

int close(int fd) {
    resolve_symbols();
    struct camera_fd *camera = find_camera(fd);
    if (camera) { free(camera->frame); reset_buffers(camera); memset(camera, 0, sizeof(*camera)); }
    return real_close(fd);
}

ssize_t read(int fd, void *buffer, size_t count) {
    resolve_symbols();
    struct camera_fd *camera = find_camera(fd);
    if (!camera) return real_read(fd, buffer, count);
    if (!camera->frame || camera->offset >= camera->size) if (fetch_frame(camera)) return -1;
    size_t remaining = camera->size - camera->offset;
    size_t copied = remaining < count ? remaining : count;
    memcpy(buffer, camera->frame + camera->offset, copied);
    camera->offset += copied;
    if (camera->offset >= camera->size) camera->frame_ready = 0;
    return (ssize_t)copied;
}

static void *map_camera_buffer(struct camera_fd *camera, size_t length, off_t offset) {
    if (offset < 0 || (unsigned long)offset % DEFAULT_SIZEIMAGE) { errno = EINVAL; return MAP_FAILED; }
    unsigned long index = (unsigned long)offset / DEFAULT_SIZEIMAGE;
    if (index >= camera->buffer_count || length > DEFAULT_SIZEIMAGE) { errno = EINVAL; return MAP_FAILED; }
    struct camera_buffer *buffer = &camera->buffers[index];
    if (!buffer->address) {
        buffer->address = real_mmap(NULL, DEFAULT_SIZEIMAGE, PROT_READ | PROT_WRITE,
            MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (buffer->address == MAP_FAILED) { buffer->address = NULL; return MAP_FAILED; }
        buffer->length = DEFAULT_SIZEIMAGE;
    }
    return buffer->address;
}

void *mmap(void *address, size_t length, int protection, int flags, int fd, off_t offset) {
    resolve_symbols();
    struct camera_fd *camera = find_camera(fd);
    if (!camera) return real_mmap(address, length, protection, flags, fd, offset);
    return map_camera_buffer(camera, length, offset);
}

void *mmap64(void *address, size_t length, int protection, int flags, int fd, off_t offset) {
    resolve_symbols();
    struct camera_fd *camera = find_camera(fd);
    if (!camera) return real_mmap64 ? real_mmap64(address, length, protection, flags, fd, offset) : real_mmap(address, length, protection, flags, fd, offset);
    return map_camera_buffer(camera, length, offset);
}

int munmap(void *address, size_t length) {
    resolve_symbols();
    for (int i = 0; i < MAX_CAMERAS; ++i) {
        if (!cameras[i].active) continue;
        for (unsigned int j = 0; j < cameras[i].buffer_count; ++j) {
            struct camera_buffer *buffer = &cameras[i].buffers[j];
            if (buffer->address == address) {
                buffer->address = NULL;
                buffer->length = 0;
                buffer->queued = 0;
                return real_munmap(address, length);
            }
        }
    }
    return real_munmap(address, length);
}

static void format(struct v4l2_format *value, struct camera_fd *camera) {
    value->type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    value->fmt.pix.width = camera->width;
    value->fmt.pix.height = camera->height;
    value->fmt.pix.pixelformat = V4L2_PIX_FMT_MJPEG;
    value->fmt.pix.field = V4L2_FIELD_NONE;
    value->fmt.pix.bytesperline = 0;
    value->fmt.pix.sizeimage = DEFAULT_SIZEIMAGE;
    value->fmt.pix.colorspace = V4L2_COLORSPACE_JPEG;
}

int ioctl(int fd, unsigned long request, ...) {
    resolve_symbols();
    va_list args; va_start(args, request); void *arg = va_arg(args, void *); va_end(args);
    struct camera_fd *camera = find_camera(fd);
    if (!camera) return real_ioctl(fd, request, arg);
    switch (request) {
        case VIDIOC_QUERYCAP: {
            struct v4l2_capability *value = arg; memset(value, 0, sizeof(*value));
            snprintf((char *)value->driver, sizeof(value->driver), "lsa-camera");
            snprintf((char *)value->card, sizeof(value->card), "Android Camera MJPEG");
            snprintf((char *)value->bus_info, sizeof(value->bus_info), "platform:lsa");
            value->version = (1 << 16); value->capabilities = V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_READWRITE | V4L2_CAP_STREAMING | V4L2_CAP_DEVICE_CAPS; value->device_caps = value->capabilities & ~V4L2_CAP_DEVICE_CAPS; return 0;
        }
        case VIDIOC_ENUM_FMT: { struct v4l2_fmtdesc *value = arg; if (value->index) { errno = EINVAL; return -1; } value->type = V4L2_BUF_TYPE_VIDEO_CAPTURE; value->pixelformat = V4L2_PIX_FMT_MJPEG; snprintf((char *)value->description, sizeof(value->description), "Motion-JPEG from Android camera"); return 0; }
        case VIDIOC_G_FMT: format(arg, camera); return 0;
        case VIDIOC_TRY_FMT:
        case VIDIOC_S_FMT: {
            struct v4l2_format *value = arg;
            if (value->fmt.pix.pixelformat && value->fmt.pix.pixelformat != V4L2_PIX_FMT_MJPEG) { errno = EINVAL; return -1; }
            // The Android source chooses its JPEG size.  Obtain a real frame
            // before format negotiation rather than claiming the caller's
            // requested dimensions while delivering a different JPEG.
            if (!camera->frame && fetch_frame(camera)) return -1;
            format(value, camera);
            return 0;
        }
        case VIDIOC_ENUM_FRAMESIZES: { struct v4l2_frmsizeenum *value = arg; if (value->index || value->pixel_format != V4L2_PIX_FMT_MJPEG) { errno = EINVAL; return -1; } value->type = V4L2_FRMSIZE_TYPE_DISCRETE; value->discrete.width = camera->width; value->discrete.height = camera->height; return 0; }
        case VIDIOC_G_PARM:
        case VIDIOC_S_PARM: { struct v4l2_streamparm *value = arg; value->type = V4L2_BUF_TYPE_VIDEO_CAPTURE; value->parm.capture.capability = V4L2_CAP_TIMEPERFRAME; value->parm.capture.timeperframe.numerator = 1; value->parm.capture.timeperframe.denominator = 1; return 0; }
        case VIDIOC_ENUMINPUT: { struct v4l2_input *value = arg; if (value->index) { errno = EINVAL; return -1; } memset(value, 0, sizeof(*value)); value->index = 0; value->type = V4L2_INPUT_TYPE_CAMERA; snprintf((char *)value->name, sizeof(value->name), "Android Camera"); return 0; }
        case VIDIOC_G_INPUT: *(int *)arg = 0; return 0;
        case VIDIOC_S_INPUT: if (*(int *)arg) { errno = EINVAL; return -1; } return 0;
        case VIDIOC_ENUM_FRAMEINTERVALS: { struct v4l2_frmivalenum *value = arg; if (value->index || value->pixel_format != V4L2_PIX_FMT_MJPEG) { errno = EINVAL; return -1; } value->type = V4L2_FRMIVAL_TYPE_DISCRETE; value->discrete.numerator = 1; value->discrete.denominator = 1; return 0; }
        case VIDIOC_REQBUFS: {
            struct v4l2_requestbuffers *value = arg;
            if (value->type != V4L2_BUF_TYPE_VIDEO_CAPTURE || value->memory != V4L2_MEMORY_MMAP) { errno = EINVAL; return -1; }
            reset_buffers(camera);
            if (!value->count) return 0;
            camera->buffer_count = value->count > 4 ? 4 : value->count;
            value->count = camera->buffer_count;
            return 0;
        }
        case VIDIOC_QUERYBUF: {
            struct v4l2_buffer *value = arg;
            if (value->type != V4L2_BUF_TYPE_VIDEO_CAPTURE || value->memory != V4L2_MEMORY_MMAP || value->index >= camera->buffer_count) { errno = EINVAL; return -1; }
            value->length = DEFAULT_SIZEIMAGE;
            value->m.offset = value->index * DEFAULT_SIZEIMAGE;
            return 0;
        }
        case VIDIOC_QBUF: {
            struct v4l2_buffer *value = arg;
            if (value->type != V4L2_BUF_TYPE_VIDEO_CAPTURE || value->memory != V4L2_MEMORY_MMAP || value->index >= camera->buffer_count) { errno = EINVAL; return -1; }
            camera->buffers[value->index].queued = 1;
            return 0;
        }
        case VIDIOC_DQBUF: {
            struct v4l2_buffer *value = arg;
            if (!camera->streaming) { errno = EAGAIN; return -1; }
            unsigned int index;
            for (index = 0; index < camera->buffer_count && !camera->buffers[index].queued; ++index) { }
            if (index == camera->buffer_count || !camera->buffers[index].address) { errno = EAGAIN; return -1; }
            if (!camera->frame_ready && fetch_frame(camera)) return -1;
            size_t bytes = camera->size < camera->buffers[index].length ? camera->size : camera->buffers[index].length;
            memcpy(camera->buffers[index].address, camera->frame, bytes);
            camera->buffers[index].queued = 0;
            camera->frame_ready = 0;
            memset(value, 0, sizeof(*value));
            value->type = V4L2_BUF_TYPE_VIDEO_CAPTURE; value->memory = V4L2_MEMORY_MMAP; value->index = index; value->length = camera->buffers[index].length; value->bytesused = bytes; value->sequence = camera->sequence++; value->flags = V4L2_BUF_FLAG_DONE; gettimeofday(&value->timestamp, NULL);
            return 0;
        }
        case VIDIOC_STREAMON: if (*(enum v4l2_buf_type *)arg != V4L2_BUF_TYPE_VIDEO_CAPTURE) { errno = EINVAL; return -1; } camera->streaming = 1; return 0;
        case VIDIOC_STREAMOFF: camera->streaming = 0; return 0;
        default: errno = ENOTTY; return -1;
    }
}
