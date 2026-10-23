#define _GNU_SOURCE

#include <android/hardware_buffer.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/uio.h>
#include <unistd.h>

#include <virgl/virglrenderer.h>

/* --------------------------------------------------------- */
/* Protocol                                                  */
/* --------------------------------------------------------- */

#define LSA_VIDEO_MAGIC   0x4c534156u
#define LSA_VIDEO_VERSION 1
#define LSA_MAX_FDS       8

struct lsa_video_frame {
    uint32_t magic;
    uint32_t version;

    uint32_t width;
    uint32_t height;

    uint32_t ahb_format;

    uint32_t stride_pixels;
    uint32_t stride_bytes;

    uint32_t num_fds;
    uint32_t pixel_fd_index;

    uint64_t pixel_size;

    uint32_t source_fourcc;
    uint32_t source_stride;

    uint32_t gl_error;
};

/* --------------------------------------------------------- */
/* Native handle ABI                                         */
/* --------------------------------------------------------- */

struct lsa_native_handle {
    int version;
    int numFds;
    int numInts;
    int data[];
};

/* --------------------------------------------------------- */
/* VirGL                                                     */
/* --------------------------------------------------------- */

typedef int (*transfer_fn)(
    uint32_t handle,
    uint32_t ctx_id,
    uint32_t level,
    uint32_t stride,
    uint32_t layer_stride,
    struct virgl_box *box,
    uint64_t offset,
    struct iovec *iov,
    int iovec_cnt);

typedef int (*info_fn)(
    int handle,
    struct virgl_renderer_resource_info *info);

static transfer_fn real_transfer;
static info_fn real_info;

/* --------------------------------------------------------- */
/* Minimal EGL ABI                                           */
/* --------------------------------------------------------- */

typedef void *EGLDisplay;
typedef void *EGLContext;
typedef void *EGLImageKHR;
typedef void *EGLClientBuffer;
typedef unsigned int EGLenum;
typedef int EGLint;
typedef int EGLBoolean;

#define EGL_NO_DISPLAY              ((EGLDisplay)0)
#define EGL_NO_CONTEXT              ((EGLContext)0)
#define EGL_NO_IMAGE_KHR            ((EGLImageKHR)0)

#define EGL_NONE                    0x3038
#define EGL_NATIVE_BUFFER_ANDROID   0x3140

typedef EGLDisplay (*PFNEGLGETCURRENTDISPLAY)(void);

typedef EGLClientBuffer
(*PFNEGLGETNATIVECLIENTBUFFERANDROID)(
    const AHardwareBuffer *);

typedef EGLImageKHR
(*PFNEGLCREATEIMAGEKHR)(
    EGLDisplay,
    EGLContext,
    EGLenum,
    EGLClientBuffer,
    const EGLint *);

typedef EGLBoolean
(*PFNEGLDESTROYIMAGEKHR)(
    EGLDisplay,
    EGLImageKHR);

typedef EGLint (*PFNEGLGETERROR)(void);

/*
 * libepoxy exports these as function-pointer VARIABLES.
 */
static PFNEGLGETCURRENTDISPLAY *p_eglGetCurrentDisplay;
static PFNEGLGETNATIVECLIENTBUFFERANDROID
    *p_eglGetNativeClientBufferANDROID;
static PFNEGLCREATEIMAGEKHR *p_eglCreateImageKHR;
static PFNEGLDESTROYIMAGEKHR *p_eglDestroyImageKHR;
static PFNEGLGETERROR *p_eglGetError;

/* --------------------------------------------------------- */
/* Minimal GL ABI                                            */
/* --------------------------------------------------------- */

typedef unsigned int GLenum;
typedef unsigned int GLuint;
typedef int GLint;
typedef int GLsizei;
typedef unsigned int GLbitfield;
typedef unsigned char GLboolean;
typedef void *GLeglImageOES;

#define GL_NO_ERROR                    0
#define GL_TEXTURE_2D                  0x0DE1
#define GL_TEXTURE_BINDING_2D          0x8069
#define GL_TEXTURE_MIN_FILTER          0x2801
#define GL_TEXTURE_MAG_FILTER          0x2800
#define GL_NEAREST                     0x2600

#define GL_TRIANGLES                   0x0004
#define GL_VERTEX_SHADER               0x8B31
#define GL_FRAGMENT_SHADER             0x8B30
#define GL_COMPILE_STATUS              0x8B81
#define GL_LINK_STATUS                 0x8B82
#define GL_CURRENT_PROGRAM             0x8B8D
#define GL_ACTIVE_TEXTURE              0x84E0
#define GL_TEXTURE0                    0x84C0
#define GL_VIEWPORT                    0x0BA2

#define GL_BLEND                       0x0BE2
#define GL_CULL_FACE                   0x0B44
#define GL_DEPTH_TEST                  0x0B71
#define GL_STENCIL_TEST                0x0B90
#define GL_SCISSOR_TEST                0x0C11
#define GL_RASTERIZER_DISCARD          0x8C89
#define GL_COLOR_WRITEMASK             0x0C23
#define GL_VERTEX_ARRAY_BINDING        0x85B5

#define GL_FALSE                       0
#define GL_TRUE                        1



#define GL_READ_FRAMEBUFFER            0x8CA8
#define GL_DRAW_FRAMEBUFFER            0x8CA9
#define GL_READ_FRAMEBUFFER_BINDING    0x8CAA
#define GL_DRAW_FRAMEBUFFER_BINDING    0x8CA6

#define GL_COLOR_ATTACHMENT0           0x8CE0
#define GL_FRAMEBUFFER_COMPLETE        0x8CD5
#define GL_COLOR_BUFFER_BIT            0x00004000

typedef void (*PFNGLGETINTEGERV)(
    GLenum,
    GLint *);

typedef void (*PFNGLGENTEXTURES)(
    GLsizei,
    GLuint *);

typedef void (*PFNGLDELETETEXTURES)(
    GLsizei,
    const GLuint *);

typedef void (*PFNGLBINDTEXTURE)(
    GLenum,
    GLuint);

typedef void (*PFNGLTEXPARAMETERI)(
    GLenum,
    GLenum,
    GLint);

