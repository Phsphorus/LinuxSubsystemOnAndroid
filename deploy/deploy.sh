#!/system/bin/sh
# LSA release deployer.  This is copied verbatim to LSADeploy/deploy.sh by
# tools/build_deploy_package.ps1.  It deliberately contains no phone model
# policy and never imports runtime state or an authentication secret.
set -eu

SELF_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
MODE="${1:-full}"

case "$MODE" in
    full|framework-only|resume-rootfs) ;;
    *)
        printf '%s\n' "usage: $0 [full|framework-only|resume-rootfs]" >&2
        exit 2
        ;;
esac

TERMUX_PACKAGE="${LSA_TERMUX_PACKAGE:-com.termux}"
TERMUX_HOME="/data/data/$TERMUX_PACKAGE/files/home"
TERMUX_PREFIX="/data/data/$TERMUX_PACKAGE/files/usr"
ROOT_DST="/data/local/RootStart"
NONROOT_DST="$TERMUX_HOME/NonRootStart"
ROOTFS="${LSA_ROOTFS:-/data/local/linux}"
BACKUP_ROOT="/data/local/LSADeploy-backups"
PREINSTALL_STATE="/data/local/LSADeploy-state"
ARCH_HELPER="$SELF_DIR/bootstrap/architecture-normalize.sh"
PAYLOAD_MANIFEST="$SELF_DIR/manifest/PAYLOAD-SHA256SUMS"
APPS_MANIFEST="$SELF_DIR/manifest/APPS.tsv"
STAMP="$(date +%Y%m%d-%H%M%S)"

note() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
warn() { printf '%s WARNING: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }
die() { printf '%s ERROR: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "deploy.sh must be run from an Android root shell."
[ -r "$ARCH_HELPER" ] || die "release bootstrap architecture helper is missing."
# shellcheck source=/dev/null
. "$ARCH_HELPER"

find_tool() {
    for lsa_tool_candidate in "$@"; do
        [ -n "$lsa_tool_candidate" ] || continue
        if [ -x "$lsa_tool_candidate" ]; then
            printf '%s\n' "$lsa_tool_candidate"
            return 0
        fi
    done
    return 1
}

shell_quote() {
    # Return one POSIX-shell-safe argument for the command interpreted by su.
    printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

run_as_termux() {
    lsa_termux_command="$1"
    lsa_termux_quoted="$(shell_quote "$lsa_termux_command")"
    su "$TERMUX_UID" -c "export HOME=$(shell_quote "$TERMUX_HOME") PREFIX=$(shell_quote "$TERMUX_PREFIX") PATH=$(shell_quote "$TERMUX_PREFIX/bin:/system/bin:/system/xbin"); exec /system/bin/sh -c $lsa_termux_quoted"
}

sha256_file() {
    "$SHA256_BIN" "$1" | awk '{print $1}'
}

write_preflight() {
    mkdir -p "$PREINSTALL_STATE"
    chmod 700 "$PREINSTALL_STATE" 2>/dev/null || true
    {
        printf 'field\tvalue\n'
        printf 'release_version\t%s\n' "$(tr -d '\r\n' < "$SELF_DIR/VERSION" 2>/dev/null || printf unknown)"
        printf 'root_uid\t%s\n' "$(id -u)"
        printf 'android_version\t%s\n' "$(getprop ro.build.version.release 2>/dev/null || printf unknown)"
        printf 'android_sdk\t%s\n' "$(getprop ro.build.version.sdk 2>/dev/null || printf unknown)"
        printf 'android_abi_raw\t%s\n' "${ANDROID_ABI_RAW:-unknown}"
        printf 'android_abi\t%s\n' "${ANDROID_ABI:-unknown}"
        printf 'kernel_arch_raw\t%s\n' "${KERNEL_ARCH_RAW:-unknown}"
        printf 'kernel_arch\t%s\n' "${KERNEL_ARCH:-unknown}"
        printf 'termux_package\t%s\n' "$TERMUX_PACKAGE"
        printf 'termux_uid_gid\t%s:%s\n' "${TERMUX_UID:-unknown}" "${TERMUX_GID:-unknown}"
        printf 'termux_prefix\t%s\n' "$TERMUX_PREFIX"
        printf 'termux_home\t%s\n' "$TERMUX_HOME"
        printf 'termux_arch_raw\t%s\n' "${TERMUX_ARCH_RAW:-unknown}"
        printf 'termux_arch\t%s\n' "${TERMUX_ARCH:-unknown}"
        printf 'debian_arch\t%s\n' "${DEBIAN_ARCH:-unknown}"
        printf 'rootfs\t%s\n' "$ROOTFS"
        printf 'rootfs_state\t%s\n' "$(rootfs_state)"
        printf 'rootstart_present\t%s\n' "$(test -e "$ROOT_DST" && printf yes || printf no)"
        printf 'nonrootstart_present\t%s\n' "$(test -e "$NONROOT_DST" && printf yes || printf no)"
        printf 'active_session\t%s\n' "$(active_session && printf yes || printf no)"
        df -k /data 2>/dev/null | awk 'NR == 2 { printf "free_data_kib\\t%s\\n", $4 }'
    } > "$PREINSTALL_STATE/preflight-$STAMP.tsv"
    note "stage 0 preflight: $PREINSTALL_STATE/preflight-$STAMP.tsv"
}

rootfs_state() {
    [ -x "$ROOTFS/bin/sh" ] && [ -r "$ROOTFS/var/lib/dpkg/status" ] && {
        printf COMPLETE
        return 0
    }
    [ -d "$ROOTFS" ] || { printf NOT_PRESENT; return 0; }
    [ -d "$ROOTFS/debootstrap" ] && { printf BOOTSTRAPPING; return 0; }
    [ "$(find "$ROOTFS" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l | tr -d ' ')" = 0 ] && {
        printf NOT_PRESENT
        return 0
    }
    printf FAILED
}

active_session() {
    grep -Eq '[[:space:]]/data/local/linux([[:space:]]|/)' /proc/mounts 2>/dev/null && return 0
    if [ -r "$ROOT_DST/Services/ModChroot/runtime/chroot.pid" ]; then
        lsa_existing_pid="$(tr -dc '0-9' < "$ROOT_DST/Services/ModChroot/runtime/chroot.pid")"
        [ -n "$lsa_existing_pid" ] && kill -0 "$lsa_existing_pid" 2>/dev/null && return 0
    fi
    if [ -r "$NONROOT_DST/Services/.supervisor/switch-watcher.pid" ]; then
        lsa_existing_pid="$(tr -dc '0-9' < "$NONROOT_DST/Services/.supervisor/switch-watcher.pid")"
        [ -n "$lsa_existing_pid" ] && kill -0 "$lsa_existing_pid" 2>/dev/null && return 0
    fi
    return 1
}

detect_target() {
    pm path "$TERMUX_PACKAGE" >/dev/null 2>&1 || die "supported Termux package $TERMUX_PACKAGE is not installed."
    [ -d "$TERMUX_HOME" ] || die "Termux home is missing: $TERMUX_HOME"
    [ -d "$TERMUX_PREFIX" ] || die "Termux prefix is missing: $TERMUX_PREFIX"
    TERMUX_UID="$(stat -c %u "$TERMUX_HOME" 2>/dev/null || toybox stat -c %u "$TERMUX_HOME")"
    TERMUX_GID="$(stat -c %g "$TERMUX_HOME" 2>/dev/null || toybox stat -c %g "$TERMUX_HOME")"
    case "$TERMUX_UID:$TERMUX_GID" in *[!0-9:]*|:) die "unable to resolve numeric Termux UID:GID" ;; esac

    ANDROID_ABI_RAW="$(getprop ro.product.cpu.abi 2>/dev/null || printf unknown)"
    ANDROID_ABILIST_RAW="$(getprop ro.product.cpu.abilist 2>/dev/null || printf unknown)"
    KERNEL_ARCH_RAW="$(uname -m 2>/dev/null || printf unknown)"
    ANDROID_ABI="$(lsa_architecture_normalize_android_abis "$ANDROID_ABI_RAW" "$ANDROID_ABILIST_RAW")"
    KERNEL_ARCH="$(lsa_architecture_normalize "$KERNEL_ARCH_RAW")"
    TERMUX_ARCH_RAW="$("$TERMUX_PREFIX/bin/dpkg" --print-architecture 2>/dev/null || printf unknown)"
    TERMUX_ARCH="$(lsa_architecture_normalize "$TERMUX_ARCH_RAW")"
    DEBIAN_ARCH="$(lsa_architecture_debian_arch "$TERMUX_ARCH")"
    TAR_BIN="$(find_tool "$TERMUX_PREFIX/bin/tar" /system/bin/tar "$(command -v tar 2>/dev/null || true)")" || die "no usable tar command found"
    SHA256_BIN="$(find_tool "$TERMUX_PREFIX/bin/sha256sum" /system/bin/sha256sum "$(command -v sha256sum 2>/dev/null || true)")" || die "no usable sha256sum command found"
}

verify_release() {
    [ -f "$SELF_DIR/VERSION" ] || die "release VERSION is missing"
    [ -f "$PAYLOAD_MANIFEST" ] || die "release checksum manifest is missing"
    [ -f "$APPS_MANIFEST" ] || die "release app manifest is missing"
    while IFS=' ' read -r lsa_expected lsa_relative; do
        # Build hosts may have produced CRLF manifests.  Package paths and
        # hashes are logical release data, not host-text-format data.
        lsa_expected="$(printf '%s' "$lsa_expected" | tr -d '\r')"
        lsa_relative="$(printf '%s' "$lsa_relative" | tr -d '\r')"
        [ -n "$lsa_expected" ] || continue
        lsa_path="$SELF_DIR/$lsa_relative"
        [ -f "$lsa_path" ] || die "checksum member missing: $lsa_relative"
        lsa_actual="$(sha256_file "$lsa_path")"
        [ "$lsa_actual" = "$lsa_expected" ] || die "checksum mismatch: $lsa_relative"
    done < "$PAYLOAD_MANIFEST"
    note "release checksum validation passed"
}

backup_existing_payload() {
    active_session && die "an active LSA session exists; stop it before deployment"
    DEPLOY_BACKUP="$BACKUP_ROOT/$STAMP"
    mkdir -p "$DEPLOY_BACKUP"
    chmod 700 "$BACKUP_ROOT" "$DEPLOY_BACKUP" 2>/dev/null || true
    PRESERVED_LEDGER="$DEPLOY_BACKUP/backend-rejections.tsv"
    if [ -r "$ROOT_DST/Services/ModChroot/state/backend-rejections.tsv" ]; then
        cp "$ROOT_DST/Services/ModChroot/state/backend-rejections.tsv" "$PRESERVED_LEDGER"
        chmod 600 "$PRESERVED_LEDGER"
    fi
    if [ -e "$ROOT_DST" ]; then
        note "preserving RootStart at $DEPLOY_BACKUP/RootStart"
        mv "$ROOT_DST" "$DEPLOY_BACKUP/RootStart" || die "unable to preserve existing RootStart"
    fi
    if [ -e "$NONROOT_DST" ]; then
        NONROOT_BACKUP="$TERMUX_HOME/.lsa-deploy-backups/$STAMP"
        mkdir -p "$NONROOT_BACKUP"
        chown "$TERMUX_UID:$TERMUX_GID" "$TERMUX_HOME/.lsa-deploy-backups" "$NONROOT_BACKUP" 2>/dev/null || true
        note "preserving NonRootStart at $NONROOT_BACKUP/NonRootStart"
        mv "$NONROOT_DST" "$NONROOT_BACKUP/NonRootStart" || die "unable to preserve existing NonRootStart"
    fi
}

install_payload() {
    backup_existing_payload
    note "stage 1: extracting framework and owned payload trees"
    "$TAR_BIN" -xf "$SELF_DIR/payload/RootStart.tar" -C /data/local || die "RootStart extraction failed"
    "$TAR_BIN" -xf "$SELF_DIR/payload/NonRootStart.tar" -C "$TERMUX_HOME" || die "NonRootStart extraction failed"
    [ -x "$ROOT_DST/Services/ModChroot/LSA/Framework/lsectl" ] || die "framework extraction verification failed"
    [ -x "$NONROOT_DST/NRS.sh" ] || die "NonRootStart extraction verification failed"
    chown -R 0:0 "$ROOT_DST"
    chown -R "$TERMUX_UID:$TERMUX_GID" "$NONROOT_DST"
    chmod 755 "$ROOT_DST/RST.sh" "$ROOT_DST/Services/ModChroot/ModChroot.sh" "$ROOT_DST/Services/ModChroot/LSA/Framework/lsectl" "$NONROOT_DST/NRS.sh"
    DEPLOY_RUNTIME="$ROOT_DST/tmp/deployments/$STAMP"
    mkdir -p "$DEPLOY_RUNTIME"
    chmod 700 "$ROOT_DST/tmp" "$ROOT_DST/tmp/deployments" "$DEPLOY_RUNTIME" 2>/dev/null || true
    cp "$PREINSTALL_STATE/preflight-$STAMP.tsv" "$DEPLOY_RUNTIME/preflight.tsv" 2>/dev/null || true
}

bootstrap_termux() {
    note "stage 2: installing generic Termux prerequisites as UID $TERMUX_UID"
    [ -x "$TERMUX_PREFIX/bin/pkg" ] || die "Termux package manager is missing from $TERMUX_PREFIX/bin"
    if ! run_as_termux "pkg install -y bash python debootstrap termux-api iw"; then
        warn "generic Termux bootstrap reported a failure; continuing to framework diagnostics"
    fi
    [ -x "$TERMUX_PREFIX/bin/bash" ] || die "Termux Bash is required for the framework"
    [ -x "$TERMUX_PREFIX/bin/python" ] || die "Termux Python is required for LSA-owned services"
    if [ "$MODE" = full ] && [ "$(rootfs_state)" != COMPLETE ]; then
        [ -x "$TERMUX_PREFIX/bin/debootstrap" ] || die "debootstrap is required to create the missing rootfs"
    fi
}

provision_root_iw() {
    # Android root cannot execute Termux-private binaries under SELinux
    # Enforcing, while the Termux app UID correctly lacks CAP_NET_ADMIN.  Copy
    # only the standard iw executable and the libnl libraries it links against
    # through a UID-owned read pipe into a root-owned LSA directory.  This is a
    # generic package/bootstrap step, not a device or chipset workaround.
    lsa_iw_dst="$ROOT_DST/Tools/iw"
    lsa_iw_lib="$lsa_iw_dst/lib"
    note "stage 2: provisioning root-owned standard iw for Wireless qualification"
    if ! run_as_termux "test -r '$TERMUX_PREFIX/bin/iw' -a -r '$TERMUX_PREFIX/lib/libnl-3.so' -a -r '$TERMUX_PREFIX/lib/libnl-genl-3.so'"; then
        warn "Termux iw/libnl is unavailable; Wireless nl80211 qualification will remain diagnostic-only"
        return 0
    fi
    mkdir -p "$lsa_iw_lib"
    chown 0:0 "$ROOT_DST/Tools" "$lsa_iw_dst" "$lsa_iw_lib"
    chmod 755 "$ROOT_DST/Tools" "$lsa_iw_dst" "$lsa_iw_lib"
    for lsa_iw_member in \
        bin/iw \
        lib/libnl-3.so \
        lib/libnl-genl-3.so
    do
        lsa_iw_source="$TERMUX_PREFIX/$lsa_iw_member"
        case "$lsa_iw_member" in
            bin/iw) lsa_iw_target="$lsa_iw_dst/iw" ;;
            lib/*) lsa_iw_target="$lsa_iw_lib/${lsa_iw_member##*/}" ;;
            *) die "internal invalid iw member" ;;
        esac
        # The source string is constructed only from fixed package members and
        # a validated Termux prefix; shell_quote prevents it changing the
        # command parsed by su.
        su "$TERMUX_UID" -c "exec /system/bin/cat $(shell_quote "$lsa_iw_source")" > "$lsa_iw_target" || {
            warn "cannot materialise Termux $lsa_iw_member for root-owned iw"
            rm -f "$lsa_iw_target"
            return 0
        }
    done
    chown -R 0:0 "$lsa_iw_dst"
    chmod 755 "$lsa_iw_dst/iw"
    chmod 644 "$lsa_iw_lib/libnl-3.so" "$lsa_iw_lib/libnl-genl-3.so"
    case "$TERMUX_ARCH" in
        arm64|armv7)
            lsa_helper_asset="$SELF_DIR/bootstrap/wireless/lsa-nl80211-$TERMUX_ARCH"
            if [ -r "$lsa_helper_asset" ]; then
                cp "$lsa_helper_asset" "$lsa_iw_dst/lsa-nl80211"
                chown 0:0 "$lsa_iw_dst/lsa-nl80211"
                chmod 700 "$lsa_iw_dst/lsa-nl80211"
            else
                warn "no generic nl80211 frame helper was shipped for $TERMUX_ARCH"
            fi
            ;;
        *)
            warn "generic nl80211 frame helper is not shipped for Termux architecture $TERMUX_ARCH"
            ;;
    esac
    if LD_LIBRARY_PATH="$lsa_iw_lib" "$lsa_iw_dst/iw" dev >/dev/null 2>&1; then
        {
            printf 'termux_arch\t%s\n' "$TERMUX_ARCH"
            printf 'iw_sha256\t%s\n' "$(sha256_file "$lsa_iw_dst/iw")"
            if [ -x "$lsa_iw_dst/lsa-nl80211" ]; then
                printf 'lsa_nl80211_sha256\t%s\n' "$(sha256_file "$lsa_iw_dst/lsa-nl80211")"
            fi
            printf 'source\tTermux package iw with libnl runtime dependencies\n'
        } > "$lsa_iw_dst/metadata.tsv"
        chmod 644 "$lsa_iw_dst/metadata.tsv"
        note "root-owned iw is ready for generic nl80211 operations"
    else
        warn "root-owned iw could not execute; Wireless reports will retain this as a provider diagnostic"
    fi
}

