#!/data/data/com.termux/files/usr/bin/bash
# Capability, provider, and backend registry for LSA.
#
# Descriptors only declare an implementation and its callbacks.  Selection,
# dependency evaluation, lifecycle invocation, and reporting stay here so a
# consumer depends on capability names rather than a device or backend ID.

: "${LSA_FRAMEWORK_BASE:=$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
: "${LSA_CHROOT_DIR:=${CHROOT_DIR:-/data/local/linux}}"
: "${LSA_START_BASE:=${START_CHROOT_BASE:-/data/local/RootStart/Services/ModChroot}}"
: "${LSA_RUNTIME_DIR:=${RUNTIME_DIR:-$LSA_START_BASE/runtime}/capability-framework}"
: "${LSA_OVERRIDE_DIR:=$LSA_START_BASE/state}"
: "${LSA_BACKEND_REJECTIONS_FILE:=$LSA_OVERRIDE_DIR/backend-rejections.tsv}"

LSA_PROBE_AVAILABLE="AVAILABLE"
LSA_PROBE_UNSUPPORTED="UNSUPPORTED"
LSA_PROBE_ERROR="ERROR"

LSA_RUNTIME_STOPPED="STOPPED"
LSA_RUNTIME_STARTING="STARTING"
LSA_RUNTIME_RUNNING="RUNNING"
LSA_RUNTIME_DEGRADED="DEGRADED"
LSA_RUNTIME_FAILED="FAILED"

declare -ag LSA_PROVIDER_IDS=()
declare -ag LSA_BACKEND_IDS=()
declare -Ag LSA_PROVIDER_CLASS=()
declare -Ag LSA_PROVIDER_PRIORITY=()
declare -Ag LSA_PROVIDER_REQUIRES=()
declare -Ag LSA_PROVIDER_PROVIDES=()
declare -Ag LSA_PROVIDER_PROBE=()
declare -Ag LSA_PROVIDER_STATUS=()
declare -Ag LSA_PROVIDER_RESULT=()
declare -Ag LSA_PROVIDER_REASON=()
declare -Ag LSA_PROVIDER_RUNTIME=()
declare -Ag LSA_BACKEND_MODULE=()
declare -Ag LSA_BACKEND_TIER=()
declare -Ag LSA_BACKEND_PRIORITY=()
declare -Ag LSA_BACKEND_REQUIRES=()
declare -Ag LSA_BACKEND_PROVIDES=()
declare -Ag LSA_BACKEND_PROBE=()
declare -Ag LSA_BACKEND_START=()
declare -Ag LSA_BACKEND_STOP=()
declare -Ag LSA_BACKEND_STATUS=()
declare -Ag LSA_BACKEND_HEALTH=()
declare -Ag LSA_BACKEND_CLASS=()
declare -Ag LSA_BACKEND_DEVICE_OPTIMIZED=()
declare -Ag LSA_BACKEND_RESULT=()
declare -Ag LSA_BACKEND_REASON=()
declare -Ag LSA_BACKEND_RUNTIME=()
declare -Ag LSA_BACKEND_POLICY=()
declare -Ag LSA_BACKEND_REJECTION_REASON=()
declare -Ag LSA_CAPABILITIES=()
declare -Ag LSA_CAPABILITY_PROVIDER=()
declare -Ag LSA_SELECTED_BACKEND=()
declare -Ag LSA_BINARY_ARCH_PATH=()
declare -Ag LSA_BINARY_ARCH_EXPECTED=()
declare -Ag LSA_BINARY_ARCH_DETECTED=()
declare -Ag LSA_BINARY_ARCH_RESULT=()
declare -ag LSA_ARCHITECTURE_HOOKS=()
declare -ag LSA_REPORT_HOOK_IDS=()
declare -Ag LSA_REPORT_HOOK_CALLBACK=()

lsa_framework_log() {
    if declare -F log >/dev/null 2>&1; then
        log "framework: $*"
    else
        printf '%s framework: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
    fi
}