typedef void
(*PFNGLEGLIMAGETARGETTEXTURE2DOES)(
    GLenum,
    GLeglImageOES);

typedef void (*PFNGLGENFRAMEBUFFERS)(
    GLsizei,
    GLuint *);

typedef void (*PFNGLDELETEFRAMEBUFFERS)(
    GLsizei,
    const GLuint *);

typedef void (*PFNGLBINDFRAMEBUFFER)(
    GLenum,
    GLuint);

typedef void
(*PFNGLFRAMEBUFFERTEXTURE2D)(
    GLenum,
    GLenum,
    GLenum,
    GLuint,
    GLint);

typedef GLenum
(*PFNGLCHECKFRAMEBUFFERSTATUS)(
    GLenum);

typedef void
(*PFNGLBLITFRAMEBUFFER)(
    GLint, GLint,
    GLint, GLint,
    GLint, GLint,
    GLint, GLint,
    GLbitfield,
    GLenum);

typedef void (*PFNGLFINISH)(void);
typedef GLenum (*PFNGLGETERROR)(void);

typedef GLuint (*PFNGLCREATESHADER)(GLenum);
typedef void (*PFNGLSHADERSOURCE)(
    GLuint, GLsizei, const char *const *, const GLint *);
typedef void (*PFNGLCOMPILESHADER)(GLuint);
typedef void (*PFNGLGETSHADERIV)(GLuint, GLenum, GLint *);
typedef void (*PFNGLGETSHADERINFOLOG)(
    GLuint, GLsizei, GLsizei *, char *);

typedef GLuint (*PFNGLCREATEPROGRAM)(void);
typedef void (*PFNGLATTACHSHADER)(GLuint, GLuint);
typedef void (*PFNGLLINKPROGRAM)(GLuint);
typedef void (*PFNGLGETPROGRAMIV)(GLuint, GLenum, GLint *);
typedef void (*PFNGLGETPROGRAMINFOLOG)(
    GLuint, GLsizei, GLsizei *, char *);
typedef void (*PFNGLUSEPROGRAM)(GLuint);
typedef void (*PFNGLDELETESHADER)(GLuint);
typedef void (*PFNGLDELETEPROGRAM)(GLuint);

typedef GLint (*PFNGLGETUNIFORMLOCATION)(
    GLuint, const char *);
typedef void (*PFNGLUNIFORM1I)(GLint, GLint);

typedef void (*PFNGLACTIVETEXTURE)(GLenum);
typedef void (*PFNGLVIEWPORT)(
    GLint, GLint, GLsizei, GLsizei);
typedef void (*PFNGLDRAWARRAYS)(
    GLenum, GLint, GLsizei);

typedef GLboolean (*PFNGLISENABLED)(GLenum);
typedef void (*PFNGLENABLE)(GLenum);
typedef void (*PFNGLDISABLE)(GLenum);

typedef void (*PFNGLCOLORMASK)(
    GLboolean,
    GLboolean,
    GLboolean,
    GLboolean);

typedef void (*PFNGLGENVERTEXARRAYS)(
    GLsizei,
    GLuint *);

typedef void (*PFNGLBINDVERTEXARRAY)(
    GLuint);

typedef void (*PFNGLDELETEVERTEXARRAYS)(
    GLsizei,
    const GLuint *);



static PFNGLGETINTEGERV *p_glGetIntegerv;
static PFNGLGENTEXTURES *p_glGenTextures;
static PFNGLDELETETEXTURES *p_glDeleteTextures;
static PFNGLBINDTEXTURE *p_glBindTexture;
static PFNGLTEXPARAMETERI *p_glTexParameteri;
static PFNGLEGLIMAGETARGETTEXTURE2DOES
    *p_glEGLImageTargetTexture2DOES;

static PFNGLGENFRAMEBUFFERS *p_glGenFramebuffers;
static PFNGLDELETEFRAMEBUFFERS *p_glDeleteFramebuffers;
static PFNGLBINDFRAMEBUFFER *p_glBindFramebuffer;
static PFNGLFRAMEBUFFERTEXTURE2D
    *p_glFramebufferTexture2D;
static PFNGLCHECKFRAMEBUFFERSTATUS
    *p_glCheckFramebufferStatus;
static PFNGLBLITFRAMEBUFFER *p_glBlitFramebuffer;

static PFNGLFINISH *p_glFinish;
static PFNGLGETERROR *p_glGetError;

static PFNGLCREATESHADER *p_glCreateShader;
static PFNGLSHADERSOURCE *p_glShaderSource;
static PFNGLCOMPILESHADER *p_glCompileShader;
static PFNGLGETSHADERIV *p_glGetShaderiv;
static PFNGLGETSHADERINFOLOG *p_glGetShaderInfoLog;

static PFNGLCREATEPROGRAM *p_glCreateProgram;
static PFNGLATTACHSHADER *p_glAttachShader;
static PFNGLLINKPROGRAM *p_glLinkProgram;
static PFNGLGETPROGRAMIV *p_glGetProgramiv;
static PFNGLGETPROGRAMINFOLOG *p_glGetProgramInfoLog;
static PFNGLUSEPROGRAM *p_glUseProgram;
static PFNGLDELETESHADER *p_glDeleteShader;
static PFNGLDELETEPROGRAM *p_glDeleteProgram;

static PFNGLGETUNIFORMLOCATION *p_glGetUniformLocation;
static PFNGLUNIFORM1I *p_glUniform1i;
static PFNGLACTIVETEXTURE *p_glActiveTexture;
static PFNGLVIEWPORT *p_glViewport;
static PFNGLDRAWARRAYS *p_glDrawArrays;

static PFNGLISENABLED *p_glIsEnabled;
static PFNGLENABLE *p_glEnable;
static PFNGLDISABLE *p_glDisable;
static PFNGLCOLORMASK *p_glColorMask;

static PFNGLGENVERTEXARRAYS *p_glGenVertexArrays;
static PFNGLBINDVERTEXARRAY *p_glBindVertexArray;
static PFNGLDELETEVERTEXARRAYS *p_glDeleteVertexArrays;

static GLuint swizzle_vao;


static GLuint swizzle_program;
static GLint swizzle_sampler = -1;