provision_root_mount_namespace_launcher() {
    # This launcher is architecture-specific only because the Android kernel
    # executes it directly.  Its policy is generic: unshare a mount namespace
    # and make the copied tree recursively private before RootStart mounts.
    # That prevents LSA's chroot /dev from propagating back into Android.
    case "$TERMUX_ARCH" in
        arm64|armv7|x86|x86_64) ;;
        *)
            warn "no safe private mount-namespace launcher is shipped for Termux architecture $TERMUX_ARCH"
            return 0
            ;;
    esac
    lsa_mountns_asset="$SELF_DIR/bootstrap/mountns/lsa-mountns-$TERMUX_ARCH"
    lsa_mountns_dir="$ROOT_DST/Tools/mountns"
    lsa_mountns_target="$lsa_mountns_dir/lsa-mountns"
    [ -r "$lsa_mountns_asset" ] || die "release lacks required mount-namespace launcher for $TERMUX_ARCH"
    note "stage 2: provisioning private mount-namespace launcher"
    mkdir -p "$lsa_mountns_dir"
    cp "$lsa_mountns_asset" "$lsa_mountns_target"
    chown 0:0 "$ROOT_DST/Tools" "$lsa_mountns_dir" "$lsa_mountns_target"
    chmod 755 "$ROOT_DST/Tools" "$lsa_mountns_dir"
    chmod 700 "$lsa_mountns_target"
    "$lsa_mountns_target" /system/bin/true >/dev/null 2>&1 || die "private mount-namespace launcher cannot run on this architecture"
    {
        printf 'termux_arch\t%s\n' "$TERMUX_ARCH"
        printf 'lsa_mountns_sha256\t%s\n' "$(sha256_file "$lsa_mountns_target")"
        printf 'source\tLSA generic private mount namespace launcher\n'
    } > "$lsa_mountns_dir/metadata.tsv"
    chmod 600 "$lsa_mountns_dir/metadata.tsv"
    note "private mount-namespace launcher is ready"
}