lsa_framework_reset() {
    mkdir -p "$LSA_RUNTIME_DIR"
    LSA_PROVIDER_IDS=()
    LSA_BACKEND_IDS=()
    LSA_PROVIDER_CLASS=()
    LSA_PROVIDER_PRIORITY=()
    LSA_PROVIDER_REQUIRES=()
    LSA_PROVIDER_PROVIDES=()
    LSA_PROVIDER_PROBE=()
    LSA_PROVIDER_STATUS=()
    LSA_PROVIDER_RESULT=()
    LSA_PROVIDER_REASON=()
    LSA_PROVIDER_RUNTIME=()
    LSA_BACKEND_MODULE=()
    LSA_BACKEND_TIER=()
    LSA_BACKEND_PRIORITY=()
    LSA_BACKEND_REQUIRES=()
    LSA_BACKEND_PROVIDES=()
    LSA_BACKEND_PROBE=()
    LSA_BACKEND_START=()
    LSA_BACKEND_STOP=()
    LSA_BACKEND_STATUS=()
    LSA_BACKEND_HEALTH=()
    LSA_BACKEND_CLASS=()
    LSA_BACKEND_DEVICE_OPTIMIZED=()
    LSA_BACKEND_RESULT=()
    LSA_BACKEND_REASON=()
    LSA_BACKEND_RUNTIME=()
    LSA_BACKEND_POLICY=()
    LSA_BACKEND_REJECTION_REASON=()
    LSA_CAPABILITIES=()
    LSA_CAPABILITY_PROVIDER=()
    LSA_SELECTED_BACKEND=()
    LSA_BINARY_ARCH_PATH=()
    LSA_BINARY_ARCH_EXPECTED=()
    LSA_BINARY_ARCH_DETECTED=()
    LSA_BINARY_ARCH_RESULT=()
    LSA_ARCHITECTURE_HOOKS=()
    LSA_REPORT_HOOK_IDS=()
    LSA_REPORT_HOOK_CALLBACK=()
}

lsa__contains_id() {
    local wanted="$1" item
    shift
    for item in "$@"; do
        [ "$item" = "$wanted" ] && return 0
    done
    return 1
}

lsa_provider_register() {
    local id="$1" class="$2" priority="$3" requires="$4" provides="$5" probe="$6" status="$7"
    if lsa__contains_id "$id" "${LSA_PROVIDER_IDS[@]}"; then
        lsa_framework_log "ERROR: duplicate provider id=$id"
        return 1
    fi
    LSA_PROVIDER_IDS+=("$id")
    LSA_PROVIDER_CLASS["$id"]="$class"
    LSA_PROVIDER_PRIORITY["$id"]="$priority"
    LSA_PROVIDER_REQUIRES["$id"]="$requires"
    LSA_PROVIDER_PROVIDES["$id"]="$provides"
    LSA_PROVIDER_PROBE["$id"]="$probe"
    LSA_PROVIDER_STATUS["$id"]="$status"
}

lsa_backend_register() {
    local id="$1" module="$2" tier="$3" priority="$4" requires="$5" provides="$6"
    local probe="$7" start="$8" stop="$9" status="${10}" class="${11}" optimized="${12}" health="${13:-}"
    if lsa__contains_id "$id" "${LSA_BACKEND_IDS[@]}"; then
        lsa_framework_log "ERROR: duplicate backend id=$id"
        return 1
    fi
    LSA_BACKEND_IDS+=("$id")
    LSA_BACKEND_MODULE["$id"]="$module"
    LSA_BACKEND_TIER["$id"]="$tier"
    LSA_BACKEND_PRIORITY["$id"]="$priority"
    LSA_BACKEND_REQUIRES["$id"]="$requires"
    LSA_BACKEND_PROVIDES["$id"]="$provides"
    LSA_BACKEND_PROBE["$id"]="$probe"
    LSA_BACKEND_START["$id"]="$start"
    LSA_BACKEND_STOP["$id"]="$stop"
    LSA_BACKEND_STATUS["$id"]="$status"
    LSA_BACKEND_HEALTH["$id"]="$health"
    LSA_BACKEND_CLASS["$id"]="$class"
    LSA_BACKEND_DEVICE_OPTIMIZED["$id"]="$optimized"
}