/* --------------------------------------------------------- */
/* AHardwareBuffer                                           */
/* --------------------------------------------------------- */

typedef int (*PFNAHBALLOCATE)(
    const AHardwareBuffer_Desc *,
    AHardwareBuffer **);

typedef void (*PFNAHBDESCRIBE)(
    const AHardwareBuffer *,
    AHardwareBuffer_Desc *);

typedef void (*PFNAHBRELEASE)(
    AHardwareBuffer *);

typedef const struct lsa_native_handle *
(*PFNAHBGETNATIVEHANDLE)(
    const AHardwareBuffer *);

static void *android_lib;

static PFNAHBALLOCATE p_AHardwareBuffer_allocate;
static PFNAHBDESCRIBE p_AHardwareBuffer_describe;
static PFNAHBRELEASE p_AHardwareBuffer_release;
static PFNAHBGETNATIVEHANDLE p_AHardwareBuffer_getNativeHandle;

/* --------------------------------------------------------- */
/* Runtime                                                   */
/* --------------------------------------------------------- */

static FILE *logfp;

static int listen_fd = -1;
static int client_fd = -1;

static AHardwareBuffer *capture_ahb;
static AHardwareBuffer_Desc capture_desc;

static EGLDisplay capture_display = EGL_NO_DISPLAY;
static EGLImageKHR capture_image = EGL_NO_IMAGE_KHR;

static GLuint capture_tex;
static GLuint src_fbo;
static GLuint dst_fbo;

/* --------------------------------------------------------- */

static void resolve_symbols(void)
{
    if (!real_transfer)
        real_transfer =
            (transfer_fn)dlsym(
                RTLD_NEXT,
                "virgl_renderer_transfer_read_iov");

    if (!real_info)
        real_info =
            (info_fn)dlsym(
                RTLD_NEXT,
                "virgl_renderer_resource_get_info");

#define EP(var, name) \
    do { \
        if (!(var)) \
            (var) = (__typeof__(var)) \
                dlsym(RTLD_DEFAULT, (name)); \
    } while (0)

    EP(p_eglGetCurrentDisplay,
       "epoxy_eglGetCurrentDisplay");

    EP(p_eglGetNativeClientBufferANDROID,
       "epoxy_eglGetNativeClientBufferANDROID");

    EP(p_eglCreateImageKHR,
       "epoxy_eglCreateImageKHR");

    EP(p_eglDestroyImageKHR,
       "epoxy_eglDestroyImageKHR");

    EP(p_eglGetError,
       "epoxy_eglGetError");

    EP(p_glGetIntegerv,
       "epoxy_glGetIntegerv");

    EP(p_glGenTextures,
       "epoxy_glGenTextures");

    EP(p_glDeleteTextures,
       "epoxy_glDeleteTextures");

    EP(p_glBindTexture,
       "epoxy_glBindTexture");

    EP(p_glTexParameteri,
       "epoxy_glTexParameteri");

    EP(p_glEGLImageTargetTexture2DOES,
       "epoxy_glEGLImageTargetTexture2DOES");

    EP(p_glGenFramebuffers,
       "epoxy_glGenFramebuffers");

    EP(p_glDeleteFramebuffers,
       "epoxy_glDeleteFramebuffers");

    EP(p_glBindFramebuffer,
       "epoxy_glBindFramebuffer");

    EP(p_glFramebufferTexture2D,
       "epoxy_glFramebufferTexture2D");

    EP(p_glCheckFramebufferStatus,
       "epoxy_glCheckFramebufferStatus");

    EP(p_glBlitFramebuffer,
       "epoxy_glBlitFramebuffer");

    EP(p_glFinish,
       "epoxy_glFinish");

    EP(p_glGetError,
       "epoxy_glGetError");

    EP(p_glCreateShader,
       "epoxy_glCreateShader");

    EP(p_glShaderSource,
       "epoxy_glShaderSource");

    EP(p_glCompileShader,
       "epoxy_glCompileShader");

    EP(p_glGetShaderiv,
       "epoxy_glGetShaderiv");

    EP(p_glGetShaderInfoLog,
       "epoxy_glGetShaderInfoLog");

    EP(p_glCreateProgram,
       "epoxy_glCreateProgram");

    EP(p_glAttachShader,
       "epoxy_glAttachShader");

    EP(p_glLinkProgram,
       "epoxy_glLinkProgram");

    EP(p_glGetProgramiv,
       "epoxy_glGetProgramiv");

    EP(p_glGetProgramInfoLog,
       "epoxy_glGetProgramInfoLog");

    EP(p_glUseProgram,
       "epoxy_glUseProgram");

    EP(p_glDeleteShader,
       "epoxy_glDeleteShader");

    EP(p_glDeleteProgram,
       "epoxy_glDeleteProgram");

    EP(p_glGetUniformLocation,
       "epoxy_glGetUniformLocation");

    EP(p_glUniform1i,
       "epoxy_glUniform1i");

    EP(p_glActiveTexture,
       "epoxy_glActiveTexture");

    EP(p_glViewport,
       "epoxy_glViewport");

    EP(p_glDrawArrays,
       "epoxy_glDrawArrays");

    EP(p_glIsEnabled,
       "epoxy_glIsEnabled");

    EP(p_glEnable,
       "epoxy_glEnable");

    EP(p_glDisable,
       "epoxy_glDisable");

    EP(p_glColorMask,
       "epoxy_glColorMask");

    EP(p_glGenVertexArrays,
       "epoxy_glGenVertexArrays");

    EP(p_glBindVertexArray,
       "epoxy_glBindVertexArray");

    EP(p_glDeleteVertexArrays,
       "epoxy_glDeleteVertexArrays");



#undef EP

    if (!android_lib)
        android_lib =
            dlopen(
                "/system/lib64/libandroid.so",
                RTLD_NOW | RTLD_LOCAL);

    if (android_lib) {
        if (!p_AHardwareBuffer_allocate)
            p_AHardwareBuffer_allocate =
                (PFNAHBALLOCATE)dlsym(
                    android_lib,
                    "AHardwareBuffer_allocate");

        if (!p_AHardwareBuffer_describe)
            p_AHardwareBuffer_describe =
                (PFNAHBDESCRIBE)dlsym(
                    android_lib,
                    "AHardwareBuffer_describe");

        if (!p_AHardwareBuffer_release)
            p_AHardwareBuffer_release =
                (PFNAHBRELEASE)dlsym(
                    android_lib,
                    "AHardwareBuffer_release");

        if (!p_AHardwareBuffer_getNativeHandle)
            p_AHardwareBuffer_getNativeHandle =
                (PFNAHBGETNATIVEHANDLE)dlsym(
                    android_lib,
                    "AHardwareBuffer_getNativeHandle");
    }
}

