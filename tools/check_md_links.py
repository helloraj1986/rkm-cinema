"""Check that every relative markdown link in the repo actually resolves.

    python3 tools/check_md_links.py

Written after moving ARCHITECTURE.md / PROGRESS.md / TAILSCALE_HOSTING.md into
docs/: a move silently breaks relative links, and a doc tree that lies about where
things are is worse than no docs. Exits 1 when anything is broken, so it can gate a
commit.

Ignores: http(s)/mailto links, pure #anchors, and image URLs.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__", ".vite", "data"}
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def md_files() -> list[Path]:
    return sorted(
        p for p in REPO.rglob("*.md")
        if not any(part in SKIP_DIRS for part in p.parts)
    )


def check(path: Path) -> list[tuple[str, str]]:
    """Return [(target, why)] for links in `path` that do not resolve."""
    broken: list[tuple[str, str]] = []
    for raw in LINK.findall(path.read_text(encoding="utf-8", errors="replace")):
        target = raw.strip().split(" ")[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        clean = target.split("#", 1)[0]
        if not clean:
            continue
        resolved = (path.parent / clean).resolve()
        if not resolved.exists():
            why = "outside the repo" if REPO not in resolved.parents and resolved != REPO \
                else "missing"
            broken.append((target, why))
    return broken


def main() -> int:
    files = md_files()
    total_links = 0
    failures: list[tuple[Path, str, str]] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        total_links += len([t for t in LINK.findall(text)
                            if not t.startswith(("http", "mailto", "#"))])
        for target, why in check(path):
            failures.append((path.relative_to(REPO), target, why))

    print(f"checked {len(files)} markdown files, {total_links} relative links")
    if not failures:
        print("all links resolve")
        return 0
    print(f"\n{len(failures)} broken link(s):")
    for rel, target, why in failures:
        print(f"  {rel}: {target}  ({why})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
