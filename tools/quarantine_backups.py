"""Move only project-owned backup artifacts out of canonical package source.

Workshop and prior-quarantine trees are evidence, not active source, and are
explicitly excluded.  The generated TSV maps the installed path to its local
quarantine copy and records a SHA-256 before the move.
"""
from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "LSALIVE" / "source"
QUARANTINE_BASE = ROOT / "tmp" / "backups" / "source-quarantine"
MANIFEST = ROOT / "LSALIVE" / "docs" / "BAK_QUARANTINE.tsv"
INSTALLED_ROOTS = {
    "RootStart": "/data/local/RootStart",
    "NonRootStart": "/data/data/com.termux/files/home/NonRootStart",
}
PATTERNS = ("*.bak", "*.bak.*", "*.bak-*", "*.backup", "*.old", "*.orig")
EXCLUDED_PARTS = {"Workshop", "bak-quarantine", "Refactor", "__pycache__"}


def is_backup(path: Path) -> bool:
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in PATTERNS)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for data in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(data)
    return hasher.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stamp")
    args = parser.parse_args()
    stamp = args.stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    planned: list[tuple[str, Path, Path, int, str]] = []
    for tree_name, installed_root in INSTALLED_ROOTS.items():
        tree = SOURCE / tree_name
        for source in sorted(tree.rglob("*")):
            if not source.is_file() or not is_backup(source):
                continue
            relative = source.relative_to(tree)
            if any(part in EXCLUDED_PARTS for part in relative.parts):
                continue
            destination = QUARANTINE_BASE / stamp / tree_name / relative
            planned.append((installed_root + "/" + relative.as_posix(), source, destination, source.stat().st_size, digest(source)))

    for installed, source, destination, size, sha in planned:
        print(f"{installed}\t{size}\t{sha}\t{destination}")
    if args.dry_run:
        print(f"dry-run entries={len(planned)}")
        return 0

    if not planned:
        print("entries=0")
        return 0
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    new_manifest = not MANIFEST.exists() or MANIFEST.stat().st_size == 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with MANIFEST.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        if new_manifest:
            writer.writerow(("original_path", "quarantine_path", "size", "sha256", "timestamp_utc", "classification"))
        for installed, source, destination, size, sha in planned:
            destination.parent.mkdir(parents=True, exist_ok=False) if not destination.parent.exists() else None
            shutil.move(str(source), str(destination))
            writer.writerow((installed, destination.relative_to(ROOT).as_posix(), size, sha, now, "OBSOLETE_PROJECT_BACKUP"))
    print(f"entries={len(planned)} manifest={MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