app_field() {
    awk -F '\t' -v wanted="$1" -v column="$2" 'NR > 1 && $2 == wanted { print $column; exit }' "$APPS_MANIFEST"
}

installed_app_hash() {
    lsa_package_path="$(pm path "$1" 2>/dev/null | sed -n 's/^package://p' | head -n 1)"
    [ -n "$lsa_package_path" ] && [ -r "$lsa_package_path" ] || return 1
    sha256_file "$lsa_package_path"
}

install_bundled_apps() {
    note "stage 3: validating exact bundled Android applications"
    while IFS='	' read -r lsa_file lsa_package lsa_code lsa_name lsa_hash; do
        lsa_file="$(printf '%s' "$lsa_file" | tr -d '\r')"
        lsa_package="$(printf '%s' "$lsa_package" | tr -d '\r')"
        lsa_code="$(printf '%s' "$lsa_code" | tr -d '\r')"
        lsa_name="$(printf '%s' "$lsa_name" | tr -d '\r')"
        lsa_hash="$(printf '%s' "$lsa_hash" | tr -d '\r')"
        [ "$lsa_file" = file ] && continue
        [ -n "$lsa_file" ] || continue
        lsa_apk="$SELF_DIR/apps/$lsa_file"
        [ -f "$lsa_apk" ] || { warn "bundled app missing: $lsa_file"; continue; }
        lsa_installed="$(installed_app_hash "$lsa_package" 2>/dev/null || true)"
        if [ "$lsa_installed" = "$lsa_hash" ]; then
            note "Android app already matches release: $lsa_package ($lsa_name)"
            continue
        fi
        if [ -n "$lsa_installed" ]; then
            warn "Android app differs from release; attempting explicit in-place update: $lsa_package"
        else
            note "installing bundled Android app: $lsa_package ($lsa_name)"
        fi
        if pm install -r "$lsa_apk"; then
            lsa_installed="$(installed_app_hash "$lsa_package" 2>/dev/null || true)"
            [ "$lsa_installed" = "$lsa_hash" ] || warn "installed $lsa_package but its package hash does not match the release"
        else
            warn "unable to install $lsa_package; its provider will remain unavailable until the application is installed"
        fi
    done < "$APPS_MANIFEST"
}

