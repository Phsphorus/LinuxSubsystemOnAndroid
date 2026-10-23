#!/data/data/com.termux/files/usr/bin/bash
# Move project-owned backup artifacts out of active phone source with a manifest.
set -eu

[ "$(id -u)" = 0 ] || { echo 'root is required' >&2; exit 2; }

STAMP="${1:-$(date -u '+%Y%m%dT%H%M%SZ')}"
BASE="/data/local/RootStart/tmp/bak-quarantine/$STAMP"
MANIFEST="$BASE/BAK_QUARANTINE.tsv"
NOW="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

mkdir -p "$BASE"
printf 'original_path\tquarantine_path\tsize\tsha256\ttimestamp_utc\tclassification\n' >"$MANIFEST"

hash_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        toybox sha256sum "$1" | awk '{print $1}'
    fi
}

quarantine_root() {
    local label="$1" root="$2" path relative destination size sha
    [ -d "$root" ] || return 0
    while IFS= read -r path; do
        case "$path" in
            */Workshop/*|*/bak-quarantine/*|*/Refactor/*|*/__pycache__/*) continue ;;
        esac
        relative="${path#"$root"/}"
        destination="$BASE/$label/$relative"
        mkdir -p "$(dirname "$destination")"
        size="$(wc -c <"$path" | tr -d '[:space:]')"
        sha="$(hash_file "$path")"
        mv "$path" "$destination"
        printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$path" "$destination" "$size" "$sha" "$NOW" OBSOLETE_PROJECT_BACKUP >>"$MANIFEST"
    done < <(find "$root" -type f \( -name '*.bak' -o -name '*.bak.*' -o -name '*.bak-*' -o -name '*.backup' -o -name '*.old' -o -name '*.orig' \) 2>/dev/null | sort)
}

quarantine_root RootStart /data/local/RootStart
quarantine_root NonRootStart /data/data/com.termux/files/home/NonRootStart
quarantine_root RootfsLSA /data/local/linux/usr/local/lib/lsa
quarantine_root RootfsHALBridge /data/local/linux/usr/local/lib/halbridge

printf 'quarantine complete: %s\n' "$MANIFEST"
