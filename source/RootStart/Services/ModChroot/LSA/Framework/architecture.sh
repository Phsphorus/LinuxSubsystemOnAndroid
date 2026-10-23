#!/data/data/com.termux/files/usr/bin/bash
# Architecture discovery is deliberately split by execution domain.  Android
# ABI, kernel, Termux userspace, and the Linux rootfs may not be interchangeable.

LSA_ARCH_ANDROID_ABI_RAW="unknown"
LSA_ARCH_ANDROID_ABILIST_RAW="unknown"
LSA_ARCH_KERNEL_RAW="unknown"
LSA_ARCH_TERMUX_RAW="unknown"
LSA_ARCH_ROOTFS_RAW="unknown"
LSA_ARCH_ANDROID_ABI="unknown"
LSA_ARCH_KERNEL="unknown"
LSA_ARCH_TERMUX="unknown"
LSA_ARCH_ROOTFS="unknown"

# shellcheck source=/dev/null
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)/architecture-normalize.sh"

lsa_architecture_add_axis_capabilities() {
    local axis="$1" normalized="$2"
    [ "$normalized" = unknown ] && return 0
    lsa_capability_add "capability.arch.$axis.known" framework.architecture
    lsa_capability_add "capability.arch.$axis.$normalized" framework.architecture
}

lsa_architecture_detect() {
    local termux_dpkg rootfs_dpkg
    LSA_ARCH_ANDROID_ABI_RAW="$(getprop ro.product.cpu.abi 2>/dev/null || printf unknown)"
    LSA_ARCH_ANDROID_ABILIST_RAW="$(getprop ro.product.cpu.abilist 2>/dev/null || printf unknown)"
    LSA_ARCH_KERNEL_RAW="$(uname -m 2>/dev/null || printf unknown)"

    termux_dpkg="${LSA_TERMUX_PREFIX:-/data/data/com.termux/files/usr}/bin/dpkg"
    if [ -x "$termux_dpkg" ]; then
        LSA_ARCH_TERMUX_RAW="$("$termux_dpkg" --print-architecture 2>/dev/null || printf unknown)"
    else
        LSA_ARCH_TERMUX_RAW="${LSA_ARCH_KERNEL_RAW:-unknown}"
    fi

    rootfs_dpkg="$LSA_CHROOT_DIR/usr/bin/dpkg"
    if [ "$(id -u)" = 0 ] && [ -x "$rootfs_dpkg" ]; then
        LSA_ARCH_ROOTFS_RAW="$(chroot "$LSA_CHROOT_DIR" /usr/bin/dpkg --print-architecture 2>/dev/null || printf unknown)"
    elif [ -r "$LSA_CHROOT_DIR/etc/dpkg/arch" ]; then
        LSA_ARCH_ROOTFS_RAW="$(head -n 1 "$LSA_CHROOT_DIR/etc/dpkg/arch" 2>/dev/null || printf unknown)"
    else
        LSA_ARCH_ROOTFS_RAW="unknown"
    fi

    LSA_ARCH_ANDROID_ABI="$(lsa_architecture_normalize_android_abis)"
    LSA_ARCH_KERNEL="$(lsa_architecture_normalize "$LSA_ARCH_KERNEL_RAW")"
    LSA_ARCH_TERMUX="$(lsa_architecture_normalize "$LSA_ARCH_TERMUX_RAW")"
    LSA_ARCH_ROOTFS="$(lsa_architecture_normalize "$LSA_ARCH_ROOTFS_RAW")"

    lsa_capability_add capability.architecture.detected framework.architecture
    lsa_architecture_add_axis_capabilities android "$LSA_ARCH_ANDROID_ABI"
    lsa_architecture_add_axis_capabilities kernel "$LSA_ARCH_KERNEL"
    lsa_architecture_add_axis_capabilities termux "$LSA_ARCH_TERMUX"
    lsa_architecture_add_axis_capabilities rootfs "$LSA_ARCH_ROOTFS"
}

lsa_architecture_binary_machine() {
    local path="$1" output="" readelf_cmd file_cmd
    [ -f "$path" ] || return 1
    readelf_cmd="${LSA_TERMUX_PREFIX:-/data/data/com.termux/files/usr}/bin/readelf"
    file_cmd="${LSA_TERMUX_PREFIX:-/data/data/com.termux/files/usr}/bin/file"
    [ -x "$readelf_cmd" ] || readelf_cmd="$(command -v readelf 2>/dev/null || true)"
    [ -x "$file_cmd" ] || file_cmd="$(command -v file 2>/dev/null || true)"
    if [ -n "$readelf_cmd" ]; then
        output="$("$readelf_cmd" -h "$path" 2>/dev/null | awk -F: '/Machine:/{gsub(/^ +/, "", $2); print $2; exit}')"
    fi
    if [ -z "$output" ] && [ -n "$file_cmd" ]; then
        output="$("$file_cmd" -b "$path" 2>/dev/null)"
    fi
    [ -n "$output" ] || return 1
    lsa_architecture_normalize "$output"
}