lsa_architecture_register_hook() {
    local callback="$1"
    lsa__contains_id "$callback" "${LSA_ARCHITECTURE_HOOKS[@]}" || LSA_ARCHITECTURE_HOOKS+=("$callback")
}

lsa_report_register() {
    local id="$1" callback="$2"
    lsa__contains_id "$id" "${LSA_REPORT_HOOK_IDS[@]}" && return 0
    LSA_REPORT_HOOK_IDS+=("$id")
    LSA_REPORT_HOOK_CALLBACK["$id"]="$callback"
}

lsa_backend_rejection_reason() {
    local wanted="$1" id reason
    LSA_BACKEND_REJECTION_REASON["$wanted"]=""
    [ -f "$LSA_BACKEND_REJECTIONS_FILE" ] || return 1
    while IFS=$'\t' read -r id reason || [ -n "$id" ]; do
        case "$id" in ''|'#'*) continue ;; esac
        [ "$id" = "$wanted" ] || continue
        LSA_BACKEND_REJECTION_REASON["$wanted"]="${reason:-disabled by user}"
        return 0
    done <"$LSA_BACKEND_REJECTIONS_FILE"
    return 1
}

lsa_backend_rejection_prepare() {
    mkdir -p "$LSA_OVERRIDE_DIR"
    chmod 700 "$LSA_OVERRIDE_DIR" 2>/dev/null || return 1
    if [ ! -e "$LSA_BACKEND_REJECTIONS_FILE" ]; then
        umask 077
        : >"$LSA_BACKEND_REJECTIONS_FILE"
    fi
    chmod 600 "$LSA_BACKEND_REJECTIONS_FILE" 2>/dev/null || return 1
}

lsa_backend_rejection_validate_id() {
    local id="$1"
    lsa__contains_id "$id" "${LSA_BACKEND_IDS[@]}" || {
        printf 'unknown backend id: %s' "$id"
        return 2
    }
}

lsa_backend_rejection_rewrite() {
    local target="$1" replacement_reason="${2:-}" current_id current_reason
    local temporary="$LSA_BACKEND_REJECTIONS_FILE.tmp.$$"
    lsa_backend_rejection_prepare || return 1
    umask 077
    : >"$temporary" || return 1
    while IFS=$'\t' read -r current_id current_reason || [ -n "$current_id" ]; do
        case "$current_id" in ''|'#'*) continue ;; esac
        [ "$current_id" = "$target" ] && continue
        printf '%s\t%s\n' "$current_id" "$current_reason" >>"$temporary"
    done <"$LSA_BACKEND_REJECTIONS_FILE"
    if [ -n "$replacement_reason" ]; then
        printf '%s\t%s\n' "$target" "$replacement_reason" >>"$temporary"
    fi
    mv "$temporary" "$LSA_BACKEND_REJECTIONS_FILE"
    chmod 600 "$LSA_BACKEND_REJECTIONS_FILE" 2>/dev/null || return 1
}

lsa_backend_reject() {
    local id="$1" reason="${2:-disabled by user}"
    reason="$(printf '%s' "$reason" | tr '\t\r\n' '   ')"
    lsa_backend_rejection_validate_id "$id" || return $?
    lsa_backend_rejection_rewrite "$id" "$reason" || return 1
    printf 'backend rejected: %s (%s)\n' "$id" "$reason"
}

lsa_backend_accept() {
    local id="$1"
    lsa_backend_rejection_validate_id "$id" || return $?
    lsa_backend_rejection_rewrite "$id" || return 1
    printf 'backend rejection cleared: %s\n' "$id"
}

lsa_backend_clear_rejections() {
    lsa_backend_rejection_prepare || return 1
    : >"$LSA_BACKEND_REJECTIONS_FILE"
    chmod 600 "$LSA_BACKEND_REJECTIONS_FILE" 2>/dev/null || return 1
    printf 'all backend rejections cleared\n'
}

lsa_backend_list_rejections() {
    [ -f "$LSA_BACKEND_REJECTIONS_FILE" ] || return 0
    while IFS=$'\t' read -r id reason || [ -n "$id" ]; do
        case "$id" in ''|'#'*) continue ;; esac
        printf '%s\t%s\n' "$id" "${reason:-disabled by user}"
    done <"$LSA_BACKEND_REJECTIONS_FILE"
}

