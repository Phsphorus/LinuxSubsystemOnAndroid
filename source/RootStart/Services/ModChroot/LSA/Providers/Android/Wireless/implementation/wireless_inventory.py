#!/data/data/com.termux/files/usr/bin/python
"""Safe, structured Android wireless inventory for the LSA Wireless provider.

This program intentionally performs read-only discovery.  It never changes an
interface, scan, channel, supplicant, P2P group, NAN session, or raw-frame
registration.  Active operations are owned by future backends only after a
separate coexistence/temporary-interface safety decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path


SAFE = {"AVAILABLE", "UNSUPPORTED", "UNKNOWN", "ERROR", "UNVERIFIED"}
EVIDENCE = {"ADVERTISED", "PROBED", "OPERATIONALLY_VERIFIED", "UNVERIFIED"}


def clean(value: object) -> str:
    return re.sub(r"[\t\r\n]+", " ", str(value)).strip() or "-"


def run(command: list[str], timeout: float = 3.0, limit: int = 262144) -> tuple[int, str, str]:
    """Run a discovery command without allowing its descendants to outlive it.

    Android diagnostic commands can spawn a shell pipeline.  Killing only that
    shell on timeout leaves (for example) ``dumpsys`` holding its pipe open,
    which defeats ``subprocess.run(timeout=...)`` and can wedge framework
    discovery.  Give every command its own process group and terminate that
    complete group when its bounded time expires.
    """
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except FileNotFoundError:
        return 127, "", "command unavailable"
    except OSError as error:
        return 126, "", str(error)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (AttributeError, OSError):
            process.kill()
        # Do not call communicate() again here.  Android shell pipelines can
        # leave a descendant holding a capture pipe open even after their
        # parent was killed.  Closing our copies lets this inventory return
        # promptly; any surviving diagnostic child was still sent SIGKILL as
        # part of the process group above.
        for stream in (process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        return 124, "", "operation timed out"
    return process.returncode, stdout[:limit].decode("utf-8", "replace"), stderr[:limit].decode("utf-8", "replace")


def command_path(name: str) -> str | None:
    prefix = os.environ.get("LSA_TERMUX_PREFIX", "/data/data/com.termux/files/usr")
    rootstart = os.environ.get("LSA_ROOTSTART_DIR", "/data/local/RootStart")
    explicit = os.environ.get("LSA_WIRELESS_IW", "") if name == "iw" else ""
    # Root cannot safely execute a binary in private Termux app data under
    # SELinux Enforcing.  The deployer materialises a minimal, root-owned copy
    # of the standard Termux iw package under the LSA-owned tree instead.
    candidates = tuple(path for path in (
        Path(explicit) if explicit else None,
        Path(rootstart) / "Tools" / "iw" / name if name == "iw" else None,
        Path("/system/bin") / name,
        Path("/vendor/bin") / name,
        Path(prefix) / "bin" / name,
    ) if path is not None)
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which(name)


def qualification_context(iw: str) -> dict[str, str]:
    digest = hashlib.sha256()
    try:
        with open(iw, "rb") as handle:
            for block in iter(lambda: handle.read(131072), b""):
                digest.update(block)
    except OSError:
        return {}
    getprop = command_path("getprop") or "/system/bin/getprop"
    build = run([getprop, "ro.build.fingerprint"], timeout=2.0)[1].strip() if os.path.exists(getprop) else "unknown"
    incremental = run([getprop, "ro.build.version.incremental"], timeout=2.0)[1].strip() if os.path.exists(getprop) else "unknown"
    return {
        "schema": "1",
        "kernel_release": os.uname().release,
        "android_build": build or "unknown",
        "android_incremental": incremental or "unknown",
        "iw_sha256": digest.hexdigest(),
    }


class Inventory:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], tuple[str, str, str, str, str, str]] = {}
        self.interfaces: list[str] = []
        self.primary = ""
        self.iw_available = False

    def add(self, category: str, key: str, support: str, evidence: str, value: object, detail: object) -> None:
        if support not in SAFE:
            raise ValueError(f"invalid support state: {support}")
        if evidence not in EVIDENCE:
            raise ValueError(f"invalid evidence state: {evidence}")
        category, key = clean(category), clean(key)
        self.rows[(category, key)] = (category, key, support, evidence, clean(value), clean(detail))

    def read_interfaces(self) -> None:
        net_root = Path("/sys/class/net")
        try:
            names = sorted(path.name for path in net_root.iterdir())
        except OSError as error:
            self.add("interface", "host.primary", "ERROR", "UNVERIFIED", "-", f"cannot enumerate /sys/class/net: {error}")
            return
        self.interfaces = [name for name in names if re.match(r"^(wlan|p2p|ap|swlan)\d+$", name)]
        if not self.interfaces:
            self.add("interface", "host.primary", "UNSUPPORTED", "PROBED", "-", "no Android wireless interface is visible in /sys/class/net")
            return

        route_interface = self.default_route_interface()
        candidates = [name for name in self.interfaces if name.startswith("wlan")]
        self.primary = route_interface if route_interface in self.interfaces else (candidates[0] if candidates else self.interfaces[0])
        self.add("interface", "host.primary", "AVAILABLE", "PROBED", self.primary, "host wireless interface is visible without changing Android ownership")
        for name in self.interfaces:
            self.add("interface", f"host.{name}", "AVAILABLE", "PROBED", name, "visible host network interface")
            self.interface_metrics(name)

        self.add(
            "interface",
            "linux.rootfs.visibility",
            "AVAILABLE" if self.rootfs_sees_interface(self.primary) else "UNVERIFIED",
            "PROBED" if self.rootfs_sees_interface(self.primary) else "UNVERIFIED",
            self.primary,
            "rootfs /sys exposes the host interface" if self.rootfs_sees_interface(self.primary) else "rootfs interface visibility requires an active mounted Linux namespace",
        )

    def rootfs_sees_interface(self, name: str) -> bool:
        rootfs = os.environ.get("LSA_CHROOT_DIR", "/data/local/linux")
        return bool(name and Path(rootfs, "sys", "class", "net", name).exists())

    def default_route_interface(self) -> str:
        ip = command_path("ip")
        if ip:
            code, output, _ = run([ip, "route", "show", "default"], timeout=2.0)
            if code == 0:
                match = re.search(r"\bdev\s+([^\s]+)", output)
                if match:
                    return match.group(1)
        try:
            for line in Path("/proc/net/route").read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
                fields = line.split()
                if len(fields) >= 4 and fields[1] == "00000000" and int(fields[3], 16) & 1:
                    return fields[0]
        except (OSError, ValueError):
            pass
        return ""

    def interface_metrics(self, name: str) -> None:
        root = Path("/sys/class/net") / name
        try:
            carrier = (root / "carrier").read_text().strip()
            operstate = (root / "operstate").read_text().strip()
            self.add("metrics", f"{name}.link", "AVAILABLE", "PROBED", f"carrier={carrier};state={operstate}", "standard sysfs link state")
        except OSError:
            self.add("metrics", f"{name}.link", "UNKNOWN", "UNVERIFIED", "-", "sysfs link state unavailable")
        stats: list[str] = []
        for metric in ("rx_bytes", "tx_bytes", "rx_packets", "tx_packets", "tx_errors", "rx_dropped", "tx_dropped"):
            try:
                stats.append(f"{metric}={(root / 'statistics' / metric).read_text().strip()}")
            except OSError:
                continue
        if stats:
            self.add("metrics", f"{name}.counters", "AVAILABLE", "PROBED", ";".join(stats), "standard /sys/class/net statistics")

    def read_proc_wireless(self) -> None:
        path = Path("/proc/net/wireless")
        if not path.is_file():
            self.add("metrics", "wireless.extensions", "UNKNOWN", "UNVERIFIED", "-", "/proc/net/wireless is unavailable")
            return
        found = False
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[2:]:
            if ":" not in line:
                continue
            name, values = line.split(":", 1)
            fields = values.split()
            if len(fields) < 3:
                continue
            found = True
            self.add("metrics", f"{name.strip()}.wireless_extensions", "AVAILABLE", "PROBED", f"quality={fields[0]};signal={fields[1]};noise={fields[2]}", "legacy kernel wireless statistics")
        if not found:
            self.add("metrics", "wireless.extensions", "UNKNOWN", "UNVERIFIED", "-", "no active wireless-extension metrics")

    def iw_inventory(self) -> None:
        iw = command_path("iw")
        if not iw:
            self.iw_available = False
            for key in ("phy.2ghz", "phy.5ghz", "phy.6ghz", "mode.mesh.advertised", "mode.ibss.advertised", "mode.monitor.advertised", "raw.nl80211.control"):
                category = "phy" if key.startswith("phy") else "mode" if key.startswith("mode") else "raw"
                self.add(category, key, "UNKNOWN", "UNVERIFIED", "-", "iw/nl80211 inspection tool is unavailable")
            return
        self.iw_available = True
        code, output, error = run([iw, "list"], timeout=5.0)
        if code:
            self.add("raw", "nl80211.control", "ERROR", "UNVERIFIED", "-", f"iw list failed: {clean(error or output)}")
            return
        lower = output.lower()
        self.add("raw", "nl80211.control", "AVAILABLE", "PROBED", "iw list", "read-only nl80211 capability discovery succeeded")
        # iw prints frequencies as either ``2412 MHz`` or ``2412.0 MHz``
        # depending on its build.  Treat both forms as the same numerical
        # capability; a formatting difference must not turn every band into
        # a false UNSUPPORTED result.
        frequencies = [int(float(value)) for value in re.findall(r"\*\s*(\d+(?:\.\d+)?)\s+mhz", lower)]
        bands = {
            "phy.2ghz": any(2400 <= value < 2500 for value in frequencies),
            "phy.5ghz": any(4900 <= value < 5925 for value in frequencies),
            "phy.6ghz": any(5925 <= value < 7125 for value in frequencies),
        }
        for key, present in bands.items():
            values = [str(value) for value in frequencies if (2400 <= value < 2500 if key == "phy.2ghz" else 4900 <= value < 5925 if key == "phy.5ghz" else 5925 <= value < 7125)]
            if not frequencies:
                self.add("phy", key, "UNKNOWN", "UNVERIFIED", "-", "iw list did not expose advertised frequencies")
            else:
                self.add("phy", key, "AVAILABLE" if present else "UNSUPPORTED", "ADVERTISED", ",".join(values) or "-", "advertised nl80211 frequencies")
        for feature, marker in (("ht", "ht capabilities"), ("vht", "vht capabilities"), ("he", "he iftypes"), ("eht", "eht iftypes")):
            self.add("phy", f"phy.{feature}", "AVAILABLE" if marker in lower else "UNKNOWN", "ADVERTISED" if marker in lower else "UNVERIFIED", "-", "advertised by iw list" if marker in lower else "not found in iw list")
        mode_markers = {
            "managed": "managed",
            "ap": "ap",
            "monitor": "monitor",
            "mesh": "mesh point",
            "ibss": "ibss",
            "p2p_client": "p2p-client",
            "p2p_go": "p2p-go",
        }
        for mode, marker in mode_markers.items():
            advertised = marker in lower
            self.add("mode", f"mode.{mode}.advertised", "AVAILABLE" if advertised else "UNSUPPORTED", "ADVERTISED", "yes" if advertised else "no", "advertised interface mode")
            if mode in {"mesh", "ibss"}:
                self.add("mode", f"mode.{mode}.create", "UNVERIFIED" if advertised else "UNSUPPORTED", "UNVERIFIED" if advertised else "ADVERTISED", "-", "not attempted because the active Wi-Fi/SSH route is protected")
                self.add(mode, f"{mode}.join", "UNVERIFIED" if advertised else "UNSUPPORTED", "UNVERIFIED" if advertised else "ADVERTISED", "-", "not attempted without a safe LSA-owned temporary interface")
        combinations = re.findall(r"<=\s*(\d+)", lower)
        if combinations:
            self.add("concurrency", "max_interfaces", "AVAILABLE", "ADVERTISED", max(map(int, combinations)), "maximum parsed from valid interface combinations")
        else:
            self.add("concurrency", "max_interfaces", "UNKNOWN", "UNVERIFIED", "-", "iw list did not expose parseable interface combinations")
        self.add("concurrency", "max_channels", "UNKNOWN", "UNVERIFIED", "-", "multiple-channel operation cannot be inferred from interface combinations")

    def framework_inventory(self) -> None:
        # `dumpsys wifi` can block behind Android's live Wi-Fi service on
        # older releases.  Package-feature discovery is a stable, read-only
        # framework-level signal and never makes the inventory depend on the
        # health of that service.
        pm = command_path("pm")
        code, output, error = run([pm, "list", "features"], timeout=2.0, limit=65536) if pm else (127, "", "pm unavailable")
        lower = output.lower()
        aware_feature = "android.hardware.wifi.aware" in lower
        if code == 0:
            self.add("nan", "framework", "AVAILABLE" if aware_feature else "UNSUPPORTED", "ADVERTISED", "android.hardware.wifi.aware" if aware_feature else "-", "Android package-feature advertisement; driver and firmware remain independently unverified")
        elif code == 127:
            self.add("nan", "framework", "UNKNOWN", "UNVERIFIED", "-", "Android package-feature command is unavailable")
        else:
            self.add("nan", "framework", "ERROR", "UNVERIFIED", "-", f"bounded Android package-feature query failed: {clean(error)}")
        self.add("nan", "driver", "UNKNOWN", "UNVERIFIED", "-", "no non-disruptive driver/firmware NAN operation has been run")
        self.add("nan", "publish", "UNKNOWN", "UNVERIFIED", "-", "requires a future LSA-owned Android framework session")
        self.add("nan", "subscribe", "UNKNOWN", "UNVERIFIED", "-", "requires a future LSA-owned Android framework session")
        self.add("nan", "data_path", "UNKNOWN", "UNVERIFIED", "-", "requires a future LSA-owned Android framework session")
        p2p_seen = any(name.startswith("p2p") for name in self.interfaces)
        self.add("p2p", "framework", "AVAILABLE" if p2p_seen else "UNKNOWN", "ADVERTISED" if p2p_seen else "UNVERIFIED", "p2p0" if any(name == "p2p0" for name in self.interfaces) else "-", "Android P2P interface/framework evidence")
        for role in ("client", "go", "group_creation", "group_join", "group_removal"):
            self.add("p2p", role, "UNVERIFIED" if p2p_seen else "UNKNOWN", "UNVERIFIED", "-", "not attempted while preserving active Wi-Fi connectivity")
        self.add("concurrency", "android.framework", "UNKNOWN", "UNVERIFIED", "-", "Android framework does not expose a safe portable numerical concurrency query")

    def raw_primitives(self) -> None:
        for key in ("remain_on_channel", "cancel_remain_on_channel", "mgmt_tx", "mgmt_tx_status", "mgmt_rx_registration", "mgmt_rx", "action_tx", "action_rx"):
            self.add("raw", key, "UNKNOWN", "UNVERIFIED", "-", "not tested: active client interface and SSH route are never repurposed for raw radio operations")

    def apply_qualification(self, path: Path) -> None:
        """Overlay only a context-matching, root-created qualification record.

        The baseline inventory remains useful even without a record.  A stale
        record is intentionally not treated as a current radio conclusion.
        """
        iw = command_path("iw")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.add("qualification", "cache", "UNVERIFIED", "UNVERIFIED", "-", "no persistent active qualification record")
            return
        if not iw or not isinstance(record, dict) or record.get("schema") != 1 or record.get("context") != qualification_context(iw):
            self.add("qualification", "cache", "UNVERIFIED", "UNVERIFIED", "-", "persistent qualification record is absent, malformed, or stale")
            return
        results = record.get("results")
        if not isinstance(results, dict):
            self.add("qualification", "cache", "ERROR", "PROBED", "-", "qualification record has no structured results")
            return
        self.add("qualification", "cache", "AVAILABLE", "PROBED", record.get("mode", "unknown"), f"active qualification completed at {record.get('completed_at', 'unknown')}")
        for name, result in results.items():
            if not isinstance(name, str) or not isinstance(result, dict):
                continue
            support = result.get("support")
            evidence = result.get("evidence")
            if support not in SAFE or evidence not in EVIDENCE:
                continue
            if name.startswith("mode."):
                category, key = "mode", name
            elif name.startswith("ibss."):
                category, key = "ibss", name
            elif name.startswith("mesh."):
                category, key = "mesh", name
            elif name.startswith("p2p."):
                category, key = "p2p", name[len("p2p."):]
            elif name.startswith("raw."):
                category, key = "raw", name[len("raw."):]
            elif name.startswith("concurrency."):
                category, key = "concurrency", name[len("concurrency."):]
            elif name.startswith("qualification."):
                category, key = "qualification", name[len("qualification."):]
            else:
                continue
            self.add(category, key, support, evidence, result.get("value", "-"), result.get("detail", "-"))

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write("category\tkey\tsupport\tevidence\tvalue\tdetail\n")
            for row in sorted(self.rows.values()):
                handle.write("\t".join(row) + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--qualification-record", type=Path)
    args = parser.parse_args()
    inventory = Inventory()
    inventory.read_interfaces()
    inventory.read_proc_wireless()
    inventory.iw_inventory()
    inventory.framework_inventory()
    inventory.raw_primitives()
    if args.qualification_record:
        inventory.apply_qualification(args.qualification_record)
    inventory.add("inventory", "timestamp", "AVAILABLE", "PROBED", int(time.time()), "read-only wireless inventory timestamp")
    inventory.write(args.state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
