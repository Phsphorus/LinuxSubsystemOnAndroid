if [ -d "$GPUBRIDGE_RUN" ]; then
  mount_if_needed "$GPUBRIDGE_RUN" \
    "$CHROOT_DIR/mnt/gpubridge" \
    "--bind"
else
  log "gpubridge: runtime directory missing; skip mount"
fi