lsa_capability_add() {
    local capability="$1" provider="$2"
    [ -n "$capability" ] || return 0
    LSA_CAPABILITIES["$capability"]=1
    LSA_CAPABILITY_PROVIDER["$capability"]="$provider"
}

lsa_capability_add_list() {
    local list="$1" provider="$2" capability
    while IFS= read -r capability || [ -n "$capability" ]; do
        [ -n "$capability" ] && lsa_capability_add "$capability" "$provider"
    done < <(printf '%s' "$list" | tr ';' '\n')
}

lsa_missing_requirements() {
    local list="$1" capability
    local -a missing=()
    while IFS= read -r capability || [ -n "$capability" ]; do
        [ -z "$capability" ] && continue
        [ "${LSA_CAPABILITIES[$capability]:-}" = "1" ] || missing+=("$capability")
    done < <(printf '%s' "$list" | tr ';' '\n')
    if [ "${#missing[@]}" -gt 0 ]; then
        printf 'missing capabilities: %s' "$(IFS=,; printf '%s' "${missing[*]}")"
        return 1
    fi
    return 0
}

lsa__run_callback() {
    local callback="$1"
    local code
    shift
    LSA_CALLBACK_OUTPUT=""
    if ! declare -F "$callback" >/dev/null 2>&1; then
        LSA_CALLBACK_OUTPUT="callback not registered: $callback"
        return 2
    fi
    if LSA_CALLBACK_OUTPUT="$("$callback" "$@" 2>&1)"; then
        return 0
    else
        code=$?
        return "$code"
    fi
}

lsa__probe_callback() {
    local callback="$1" id="$2" requires="$3"
    local missing code
    LSA_PROBE_CALLBACK_RESULT=""
    LSA_PROBE_CALLBACK_REASON=""
    if ! missing="$(lsa_missing_requirements "$requires")"; then
        LSA_PROBE_CALLBACK_RESULT="$LSA_PROBE_UNSUPPORTED"
        LSA_PROBE_CALLBACK_REASON="$missing"
        return 0
    fi
    if lsa__run_callback "$callback" "$id"; then
        LSA_PROBE_CALLBACK_RESULT="$LSA_PROBE_AVAILABLE"
        LSA_PROBE_CALLBACK_REASON="${LSA_CALLBACK_OUTPUT:-probe passed}"
    else
        code=$?
        case "$code" in
            3) LSA_PROBE_CALLBACK_RESULT="$LSA_PROBE_UNSUPPORTED" ;;
            *) LSA_PROBE_CALLBACK_RESULT="$LSA_PROBE_ERROR" ;;
        esac
        LSA_PROBE_CALLBACK_REASON="${LSA_CALLBACK_OUTPUT:-probe callback exit=$code}"
    fi
}

lsa__source_descriptors() {
    local directory="$1" suffix="$2" descriptor
    [ -d "$directory" ] || return 0
    while IFS= read -r descriptor; do
        # shellcheck source=/dev/null
        source "$descriptor"
    done < <(find "$directory" -type f -name "$suffix" | sort)
}

lsa_framework_load() {
    lsa_framework_reset
    # shellcheck source=/dev/null
    source "$LSA_FRAMEWORK_BASE/compat.sh"
    # shellcheck source=/dev/null
    source "$LSA_FRAMEWORK_BASE/architecture.sh"
    lsa__source_descriptors "$LSA_FRAMEWORK_BASE/../Providers" '*.provider'
    lsa__source_descriptors "$LSA_FRAMEWORK_BASE/../Modules" '*.backend'
}