write_rootfs_state() {
    lsa_state="$1"
    lsa_reason="${2:-}"
    mkdir -p "$ROOT_DST/tmp/rootfs-bootstrap"
    chmod 700 "$ROOT_DST/tmp/rootfs-bootstrap" 2>/dev/null || true
    {
        printf 'state=%s\n' "$lsa_state"
        printf 'time=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        printf 'termux_arch=%s\n' "$TERMUX_ARCH"
        printf 'debian_arch=%s\n' "$DEBIAN_ARCH"
        printf 'reason=%s\n' "$lsa_reason"
    } > "$ROOT_DST/tmp/rootfs-bootstrap/state"
    chmod 600 "$ROOT_DST/tmp/rootfs-bootstrap/state"
}

provision_rootfs() {
    lsa_current_rootfs_state="$(rootfs_state)"
    if [ "$lsa_current_rootfs_state" = COMPLETE ]; then
        note "stage 4: existing rootfs is complete: $ROOTFS"
        return 0
    fi
    [ "$DEBIAN_ARCH" != unknown ] || {
        write_rootfs_state FAILED "Termux userspace architecture is unsupported: $TERMUX_ARCH_RAW"
        die "cannot map Termux userspace architecture to a supported Debian architecture"
    }
    lsa_rootfs_log="$ROOT_DST/tmp/rootfs-bootstrap/bootstrap-$STAMP.log"
    if [ "$lsa_current_rootfs_state" = BOOTSTRAPPING ] && [ -x "$ROOTFS/debootstrap/debootstrap" ]; then
        note "stage 4: resuming interrupted debootstrap second stage for $DEBIAN_ARCH"
        write_rootfs_state BOOTSTRAPPING "resuming debootstrap second stage"
        if env PATH="$TERMUX_PREFIX/bin:/system/bin:/system/xbin" chroot "$ROOTFS" /debootstrap/debootstrap --second-stage >> "$lsa_rootfs_log" 2>&1; then
            :
        else
            write_rootfs_state FAILED "second stage failed; see $lsa_rootfs_log"
            die "rootfs resume failed; retained the partial rootfs and log"
        fi
    elif [ "$lsa_current_rootfs_state" = NOT_PRESENT ]; then
        note "stage 4: creating Debian rootfs for $DEBIAN_ARCH"
        write_rootfs_state BOOTSTRAPPING "debootstrap trixie $DEBIAN_ARCH"
        mkdir -p "$ROOTFS"
        chown 0:0 "$ROOTFS"
        chmod 755 "$ROOTFS"
        if env PATH="$TERMUX_PREFIX/bin:/system/bin:/system/xbin" "$TERMUX_PREFIX/bin/debootstrap" --arch="$DEBIAN_ARCH" --variant=minbase trixie "$ROOTFS" https://deb.debian.org/debian >> "$lsa_rootfs_log" 2>&1; then
            :
        else
            write_rootfs_state FAILED "debootstrap failed; see $lsa_rootfs_log"
            die "rootfs bootstrap failed; retained its state and log"
        fi
    else
        write_rootfs_state FAILED "non-empty incomplete rootfs requires explicit recovery; see prior bootstrap state"
        die "refusing to treat a partial rootfs as complete or delete it automatically"
    fi
    if [ "$(rootfs_state)" = COMPLETE ]; then
        write_rootfs_state COMPLETE "rootfs verified bootable with dpkg status"
        note "rootfs provisioning complete: $ROOTFS"
    else
        write_rootfs_state FAILED "bootstrap returned without a complete rootfs"
        die "rootfs bootstrap did not produce a complete Debian environment"
    fi
}

