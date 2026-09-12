#!/usr/bin/env python3
"""Splice a hand-off block onto the top of docs/PROGRESS.md, with the checks that caught two broken
splices on 2026-09-13. Usage (from the repo root):\n\n    python tools/splice_progress.py /tmp/block-x.md \\\n        --annotate=1="  -> annotated" --annotate=63="  -> also annotated"\n\nTwo splices on 2026-09-13 passed a check that could not fail (a diff of a list against ITSELF, and a\ntail assertion made against the whole document instead of the tail), so the guards below are\ndeliberately redundant: they compare the NEW document against a snapshot taken BEFORE any edit.

Guards, in order:
  * the block itself is whole (starts with `## ▶ `, ends with a newline)
  * exactly ONE more block after the splice
  * the surviving tail is byte-identical to the history, with ONLY the annotated heading lines changed
  * the annotation diff is exactly 2 lines per annotated heading
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

PROGRESS = Path("/workspace/projects/rkm-cinema/docs/PROGRESS.md")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--annotate")]
    annotations = [a.split("=", 1) for a in sys.argv[1:] if a.startswith("--annotate")]
    if not args:
        print("usage: splice_progress.py <block-file> [--annotate=N=TEXT ...]")
        return 2
    block = Path(args[0]).read_text(encoding="utf-8")
    assert block.startswith("## ▶ ") and block.endswith("\n"), "the block is not whole"

    old = PROGRESS.read_text(encoding="utf-8")
    old_before = old.split("\n")
    lines = list(old_before)
    for spec in annotations:
        idx, text = spec[1].split("=", 1)
        n = int(idx)
        assert lines[n - 1].startswith("## ▶ "), f"line {n} is not a block heading"
        lines[n - 1] = lines[n - 1] + text
    annotated = "\n".join(lines)
    new = block + "\n" + annotated + "\n"

    blocks_old = len(re.findall(r"^## ▶ ", old, re.M))
    blocks_new = len(re.findall(r"^## ▶ ", new, re.M))
    assert blocks_new == blocks_old + 1, (blocks_old, blocks_new)
    b = len(block.split("\n"))
    assert new.split("\n")[b:][:-1] == annotated.split("\n"), "the tail changed beyond the annotations"
    d = [l for l in difflib.unified_diff(old_before, annotated.split("\n"), n=0, lineterm="")
         if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
    assert len(d) == 2 * len(annotations), f"annotation diff was {len(d)} lines, expected {2 * len(annotations)}"

    PROGRESS.write_text(new, encoding="utf-8")
    print(f"SPLICED ok — blocks: {blocks_new} | lines: {len(new.split(chr(10)))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
