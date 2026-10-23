log_init() {
  mkdir -p "$RUNTIME_DIR"
  touch "$LOG_FILE"
  chmod 644 "$LOG_FILE" 2>/dev/null || true
  exec > >(tee -a "$LOG_FILE") 2>&1
}

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}