static int ready(void)
{
    return
        real_transfer &&
        real_info &&

        p_eglGetCurrentDisplay &&
        *p_eglGetCurrentDisplay &&

        p_eglGetNativeClientBufferANDROID &&
        *p_eglGetNativeClientBufferANDROID &&

        p_eglCreateImageKHR &&
        *p_eglCreateImageKHR &&

        p_eglGetError &&
        *p_eglGetError &&

        p_glGetIntegerv &&
        *p_glGetIntegerv &&

        p_glGenTextures &&
        *p_glGenTextures &&

        p_glBindTexture &&
        *p_glBindTexture &&

        p_glTexParameteri &&
        *p_glTexParameteri &&

        p_glEGLImageTargetTexture2DOES &&
        *p_glEGLImageTargetTexture2DOES &&

        p_glGenFramebuffers &&
        *p_glGenFramebuffers &&

        p_glBindFramebuffer &&
        *p_glBindFramebuffer &&

        p_glFramebufferTexture2D &&
        *p_glFramebufferTexture2D &&

        p_glCheckFramebufferStatus &&
        *p_glCheckFramebufferStatus &&

        p_glBlitFramebuffer &&
        *p_glBlitFramebuffer &&

        p_glFinish &&
        *p_glFinish &&

        p_glGetError &&
        *p_glGetError &&

        p_glCreateShader &&
        *p_glCreateShader &&

        p_glShaderSource &&
        *p_glShaderSource &&

        p_glCompileShader &&
        *p_glCompileShader &&

        p_glGetShaderiv &&
        *p_glGetShaderiv &&

        p_glGetShaderInfoLog &&
        *p_glGetShaderInfoLog &&

        p_glCreateProgram &&
        *p_glCreateProgram &&

        p_glAttachShader &&
        *p_glAttachShader &&

        p_glLinkProgram &&
        *p_glLinkProgram &&

        p_glGetProgramiv &&
        *p_glGetProgramiv &&

        p_glGetProgramInfoLog &&
        *p_glGetProgramInfoLog &&

        p_glUseProgram &&
        *p_glUseProgram &&

        p_glDeleteShader &&
        *p_glDeleteShader &&

        p_glDeleteProgram &&
        *p_glDeleteProgram &&

        p_glGetUniformLocation &&
        *p_glGetUniformLocation &&

        p_glUniform1i &&
        *p_glUniform1i &&

        p_glActiveTexture &&
        *p_glActiveTexture &&

        p_glViewport &&
        *p_glViewport &&

        p_glDrawArrays &&
        *p_glDrawArrays &&

        p_glIsEnabled &&
        *p_glIsEnabled &&

        p_glEnable &&
        *p_glEnable &&

        p_glDisable &&
        *p_glDisable &&

        p_glColorMask &&
        *p_glColorMask &&

        p_glGenVertexArrays &&
        *p_glGenVertexArrays &&

        p_glBindVertexArray &&
        *p_glBindVertexArray &&

        p_glDeleteVertexArrays &&
        *p_glDeleteVertexArrays &&

        p_AHardwareBuffer_allocate &&
        p_AHardwareBuffer_describe &&
        p_AHardwareBuffer_release &&
        p_AHardwareBuffer_getNativeHandle;
}

/* --------------------------------------------------------- */
/* Socket                                                    */
/* --------------------------------------------------------- */

static int create_listener(void)
{
    const char *path =
        getenv("LSA_GPU_TAP_SOCKET");

    if (!path || !*path)
        return -1;

    int fd =
        socket(
            AF_UNIX,
            SOCK_SEQPACKET | SOCK_CLOEXEC,
            0);

    if (fd < 0)
        return -1;

    struct sockaddr_un sa;
    memset(&sa, 0, sizeof(sa));

    sa.sun_family = AF_UNIX;

    if (strlen(path) >=
        sizeof(sa.sun_path)) {

        close(fd);
        return -1;
    }

    strcpy(
        sa.sun_path,
        path);

    unlink(path);

    if (bind(
            fd,
            (struct sockaddr *)&sa,
            sizeof(sa)) < 0) {

        fprintf(
            logfp,
            "bind failed: %s\n",
            strerror(errno));

        close(fd);
        return -1;
    }

    if (listen(fd, 2) < 0) {
        close(fd);
        return -1;
    }

    int fl =
        fcntl(
            fd,
            F_GETFL,
            0);

    if (fl >= 0)
        fcntl(
            fd,
            F_SETFL,
            fl | O_NONBLOCK);

    fprintf(
        logfp,
        "LSA Video idle/listening: %s\n",
        path);

    return fd;
}

static void try_accept(void)
{
    if (listen_fd < 0 ||
        client_fd >= 0)
        return;

    int fd =
        accept4(
            listen_fd,
            NULL,
            NULL,
            SOCK_NONBLOCK |
            SOCK_CLOEXEC);

    if (fd < 0)
        return;

    client_fd = fd;

    fprintf(
        logfp,
        "LSA Video capture ON client_fd=%d\n",
        client_fd);
}

/* --------------------------------------------------------- */
/* AHB capture buffer                                        */
/* --------------------------------------------------------- */

