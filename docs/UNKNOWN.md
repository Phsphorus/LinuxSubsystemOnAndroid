# Unresolved items

- The package does not prove system D-Bus policy/service activation. The SensorProxy code needs it, but live D-Bus policy and activation ownership require a separate rootfs audit.
- The known generated `iio-sensor-proxy` launcher points to `sensorproxy/LSASensorProxy.py`, while the packaged injected source is under `sensors/`. The live rootfs currently has no file in that `sensorproxy` directory. This must be repaired as a distinct compatibility change, not hidden by a framework claim.
- The live N6000 H.264 proof does not validate H.265, device portability, sustained encoding, or teardown of a full video capture session.
- `NonRootStart/Services/DNS` exists but is not in the canonical NonRootStart service order. It remains inactive historical code pending manual-caller evidence.
- The old public labels in snapshot filenames are historical. New tier policy is carried only by backend metadata and is module-local.