lsa_architecture_register_binary() {
    local id="$1" path="$2" expected="$3" detected
    detected="$(lsa_architecture_binary_machine "$path" 2>/dev/null || printf unknown)"
    LSA_BINARY_ARCH_PATH["$id"]="$path"
    LSA_BINARY_ARCH_EXPECTED["$id"]="$expected"
    LSA_BINARY_ARCH_DETECTED["$id"]="$detected"
    if [ "$detected" = unknown ]; then
        LSA_BINARY_ARCH_RESULT["$id"]="UNSUPPORTED"
        return 1
    fi
    if [ "$expected" != unknown ] && [ "$detected" != "$expected" ]; then
        LSA_BINARY_ARCH_RESULT["$id"]="UNSUPPORTED"
        return 1
    fi
    LSA_BINARY_ARCH_RESULT["$id"]="AVAILABLE"
    return 0
}

lsa_architecture_termux_vulkan_icd() {
    local directory="${LSA_TERMUX_PREFIX:-/data/data/com.termux/files/usr}/share/vulkan/icd.d"
    local suffix suffixes candidate count=0 selected=""
    case "$LSA_ARCH_TERMUX" in
        arm64) suffixes='aarch64 arm64 arm64-v8a' ;;
        armv7) suffixes='armv7a armv7 armeabi-v7a' ;;
        x86) suffixes='x86 i686' ;;
        x86_64) suffixes='x86_64 amd64' ;;
        *) suffixes='' ;;
    esac
    for suffix in $suffixes; do
        candidate="$directory/wrapper_icd.$suffix.json"
        [ -f "$candidate" ] && { printf '%s' "$candidate"; return 0; }
    done
    for candidate in "$directory"/wrapper_icd.*.json; do
        [ -f "$candidate" ] || continue
        selected="$candidate"
        count=$((count + 1))
    done
    [ "$count" = 1 ] || return 1
    printf '%s' "$selected"
}

lsa_architecture_android_system_library() {
    local library="$1" directory
    case "$LSA_ARCH_ANDROID_ABI" in
        arm64|x86_64) directories='/system/lib64 /system/lib' ;;
        armv7|x86) directories='/system/lib /system/lib64' ;;
        *) directories='/system/lib64 /system/lib' ;;
    esac
    for directory in $directories; do
        [ -e "$directory/$library" ] && { printf '%s' "$directory/$library"; return 0; }
    done
    return 1
}

lsa_architecture_write_state() {
    {
        printf 'axis\traw\tnormalized\n'
        printf 'android_abi\t%s\t%s\n' "$(lsa__safe_field "$LSA_ARCH_ANDROID_ABI_RAW")" "$LSA_ARCH_ANDROID_ABI"
        printf 'android_abilist\t%s\t%s\n' "$(lsa__safe_field "$LSA_ARCH_ANDROID_ABILIST_RAW")" "(list)"
        printf 'kernel\t%s\t%s\n' "$(lsa__safe_field "$LSA_ARCH_KERNEL_RAW")" "$LSA_ARCH_KERNEL"
        printf 'termux_userspace\t%s\t%s\n' "$(lsa__safe_field "$LSA_ARCH_TERMUX_RAW")" "$LSA_ARCH_TERMUX"
        printf 'linux_rootfs\t%s\t%s\n' "$(lsa__safe_field "$LSA_ARCH_ROOTFS_RAW")" "$LSA_ARCH_ROOTFS"
    } >"$LSA_RUNTIME_DIR/architecture.tsv"
    {
        printf 'id\tpath\texpected\tdetected\tresult\n'
        local id
        for id in "${!LSA_BINARY_ARCH_PATH[@]}"; do
            printf '%s\t%s\t%s\t%s\t%s\n' "$id" \
                "$(lsa__safe_field "${LSA_BINARY_ARCH_PATH[$id]}")" \
                "${LSA_BINARY_ARCH_EXPECTED[$id]}" "${LSA_BINARY_ARCH_DETECTED[$id]}" \
                "${LSA_BINARY_ARCH_RESULT[$id]}"
        done | sort
    } >"$LSA_RUNTIME_DIR/binaries.tsv"
}
