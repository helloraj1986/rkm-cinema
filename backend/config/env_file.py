"""The ONE `.env` parser — shared by every component that reads a `.env` file.

Why this module exists (2026-09-12, ``SUBTITLES_OPENSUBTITLES_PLAN`` Phase 0): the
same `.env` was read by three separate implementations — ``render_config.py`` (the
host-side renderer that Compose is compared against), ``config.settings`` (the api's
own file layer) and ``tools/rkm_common`` (the probe tools). Two of them disagreed
about quoting: the renderer took a quoted value verbatim, while the api's reader did
a bare ``partition("=")`` + ``strip()`` and kept the quotes — one file, two values,
which is exactly how ``KEY='p#ss w0rd'`` "works in Docker and fails locally", and how
a password containing ``#`` gets silently truncated.

The rules implemented here match Docker Compose / godotenv, i.e. what the containers
actually receive:

* blank lines and lines starting with ``#`` are ignored;
* an optional ``export `` prefix is not part of the key name;
* a value wrapped in MATCHING ``"`` or ``'`` is taken verbatim (quotes stripped);
* otherwise a ``␣#`` (a hash preceded by whitespace) starts an inline comment and is
  dropped — so ``D:/a#b`` survives, but ``D:/a   # note`` does not;
* a leading UTF-8 BOM (``\\ufeff``) is stripped from the text and from the first key.

The BOM rule is not cosmetic. Reading the file as ``utf-8`` (rather than
``utf-8-sig``) is what a config block pasted out of a chat message or saved by a
Windows editor produces, and a leading BOM silently renames the FIRST key to
``\\ufeffKEY``: the setting then vanishes with no error anywhere. This module never
writes a file — the writers stay where they are.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

#: A UTF-8 byte-order mark as a str. Stripped from a file's head and from a key.
BOM = "\ufeff"

#: Shell-style prefix that is syntax, not part of the name.
_EXPORT = "export "


def strip_bom(text: str) -> str:
    """Drop a leading UTF-8 BOM (and any duplicated ones) from a file's text."""
    return text.lstrip(BOM) if text else text


def strip_inline_comment(value: str) -> str:
    """Drop a trailing ``␣#…`` comment from an UNQUOTED .env value.

    A ``#`` only starts a comment when preceded by whitespace, so ``D:/a#b`` and
    ``pass#word`` survive. Quoted values never reach here — a literal ``' #'`` is
    still expressible by quoting the value.
    """
    idx = value.find(" #")
    return (value[:idx] if idx != -1 else value).rstrip()


def parse_env_line(line: str) -> Optional[Tuple[str, str]]:
    """Parse one .env line into ``(key, value)``, or ``None`` when it carries none."""
    s = strip_bom((line or "").strip())
    if not s or s.startswith("#") or "=" not in s:
        return None
    key, _, value = s.partition("=")
    key = key.strip()
    if key.startswith(_EXPORT):
        key = key[len(_EXPORT):].strip()
    key = key.lstrip(BOM).strip()
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]          # quoted → verbatim between the quotes
    else:
        value = strip_inline_comment(value)
    if not key:
        return None
    return key, value


def parse_env_text(text: str) -> dict:
    """Parse .env file CONTENT (comments, blank lines, ``export``, quotes, BOM)."""
    parsed: dict = {}
    for line in strip_bom(text).splitlines():
        pair = parse_env_line(line)
        if pair:
            parsed[pair[0]] = pair[1]
    return parsed


def parse_env_file(path) -> dict:
    """Parse a .env file. A missing file parses to ``{}`` (never raises)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return {}
    return parse_env_text(text)