prepare_runtime_and_secret() {
    note "stage 5: creating fresh LSA runtime state and device-local secret"
    HAL_STATE="$ROOT_DST/Services/halagent/state"
    mkdir -p "$HAL_STATE/cam" "$HAL_STATE/rec" "$HAL_STATE/secret" "$ROOT_DST/Services/ModChroot/runtime"
    chown -R 0:0 "$HAL_STATE" "$ROOT_DST/Services/ModChroot/runtime"
    chmod 711 "$HAL_STATE"
    chmod 700 "$HAL_STATE/cam" "$HAL_STATE/rec"
    chmod 700 "$HAL_STATE/secret"
    umask 077
    "$TERMUX_PREFIX/bin/python" -c 'import secrets; print(secrets.token_hex(32))' > "$HAL_STATE/secret/secret"
    chown 0:0 "$HAL_STATE/secret/secret"
    chmod 600 "$HAL_STATE/secret/secret"
    mkdir -p "$NONROOT_DST/Services/.pids" "$NONROOT_DST/Services/.supervisor"
    chown -R "$TERMUX_UID:$TERMUX_GID" "$NONROOT_DST"
    if [ -r "${PRESERVED_LEDGER:-}" ]; then
        mkdir -p "$ROOT_DST/Services/ModChroot/state"
        cp "$PRESERVED_LEDGER" "$ROOT_DST/Services/ModChroot/state/backend-rejections.tsv"
        chown 0:0 "$ROOT_DST/Services/ModChroot/state/backend-rejections.tsv"
        chmod 700 "$ROOT_DST/Services/ModChroot/state"
        chmod 600 "$ROOT_DST/Services/ModChroot/state/backend-rejections.tsv"
        note "preserved user backend-rejection ledger"
    fi
}

