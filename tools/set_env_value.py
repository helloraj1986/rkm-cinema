#!/usr/bin/env python3
"""Set ONE value in the repo `.env`, safely — the engine behind `rkm-cinema.ps1 auth on|off`.

**Why this exists rather than a line of PowerShell.** `.env` is the single source for the whole stack
(compose interpolates it, `render_config.py` renders it, every tool reads it), so an edit that drops a
comment, reorders the file or duplicates a key is a config corruption the user has to notice
themselves. The rules therefore live in **one tested place** — this tool, on top of
`render_config.py::write_env_key`, which already owns "append or replace one key, preserve everything
else". What this adds:

* a **backup** before any write (`.env.bak-YYYYMMDD-HHMM`, beside the file);
* a **no-op when the value is already right** — no write, no backup, nothing to explain;
* a refusal for values that would break the file (a newline in a value is a second line);
* a `--dry-run`, and a one-line report of what it did.

    python tools/set_env_value.py RKM_AUTH_REQUIRED true
    python tools/set_env_value.py RKM_AUTH_REQUIRED true --dry-run
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for extra in (ROOT, ROOT / "backend"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from config.env_file import parse_env_file  # noqa: E402
from render_config import write_env_key  # noqa: E402

DEFAULT_FILE = ROOT / ".env"


class ValueError_(ValueError):
    """A value we refuse to write, so nothing half-applied ever reaches the file."""


def _validate(key: str, value: str) -> None:
    if not key or not key.strip():
        raise ValueError_("a key is required")
    if any(ch in key for ch in "=\n\r\t #"):
        raise ValueError_(f"not a usable .env key: {key!r}")
    if any(ch in value for ch in "\n\r"):
        raise ValueError_(
            f"a value cannot contain a line break — {value[:40]!r} would add a second line to .env")


def set_value(path: Path, key: str, value: str, *, dry_run: bool = False,
              backup: bool = True) -> dict:
    """Set ``key`` to ``value`` in ``path``. Returns what happened (never raises for a no-op)."""
    _validate(key, value)
    path = Path(path)
    current = parse_env_file(path).get(key) if path.exists() else None
    if current is not None and str(current).strip() == value:
        return {"key": key, "old": current, "new": value, "changed": False, "backup": None,
                "path": str(path)}
    made = None
    if not dry_run:
        if backup and path.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M")
            made = path.with_name(f"{path.name}.bak-{stamp}")
            shutil.copy2(path, made)
        write_env_key(path, key, value)
    return {"key": key, "old": current, "new": value, "changed": True,
            "backup": str(made) if made else None, "path": str(path), "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Set one value in the repo .env")
    ap.add_argument("key")
    ap.add_argument("value")
    ap.add_argument("--file", default=str(DEFAULT_FILE), help="the .env to edit")
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    ap.add_argument("--no-backup", action="store_true", help="skip the .env backup")
    args = ap.parse_args(argv)

    try:
        result = set_value(Path(args.file), args.key, args.value,
                           dry_run=args.dry_run, backup=not args.no_backup)
    except ValueError_ as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError:
        print(f"REFUSED: no such file: {args.file}", file=sys.stderr)
        return 2

    where = Path(result["path"]).name
    if not result["changed"]:
        print(f"{result['key']} is already {result['new']} in {where} — nothing to do")
        return 0
    verb = "would set" if result.get("dry_run") else "set"
    print(f"{verb} {result['key']}: {result['old'] if result['old'] is not None else '(absent)'}"
          f" -> {result['new']}  ({where})")
    if result.get("backup"):
        print(f"backup: {Path(result['backup']).name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
