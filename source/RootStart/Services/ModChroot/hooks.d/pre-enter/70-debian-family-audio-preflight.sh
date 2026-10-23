#!/data/data/com.termux/files/usr/bin/bash
# Hooks may be sourced by ModChroot or executed independently depending on
# their packaged file mode.  Load the module helper when this hook is executed
# so the audio check is not silently skipped with "command not found".
if ! declare -F debian_family_audio_preflight >/dev/null 2>&1; then
    BASE="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
    # shellcheck source=/dev/null
    source "$BASE/config/config.sh"
    # shellcheck source=/dev/null
    source "$BASE/lib/logging.sh"
    # shellcheck source=/dev/null
    source "$BASE/lib/debian_family.sh"
fi

debian_family_audio_preflight || true
