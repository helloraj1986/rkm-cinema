"""Round-trip check for the backup/restore archive shape.

Simulates what the PowerShell scripts do inside the alpine helper container:

    tar czf /backup/<name>.tar.gz -C / config shared      (backup)
    tar xzf /backup/<name>.tar.gz -C /                    (restore)

against stand-in "volumes" (a fake Jellyfin /config with a sqlite db + a metadata
tree, and a /shared runtime.json), then compares every file's sha256 before and
after. The layouts must match exactly: if the archive stored absolute paths, the
restore would write outside the volumes.

Run: python3 tools/verify_state_archive_roundtrip.py
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


def snapshot(mapping) -> dict[str, str]:
    """{canonical-relative-path: sha256} across one or more (root, prefix) pairs."""
    out: dict[str, str] = {}
    for root, prefix in mapping:
        for dirpath, _, files in os.walk(root):
            for name in files:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                with open(full, "rb") as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()
                out[f"{prefix}/{rel}"] = digest
    return out


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="rkm-archive-"))
    vol_config = tmp / "vol-config"
    vol_shared = tmp / "vol-shared"
    (vol_config / "data").mkdir(parents=True)
    (vol_config / "metadata" / "Movies" / "abc123").mkdir(parents=True)
    (vol_shared).mkdir()

    # A stand-in volume: the state file, a metadata tree, and a top-level config file.
    (vol_config / "data" / "jellyfin.db").write_bytes(b"SQLITE-STATE-v1")
    (vol_config / "metadata" / "Movies" / "abc123" / "poster.jpg").write_bytes(b"poster-bytes")
    (vol_config / "config.xml").write_bytes(b"admin-pw-hash")
    (vol_shared / "runtime.json").write_bytes(b'{"JELLYFIN_API_KEY":"abc"}')

    # The container's view: each named volume mounted at /config and /shared.
    root = tmp / "root"
    (root).mkdir()
    shutil.copytree(vol_config, root / "config")
    shutil.copytree(vol_shared, root / "shared")

    archive = tmp / "rkm-state-test.tar.gz"
    cmd = f"tar czf {archive} -C {root} config shared"
    res = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FAIL: tar failed: {res.stderr}")
        return 1

    with tarfile.open(archive) as tf:
        names = tf.getnames()
    print(f"archive: {len(names)} entries")
    for n in names:
        print(f"   {n}")

    failures: list[str] = []
    if not names or not all(n == "config" or n == "shared" or n.startswith(("config/", "shared/"))
                            for n in names):
        failures.append("archive does not use container-relative config/ + shared/ paths")
    # the verification the scripts rely on
    if not any(n.startswith("config/") for n in names):
        failures.append("'config/*' glob would not match - the restore guard would reject this")
    if not any(n.startswith("shared/") for n in names):
        failures.append("'shared/*' glob would not match")

    # restore exactly as the scripts do
    restore = tmp / "restore"
    (restore / "config").mkdir(parents=True)
    (restore / "shared").mkdir(parents=True)
    res = subprocess.run(["sh", "-c", f"tar xzf {archive} -C {restore}"],
                         capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FAIL: extract failed: {res.stderr}")
        return 1

    before = snapshot([(str(vol_config), "config"), (str(vol_shared), "shared")])
    after = snapshot([(str(restore / "config"), "config"), (str(restore / "shared"), "shared")])
    print(f"\nfiles before: {len(before)}  after: {len(after)}")
    missing = sorted(set(before) - set(after))
    extra = sorted(set(after) - set(before))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    if missing:
        failures.append(f"missing after restore: {missing}")
    if extra:
        failures.append(f"unexpected after restore: {extra}")
    if changed:
        failures.append(f"content changed: {changed}")

    for key in sorted(before):
        print(f"   {key:45} {before[key][:12]} -> {after.get(key, 'MISSING')[:12]}")

    if failures:
        print("\nFAILED:")
        for f in failures:
            print("   -", f)
        return 1
    print("\nROUND-TRIP OK: byte-identical, container-relative layout confirmed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
