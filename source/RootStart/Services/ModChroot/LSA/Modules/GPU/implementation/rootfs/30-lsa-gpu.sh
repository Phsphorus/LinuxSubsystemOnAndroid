# Make the Android GPUBridge client policy available to every Bash login shell
# in the disposable Debian rootfs.  Graphical sessions source the same file
# explicitly because they do not necessarily execute /etc/profile.
[ -r /usr/local/lib/lsa/gpu/lsa-gpu-env.sh ] && . /usr/local/lib/lsa/gpu/lsa-gpu-env.sh
