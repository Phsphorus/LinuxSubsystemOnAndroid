#!/system/bin/sh
# Normalization shared by the full Bash framework and the POSIX deployment
# bootstrap.  Keep this file free of framework registry calls so it can run
# before RootStart, a rootfs, or the Termux package set exist.

lsa_architecture_normalize() {
    lsa_arch_raw="$(printf '%s' "${1:-unknown}" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
    case "$lsa_arch_raw" in
        aarch64|arm64|arm64-v8a|*aarch64*) printf '%s\n' arm64 ;;
        armv8l|armv7l|armv7|armv7a|armeabi-v7a|armhf|armel|arm|*armv7*|*'arm,'*) printf '%s\n' armv7 ;;
        x86_64|amd64|*x86-64*|*amd64*) printf '%s\n' x86_64 ;;
        i386|i486|i586|i686|x86|*80386*|*i686*|*'x86,'*) printf '%s\n' x86 ;;
        *) printf '%s\n' unknown ;;
    esac
}

lsa_architecture_normalize_android_abis() {
    lsa_arch_abis="${1:-${LSA_ARCH_ANDROID_ABI_RAW:-unknown}},${2:-${LSA_ARCH_ANDROID_ABILIST_RAW:-unknown}}"
    lsa_arch_old_ifs="$IFS"
    IFS=,
    set -- $lsa_arch_abis
    IFS="$lsa_arch_old_ifs"
    for lsa_arch_candidate in "$@"; do
        lsa_arch_normalized="$(lsa_architecture_normalize "$lsa_arch_candidate")"
        [ "$lsa_arch_normalized" = unknown ] || {
            printf '%s\n' "$lsa_arch_normalized"
            return 0
        }
    done
    printf '%s\n' unknown
}

lsa_architecture_debian_arch() {
    case "$(lsa_architecture_normalize "${1:-unknown}")" in
        arm64) printf '%s\n' arm64 ;;
        armv7) printf '%s\n' armhf ;;
        x86_64) printf '%s\n' amd64 ;;
        x86) printf '%s\n' i386 ;;
        *) printf '%s\n' unknown ;;
    esac
}