framework_report() {
    lsa_phase="$1"
    lsa_report="$DEPLOY_RUNTIME/framework-$lsa_phase.tsv"
    note "stage 6: framework capability report ($lsa_phase)"
    if env LSA_TERMUX_PREFIX="$TERMUX_PREFIX" LSA_TERMUX_HOME="$TERMUX_HOME" LSA_CHROOT_DIR="$ROOTFS" LSA_ROOTSTART_DIR="$ROOT_DST" LSA_START_BASE="$ROOT_DST/Services/ModChroot" RUNTIME_DIR="$ROOT_DST/Services/ModChroot/runtime" "$TERMUX_PREFIX/bin/bash" "$ROOT_DST/Services/ModChroot/LSA/Framework/lsectl" report "$lsa_phase" --verbose > "$lsa_report" 2>&1; then
        cat "$lsa_report"
    else
        warn "framework report encountered probe errors; diagnostics retained at $lsa_report"
        cat "$lsa_report" 2>/dev/null || true
    fi
}

start_selected_stack() {
    note "stage 7: starting NonRootStart as the Termux UID"
    run_as_termux "if [ -r '$NONROOT_DST/Services/.supervisor/switch-watcher.pid' ] && kill -0 \$(tr -dc '0-9' < '$NONROOT_DST/Services/.supervisor/switch-watcher.pid') 2>/dev/null; then exit 0; fi; nohup '$TERMUX_PREFIX/bin/bash' '$NONROOT_DST/NRS.sh' > '$NONROOT_DST/Services/deploy-nonroot.log' 2>&1 &" || warn "NonRootStart launch failed; root capabilities will report prerequisite failures"
    sleep 3
    if [ -r "$NONROOT_DST/Services/.supervisor/components.tsv" ]; then
        cp "$NONROOT_DST/Services/.supervisor/components.tsv" "$DEPLOY_RUNTIME/nonroot-components.tsv" 2>/dev/null || true
    fi
    note "stage 7: starting RootStart with its persistent pseudo-terminal"
    nohup "$TERMUX_PREFIX/bin/python" "$SELF_DIR/bootstrap/rootstart_pty.py" "$DEPLOY_RUNTIME/rootstart.log" "$TERMUX_PREFIX/bin/bash" "$ROOT_DST/RST.sh" > "$DEPLOY_RUNTIME/rootstart-supervisor.log" 2>&1 &
    ROOTSTART_PID=$!
    printf '%s\n' "$ROOTSTART_PID" > "$DEPLOY_RUNTIME/rootstart-launch.pid"
    sleep 8
    if kill -0 "$ROOTSTART_PID" 2>/dev/null; then
        note "RootStart PTY supervisor is active (pid $ROOTSTART_PID)"
    else
        warn "RootStart exited during launch; see $DEPLOY_RUNTIME/rootstart.log"
    fi
}