static void clear_capture(void)
{
    if (capture_image != EGL_NO_IMAGE_KHR &&
        p_eglDestroyImageKHR &&
        *p_eglDestroyImageKHR &&
        capture_display != EGL_NO_DISPLAY) {

        (*p_eglDestroyImageKHR)(
            capture_display,
            capture_image);
    }

    capture_image =
        EGL_NO_IMAGE_KHR;

    if (capture_tex &&
        p_glDeleteTextures &&
        *p_glDeleteTextures) {

        (*p_glDeleteTextures)(
            1,
            &capture_tex);
    }

    if (src_fbo &&
        p_glDeleteFramebuffers &&
        *p_glDeleteFramebuffers) {

        (*p_glDeleteFramebuffers)(
            1,
            &src_fbo);
    }

    if (dst_fbo &&
        p_glDeleteFramebuffers &&
        *p_glDeleteFramebuffers) {

        (*p_glDeleteFramebuffers)(
            1,
            &dst_fbo);
    }

    capture_tex = 0;
    src_fbo = 0;
    dst_fbo = 0;

    if (capture_ahb &&
        p_AHardwareBuffer_release) {

        p_AHardwareBuffer_release(
            capture_ahb);
    }

    capture_ahb = NULL;

    memset(
        &capture_desc,
        0,
        sizeof(capture_desc));
}

static int setup_capture(
    uint32_t width,
    uint32_t height)
{
    clear_capture();

    AHardwareBuffer_Desc req;
    memset(
        &req,
        0,
        sizeof(req));

    req.width = width;
    req.height = height;
    req.layers = 1;

    req.format =
        AHARDWAREBUFFER_FORMAT_R8G8B8A8_UNORM;

    req.usage =
        AHARDWAREBUFFER_USAGE_GPU_FRAMEBUFFER |
        AHARDWAREBUFFER_USAGE_VIDEO_ENCODE;

    int ar =
        p_AHardwareBuffer_allocate(
            &req,
            &capture_ahb);

    if (ar != 0 ||
        !capture_ahb) {

        fprintf(
            logfp,
            "AHB allocate FAIL ret=%d\n",
            ar);

        return -1;
    }

    p_AHardwareBuffer_describe(
        capture_ahb,
        &capture_desc);

    fprintf(
        logfp,
        "AHB allocated "
        "%ux%u format=%u "
        "stride_pixels=%u "
        "stride_bytes=%u "
        "usage=0x%016" PRIx64 "\n",
        capture_desc.width,
        capture_desc.height,
        capture_desc.format,
        capture_desc.stride,
        capture_desc.stride * 4,
        capture_desc.usage);

    capture_display =
        (*p_eglGetCurrentDisplay)();

    if (capture_display ==
        EGL_NO_DISPLAY) {

        fprintf(
            logfp,
            "AHB EGL FAIL: no current display\n");

        return -1;
    }

    EGLClientBuffer cb =
        (*p_eglGetNativeClientBufferANDROID)(
            capture_ahb);

    if (!cb) {
        fprintf(
            logfp,
            "eglGetNativeClientBufferANDROID FAIL\n");

        return -1;
    }

    const EGLint attrs[] = {
        EGL_NONE
    };

    capture_image =
        (*p_eglCreateImageKHR)(
            capture_display,
            EGL_NO_CONTEXT,
            EGL_NATIVE_BUFFER_ANDROID,
            cb,
            attrs);

    if (capture_image ==
        EGL_NO_IMAGE_KHR) {

        fprintf(
            logfp,
            "eglCreateImageKHR(AHB) FAIL "
            "egl=0x%04x\n",
            (*p_eglGetError)());

        return -1;
    }

    GLint old_tex = 0;

    (*p_glGetIntegerv)(
        GL_TEXTURE_BINDING_2D,
        &old_tex);

    (*p_glGenTextures)(
        1,
        &capture_tex);

    (*p_glBindTexture)(
        GL_TEXTURE_2D,
        capture_tex);

    (*p_glTexParameteri)(
        GL_TEXTURE_2D,
        GL_TEXTURE_MIN_FILTER,
        GL_NEAREST);

    (*p_glTexParameteri)(
        GL_TEXTURE_2D,
        GL_TEXTURE_MAG_FILTER,
        GL_NEAREST);

    (*p_glEGLImageTargetTexture2DOES)(
        GL_TEXTURE_2D,
        capture_image);

    GLenum ge =
        (*p_glGetError)();

    (*p_glBindTexture)(
        GL_TEXTURE_2D,
        (GLuint)old_tex);

    if (ge != GL_NO_ERROR) {
        fprintf(
            logfp,
            "AHB image->texture FAIL "
            "gl=0x%04x\n",
            ge);

        return -1;
    }

    (*p_glGenFramebuffers)(
        1,
        &src_fbo);

    (*p_glGenFramebuffers)(
        1,
        &dst_fbo);

    fprintf(
        logfp,
        "AHB EGL IMPORT PASS "
        "tex=%u\n",
        capture_tex);

    return 0;
}

/* --------------------------------------------------------- */
/* Identify backing FDs                                      */
/* --------------------------------------------------------- */

static int choose_pixel_fd(
    const struct lsa_native_handle *h,
    uint64_t *out_size)
{
    int best = -1;
    uint64_t best_size = 0;

    for (int i = 0;
         i < h->numFds;
         i++) {

        int fd = h->data[i];

        char proc[64];
        char target[256];

        snprintf(
            proc,
            sizeof(proc),
            "/proc/self/fd/%d",
            fd);

        ssize_t n =
            readlink(
                proc,
                target,
                sizeof(target) - 1);

        if (n >= 0)
            target[n] = 0;
        else
            strcpy(
                target,
                "?");

        struct stat st;
        memset(
            &st,
            0,
            sizeof(st));

        uint64_t size = 0;

        if (fstat(fd, &st) == 0)
            size =
                (uint64_t)st.st_size;

        fprintf(
            logfp,
            "AHB fd[%d]=%d "
            "target=%s size=%" PRIu64 "\n",
            i,
            fd,
            target,
            size);

        if (strstr(
                target,
                "/dmabuf:") ||
            strstr(
                target,
                "dmabuf")) {

            best = i;
            best_size = size;
            break;
        }

        if (size > best_size) {
            best = i;
            best_size = size;
        }
    }

    if (out_size)
        *out_size =
            best_size;

    return best;
}

/* --------------------------------------------------------- */
/* Send frame + all AHB native FDs                           */
/* --------------------------------------------------------- */