lsa_framework_probe_primitives() {
    local architecture_hook
    lsa_architecture_detect
    for architecture_hook in "${LSA_ARCHITECTURE_HOOKS[@]}"; do
        if declare -F "$architecture_hook" >/dev/null 2>&1; then
            "$architecture_hook" || lsa_framework_log "architecture asset hook failed: $architecture_hook"
        fi
    done
    [ "$(id -u)" = "0" ] && lsa_capability_add capability.host.root framework.primitive
    [ -x "$LSA_CHROOT_DIR/bin/sh" ] && lsa_capability_add capability.chroot.rootfs framework.primitive
    command -v mount >/dev/null 2>&1 && lsa_capability_add capability.mount framework.primitive
    [ -e /dev/null ] && lsa_capability_add capability.device.host framework.primitive
    [ -e /dev/fuse ] && lsa_capability_add capability.fuse.kernel framework.primitive
    command -v getprop >/dev/null 2>&1 && lsa_capability_add capability.android.properties framework.primitive
}

lsa__ids_by_priority() {
    local kind="$1" id priority
    if [ "$kind" = provider ]; then
        for id in "${LSA_PROVIDER_IDS[@]}"; do
            printf '%s\t%s\n' "${LSA_PROVIDER_PRIORITY[$id]}" "$id"
        done
    else
        for id in "${LSA_BACKEND_IDS[@]}"; do
            printf '%s\t%s\n' "${LSA_BACKEND_PRIORITY[$id]}" "$id"
        done
    fi | sort -rn | while IFS=$'\t' read -r priority id; do
        printf '%s\n' "$id"
    done
}

lsa_framework_probe_providers() {
    local pass id result reason before after
    for pass in 1 2 3 4; do
        before="${#LSA_CAPABILITIES[@]}"
        while IFS= read -r id; do
            [ -n "$id" ] || continue
            lsa__probe_callback "${LSA_PROVIDER_PROBE[$id]}" "$id" "${LSA_PROVIDER_REQUIRES[$id]}"
            LSA_PROVIDER_RESULT["$id"]="$LSA_PROBE_CALLBACK_RESULT"
            LSA_PROVIDER_REASON["$id"]="$LSA_PROBE_CALLBACK_REASON"
            [ "$LSA_PROBE_CALLBACK_RESULT" = "$LSA_PROBE_AVAILABLE" ] && lsa_capability_add_list "${LSA_PROVIDER_PROVIDES[$id]}" "$id"
        done < <(lsa__ids_by_priority provider)
        after="${#LSA_CAPABILITIES[@]}"
        [ "$after" = "$before" ] && break
    done
}

lsa__modules() {
    local id
    for id in "${LSA_BACKEND_IDS[@]}"; do
        printf '%s\n' "${LSA_BACKEND_MODULE[$id]}"
    done | sort -u
}

lsa__backend_candidates() {
    local module="$1" id priority
    for id in "${LSA_BACKEND_IDS[@]}"; do
        [ "${LSA_BACKEND_MODULE[$id]}" = "$module" ] || continue
        printf '%s\t%s\n' "${LSA_BACKEND_PRIORITY[$id]}" "$id"
    done | sort -rn | while IFS=$'\t' read -r priority id; do
        printf '%s\n' "$id"
    done
}

lsa_framework_select_module() {
    local module="$1" id result reason
    [ -z "${LSA_SELECTED_BACKEND[$module]:-}" ] || return 1
    while IFS= read -r id; do
        [ -n "$id" ] || continue
        lsa__probe_callback "${LSA_BACKEND_PROBE[$id]}" "$id" "${LSA_BACKEND_REQUIRES[$id]}"
        LSA_BACKEND_RESULT["$id"]="$LSA_PROBE_CALLBACK_RESULT"
        LSA_BACKEND_REASON["$id"]="$LSA_PROBE_CALLBACK_REASON"
        LSA_BACKEND_POLICY["$id"]="ACCEPTED"
        if lsa_backend_rejection_reason "$id"; then
            LSA_BACKEND_POLICY["$id"]="REJECTED"
            reason="${LSA_BACKEND_REJECTION_REASON[$id]}"
            LSA_BACKEND_REASON["$id"]="${LSA_BACKEND_REASON[$id]}; rejected by user: $reason"
            continue
        fi
        if [ "$LSA_PROBE_CALLBACK_RESULT" = "$LSA_PROBE_AVAILABLE" ]; then
            LSA_SELECTED_BACKEND["$module"]="$id"
            lsa_capability_add_list "${LSA_BACKEND_PROVIDES[$id]}" "$id"
            return 0
        fi
    done < <(lsa__backend_candidates "$module")
    return 1
}

