pid_read() {
  [ -f "$1" ] && cat "$1" 2>/dev/null || true
}

pid_valid() {
  echo "${1:-}" | grep -Eq '^[0-9]+$'
}

pid_alive() {
  pid_valid "$1" && kill -0 "$1" 2>/dev/null
}

pid_kill() {
  local pid="$1" sig="${2:-TERM}"
  pid_valid "$pid" && kill "-$sig" "$pid" 2>/dev/null || true
}