static int send_frame(
    struct virgl_renderer_resource_info *src,
    GLenum gl_error)
{
    const struct lsa_native_handle *h =
        p_AHardwareBuffer_getNativeHandle(
            capture_ahb);

    if (!h ||
        h->numFds <= 0 ||
        h->numFds > LSA_MAX_FDS) {

        fprintf(
            logfp,
            "bad AHB native handle\n");

        return -1;
    }

    uint64_t pixel_size = 0;

    int pixel_index =
        choose_pixel_fd(
            h,
            &pixel_size);

    if (pixel_index < 0) {
        fprintf(
            logfp,
            "could not identify pixel DMA-BUF\n");

        return -1;
    }

    struct lsa_video_frame frame;
    memset(
        &frame,
        0,
        sizeof(frame));

    frame.magic =
        LSA_VIDEO_MAGIC;

    frame.version =
        LSA_VIDEO_VERSION;

    frame.width =
        capture_desc.width;

    frame.height =
        capture_desc.height;

    frame.ahb_format =
        capture_desc.format;

    frame.stride_pixels =
        capture_desc.stride;

    frame.stride_bytes =
        capture_desc.stride * 4;

    frame.num_fds =
        (uint32_t)h->numFds;

    frame.pixel_fd_index =
        (uint32_t)pixel_index;

    frame.pixel_size =
        pixel_size;

    frame.source_fourcc =
        src->drm_fourcc;

    frame.source_stride =
        src->stride;

    frame.gl_error =
        gl_error;

    struct iovec iov = {
        .iov_base = &frame,
        .iov_len = sizeof(frame)
    };

    char control[
        CMSG_SPACE(
            sizeof(int) *
            LSA_MAX_FDS)];

    memset(
        control,
        0,
        sizeof(control));

    struct msghdr msg;
    memset(
        &msg,
        0,
        sizeof(msg));

    msg.msg_iov =
        &iov;

    msg.msg_iovlen =
        1;

    msg.msg_control =
        control;

    msg.msg_controllen =
        CMSG_SPACE(
            sizeof(int) *
            h->numFds);

    struct cmsghdr *cmsg =
        CMSG_FIRSTHDR(
            &msg);

    cmsg->cmsg_level =
        SOL_SOCKET;

    cmsg->cmsg_type =
        SCM_RIGHTS;

    cmsg->cmsg_len =
        CMSG_LEN(
            sizeof(int) *
            h->numFds);

    memcpy(
        CMSG_DATA(cmsg),
        h->data,
        sizeof(int) *
        h->numFds);

    ssize_t n =
        sendmsg(
            client_fd,
            &msg,
            MSG_NOSIGNAL);

    if (n !=
        (ssize_t)sizeof(frame)) {

        fprintf(
            logfp,
            "sendmsg frame FAIL: %s\n",
            n < 0
                ? strerror(errno)
                : "short write");

        return -1;
    }

    fprintf(
        logfp,
        "FRAME SENT "
        "%ux%u stride=%u "
        "fds=%d pixel_index=%d "
        "pixel_size=%" PRIu64 "\n",
        frame.width,
        frame.height,
        frame.stride_bytes,
        h->numFds,
        pixel_index,
        pixel_size);

    return 0;
}
static GLuint compile_shader(
    GLenum type,
    const char *source,
    const char *name)
{
    GLuint sh =
        (*p_glCreateShader)(type);

    if (!sh)
        return 0;

    (*p_glShaderSource)(
        sh,
        1,
        &source,
        NULL);

    (*p_glCompileShader)(sh);

    GLint ok = 0;

    (*p_glGetShaderiv)(
        sh,
        GL_COMPILE_STATUS,
        &ok);

    if (!ok) {
        char log[2048];
        GLsizei len = 0;

        memset(log, 0, sizeof(log));

        (*p_glGetShaderInfoLog)(
            sh,
            sizeof(log) - 1,
            &len,
            log);

        fprintf(
            logfp,
            "%s shader compile FAIL: %s\n",
            name,
            log);

        (*p_glDeleteShader)(sh);
        return 0;
    }

    return sh;
}

static int ensure_swizzle_program(void)
{
    if (swizzle_program)
        return 0;

    static const char *vs_source =
        "#version 300 es\n"
        "void main() {\n"
        "    vec2 p;\n"
        "    if (gl_VertexID == 0)\n"
        "        p = vec2(-1.0, -1.0);\n"
        "    else if (gl_VertexID == 1)\n"
        "        p = vec2( 3.0, -1.0);\n"
        "    else\n"
        "        p = vec2(-1.0,  3.0);\n"
        "    gl_Position = vec4(p, 0.0, 1.0);\n"
        "}\n";

    /*
     * AHB storage is RGBA.
     *
     * MTK AR24 expects memory bytes B,G,R,A.
     * Writing c.bgra into an RGBA8 render target therefore
     * produces exactly the byte layout the encoder expects.
     *
     * texelFetch + gl_FragCoord also preserves the same pixel
     * coordinates as the previous framebuffer blit.
     */
    static const char *fs_source =
        "#version 300 es\n"
        "precision highp float;\n"
        "uniform highp sampler2D u_src;\n"
        "layout(location = 0) out highp vec4 o_color;\n"
        "void main() {\n"
        "    ivec2 p = ivec2(gl_FragCoord.xy);\n"
        "    vec4 c = texelFetch(u_src, p, 0);\n"
        "    o_color = c.bgra;\n"
        "}\n";

    GLuint vs =
        compile_shader(
            GL_VERTEX_SHADER,
            vs_source,
            "vertex");

    if (!vs)
        return -1;

    GLuint fs =
        compile_shader(
            GL_FRAGMENT_SHADER,
            fs_source,
            "fragment");

    if (!fs) {
        (*p_glDeleteShader)(vs);
        return -1;
    }

    GLuint prog =
        (*p_glCreateProgram)();

    if (!prog) {
        (*p_glDeleteShader)(vs);
        (*p_glDeleteShader)(fs);
        return -1;
    }

    (*p_glAttachShader)(prog, vs);
    (*p_glAttachShader)(prog, fs);
    (*p_glLinkProgram)(prog);

    GLint ok = 0;

    (*p_glGetProgramiv)(
        prog,
        GL_LINK_STATUS,
        &ok);

    if (!ok) {
        char log[2048];
        GLsizei len = 0;

        memset(log, 0, sizeof(log));

        (*p_glGetProgramInfoLog)(
            prog,
            sizeof(log) - 1,
            &len,
            log);

        fprintf(
            logfp,
            "swizzle program link FAIL: %s\n",
            log);

        (*p_glDeleteProgram)(prog);
        (*p_glDeleteShader)(vs);
        (*p_glDeleteShader)(fs);

        return -1;
    }

    (*p_glDeleteShader)(vs);
    (*p_glDeleteShader)(fs);

    swizzle_sampler =
        (*p_glGetUniformLocation)(
            prog,
            "u_src");

    if (swizzle_sampler < 0) {
        fprintf(
            logfp,
            "swizzle sampler optimized out (debug shader)\n");
    }

    swizzle_program = prog;

    (*p_glGenVertexArrays)(
        1,
        &swizzle_vao);

    if (!swizzle_vao) {
        fprintf(
            logfp,
            "swizzle VAO creation FAIL\n");

        (*p_glDeleteProgram)(
            swizzle_program);

        swizzle_program = 0;
        return -1;
    }

    fprintf(
        logfp,
        "RGBA->BGRA GPU swizzle program READY "
        "program=%u vao=%u\n",
        swizzle_program,
        swizzle_vao);

    return 0;
}