lsa_framework_select_backends() {
    local pass module changed
    for pass in 1 2 3 4 5 6 7 8; do
        changed=0
        while IFS= read -r module; do
            [ -n "$module" ] || continue
            if lsa_framework_select_module "$module"; then
                changed=1
            fi
        done < <(lsa__modules)
        [ "$changed" = 1 ] || break
    done
}

lsa__runtime_callback() {
    local callback="$1" id="$2" runtime
    if [ -z "$callback" ] || ! declare -F "$callback" >/dev/null 2>&1; then
        printf '%s' "UNKNOWN"
        return 0
    fi
    if runtime="$("$callback" "$id" 2>/dev/null)"; then
        case "$runtime" in
            "$LSA_RUNTIME_STOPPED"|"$LSA_RUNTIME_STARTING"|"$LSA_RUNTIME_RUNNING"|"$LSA_RUNTIME_DEGRADED"|"$LSA_RUNTIME_FAILED")
                printf '%s' "$runtime"
                ;;
            *) printf '%s' "UNKNOWN" ;;
        esac
    else
        printf '%s' "$LSA_RUNTIME_FAILED"
    fi
}

lsa_framework_refresh_runtime() {
    local id module
    for id in "${LSA_PROVIDER_IDS[@]}"; do
        LSA_PROVIDER_RUNTIME["$id"]="$(lsa__runtime_callback "${LSA_PROVIDER_STATUS[$id]}" "$id")"
    done
    for module in "${!LSA_SELECTED_BACKEND[@]}"; do
        id="${LSA_SELECTED_BACKEND[$module]}"
        LSA_BACKEND_RUNTIME["$id"]="$(lsa__runtime_callback "${LSA_BACKEND_STATUS[$id]}" "$id")"
    done
}

lsa__safe_field() {
    printf '%s' "$1" | tr '\t\r\n' '   '
}

lsa_framework_write_state() {
    local phase="$1" id module capability
    {
        printf 'phase\t%s\n' "$(lsa__safe_field "$phase")"
        printf 'generated_utc\t%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        printf 'schema\t1\n'
    } >"$LSA_RUNTIME_DIR/state.tsv"
    {
        printf 'capability\tprovider\n'
        for capability in "${!LSA_CAPABILITIES[@]}"; do
            printf '%s\t%s\n' "$capability" "${LSA_CAPABILITY_PROVIDER[$capability]}"
        done | sort
    } >"$LSA_RUNTIME_DIR/capabilities.tsv"
    {
        printf 'id\tclass\tpriority\tprobe\truntime\trequires\tprovides\treason\n'
        for id in "${LSA_PROVIDER_IDS[@]}"; do
            printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
                "$id" "${LSA_PROVIDER_CLASS[$id]}" "${LSA_PROVIDER_PRIORITY[$id]}" \
                "${LSA_PROVIDER_RESULT[$id]:-UNKNOWN}" "${LSA_PROVIDER_RUNTIME[$id]:-UNKNOWN}" \
                "${LSA_PROVIDER_REQUIRES[$id]}" "${LSA_PROVIDER_PROVIDES[$id]}" \
                "$(lsa__safe_field "${LSA_PROVIDER_REASON[$id]:-not probed}")"
        done
    } >"$LSA_RUNTIME_DIR/providers.tsv"
    {
        printf 'module\tid\ttier\tpriority\tclass\tdevice_optimized\tselected\tpolicy\tprobe\truntime\trequires\tprovides\treason\n'
        for id in "${LSA_BACKEND_IDS[@]}"; do
            module="${LSA_BACKEND_MODULE[$id]}"
            printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
                "$module" "$id" "${LSA_BACKEND_TIER[$id]}" "${LSA_BACKEND_PRIORITY[$id]}" \
                "${LSA_BACKEND_CLASS[$id]}" "${LSA_BACKEND_DEVICE_OPTIMIZED[$id]}" \
                "$([ "${LSA_SELECTED_BACKEND[$module]:-}" = "$id" ] && printf YES || printf NO)" \
                "${LSA_BACKEND_POLICY[$id]:-NOT_EVALUATED}" \
                "${LSA_BACKEND_RESULT[$id]:-UNKNOWN}" "${LSA_BACKEND_RUNTIME[$id]:-UNKNOWN}" \
                "${LSA_BACKEND_REQUIRES[$id]}" "${LSA_BACKEND_PROVIDES[$id]}" \
                "$(lsa__safe_field "${LSA_BACKEND_REASON[$id]:-not probed}")"
        done
    } >"$LSA_RUNTIME_DIR/backends.tsv"
    # A failed early bootstrap can enter teardown before the first framework
    # refresh loads architecture.sh.  Persist architecture evidence when it is
    # loaded, but never turn that cleanup path into a second failure.
    if declare -F lsa_architecture_write_state >/dev/null 2>&1; then
        lsa_architecture_write_state
    fi
}

