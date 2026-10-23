#!/data/data/com.termux/files/usr/bin/bash
# Runs after ModChroot has installed its DNS routing/resolver configuration.
# Hooks may be sourced by ModChroot or executed independently depending on
# package file modes, so load their module-owned helpers when needed.
if ! declare -F debian_family_provision >/dev/null 2>&1; then
    BASE="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
    # shellcheck source=/dev/null
    source "$BASE/config/config.sh"
    # shellcheck source=/dev/null
    source "$BASE/lib/logging.sh"
    # shellcheck source=/dev/null
    source "$BASE/lib/debian_family.sh"
fi

debian_family_provision || true
