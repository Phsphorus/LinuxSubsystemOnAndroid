#!/bin/sh
# Linux-side client policy for the Android GPUBridge VirGL endpoint.
#
# This is deliberately independent of the current DISPLAY value.  A process
# may be started on the VNC desktop and later point DISPLAY at :0, so deciding
# whether to expose VirGL when the shell starts would leave that process on
# llvmpipe.  With this policy present, any descendant that opens an OpenGL or
# EGL context can use the mounted Android GPUBridge socket.

if [ -S /mnt/gpubridge/.virgl_test ]; then
    export VTEST_SOCKET_NAME=/mnt/gpubridge/.virgl_test
    # This selects Mesa's software-loader frontend.  `virpipe` forwards GPU
    # commands to Android over VTEST; it is not llvmpipe rendering.
    export LIBGL_ALWAYS_SOFTWARE=1
    export GALLIUM_DRIVER=virpipe
    export MESA_GL_VERSION_OVERRIDE=4.1COMPAT
    export MESA_GLSL_VERSION_OVERRIDE=410
fi