lsa_framework_report() {
    local verbose="${1:-}" module id tier runtime optimized candidate has_rejection callback
    printf 'LSA Platform Report\n'
    printf '%-20s %s\n' 'Android' "$(getprop ro.build.version.release 2>/dev/null || printf unknown) / API $(getprop ro.build.version.sdk 2>/dev/null || printf unknown)"
    printf '%-20s %s (%s)\n' 'Android ABI' "$LSA_ARCH_ANDROID_ABI_RAW" "$LSA_ARCH_ANDROID_ABI"
    printf '%-20s %s (%s)\n' 'Kernel architecture' "$LSA_ARCH_KERNEL_RAW" "$LSA_ARCH_KERNEL"
    printf '%-20s %s (%s)\n' 'Termux userspace' "$LSA_ARCH_TERMUX_RAW" "$LSA_ARCH_TERMUX"
    printf '%-20s %s (%s)\n' 'Linux rootfs' "$LSA_ARCH_ROOTFS_RAW" "$LSA_ARCH_ROOTFS"
    printf '%-20s %s\n' 'Kernel' "$(uname -r 2>/dev/null || printf unknown)"
    printf '%-20s %s\n' 'SELinux' "$(getenforce 2>/dev/null || printf unknown)"
    printf '\n'
    while IFS= read -r module; do
        id="${LSA_SELECTED_BACKEND[$module]:-}"
        if [ -z "$id" ]; then
            has_rejection=0
            while IFS= read -r candidate; do
                [ "${LSA_BACKEND_POLICY[$candidate]:-}" = REJECTED ] && has_rejection=1
            done < <(lsa__backend_candidates "$module")
            if [ "$has_rejection" = 1 ]; then
                printf '%-20s NO ACCEPTED BACKEND\n' "$module"
            else
                printf '%-20s UNSUPPORTED\n' "$module"
            fi
            if [ "$verbose" = '--verbose' ]; then
                while IFS= read -r candidate; do
                    [ -n "$candidate" ] || continue
                    printf '  tier %-3s backend=%s\n' "${LSA_BACKEND_TIER[$candidate]}" "$candidate"
                    printf '    probe              %s\n' "${LSA_BACKEND_RESULT[$candidate]:-UNKNOWN}"
                    if [ "${LSA_BACKEND_POLICY[$candidate]:-}" = REJECTED ]; then
                        printf '    selection          REJECTED BY USER\n'
                    else
                        printf '    selection          NOT SELECTED\n'
                    fi
                    printf '    diagnostics        %s\n' "${LSA_BACKEND_REASON[$candidate]:-not probed}"
                done < <(lsa__backend_candidates "$module")
            fi
            continue
        fi
        tier="${LSA_BACKEND_TIER[$id]}"
        runtime="${LSA_BACKEND_RUNTIME[$id]:-UNKNOWN}"
        printf '%-20s TIER %s / %s\n' "$module" "$tier" "$runtime"
        if [ "$verbose" = '--verbose' ]; then
            optimized="${LSA_BACKEND_DEVICE_OPTIMIZED[$id]}"
            printf '  backend            %s\n' "$id"
            printf '  support            %s\n' "${LSA_BACKEND_RESULT[$id]}"
            printf '  device optimized   %s\n' "$optimized"
            printf '  requires           %s\n' "${LSA_BACKEND_REQUIRES[$id]:-(none)}"
            printf '  provides           %s\n' "${LSA_BACKEND_PROVIDES[$id]:-(none)}"
            printf '  diagnostics        %s\n' "${LSA_BACKEND_REASON[$id]}"
            printf '  candidates\n'
            while IFS= read -r candidate; do
                [ -n "$candidate" ] || continue
                printf '    tier %-3s backend=%s\n' "${LSA_BACKEND_TIER[$candidate]}" "$candidate"
                printf '      probe            %s\n' "${LSA_BACKEND_RESULT[$candidate]:-UNKNOWN}"
                if [ "$candidate" = "$id" ]; then
                    printf '      selection        SELECTED\n'
                elif [ "${LSA_BACKEND_POLICY[$candidate]:-}" = REJECTED ]; then
                    printf '      selection        REJECTED BY USER\n'
                else
                    printf '      selection        NOT SELECTED\n'
                fi
                printf '      diagnostics      %s\n' "${LSA_BACKEND_REASON[$candidate]:-not probed}"
            done < <(lsa__backend_candidates "$module")
        fi
    done < <(lsa__modules)
    if [ "${#LSA_REPORT_HOOK_IDS[@]}" -gt 0 ]; then
        printf '\n'
        for id in "${LSA_REPORT_HOOK_IDS[@]}"; do
            callback="${LSA_REPORT_HOOK_CALLBACK[$id]:-}"
            [ -n "$callback" ] || continue
            if declare -F "$callback" >/dev/null 2>&1; then
                "$callback" "$verbose" || lsa_framework_log "report hook failed: $id"
            else
                lsa_framework_log "report hook callback missing: $id"
            fi
        done
    fi
}

