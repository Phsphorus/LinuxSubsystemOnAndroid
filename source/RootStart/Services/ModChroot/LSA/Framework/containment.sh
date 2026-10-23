#!/system/bin/sh
#
# Read-only qualification for a runtime that wants to offer generic Linux root
# operations (sudo, package maintainer scripts, and privileged D-Bus service
# activation).  It deliberately does not unshare, remount, change credentials,
# or launch a test payload.  The caller supplies the long-lived candidate PID;
# the report describes that process's actual kernel boundary.
#

lsa_containment_safe_field() {
    printf '%s' "$1" | tr '\t\r\n' '   '
}

lsa_containment_ns() {
    readlink "/proc/$1/ns/$2" 2>/dev/null || printf MISSING
}

lsa_containment_status_value() {
    awk -v key="$2" '$1 == key ":" { print $2; exit }' "$1" 2>/dev/null
}

lsa_containment_row() {
    printf '%s\t%s\t%s\t%s\t%s\n' \
        "$(lsa_containment_safe_field "$1")" \
        "$(lsa_containment_safe_field "$2")" \
        "$(lsa_containment_safe_field "$3")" \
        "$(lsa_containment_safe_field "$4")" \
        "$(lsa_containment_safe_field "$5")" >>"$LSA_CONTAINMENT_REPORT_TMP"
}

lsa_containment_fail() {
    LSA_CONTAINMENT_FAILED=1
    lsa_containment_row "$1" "$2" "$3" FAIL "$4"
}

lsa_containment_pass() {
    lsa_containment_row "$1" "$2" "$3" PASS "$4"
}

lsa_containment_info() {
    lsa_containment_row "$1" "$2" "$3" INFO "$4"
}

lsa_containment_write_mounts() {
    printf 'mountpoint\tmount_options\tfilesystem\tsource\tsuper_options\n' >"$LSA_CONTAINMENT_MOUNTS_TMP"
    awk '
        {
            filesystem = ""
            source = ""
            super_options = ""
            for (field = 7; field <= NF; field++) {
                if ($field == "-") {
                    filesystem = $(field + 1)
                    source = $(field + 2)
                    super_options = $(field + 3)
                    break
                }
            }
            printf "%s\t%s\t%s\t%s\t%s\n", $5, $6, filesystem, source, super_options
        }
    ' "$1" 2>/dev/null >>"$LSA_CONTAINMENT_MOUNTS_TMP"
}

lsa_containment_rootfs_nosuid() {
    [ -x "$2/usr/bin/python3" ] || return 2
    nsenter -t "$1" -m -- chroot "$2" /usr/bin/python3 -c '
import os
raise SystemExit(0 if os.statvfs("/").f_flag & getattr(os, "ST_NOSUID", 2) else 1)
' >/dev/null 2>&1
}

