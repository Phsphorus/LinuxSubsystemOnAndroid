#!/data/data/com.termux/files/usr/bin/python
"""Bounded, root-owned Wireless qualification for LSA.

Normal LSA startup must not repeatedly disrupt Android Wi-Fi.  This tool is
therefore deliberately separate from the read-only inventory: it records a
per-device result once, associates it with the radio-relevant environment,
and only reruns active operations when the record is stale or explicitly
requested.  It uses the standard ``iw`` utility for every operation it can
express.  A missing ``iw`` operation is recorded as a tooling limitation, not
as a claim about the underlying radio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path


SCHEMA = 1
MAX_CAPTURE = 262144
SUPPORT = {"AVAILABLE", "UNSUPPORTED", "UNKNOWN", "ERROR", "UNVERIFIED"}
EVIDENCE = {"ADVERTISED", "PROBED", "OPERATIONALLY_VERIFIED", "UNVERIFIED"}


def scrub(value: object) -> str:
    return re.sub(r"[\r\n\t]+", " ", str(value)).strip() or "-"


def run(command: list[str], environment: dict[str, str], timeout: float = 5.0) -> tuple[int, str, str]:
    """Execute a fixed argv operation with bounded output and lifetime."""
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
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
        except OSError:
            process.kill()
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        return 124, "", "operation timed out"
    return process.returncode, stdout[:MAX_CAPTURE].decode("utf-8", "replace"), stderr[:MAX_CAPTURE].decode("utf-8", "replace")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(131072), b""):
            digest.update(block)
    return digest.hexdigest()


def android_property(name: str) -> str:
    code, output, _ = run(["/system/bin/getprop", name], {"PATH": "/system/bin:/system/xbin"}, timeout=2.0)
    return output.strip() if code == 0 else "unknown"


def current_context(iw: Path) -> dict[str, str]:
    return {
        "schema": str(SCHEMA),
        "kernel_release": os.uname().release,
        "android_build": android_property("ro.build.fingerprint"),
        "android_incremental": android_property("ro.build.version.incremental"),
        "iw_sha256": sha256(iw),
    }


def read_record(path: Path) -> dict | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def record_is_current(path: Path, iw: Path) -> bool:
    record = read_record(path)
    return bool(record and record.get("schema") == SCHEMA and record.get("context") == current_context(iw))


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(str(temporary), flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class Qualification:
    def __init__(self, iw: Path, evidence_dir: Path, mode: str) -> None:
        self.iw = str(iw)
        self.mode = mode
        evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(evidence_dir, 0o700)
        self.environment = {
            "PATH": "/system/bin:/system/xbin",
            "LD_LIBRARY_PATH": os.environ.get("LSA_WIRELESS_IW_LIB", ""),
            "HOME": "/",
            # No privileged command inherits the ambient shared Android tmp.
            # This directory is root-owned and 0700 before it becomes visible
            # to iw or any future generic helper.
            "TMPDIR": str(evidence_dir),
        }
        self.evidence_dir = evidence_dir
        self.results: dict[str, dict[str, str]] = {}
        self.created: set[str] = set()
        self.iw_list = ""
        self.iw_dev = ""
        self.primary = ""

    def add(self, key: str, support: str, evidence: str, value: object = "-", detail: object = "-") -> None:
        if support not in SUPPORT or evidence not in EVIDENCE:
            raise ValueError(f"invalid qualification state for {key}")
        self.results[key] = {
            "support": support,
            "evidence": evidence,
            "value": scrub(value),
            "detail": scrub(detail),
        }

    def evidence(self, name: str, content: str) -> None:
        self.evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.evidence_dir, 0o700)
        target = self.evidence_dir / name
        temporary = self.evidence_dir / f".{name}.{os.getpid()}.tmp"
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content[:MAX_CAPTURE])
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)

    def command(self, arguments: list[str], timeout: float = 5.0) -> tuple[int, str, str]:
        return run([self.iw, *arguments], self.environment, timeout)

    @staticmethod
    def conclusion(code: int, output: str, error: str) -> tuple[str, str]:
        text = scrub(error or output)
        lower = text.lower()
        if code == 0:
            return "AVAILABLE", text
        if any(marker in lower for marker in ("operation not supported", "not supported", "eopnotsupp")):
            return "UNSUPPORTED", text
        return "ERROR", text

    def capture_baseline(self) -> None:
        for name, arguments in (("iw-dev.txt", ["dev"]), ("iw-list.txt", ["list"]), ("iw-reg-get.txt", ["reg", "get"])):
            code, output, error = self.command(arguments)
            text = output + ("\nSTDERR: " + error if error else "")
            self.evidence(name, text)
            if arguments == ["dev"]:
                self.iw_dev = output
            elif arguments == ["list"]:
                self.iw_list = output
        # Android commonly keeps per-interface routing tables.  A bare
        # ``ip route show default`` can therefore select a stale LSA-created
        # route rather than the route carrying the management connection.
        # Route lookup is both standard rtnetlink and an operational answer.
        route_code, route, route_error = run(["/system/bin/ip", "route", "get", "1.1.1.1"], self.environment, timeout=3.0)
        if route_code:
            route_code, route, route_error = run(["/system/bin/ip", "route", "show", "default"], self.environment, timeout=3.0)
        self.evidence("route-before.txt", route + ("\nSTDERR: " + route_error if route_error else ""))
        match = re.search(r"\bdev\s+([^\s]+)", route) if route_code == 0 else None
        wlan = re.search(r"^\s*Interface\s+(wlan\d+)\s*$", self.iw_dev, re.MULTILINE)
        self.primary = match.group(1) if match else (wlan.group(1) if wlan else "")
        self.add("qualification.cache", "AVAILABLE", "PROBED", self.mode, "active qualification baseline captured")

    def phy_name(self) -> str:
        match = re.search(r"^phy#(\d+)$", self.iw_dev, re.MULTILINE)
        return f"phy{match.group(1)}" if match else ""

    def temporary_name(self, suffix: str) -> str:
        # Linux ifnames are capped at 15 bytes.  The random component prevents
        # collision with an interrupted prior qualification without ever
        # deleting a non-LSA interface.
        return f"lsaq{suffix}{secrets.token_hex(3)}"[:15]

    def delete_owned(self, name: str) -> None:
        if name not in self.created:
            return
        self.command(["dev", name, "del"], timeout=5.0)
        self.created.discard(name)

    def test_mode(self, mode: str, join: str | None = None) -> None:
        name = self.temporary_name(mode[:2])
        phy = self.phy_name()
        if not phy:
            self.add(f"mode.{mode}.create", "ERROR", "PROBED", "-", "iw dev did not expose a PHY name")
            return
        code, output, error = self.command(["phy", phy, "interface", "add", name, "type", mode])
        support, detail = self.conclusion(code, output, error)
        if code != 0:
            self.add(f"mode.{mode}.create", support, "PROBED", "-", f"NEW_INTERFACE failed: {detail}")
            return
        self.created.add(name)
        try:
            up_code, up_output, up_error = run(["/system/bin/ip", "link", "set", "dev", name, "up"], self.environment, timeout=5.0)
            if up_code:
                self.add(f"mode.{mode}.create", "ERROR", "PROBED", name, f"interface created but link-up failed: {scrub(up_error or up_output)}")
                return
            self.add(f"mode.{mode}.create", "AVAILABLE", "OPERATIONALLY_VERIFIED", name, "temporary LSA-owned interface created and raised")
            if join == "ibss":
                code, output, error = self.command(["dev", name, "ibss", "join", f"LSA-{secrets.token_hex(3)}", "2412", "fixed-freq"], timeout=8.0)
                support, detail = self.conclusion(code, output, error)
                self.add("ibss.join", support, "OPERATIONALLY_VERIFIED" if code == 0 else "PROBED", "2412" if code == 0 else "-", f"JOIN_IBSS: {detail}")
                self.command(["dev", name, "ibss", "leave"], timeout=5.0)
            elif join == "mesh":
                code, output, error = self.command(["dev", name, "mesh", "join", f"LSA-{secrets.token_hex(3)}", "freq", "2412"], timeout=8.0)
                support, detail = self.conclusion(code, output, error)
                self.add("mesh.join", support, "OPERATIONALLY_VERIFIED" if code == 0 else "PROBED", "2412" if code == 0 else "-", f"JOIN_MESH: {detail}")
                self.command(["dev", name, "mesh", "leave"], timeout=5.0)
        finally:
            self.delete_owned(name)

    def test_concurrency(self) -> None:
        phy = self.phy_name()
        if not phy:
            self.add("concurrency.verified_temp_interfaces", "ERROR", "PROBED", "-", "PHY name unavailable")
            return
        names = [self.temporary_name("c1"), self.temporary_name("c2")]
        made: list[str] = []
        try:
            for name in names:
                code, output, error = self.command(["phy", phy, "interface", "add", name, "type", "managed"])
                if code:
                    support, detail = self.conclusion(code, output, error)
                    self.add("concurrency.verified_temp_interfaces", support, "PROBED", len(made), f"additional managed interface {len(made) + 1} failed: {detail}")
                    return
                self.created.add(name)
                made.append(name)
                run(["/system/bin/ip", "link", "set", "dev", name, "up"], self.environment, timeout=5.0)
            self.add("concurrency.verified_temp_interfaces", "AVAILABLE", "OPERATIONALLY_VERIFIED", len(made), "two temporary managed interfaces created concurrently")
        finally:
            for name in reversed(made):
                self.delete_owned(name)

    def test_roc(self) -> None:
        if not self.primary:
            self.add("raw.remain_on_channel", "ERROR", "PROBED", "-", "no active wireless interface was identified")
            return
        candidates: list[str] = []
        for line in self.iw_list.splitlines():
            match = re.search(r"\*\s*(\d+(?:\.\d+)?)\s+MHz", line, flags=re.IGNORECASE)
            if match and "disabled" not in line.lower():
                candidates.append(str(int(float(match.group(1)))))
        frequency = next((value for value in candidates if 2400 <= int(value) < 2500), candidates[0] if candidates else "")
        if not frequency:
            self.add("raw.remain_on_channel", "ERROR", "PROBED", "-", "iw list provided no usable frequency for qualification")
            return
        code, output, error = self.command(["dev", self.primary, "roc", "start", frequency, "150"], timeout=3.0)
        support, detail = self.conclusion(code, output, error)
        self.add("raw.remain_on_channel", support, "OPERATIONALLY_VERIFIED" if code == 0 else "PROBED", frequency, f"iw roc start on {self.primary}: {detail}")
        self.add("raw.cancel_remain_on_channel", "ERROR", "PROBED", "-", "standard iw roc start does not expose the netlink ROC cookie needed for a separate cancel test")

    def test_mgmt_registration(self) -> None:
        if not self.primary:
            self.add("raw.mgmt_rx_registration", "ERROR", "PROBED", "-", "no active wireless interface was identified")
            self.add("raw.mgmt_rx", "ERROR", "PROBED", "-", "no active wireless interface was identified")
            return
        command = [self.iw, "dev", self.primary, "mgmt", "dump", "frame", "d0", "00", "count", "1"]
        try:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.environment, start_new_session=True)
            time.sleep(0.5)
            code = process.poll()
            if code is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2.0)
                self.add("raw.mgmt_rx_registration", "AVAILABLE", "PROBED", "d0:00", "iw retained a management-frame registration awaiting input")
                self.add("raw.mgmt_rx", "ERROR", "PROBED", "-", "registration was accepted but this single-device qualification had no peer frame stimulus")
                return
            output, error = process.communicate(timeout=1.0)
            support, detail = self.conclusion(code, output.decode("utf-8", "replace"), error.decode("utf-8", "replace"))
            self.add("raw.mgmt_rx_registration", support, "PROBED", "d0:00", f"iw management registration exited: {detail}")
            self.add("raw.mgmt_rx", "ERROR", "PROBED", "-", "frame delivery was not established")
        except OSError as error:
            self.add("raw.mgmt_rx_registration", "ERROR", "PROBED", "-", str(error))
            self.add("raw.mgmt_rx", "ERROR", "PROBED", "-", "frame delivery was not established")

    def active(self) -> None:
        self.test_mode("managed")
        # iw deliberately exposes NEW_INTERFACE only for the generic types
        # below.  AP is configured through hostapd/Android rather than by an
        # invented iw spelling, so keep that missing control-plane explicit.
        self.add("mode.ap.create", "ERROR", "PROBED", "-", "standard iw does not create AP iftypes; no generic LSA AP control provider is installed")
        self.test_mode("monitor")
        self.test_mode("mesh", "mesh")
        self.test_mode("ibss", "ibss")
        self.add("p2p.device_control", "ERROR", "PROBED", "-", "P2P group qualification requires the generic Android/wpa_supplicant provider, which is not installed yet")
        self.test_concurrency()
        self.test_roc()
        self.test_mgmt_registration()
        helper = os.environ.get("LSA_WIRELESS_NL80211", "")
        if helper and os.path.isfile(helper) and os.access(helper, os.X_OK):
            helper_detail = "generic frame-TX helper is installed; a two-peer action-frame stimulus remains required for operational verification"
        else:
            helper_detail = "standard iw has no arbitrary NL80211_CMD_FRAME transmit operation and no generic LSA frame-TX helper is installed"
        self.add("raw.mgmt_tx", "ERROR", "PROBED", "-", helper_detail)
        self.add("raw.mgmt_tx_status", "ERROR", "PROBED", "-", helper_detail)
        self.add("raw.action_tx", "ERROR", "PROBED", "-", helper_detail)
        self.add("raw.action_rx", "ERROR", "PROBED", "-", "requires an actual peer action-frame transmitter")

    def execute(self) -> dict:
        self.capture_baseline()
        try:
            if self.mode == "aggressive":
                self.active()
            else:
                self.add("qualification.active", "UNVERIFIED", "UNVERIFIED", "safe", "administrative policy disabled disruptive first-run qualification")
        finally:
            for name in list(self.created):
                self.delete_owned(name)
            code, output, error = self.command(["dev"], timeout=5.0)
            self.evidence("iw-dev-after.txt", output + ("\nSTDERR: " + error if error else ""))
        return {
            "schema": SCHEMA,
            "completed_at": int(time.time()),
            "mode": self.mode,
            "context": current_context(Path(self.iw)),
            "primary_interface": self.primary,
            "results": self.results,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iw", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("safe", "aggressive"), default="aggressive")
    parser.add_argument("--check", action="store_true", help="exit zero only when the cache matches the current environment")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("qualification requires Android root")
    if not args.iw.is_file() or not os.access(args.iw, os.X_OK):
        parser.error(f"root-owned iw is unavailable: {args.iw}")
    if args.check:
        return 0 if record_is_current(args.record, args.iw) else 1
    record = Qualification(args.iw, args.evidence_dir, args.mode).execute()
    atomic_json(args.record, record)
    print(f"wireless qualification recorded: {args.record}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