post_install_validation() {
    note "stage 8: post-install health checks"
    {
        printf 'check\tresult\tdetail\n'
        if [ -x "$ROOTFS/bin/sh" ] && chroot "$ROOTFS" /bin/sh -c 'printf lsa-rootfs-ok' >/dev/null 2>&1; then
            printf 'core_chroot\tPASS\trootfs command executed\n'
        else
            printf 'core_chroot\tFAIL\trootfs command unavailable\n'
        fi
        if [ -d "$ROOTFS/mnt/sdcard" ]; then
            lsa_test_path="$ROOTFS/mnt/sdcard/.lsa-deploy-test-$STAMP"
            if (umask 077; : > "$lsa_test_path") 2>/dev/null && [ -r "$lsa_test_path" ] && rm -f "$lsa_test_path"; then
                printf 'storage\tPASS\tcreate-read-delete test passed\n'
            else
                printf 'storage\tUNAVAILABLE\tselected storage mount is not writable\n'
            fi
        else
            printf 'storage\tUNAVAILABLE\tno Linux-visible shared storage mount\n'
        fi
        if [ -S "$ROOTFS/var/run/dbus/system_bus_socket" ] && chroot "$ROOTFS" /usr/bin/dbus-send --system --dest=org.freedesktop.DBus --type=method_call --print-reply / org.freedesktop.DBus.ListNames >/dev/null 2>&1; then
            printf 'dbus\tPASS\tsystem bus roundtrip\n'
        else
            printf 'dbus\tUNAVAILABLE\tsystem bus not active\n'
        fi
        if [ -e "$ROOTFS/dev/fuse" ] && "$TERMUX_PREFIX/bin/python" -c 'import os, sys; fd = os.open(sys.argv[1], os.O_RDWR); os.close(fd)' "$ROOTFS/dev/fuse" >/dev/null 2>&1; then
            # Opening the propagated Linux device verifies a real device
            # operation. A module which needs a mount must still perform and
            # report its own mount operation; this result never overclaims it.
            printf 'fuse\tOPEN_PASS\tLinux /dev/fuse open succeeded; mount use remains module-probed\n'
        else
            printf 'fuse\tUNAVAILABLE\tLinux /dev/fuse could not be opened\n'
        fi
    } > "$DEPLOY_RUNTIME/health.tsv"
    cat "$DEPLOY_RUNTIME/health.tsv"
}

note "LSA deployment package: $(tr -d '\r\n' < "$SELF_DIR/VERSION")"
detect_target
write_preflight
verify_release
install_payload
bootstrap_termux
provision_root_mount_namespace_launcher
provision_root_iw
install_bundled_apps
prepare_runtime_and_secret

framework_report framework-only

case "$MODE" in
    framework-only)
        note "framework-only deployment complete; no rootfs provisioning or stack start was requested"
        ;;
    full|resume-rootfs)
        provision_rootfs
        framework_report post-rootfs
        start_selected_stack
        framework_report post-start
        post_install_validation
        ;;
esac

note "LSA deployment complete; runtime evidence: $DEPLOY_RUNTIME"