lsa_containment_write_fds() {
    printf 'fd\ttarget\tclassification\n' >"$LSA_CONTAINMENT_FDS_TMP"
    LSA_CONTAINMENT_EXTERNAL_FDS=""
    for lsa_containment_fd in "/proc/$1/fd"/*; do
        [ -e "$lsa_containment_fd" ] || [ -L "$lsa_containment_fd" ] || continue
        lsa_containment_fd_number="${lsa_containment_fd##*/}"
        lsa_containment_fd_target="$(readlink "$lsa_containment_fd" 2>/dev/null || printf unreadable)"
        case "$lsa_containment_fd_target" in
            /dev/null|/dev/zero|/dev/random|/dev/urandom|/dev/tty|/dev/pts/*|pipe:*|socket:*|anon_inode:*|"$2"/*)
                lsa_containment_fd_classification=expected
                ;;
            *)
                lsa_containment_fd_classification=external
                LSA_CONTAINMENT_EXTERNAL_FDS="${LSA_CONTAINMENT_EXTERNAL_FDS}${LSA_CONTAINMENT_EXTERNAL_FDS:+,}${lsa_containment_fd_number}:${lsa_containment_fd_target}"
                ;;
        esac
        printf '%s\t%s\t%s\n' \
            "$lsa_containment_fd_number" \
            "$(lsa_containment_safe_field "$lsa_containment_fd_target")" \
            "$lsa_containment_fd_classification" >>"$LSA_CONTAINMENT_FDS_TMP"
    done
}

lsa_containment_dangerous_capabilities() {
    # These capabilities allow host-level escape or control when a process has
    # not been placed in a separate user namespace.  A future container may
    # define a stricter policy, but none of these are acceptable in this v1
    # qualification gate.
    LSA_CONTAINMENT_DANGEROUS_CAPS=""
    lsa_containment_capability_hex="$1"
    case "$lsa_containment_capability_hex" in
        ''|*[!0-9A-Fa-f]*) return 1 ;;
    esac
    lsa_containment_capability_value=$((0x$lsa_containment_capability_hex))
    for lsa_containment_capability in \
        '1:CAP_DAC_OVERRIDE' \
        '2:CAP_DAC_READ_SEARCH' \
        '6:CAP_SETGID' \
        '7:CAP_SETUID' \
        '12:CAP_NET_ADMIN' \
        '13:CAP_NET_RAW' \
        '16:CAP_SYS_MODULE' \
        '17:CAP_SYS_RAWIO' \
        '18:CAP_SYS_CHROOT' \
        '19:CAP_SYS_PTRACE' \
        '21:CAP_SYS_ADMIN' \
        '22:CAP_SYS_BOOT' \
        '25:CAP_SYS_TIME' \
        '31:CAP_SETFCAP' \
        '32:CAP_MAC_OVERRIDE' \
        '33:CAP_MAC_ADMIN' \
        '38:CAP_PERFMON' \
        '39:CAP_BPF' \
        '40:CAP_CHECKPOINT_RESTORE'; do
        lsa_containment_bit="${lsa_containment_capability%%:*}"
        lsa_containment_name="${lsa_containment_capability#*:}"
        lsa_containment_mask=$((1 << lsa_containment_bit))
        if [ $((lsa_containment_capability_value & lsa_containment_mask)) -ne 0 ]; then
            LSA_CONTAINMENT_DANGEROUS_CAPS="${LSA_CONTAINMENT_DANGEROUS_CAPS}${LSA_CONTAINMENT_DANGEROUS_CAPS:+,}${lsa_containment_name}"
        fi
    done
    return 0
}

lsa_containment_qualify() {
    LSA_CONTAINMENT_TARGET_PID="${1:-}"
    case "$LSA_CONTAINMENT_TARGET_PID" in
        --pid)
            LSA_CONTAINMENT_TARGET_PID="${2:-}"
            ;;
    esac
    if [ -z "$LSA_CONTAINMENT_TARGET_PID" ]; then
        LSA_CONTAINMENT_PID_FILE="${LSA_CHROOT_PID_FILE:-${LSA_START_BASE:-/data/local/RootStart/Services/ModChroot}/runtime/chroot.pid}"
        LSA_CONTAINMENT_TARGET_PID="$(tr -cd '0-9' <"$LSA_CONTAINMENT_PID_FILE" 2>/dev/null || true)"
    fi

    LSA_CONTAINMENT_RUNTIME_DIR="${LSA_RUNTIME_DIR:-${RUNTIME_DIR:-/data/local/RootStart/Services/ModChroot/runtime}/capability-framework}"
    LSA_CONTAINMENT_ROOTFS="${LSA_CHROOT_DIR:-${CHROOT_DIR:-/data/local/linux}}"
    mkdir -p "$LSA_CONTAINMENT_RUNTIME_DIR" || return 1
    umask 077
    LSA_CONTAINMENT_REPORT="$LSA_CONTAINMENT_RUNTIME_DIR/containment.tsv"
    LSA_CONTAINMENT_MOUNTS="$LSA_CONTAINMENT_RUNTIME_DIR/containment-mounts.tsv"
    LSA_CONTAINMENT_FDS="$LSA_CONTAINMENT_RUNTIME_DIR/containment-fds.tsv"
    LSA_CONTAINMENT_REPORT_TMP="$LSA_CONTAINMENT_REPORT.tmp.$$"
    LSA_CONTAINMENT_MOUNTS_TMP="$LSA_CONTAINMENT_MOUNTS.tmp.$$"
    LSA_CONTAINMENT_FDS_TMP="$LSA_CONTAINMENT_FDS.tmp.$$"
    trap 'rm -f "$LSA_CONTAINMENT_REPORT_TMP" "$LSA_CONTAINMENT_MOUNTS_TMP" "$LSA_CONTAINMENT_FDS_TMP"' HUP INT TERM

    {
        printf 'schema\tcontainment-v1\n'
        printf 'generated_utc\t%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        printf 'target_pid\t%s\n' "${LSA_CONTAINMENT_TARGET_PID:-missing}"
        printf 'check\texpected\tactual\tresult\tdetail\n'
    } >"$LSA_CONTAINMENT_REPORT_TMP"
    LSA_CONTAINMENT_FAILED=0

    case "$LSA_CONTAINMENT_TARGET_PID" in
        ''|*[!0-9]*)
            lsa_containment_fail candidate_process 'live candidate PID' "${LSA_CONTAINMENT_TARGET_PID:-missing}" 'no readable candidate PID was supplied or recorded'
            LSA_CONTAINMENT_FAILED=1
            ;;
        *)
            if [ -r "/proc/$LSA_CONTAINMENT_TARGET_PID/status" ] && [ -r "/proc/$LSA_CONTAINMENT_TARGET_PID/mountinfo" ]; then
                lsa_containment_pass candidate_process 'live candidate PID' "$LSA_CONTAINMENT_TARGET_PID" 'process status and mountinfo are readable'
            else
                lsa_containment_fail candidate_process 'readable process status and mountinfo' "$LSA_CONTAINMENT_TARGET_PID" 'candidate exited or caller cannot inspect it'
            fi
            ;;
    esac

    if [ ! -r "/proc/$LSA_CONTAINMENT_TARGET_PID/status" ] || [ ! -r "/proc/$LSA_CONTAINMENT_TARGET_PID/mountinfo" ]; then
        printf 'overall\tNOT_QUALIFIED\n' >>"$LSA_CONTAINMENT_REPORT_TMP"
        mv -f "$LSA_CONTAINMENT_REPORT_TMP" "$LSA_CONTAINMENT_REPORT"
        rm -f "$LSA_CONTAINMENT_MOUNTS_TMP" "$LSA_CONTAINMENT_FDS_TMP"
        trap - HUP INT TERM
        cat "$LSA_CONTAINMENT_REPORT"
        return 4
    fi

    # This qualifier runs in RootStart's host namespace.  Android may hide the
    # namespace links of PID 1 even from a root shell, so the caller's own PID
    # is the stable host-side comparison point.
    LSA_CONTAINMENT_HOST_PID="${LSA_CONTAINMENT_HOST_PID:-$$}"
    LSA_CONTAINMENT_HOST_USER_NS="$(lsa_containment_ns "$LSA_CONTAINMENT_HOST_PID" user)"
    LSA_CONTAINMENT_TARGET_USER_NS="$(lsa_containment_ns "$LSA_CONTAINMENT_TARGET_PID" user)"
    if [ "$LSA_CONTAINMENT_HOST_USER_NS" = MISSING ] || [ "$LSA_CONTAINMENT_TARGET_USER_NS" = MISSING ]; then
        lsa_containment_fail user_namespace 'separate user namespace with UID mapping' "host=$LSA_CONTAINMENT_HOST_USER_NS target=$LSA_CONTAINMENT_TARGET_USER_NS" 'kernel does not expose a user namespace boundary'
    elif [ "$LSA_CONTAINMENT_HOST_USER_NS" = "$LSA_CONTAINMENT_TARGET_USER_NS" ]; then
        lsa_containment_fail user_namespace 'target user namespace differs from Android init' "$LSA_CONTAINMENT_TARGET_USER_NS" 'mount namespaces do not remap UID 0'
    else
        lsa_containment_pass user_namespace 'target user namespace differs from Android init' "$LSA_CONTAINMENT_TARGET_USER_NS" "host=$LSA_CONTAINMENT_HOST_USER_NS"
    fi

    LSA_CONTAINMENT_TARGET_ROOT_MAP="$(awk '$1 == "0" { print $2; exit }' "/proc/$LSA_CONTAINMENT_TARGET_PID/uid_map" 2>/dev/null)"
    case "$LSA_CONTAINMENT_TARGET_ROOT_MAP" in
        ''|*[!0-9]*)
            lsa_containment_fail uid_zero_mapping 'target UID 0 maps to a nonzero host UID' "${LSA_CONTAINMENT_TARGET_ROOT_MAP:-missing}" 'unable to inspect the candidate UID map'
            ;;
        0)
            lsa_containment_fail uid_zero_mapping 'target UID 0 maps to a nonzero host UID' 0 'candidate root is Android host UID 0'
            ;;
        *)
            lsa_containment_pass uid_zero_mapping 'target UID 0 maps to a nonzero host UID' "$LSA_CONTAINMENT_TARGET_ROOT_MAP" 'container root is not Android root'
            ;;
    esac

    LSA_CONTAINMENT_HOST_MOUNT_NS="$(lsa_containment_ns "$LSA_CONTAINMENT_HOST_PID" mnt)"
    LSA_CONTAINMENT_TARGET_MOUNT_NS="$(lsa_containment_ns "$LSA_CONTAINMENT_TARGET_PID" mnt)"
    if [ "$LSA_CONTAINMENT_HOST_MOUNT_NS" != MISSING ] && [ "$LSA_CONTAINMENT_TARGET_MOUNT_NS" != MISSING ] && [ "$LSA_CONTAINMENT_HOST_MOUNT_NS" != "$LSA_CONTAINMENT_TARGET_MOUNT_NS" ]; then
        lsa_containment_pass mount_namespace 'target mount namespace differs from Android init' "$LSA_CONTAINMENT_TARGET_MOUNT_NS" "host=$LSA_CONTAINMENT_HOST_MOUNT_NS"
    else
        lsa_containment_fail mount_namespace 'target mount namespace differs from Android init' "host=$LSA_CONTAINMENT_HOST_MOUNT_NS target=$LSA_CONTAINMENT_TARGET_MOUNT_NS" 'candidate can inherit Android mount visibility'
    fi

    LSA_CONTAINMENT_HOST_PID_NS="$(lsa_containment_ns "$LSA_CONTAINMENT_HOST_PID" pid)"
    LSA_CONTAINMENT_TARGET_PID_NS="$(lsa_containment_ns "$LSA_CONTAINMENT_TARGET_PID" pid)"
    if [ "$LSA_CONTAINMENT_HOST_PID_NS" != MISSING ] && [ "$LSA_CONTAINMENT_TARGET_PID_NS" != MISSING ] && [ "$LSA_CONTAINMENT_HOST_PID_NS" != "$LSA_CONTAINMENT_TARGET_PID_NS" ]; then
        lsa_containment_pass pid_namespace 'target PID namespace differs from Android init' "$LSA_CONTAINMENT_TARGET_PID_NS" "host=$LSA_CONTAINMENT_HOST_PID_NS"
    else
        lsa_containment_fail pid_namespace 'target PID namespace differs from Android init' "host=$LSA_CONTAINMENT_HOST_PID_NS target=$LSA_CONTAINMENT_TARGET_PID_NS" 'candidate can inspect Android process identities through procfs'
    fi

    LSA_CONTAINMENT_STATUS="/proc/$LSA_CONTAINMENT_TARGET_PID/status"
    LSA_CONTAINMENT_CAP_BND="$(lsa_containment_status_value "$LSA_CONTAINMENT_STATUS" CapBnd)"
    LSA_CONTAINMENT_CAP_EFF="$(lsa_containment_status_value "$LSA_CONTAINMENT_STATUS" CapEff)"
    if lsa_containment_dangerous_capabilities "$LSA_CONTAINMENT_CAP_BND"; then
        if [ -n "$LSA_CONTAINMENT_DANGEROUS_CAPS" ]; then
            lsa_containment_fail capability_bounding_set 'no host-escape capabilities in CapBnd' "$LSA_CONTAINMENT_CAP_BND" "$LSA_CONTAINMENT_DANGEROUS_CAPS"
        else
            lsa_containment_pass capability_bounding_set 'no host-escape capabilities in CapBnd' "$LSA_CONTAINMENT_CAP_BND" 'critical capabilities are absent from the bounding set'
        fi
    else
        lsa_containment_fail capability_bounding_set 'valid CapBnd hexadecimal mask' "${LSA_CONTAINMENT_CAP_BND:-missing}" 'unable to decode candidate capability bounding set'
    fi
    lsa_containment_info effective_capabilities 'recorded for review' "${LSA_CONTAINMENT_CAP_EFF:-missing}" 'CapEff is not used as a substitute for a bounding-set policy'
    lsa_containment_info no_new_privs 'recorded for review' "$(lsa_containment_status_value "$LSA_CONTAINMENT_STATUS" NoNewPrivs)" 'a root-capable profile must declare its exec transition policy'
    lsa_containment_info seccomp 'recorded for review' "$(lsa_containment_status_value "$LSA_CONTAINMENT_STATUS" Seccomp)" 'a root-capable profile must declare its syscall policy'

    LSA_CONTAINMENT_MOUNTINFO="/proc/$LSA_CONTAINMENT_TARGET_PID/mountinfo"
    lsa_containment_write_mounts "$LSA_CONTAINMENT_MOUNTINFO" "$LSA_CONTAINMENT_ROOTFS"
    if awk '$5 == "/dev/.host" { found = 1 } END { exit(found ? 0 : 1) }' "$LSA_CONTAINMENT_MOUNTINFO"; then
        lsa_containment_fail host_device_view 'no raw Android /dev bind in root-capable runtime' /dev/.host 'private-device host read-through is visible'
    else
        lsa_containment_pass host_device_view 'no raw Android /dev bind in root-capable runtime' absent 'no .host device mount is present'
    fi
    LSA_CONTAINMENT_SYS_OPTIONS="$(awk '$5 == "/sys" { print $6; exit }' "$LSA_CONTAINMENT_MOUNTINFO")"
    case ",$LSA_CONTAINMENT_SYS_OPTIONS," in
        *,rw,*) lsa_containment_fail sysfs 'sysfs absent or read-only' "$LSA_CONTAINMENT_SYS_OPTIONS" 'writable sysfs exposes Android kernel control surfaces' ;;
        '') lsa_containment_pass sysfs 'sysfs absent or read-only' absent 'no sysfs mount is present' ;;
        *) lsa_containment_pass sysfs 'sysfs absent or read-only' "$LSA_CONTAINMENT_SYS_OPTIONS" 'sysfs mount is not writable' ;;
    esac
    lsa_containment_rootfs_nosuid "$LSA_CONTAINMENT_TARGET_PID" "$LSA_CONTAINMENT_ROOTFS"
    LSA_CONTAINMENT_ROOTFS_RESULT=$?
    case "$LSA_CONTAINMENT_ROOTFS_RESULT" in
        0) lsa_containment_fail rootfs_suid 'suid permitted only after all containment checks pass' nosuid 'statvfs reports ST_NOSUID for the candidate rootfs' ;;
        1) lsa_containment_pass rootfs_suid 'suid permitted only after all containment checks pass' suid 'statvfs reports no ST_NOSUID flag' ;;
        *) lsa_containment_fail rootfs_suid 'readable rootfs statvfs flags' unknown 'unable to inspect the candidate rootfs from its mount namespace' ;;
    esac

    LSA_CONTAINMENT_HOST_WRITABLE_MOUNTS="$(awk '
        {
            filesystem = ""
            source = ""
            for (field = 7; field <= NF; field++) {
                if ($field == "-") {
                    filesystem = $(field + 1)
                    source = $(field + 2)
                    break
                }
            }
            if ($6 ~ /(^|,)rw(,|$)/ && filesystem != "tmpfs" && filesystem != "devpts" && filesystem != "proc" && filesystem != "sysfs") {
                printf "%s:%s:%s;", $5, filesystem, source
            }
        }
    ' "$LSA_CONTAINMENT_MOUNTINFO")"
    if [ -n "$LSA_CONTAINMENT_HOST_WRITABLE_MOUNTS" ]; then
        lsa_containment_fail writable_host_mounts 'no writable host-backed mounts in root-capable runtime' "$LSA_CONTAINMENT_HOST_WRITABLE_MOUNTS" 'use provider sockets or a deliberately reviewed writable volume instead'
    else
        lsa_containment_pass writable_host_mounts 'no writable host-backed mounts in root-capable runtime' none 'only private runtime mounts are writable'
    fi

    lsa_containment_write_fds "$LSA_CONTAINMENT_TARGET_PID" "$LSA_CONTAINMENT_ROOTFS"
    if [ -n "$LSA_CONTAINMENT_EXTERNAL_FDS" ]; then
        lsa_containment_fail inherited_file_descriptors 'no inherited external path descriptors' "$LSA_CONTAINMENT_EXTERNAL_FDS" 'close or mark inherited host descriptors close-on-exec before launching root-capable code'
    else
        lsa_containment_pass inherited_file_descriptors 'no inherited external path descriptors' none 'only expected device, pipe, socket, or rootfs descriptors are open'
    fi

    if [ "$LSA_CONTAINMENT_FAILED" = 0 ]; then
        LSA_CONTAINMENT_OVERALL=QUALIFIED
        LSA_CONTAINMENT_RETURN=0
    else
        LSA_CONTAINMENT_OVERALL=NOT_QUALIFIED
        LSA_CONTAINMENT_RETURN=4
    fi
    printf 'overall\t%s\n' "$LSA_CONTAINMENT_OVERALL" >>"$LSA_CONTAINMENT_REPORT_TMP"
    mv -f "$LSA_CONTAINMENT_REPORT_TMP" "$LSA_CONTAINMENT_REPORT"
    mv -f "$LSA_CONTAINMENT_MOUNTS_TMP" "$LSA_CONTAINMENT_MOUNTS"
    mv -f "$LSA_CONTAINMENT_FDS_TMP" "$LSA_CONTAINMENT_FDS"
    trap - HUP INT TERM
    cat "$LSA_CONTAINMENT_REPORT"
    return "$LSA_CONTAINMENT_RETURN"
}

if [ "${LSA_CONTAINMENT_LIBRARY:-0}" != 1 ]; then
    lsa_containment_qualify "$@"
    exit $?
fi