lsa_framework_lifecycle() {
    local action="$1" module id callback
    for module in "${!LSA_SELECTED_BACKEND[@]}"; do
        lsa_framework_lifecycle_module "$action" "$module" || return 1
    done
}

lsa_framework_lifecycle_module() {
    local action="$1" module="$2" id callback
    id="${LSA_SELECTED_BACKEND[$module]:-}"
    if [ -z "$id" ]; then
        lsa_framework_log "$action skipped module=$module: no selected backend"
        return 3
    fi
    if [ "$action" = start ]; then
        callback="${LSA_BACKEND_START[$id]}"
    else
        callback="${LSA_BACKEND_STOP[$id]}"
    fi
    lsa__run_callback "$callback" "$id" || {
        lsa_framework_log "$action failed backend=$id: $LSA_CALLBACK_OUTPUT"
        return 1
    }
}

lsa_framework_health_module() {
    local module="$1" id callback
    id="${LSA_SELECTED_BACKEND[$module]:-}"
    if [ -z "$id" ]; then
        printf '%s\tUNSUPPORTED\tno selected backend\n' "$module"
        return 3
    fi
    callback="${LSA_BACKEND_HEALTH[$id]:-}"
    if [ -z "$callback" ]; then
        printf '%s\tUNKNOWN\tbackend has no health callback\n' "$module"
        return 0
    fi
    if lsa__run_callback "$callback" "$id"; then
        printf '%s\tPASS\t%s\n' "$module" "${LSA_CALLBACK_OUTPUT:-health check passed}"
    else
        printf '%s\tFAIL\t%s\n' "$module" "${LSA_CALLBACK_OUTPUT:-health callback failed}"
        return 1
    fi
}

lsa_framework_health() {
    local module overall=0
    printf 'module\tresult\tdetail\n'
    while IFS= read -r module; do
        lsa_framework_health_module "$module" || overall=1
    done < <(lsa__modules)
    return "$overall"
}

lsa_framework_refresh() {
    local phase="${1:-manual}"
    lsa_framework_load
    lsa_framework_probe_primitives
    lsa_framework_probe_providers
    lsa_framework_select_backends
    lsa_framework_refresh_runtime
    lsa_framework_write_state "$phase"
    lsa_framework_log "refresh phase=$phase providers=${#LSA_PROVIDER_IDS[@]} backends=${#LSA_BACKEND_IDS[@]} capabilities=${#LSA_CAPABILITIES[@]}"
}