/* --------------------------------------------------------- */
/* GPU blit                                                  */
/* --------------------------------------------------------- */

static int capture_one(
    struct virgl_renderer_resource_info *info)
{
    if (!capture_ahb) {
        fprintf(
            logfp,
            "SOURCE tex=%u "
            "%ux%u "
            "fourcc=0x%08x "
            "stride=%u\n",
            info->tex_id,
            info->width,
            info->height,
            (unsigned)info->drm_fourcc,
            info->stride);

        if (setup_capture(
                info->width,
                info->height) != 0)
            return -1;
    }

    if (ensure_swizzle_program() != 0) {
        fprintf(
            logfp,
            "GPU swizzle setup FAIL\n");

        return -1;
    }

    GLint old_draw = 0;
    GLint old_program = 0;
    GLint old_active_texture = 0;
    GLint old_tex0 = 0;
    GLint old_viewport[4] = {0};

    GLint old_vao = 0;
    GLint old_color_mask[4] = {1, 1, 1, 1};

    GLboolean old_blend;
    GLboolean old_cull;
    GLboolean old_depth;
    GLboolean old_stencil;
    GLboolean old_scissor;
    GLboolean old_discard;


    (*p_glGetIntegerv)(
        GL_DRAW_FRAMEBUFFER_BINDING,
        &old_draw);

    (*p_glGetIntegerv)(
        GL_CURRENT_PROGRAM,
        &old_program);

    (*p_glGetIntegerv)(
        GL_ACTIVE_TEXTURE,
        &old_active_texture);

    (*p_glGetIntegerv)(
        GL_VIEWPORT,
        old_viewport);

    (*p_glGetIntegerv)(
        GL_VERTEX_ARRAY_BINDING,
        &old_vao);

    (*p_glGetIntegerv)(
        GL_COLOR_WRITEMASK,
        old_color_mask);

    old_blend =
        (*p_glIsEnabled)(GL_BLEND);

    old_cull =
        (*p_glIsEnabled)(GL_CULL_FACE);

    old_depth =
        (*p_glIsEnabled)(GL_DEPTH_TEST);

    old_stencil =
        (*p_glIsEnabled)(GL_STENCIL_TEST);

    old_scissor =
        (*p_glIsEnabled)(GL_SCISSOR_TEST);

    old_discard =
        (*p_glIsEnabled)(GL_RASTERIZER_DISCARD);


    /*
     * Save texture unit 0 independently of whichever unit the
     * VirGL renderer currently has active.
     */
    (*p_glActiveTexture)(
        GL_TEXTURE0);

    (*p_glGetIntegerv)(
        GL_TEXTURE_BINDING_2D,
        &old_tex0);

    (*p_glBindFramebuffer)(
        GL_DRAW_FRAMEBUFFER,
        dst_fbo);

    (*p_glFramebufferTexture2D)(
        GL_DRAW_FRAMEBUFFER,
        GL_COLOR_ATTACHMENT0,
        GL_TEXTURE_2D,
        capture_tex,
        0);

    GLenum d =
        (*p_glCheckFramebufferStatus)(
            GL_DRAW_FRAMEBUFFER);

    if (d != GL_FRAMEBUFFER_COMPLETE) {
        fprintf(
            logfp,
            "swizzle destination FBO FAIL "
            "status=0x%04x\n",
            d);

        goto fail;
    }

    uint32_t w =
        info->width <
        capture_desc.width
            ? info->width
            : capture_desc.width;

    uint32_t h =
        info->height <
        capture_desc.height
            ? info->height
            : capture_desc.height;


    /*
     * VirGL owns this GL context, so do not trust inherited
     * raster state. Force a known state for our fullscreen pass.
     */
    (*p_glDisable)(GL_BLEND);
    (*p_glDisable)(GL_CULL_FACE);
    (*p_glDisable)(GL_DEPTH_TEST);
    (*p_glDisable)(GL_STENCIL_TEST);
    (*p_glDisable)(GL_SCISSOR_TEST);
    (*p_glDisable)(GL_RASTERIZER_DISCARD);

    (*p_glColorMask)(
        GL_TRUE,
        GL_TRUE,
        GL_TRUE,
        GL_TRUE);

    (*p_glBindVertexArray)(
        swizzle_vao);

    (*p_glBindTexture)(
        GL_TEXTURE_2D,
        info->tex_id);

    (*p_glUseProgram)(
        swizzle_program);

    if (swizzle_sampler >= 0) {
        (*p_glUniform1i)(
            swizzle_sampler,
            0);
    }

    (*p_glViewport)(
        0,
        0,
        (GLsizei)w,
        (GLsizei)h);

    (*p_glDrawArrays)(
        GL_TRIANGLES,
        0,
        3);

    /*
     * Still proof synchronization.
     * Native fence FD replaces this next.
     */
    (*p_glFinish)();

    GLenum ge =
        (*p_glGetError)();

    /*
     * Restore VirGL raster state.
     */
#define RESTORE_CAP(cap, enabled) \
    do { \
        if (enabled) \
            (*p_glEnable)(cap); \
        else \
            (*p_glDisable)(cap); \
    } while (0)

    RESTORE_CAP(GL_BLEND, old_blend);
    RESTORE_CAP(GL_CULL_FACE, old_cull);
    RESTORE_CAP(GL_DEPTH_TEST, old_depth);
    RESTORE_CAP(GL_STENCIL_TEST, old_stencil);
    RESTORE_CAP(GL_SCISSOR_TEST, old_scissor);
    RESTORE_CAP(GL_RASTERIZER_DISCARD, old_discard);

#undef RESTORE_CAP

    (*p_glColorMask)(
        old_color_mask[0] ? GL_TRUE : GL_FALSE,
        old_color_mask[1] ? GL_TRUE : GL_FALSE,
        old_color_mask[2] ? GL_TRUE : GL_FALSE,
        old_color_mask[3] ? GL_TRUE : GL_FALSE);

    (*p_glBindVertexArray)(
        (GLuint)old_vao);

    /*
     * Restore remaining state touched by the tap.
     */
    (*p_glUseProgram)(
        (GLuint)old_program);

    (*p_glBindTexture)(
        GL_TEXTURE_2D,
        (GLuint)old_tex0);

    (*p_glActiveTexture)(
        (GLenum)old_active_texture);

    (*p_glBindFramebuffer)(
        GL_DRAW_FRAMEBUFFER,
        (GLuint)old_draw);

    (*p_glViewport)(
        old_viewport[0],
        old_viewport[1],
        old_viewport[2],
        old_viewport[3]);

    fprintf(
        logfp,
        "AHB SWIZZLE "
        "RGBA->BGRA "
        "src_tex=%u "
        "%ux%u "
        "gl=0x%04x\n",
        info->tex_id,
        w,
        h,
        ge);

    if (ge != GL_NO_ERROR)
        return -1;

    return send_frame(
        info,
        ge);

fail:

#define RESTORE_CAP(cap, enabled) \
    do { \
        if (enabled) \
            (*p_glEnable)(cap); \
        else \
            (*p_glDisable)(cap); \
    } while (0)

    RESTORE_CAP(GL_BLEND, old_blend);
    RESTORE_CAP(GL_CULL_FACE, old_cull);
    RESTORE_CAP(GL_DEPTH_TEST, old_depth);
    RESTORE_CAP(GL_STENCIL_TEST, old_stencil);
    RESTORE_CAP(GL_SCISSOR_TEST, old_scissor);
    RESTORE_CAP(GL_RASTERIZER_DISCARD, old_discard);

#undef RESTORE_CAP

    (*p_glColorMask)(
        old_color_mask[0] ? GL_TRUE : GL_FALSE,
        old_color_mask[1] ? GL_TRUE : GL_FALSE,
        old_color_mask[2] ? GL_TRUE : GL_FALSE,
        old_color_mask[3] ? GL_TRUE : GL_FALSE);

    (*p_glBindVertexArray)(
        (GLuint)old_vao);

    (*p_glUseProgram)(
        (GLuint)old_program);

    (*p_glBindTexture)(
        GL_TEXTURE_2D,
        (GLuint)old_tex0);

    (*p_glActiveTexture)(
        (GLenum)old_active_texture);

    (*p_glBindFramebuffer)(
        GL_DRAW_FRAMEBUFFER,
        (GLuint)old_draw);

    (*p_glViewport)(
        old_viewport[0],
        old_viewport[1],
        old_viewport[2],
        old_viewport[3]);

    return -1;
}


/* --------------------------------------------------------- */
/* Constructor                                               */
/* --------------------------------------------------------- */

__attribute__((constructor))
static void init(void)
{
    const char *path =
        getenv(
            "LSA_GPU_TAP_LOG");

    if (!path || !*path)
        path = "/dev/null";

    logfp =
        fopen(
            path,
            "a");

    if (!logfp)
        logfp = stderr;

    setvbuf(
        logfp,
        NULL,
        _IOLBF,
        0);

    resolve_symbols();

    fprintf(
        logfp,
        "LSA Video AHB tap pid=%d\n",
        getpid());

    fprintf(
        logfp,
        "virgl transfer=%p "
        "info=%p "
        "AHB/EGL_ready=%s\n",
        real_transfer,
        real_info,
        ready()
            ? "YES"
            : "NO");

    listen_fd =
        create_listener();
}

/* --------------------------------------------------------- */
/* VirGL interposition                                       */
/* --------------------------------------------------------- */

int virgl_renderer_transfer_read_iov(
    uint32_t handle,
    uint32_t ctx_id,
    uint32_t level,
    uint32_t stride,
    uint32_t layer_stride,
    struct virgl_box *box,
    uint64_t offset,
    struct iovec *iov,
    int iovec_cnt)
{
    resolve_symbols();

    if (!real_transfer)
        return -ENOSYS;

    int ret =
        real_transfer(
            handle,
            ctx_id,
            level,
            stride,
            layer_stride,
            box,
            offset,
            iov,
            iovec_cnt);

    try_accept();

    if (client_fd < 0)
        return ret;

    if (!ready()) {
        fprintf(
            logfp,
            "capture requested but "
            "AHB/EGL not ready\n");

        close(client_fd);
        client_fd = -1;

        return ret;
    }

    struct virgl_renderer_resource_info info;
    memset(
        &info,
        0,
        sizeof(info));

    if (real_info(
            (int)handle,
            &info) != 0 ||
        !info.tex_id)
        return ret;

    if (capture_one(
            &info) == 0) {

        fprintf(
            logfp,
            "LSA Video one-frame capture complete\n");
    } else {
        fprintf(
            logfp,
            "LSA Video capture FAIL\n");
    }

    /*
     * Proof mode: one connection requests one frame.
     * Streaming mode will keep this open and use a ring.
     */
    close(client_fd);
    client_fd = -1;

    clear_capture();

    fprintf(
        logfp,
        "LSA Video capture OFF\n");

    return ret;
}

