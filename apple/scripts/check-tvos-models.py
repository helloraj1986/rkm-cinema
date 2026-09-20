#!/usr/bin/env python3
"""Check the tvOS models and endpoints against the FROZEN API contract — on Linux, with no Mac.

    python3 apple/scripts/check-tvos-models.py
    python3 apple/scripts/check-tvos-models.py --falsify

WHY THIS EXISTS
---------------
`docs/APPLE_CLIENTS_PLAN.md` §4.3 wanted `swift-openapi-generator` to produce the tvOS types from
`docs/api/openapi.v1.json`, so there is one source of truth and no handwritten drift. That tool needs
`brew`, a SwiftPM plugin, and a script that has never been run — and none of it can be exercised from
this sandbox, where every Mac-bound artefact is *written, never executed* until a handover round.

So the types are handwritten and THIS is what keeps them honest. It is the same trade the rest of
`apple/` makes (`apple/WORKFLOW.md` §5): push the decision to where it can be RUN, and leave the
unverifiable surface as small as possible. A generated client would be verified by the generator; a
handwritten one is verified here.

WHAT IT CHECKS
--------------
R1  every model in `apple/tvos/RKMCinemaTV/Core/Models/` exists as a schema in the contract;
R2  every JSON key decoded there is a property of that schema — a mistyped key does NOT fail at
    runtime, it silently decodes to nil/0/false, which is the class of bug a TV in another room makes
    undiagnosable;
R3  every NON-optional property of a `Decodable` model is `required` in the contract or carries a
    `default` — i.e. the server has promised to send it. This is not pedantry: in this contract almost
    nothing is `required`, so `LoginResponse.user`, `ProfilesResponse.profiles`,
    `SelectProfileResponse.profile` and both of `MeResponse`'s are optional *in the contract*, and
    decoding them as non-optional would turn a server that omitted one into a decoding failure;
R4  every endpoint string literal in the tvOS sources is a real path in the contract, so a typo is a
    failed round here rather than a 404 on a TV. ⚠ A literal with an **interpolation**
    (`"api/library/folders/\\(folderID)/items"`) is turned into a pattern — each interpolation becomes one
    path component (`[^/]+`) and the result must match a contract path EXACTLY, so the static parts are
    still fully checked; `".../itemss"` fails. This is what lets a parameterised endpoint be written the
    natural way, and Phase C's `/api/jellyfin/hls/{id}/master.m3u8` needs the same rule;
R5  no `Decodable`/`Codable` type is declared OUTSIDE `Core/Models/` unless it is named in
    `NON_CONTRACT_MODELS` below with a reason — otherwise a model could be smuggled past R1-R3 by
    moving the file. (One is: FastAPI's error envelope, which the framework generates and which is not
    in the contract.)
R6  ⚠⚠ **THE SECOND WIRE-FORMAT SOURCE, ADDED 2026-09-19 (decision B0).** The item shape this phase is
    built from is **not** in the contract at all — `FolderItemsResponse.items` and `LibraryResponse.recent`
    are `array` of `object` with `additionalProperties: true`, and continue-watching / recently-watched /
    series-episodes / detail / poster have no documented 200 schema. Extending the contract was considered
    and rejected (see `docs/TVOS_LIBRARY_PLAN.md` §5), so a model that is NOT a contract schema may
    instead declare a **shape source**: a TypeScript interface in the frontend, which is the description
    the app has actually been reading in production. R6 is then R2 against that interface — every JSON key
    decoded must be one of its properties;
R7  and R3 against that interface — a non-optional Swift property must be non-optional there too. (If the
    contract will not promise a field, the interface has to; `item_id` is promised, `thumb` is not.)
    ⚠ R1 is NOT weakened: a model still fails R1 unless it is named in `NON_CONTRACT_MODELS` *and* its
    declared shape source resolves, so exemption stays a deliberate act rather than "any model that
    happens to share a name with an interface".
    ⚠⚠ **What R6/R7 do NOT prove.** They prove the Swift and the TypeScript agree. They do NOT prove
    either agrees with the server: nothing in this sandbox can, with no Docker daemon and no signed-in
    session. The TypeScript side is the closest thing to a production-verified description this repo has
    outside the contract, and saying so is the point rather than implying more.

⚠ `--falsify` REVERTS EVERY RULE ONE AT A TIME and requires the matching check to go red. A gate that
has never been seen to fail is not evidence — that lesson is in `apple/` three times over.

Exit codes: 0 clean · 1 a real failure · 2 the contract or a source file is missing.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTRACT = REPO / "docs" / "api" / "openapi.v1.json"
TVOS = REPO / "apple" / "tvos"
MODEL_DIR = TVOS / "RKMCinemaTV" / "Core" / "Models"
#: The second wire-format source (R6/R7): the frontend's own TypeScript interfaces. See the docstring.
TS_SHAPE_FILE = REPO / "frontend" / "src" / "lib" / "api" / "client.ts"

#: The item shape is undocumented in the contract — this is the ONE reason every Phase B model below is
#: outside it, written once so the entries read as one decision rather than eight excuses.
_ITEM_SHAPE_REASON = (
    "The item shape is NOT in the frozen contract (B0, 2026-09-19): `FolderItemsResponse.items` and "
    "`LibraryResponse.recent` are `array` of `object` with `additionalProperties: true`, and the "
    "continue-watching / recently-watched / series-episodes routes have no 200 schema. The contract is "
    "deliberately NOT being extended (his decision, 2026-09-19), so the shape source is the frontend's "
    "own TypeScript interface — checked by R6/R7, which is what makes an exemption here `checked against "
    "a second source` rather than `unguarded`."
)

_PLAYER_SHAPE_REASON = (
    "Phase C2: the player's RESPONSE shapes. Every route behind them answers with `{}` documented in the "
    "contract — measured 2026-09-20, five player routes have no 200 schema (playback-info, subtitle, "
    "subtitle-search, subtitle-select, progress) — so each model declares the interface the WEB PLAYER has "
    "been reading in production instead. ⚠ R6/R7 prove the Swift and the TypeScript agree; they do NOT "
    "prove either matches the server."
)

#: Types that are deliberately NOT contract schemas, each with a reason — and, where one exists, a
#: declared **shape source** `(frontend file, interface name)`. R5 fails on anything else found outside
#: `Core/Models/`, so this list is the only way a model escapes R1-R3 — and adding an entry is a
#: deliberate act with a written justification, not an omission.
NON_CONTRACT_MODELS = {
    # ⚠⚠ PHASE C2 — the player. Registered here so the exemption is a deliberate act, not an omission.
    "PlaybackTrack": {"reason": _PLAYER_SHAPE_REASON,
                    "shape": ("frontend/src/lib/api/client.ts", "PlaybackTrack")},
        # ⚠ `bit_depth` keeps its snake_case spelling: the wire says `bit_depth` and so does
        # R6's source (`PlaybackVideo`), while the OTHER four fields are camelCase on the wire.
    "PlaybackVideoFacts": {"reason": _PLAYER_SHAPE_REASON,
                    "shape": ("frontend/src/lib/api/client.ts", "PlaybackVideo")},
    "PreferredSubtitle": {"reason": _PLAYER_SHAPE_REASON,
                    "shape": ("frontend/src/lib/api/client.ts", "PreferredSubtitle")},
    "PlaybackInfo": {"reason": _PLAYER_SHAPE_REASON,
                    "shape": ("frontend/src/lib/api/client.ts", "PlaybackInfo")},
    "SubtitleRow": {"reason": _PLAYER_SHAPE_REASON,
                    "shape": ("frontend/src/lib/api/client.ts", "SubtitleRow")},
    "SubtitleSearch": {"reason": _PLAYER_SHAPE_REASON,
                    "shape": ("frontend/src/lib/api/client.ts", "SubtitleSearchShape")},
    "SubtitleSelection": {"reason": _PLAYER_SHAPE_REASON,
                    "shape": ("frontend/src/lib/api/client.ts", "SubtitleSelectResult")},
    "ErrorEnvelope": {
        "reason": "FastAPI's error envelope is generated by the framework, not by us; it is not in "
                  "the contract and must not be invented into it (see Core/APIClient.swift).",
        # ⚠ No shape source: the framework writes this, so there is no interface in the app that
        # describes it. Declared `None` rather than omitted, so "deliberately without a source" and
        # "someone forgot" are different values.
        "shape": None,
    },
    "MediaItem": {"reason": _ITEM_SHAPE_REASON,
                  "shape": ("frontend/src/lib/api/client.ts", "MediaItem")},
    "EpisodeContext": {"reason": _ITEM_SHAPE_REASON + " This one is INLINE in that interface, so its "
                                 "source is the dotted path `MediaItem.episode`.",
                       "shape": ("frontend/src/lib/api/client.ts", "MediaItem.episode")},
    "EpisodeItem": {"reason": _ITEM_SHAPE_REASON,
                    "shape": ("frontend/src/lib/api/client.ts", "EpisodeShape")},
    "LibraryItemsResponse": {"reason": _ITEM_SHAPE_REASON,
                             "shape": ("frontend/src/lib/api/client.ts", "LibraryItemsShape")},
    "FolderItemsResponse": {"reason": _ITEM_SHAPE_REASON,
                            "shape": ("frontend/src/lib/api/client.ts", "FolderItemsShape")},
    "LibraryRecentResponse": {"reason": _ITEM_SHAPE_REASON,
                              "shape": ("frontend/src/lib/api/client.ts", "LibraryRecentShape")},
    "EpisodesResponse": {"reason": _ITEM_SHAPE_REASON,
                         "shape": ("frontend/src/lib/api/client.ts", "EpisodesShape")},
    # ---- Phase B4 — the item detail screen. `GET /api/jellyfin/detail` has no 200 schema in the contract
    # at all, so the same second source is used: the five interfaces below are what the desktop page and the
    # phone's detail screen read in production.
    "ItemDetail": {"reason": _ITEM_SHAPE_REASON,
                   "shape": ("frontend/src/lib/api/client.ts", "ItemDetail")},
    "DetailPlay": {"reason": _ITEM_SHAPE_REASON,
                   "shape": ("frontend/src/lib/api/client.ts", "DetailPlay")},
    "DetailSeriesContext": {"reason": _ITEM_SHAPE_REASON,
                            "shape": ("frontend/src/lib/api/client.ts", "DetailSeriesContext")},
    "DetailPerson": {"reason": _ITEM_SHAPE_REASON,
                     "shape": ("frontend/src/lib/api/client.ts", "DetailPerson")},
    "DetailPeople": {"reason": _ITEM_SHAPE_REASON,
                     "shape": ("frontend/src/lib/api/client.ts", "DetailPeople")},
}


# --------------------------------------------------------------------------- Swift parsing
def strip_comments_and_strings(text: str) -> tuple[str, list[str]]:
    """Return (code with comments blanked and string literals replaced by "", the literals).

    ⚠ A naive `//`-strip corrupts a file whose string literals contain `//` — `"http://rkm-hp…"` is in
    this very tree — so the scan walks the text once, tracking string and comment state. Literals are
    collected here rather than by a regex over the raw text, because a regex cannot tell a string from
    a doc comment, and a doc comment mentioning `api/status` would then be checked as an endpoint.
    """
    out: list[str] = []
    literals: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        two = text[i:i + 2]
        if two == "//":
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if two == "/*":
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if ch == '"':
            j = i + 1
            buf: list[str] = []
            while j < n:
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j:j + 2])
                    j += 2
                    continue
                if text[j] == '"':
                    break
                buf.append(text[j])
                j += 1
            literals.append("".join(buf))
            # ⚠ The literal is KEPT in the code text, not blanked: `case isAdmin = "is_admin"` must still
            # read as a CodingKeys mapping (blanking it here silently downgraded every snake_case key to
            # its Swift name and made R2 fire on all of them). The walker still advances past the literal,
            # which is what keeps a `//` inside a string from being mistaken for a comment.
            out.append(text[i:j + 1])
            i = j + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out), literals


def block_body(text: str, start: int) -> tuple[str, int]:
    """The brace-matched body of a declaration whose opening `{` is at or after `start`."""
    open_at = text.find("{", start)
    if open_at == -1:
        return "", len(text)
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_at + 1:i], i + 1
    return text[open_at + 1:], len(text)


STRUCT_RE = re.compile(r"\bstruct\s+(\w+)\s*(?::\s*([^\{]+))?\{")
PROPERTY_RE = re.compile(r"^\s*(?:let|var)\s+(\w+)\s*:\s*([^=\n]+?)(\s*=\s*.*)?$", re.M)
CASE_RE = re.compile(r"^\s*case\s+(\w+)\s*(?:=\s*\"([^\"]*)\")?\s*$", re.M)

MODEL_CONFORMANCES = ("Decodable", "Codable", "Encodable")

#: A Swift string interpolation, `\(expr)`, as it survives in a collected string literal. R4 replaces each
#: one with a single path component — see `endpoint_matches`.
INTERPOLATION_RE = re.compile(r"\\\([^)]*\)")


def parse_models(path: Path, root: Path) -> list[dict]:
    """Every `struct` in a Swift file, with its conformances, properties and CodingKeys mapping.

    `root` is threaded through so the reported file path is relative to the tree being checked — which is
    the real repo in a normal run and a TEMP COPY under `--falsify`. (Hardcoding `REPO` here made every
    falsification run die with a `relative_to` ValueError instead of reporting a mutation.)
    """
    code, _ = strip_comments_and_strings(path.read_text(encoding="utf-8"))
    found: list[dict] = []
    for match in STRUCT_RE.finditer(code):
        name, conformances = match.group(1), (match.group(2) or "")
        body, _ = block_body(code, match.start())
        enum_at = body.find("CodingKeys")
        keys: dict[str, str] = {}
        if enum_at != -1:
            enum_body, _ = block_body(body, enum_at)
            for swift_name, json_name in CASE_RE.findall(enum_body):
                keys[swift_name] = json_name or swift_name
        props = []
        for prop_name, prop_type, _default in PROPERTY_RE.findall(body):
            if prop_name == "CodingKeys":
                continue
            # ⚠ A COMPUTED property is not decoded, and this guard is not hypothetical: `warningText`
            # in `ProfilesResponse` matched the regex on the first run and was reported as an invented
            # JSON key. A stored property's type never contains a `{`.
            if "{" in prop_type:
                continue
            props.append({
                "name": prop_name,
                "json_key": keys.get(prop_name, prop_name),
                "type": prop_type.strip(),
                "optional": prop_type.strip().endswith("?"),
            })
        found.append({
            "name": name,
            "conformances": [c.strip() for c in conformances.split(",") if c.strip()],
            "properties": props,
            "coding_key_cases": sorted(keys),
            "has_coding_keys": enum_at != -1,
            "file": str(path.relative_to(root)),
        })
    return found


# --------------------------------------------------------------------------- TypeScript parsing
# ⚠ The second wire-format source (R6/R7). This is deliberately a SMALL parser for the one file the shape
# sources name: top-level `export interface` blocks, and inline `{ … }` object types registered under the
# dotted path `Owner.key`. It is not a TypeScript parser and must not become one — anything it cannot read
# fails loudly (a named source that resolves to nothing is a failure, see R6), never silently.
TS_INTERFACE_RE = re.compile(r"^export\s+interface\s+(\w+)[^{]*\{", re.M)
TS_PROP_RE = re.compile(r"^[ \t]+(\w+)(\?)?\s*:\s*(.*)$", re.M)


def ts_body(text: str, open_at: int) -> str:
    """The brace-matched body of a TypeScript block whose opening `{` is at `open_at`."""
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_at + 1:i]
    return text[open_at + 1:]


def ts_properties(body: str, owner: str, shapes: dict) -> dict:
    """`{property: {"type": str, "optional": bool}}` for one interface body, recursing into inline types.

    ⚠ `optional` is `true` for `key?:` **and** it is what R7 reads, so a `| null` union with no `?` is
    still non-optional here — the union says the value may be null, the `?` says the key may be absent,
    and only the second one decides whether a Swift property of that name may be non-optional.

    ⚠⚠ **`skip_until` IS NOT OPTIONAL — it was a real hole on this function's first run.** A nested
    object's own lines are indented, so `TS_PROP_RE` matched them against the PARENT body too: `MediaItem`
    came back with 19 properties instead of 15, which meant a Swift `number` on the item itself would have
    passed R6 as a legitimate key. What exposed it was the note line printing
    `not decoded: number, season, series_id, series_name` — i.e. the check's own output, not a review.
    (Same shape of failure as `ProfilesResponse.warningText` being parsed as a key: a parser that is right
    about the common case and silently wrong about the nested one.)
    """
    props: dict[str, dict] = {}
    skip_until = 0
    for match in TS_PROP_RE.finditer(body):
        if match.start() < skip_until:
            continue
        name, optional, raw = match.group(1), bool(match.group(2)), match.group(3).strip().rstrip(";").strip()
        props[name] = {"type": raw, "optional": optional}
        if raw == "{":
            # An INLINE object type (`episode?: { number: number; … }`). Registered under the dotted path
            # so a nested Swift model can name its source (`MediaItem.episode`) rather than being excused.
            open_at = body.index("{", match.start())
            inner = ts_body(body, open_at)
            shapes[f"{owner}.{name}"] = ts_properties(inner, f"{owner}.{name}", shapes)
            # Past the closing brace of this inline object — its lines belong to `Owner.name`, not `Owner`.
            skip_until = open_at + len(inner) + 2
    return props


def parse_ts_shapes(path: Path) -> dict:
    """Every interface in a TypeScript file: `name` → property table, plus `Owner.key` for inline types."""
    text = path.read_text(encoding="utf-8")
    shapes: dict[str, dict] = {}
    for match in TS_INTERFACE_RE.finditer(text):
        shapes[match.group(1)] = ts_properties(ts_body(text, text.index("{", match.start())),
                                               match.group(1), shapes)
    return shapes


# --------------------------------------------------------------------------- checks
def endpoint_matches(literal: str, paths: set) -> bool:
    """Does this endpoint literal name a real contract path?

    ⚠ A literal WITHOUT an interpolation matches a path exactly. One WITH an interpolation
    (`api/library/folders/\\(folderID)/items`) becomes a pattern in which each interpolation stands for
    exactly ONE path component — so the static parts are checked character for character and a typo like
    `.../itemss` still fails, while the parameterised form can be written the natural way.
    ⚠ Without this, R4 would reject every parameterised endpoint (it would compare the literal text,
    `\\(folderID)` and all, against the path list) — and Phase C's HLS endpoint is parameterised.
    """
    if INTERPOLATION_RE.search(literal):
        parts = INTERPOLATION_RE.split(literal)
        pattern = "^/" + "[^/]+".join(re.escape(part) for part in parts) + "$"
        return any(re.match(pattern, candidate) for candidate in paths)
    return "/" + literal in paths


def check(root: Path) -> tuple[list[str], list[str]]:
    """Run every rule against `root`. Returns (failures, notes)."""
    failures: list[str] = []
    notes: list[str] = []

    contract_path = root / CONTRACT.relative_to(REPO)
    if not contract_path.is_file():
        raise SystemExit(f"contract not found: {contract_path}")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    schemas = contract.get("components", {}).get("schemas", {})
    paths = set(contract.get("paths", {}))

    tvos = root / TVOS.relative_to(REPO)
    model_dir = root / MODEL_DIR.relative_to(REPO)
    if not model_dir.is_dir():
        raise SystemExit(f"model directory not found: {model_dir}")

    # ---- the second wire-format source, for models the contract does not describe (R6/R7)
    ts_path = root / TS_SHAPE_FILE.relative_to(REPO)
    ts_shapes: dict[str, dict] = {}
    if ts_path.is_file():
        ts_shapes = parse_ts_shapes(ts_path)
    notes.append(
        f"shape sources: {CONTRACT.name} ({len(schemas)} schemas) + {TS_SHAPE_FILE.name} "
        f"({len(ts_shapes)} interface(s))"
    )

    # ---- R1/R2/R3, on every file in Core/Models/
    model_files = sorted(model_dir.glob("*.swift"))
    if not model_files:
        failures.append(f"R1: no models found in {model_dir}")
    checked_keys = 0
    for path in model_files:
        for model in parse_models(path, root):
            contract_conformances = [c for c in model["conformances"] if c in MODEL_CONFORMANCES]
            if not contract_conformances:
                continue  # a plain value type, not wire data — nothing to check
            # ---- R1: where does this model's shape come from? The contract first, then a declared
            # shape source. ⚠ A model the contract does not describe is an "invented model" UNLESS it is
            # named in NON_CONTRACT_MODELS with a source that resolves — so R1 keeps its teeth.
            schema = schemas.get(model["name"])
            from_contract = schema is not None
            if from_contract:
                properties = schema.get("properties", {})
                required = set(schema.get("required", []))
                source = CONTRACT.name
                key_rule, optional_rule = "R2", "R3"
            else:
                exempt = NON_CONTRACT_MODELS.get(model["name"]) or {}
                source_ref = exempt.get("shape")
                if source_ref is None:
                    failures.append(
                        f"R1: {model['file']} declares `{model['name']}`, which is not a schema in "
                        f"{CONTRACT.name} — an invented model"
                    )
                    continue
                shape = ts_shapes.get(source_ref[1])
                if shape is None:
                    why = (f"{source_ref[0]} is missing" if not ts_path.is_file()
                           else f"`{source_ref[1]}` is not an interface there")
                    failures.append(
                        f"R6: {model['name']} declares the shape source `{source_ref[1]}` "
                        f"({source_ref[0]}), which cannot be read — {why}. An unguarded model is worse "
                        f"than an invented one, because it LOOKS checked."
                    )
                    continue
                properties = shape
                required = {k for k, v in shape.items() if not v["optional"]}
                source = f"{source_ref[0]}::{source_ref[1]}"
                key_rule, optional_rule = "R6", "R7"
            decoded = model["conformances"] and (
                "Decodable" in model["conformances"] or "Codable" in model["conformances"]
            )
            # ⚠ R2b — a CodingKeys case with no matching property. It compiles, and it decodes to nothing,
            # so it is invisible until someone wonders why a field is always empty: it is the residue of a
            # rename that only happened on one side. Found by falsification, not by review.
            property_names = {p["name"] for p in model["properties"]}
            for case_name in model["coding_key_cases"]:
                if case_name not in property_names:
                    failures.append(
                        f"R2b: {model['name']}'s CodingKeys declares `{case_name}`, which is not a "
                        f"property of the struct — a key nothing decodes"
                    )
            missing_from_swift = [k for k in properties if k not in {p["json_key"] for p in model["properties"]}]
            for prop in model["properties"]:
                checked_keys += 1
                if prop["json_key"] not in properties:
                    failures.append(
                        f"{key_rule}: {model['name']}.{prop['name']} decodes \"{prop['json_key']}\", "
                        f"which is not a property of {source} — it would silently decode to nil"
                    )
                    continue
                if not decoded or prop["optional"]:
                    continue
                prop_shape = properties[prop["json_key"]]
                # ⚠ `default` is a contract concept; the interface's equivalent is simply whether the key
                # is optional, which is what `required` holds for a shape source.
                promised = prop["json_key"] in required or (from_contract and "default" in prop_shape)
                if not promised:
                    failures.append(
                        f"{optional_rule}: {model['name']}.{prop['name']} is NON-OPTIONAL but "
                        f"\"{prop['json_key']}\" is neither required nor defaulted in {source} — "
                        f"a server that omitted it would fail the decode"
                    )
            notes.append(
                f"{model['name']:24s} {len(model['properties'])} key(s) checked vs {source}"
                + (f", not decoded: {', '.join(missing_from_swift)}" if missing_from_swift else "")
            )

    # ---- R4, endpoint literals anywhere in the tvOS sources
    endpoints = 0
    for path in sorted(tvos.rglob("*.swift")):
        _, literals = strip_comments_and_strings(path.read_text(encoding="utf-8"))
        for literal in literals:
            if not literal.startswith("api/"):
                continue
            endpoints += 1
            if not endpoint_matches(literal, paths):
                failures.append(
                    f"R4: {path.relative_to(root)} uses \"{literal}\", which is not a path in "
                    f"{CONTRACT.name}"
                )
    # ---- R5, wire types hiding outside Core/Models/
    outside = 0
    for path in sorted(tvos.rglob("*.swift")):
        if path.parent == model_dir:
            continue
        for model in parse_models(path, root):
            if not any(c in ("Decodable", "Codable") for c in model["conformances"]):
                continue
            if model["name"] in NON_CONTRACT_MODELS:
                reason = NON_CONTRACT_MODELS[model["name"]]["reason"]
                notes.append(f"{model['name']:24s} exempt — {reason[:110]}{'…' if len(reason) > 110 else ''}")
                continue
            outside += 1
            failures.append(
                f"R5: {model['file']} declares `{model['name']}: Decodable` OUTSIDE Core/Models/ — it "
                f"is not covered by R1-R3. Move it, or add it to NON_CONTRACT_MODELS with a reason."
            )

    notes.append(f"{len(model_files)} model file(s), {checked_keys} key(s), {endpoints} endpoint "
                 f"literal(s), {outside} unchecked wire type(s)")
    if not endpoints:
        failures.append("R4: no endpoint literals were found at all — the scan is looking at nothing")
    return failures, notes


# --------------------------------------------------------------------------- falsify
MUTATIONS = [
    ("R2 a mistyped JSON key",
     "RKMCinemaTV/Core/Models/AuthModels.swift",
     'case isAdmin = "is_admin"', 'case isAdmin = "isadmin"'),
    ("R2 an invented field",
     "RKMCinemaTV/Core/Models/AuthModels.swift",
     'case warning\n    }', 'case warning\n        case nope = "nope"\n    }'),
    ("R3 an optional read as non-optional",
     "RKMCinemaTV/Core/Models/AuthModels.swift",
     "let user: SessionUser?", "let user: SessionUser"),
    ("R1 an invented model",
     "RKMCinemaTV/Core/Models/AuthModels.swift",
     "struct LoginResponse: Decodable {", "struct LoginResponses: Decodable {"),
    ("R4 a mistyped endpoint",
     "RKMCinemaTV/Server/ServerProbe.swift",
     'appendingPathComponent("api/status")', 'appendingPathComponent("api/stauts")'),
    # ⚠ The INTERPOLATED case, which is a different code path: R4 builds a pattern from the literal and
    # requires an exact match against a contract path, so a typo in the STATIC part must still fail. Without
    # this mutation the rule could be silently comparing the literal (interpolation and all) and letting
    # every parameterised endpoint through.
    ("R4 a typo in an interpolated endpoint",
     "RKMCinemaTV/Core/LibraryAPI.swift",
     'api/library/folders/\\(folderID)/items', 'api/library/folders/\\(folderID)/itemss'),
    ("R5 a wire type outside Models/",
     "RKMCinemaTV/Debug/DebugHUD.swift",
     "struct DebugHUD: View {", "struct Sneaky: Decodable { let a: String }\n\nstruct DebugHUD: View {"),
    # ---- R6/R7 — the SECOND shape source (the frontend's TypeScript interfaces). ⚠ These four exist
    # because B0 put Phase B's models outside the contract, so the rules that guard them need proving just
    # as much as R1-R3 did — including that R1 was not quietly weakened to let them through.
    ("R6 a mistyped item key",
     "RKMCinemaTV/Core/Models/LibraryModels.swift",
     'case itemID = "item_id"', 'case itemID = "itemid"'),
    ("R7 an optional read as non-optional",
     "RKMCinemaTV/Core/Models/LibraryModels.swift",
     "let thumb: String?", "let thumb: String"),
    ("R1 an invented model beside a shape-sourced one",
     "RKMCinemaTV/Core/Models/LibraryModels.swift",
     "struct MediaItem: Decodable",
     "struct SneakyItem: Decodable { let a: String }\n\nstruct MediaItem: Decodable"),
    ("R6 a shape source that has vanished",
     "frontend/src/lib/api/client.ts",
     "export interface MediaItem {", "export interface MediaItemRenamed {"),
    # ---- B4's models. ⚠ These exist so the five new models are provably COVERED rather than merely
    # listed: a `NON_CONTRACT_MODELS` entry whose shape source resolves looks IDENTICAL to one that is
    # being checked properly, which is why each shape-source rule gets a mutation on a B4 file.
    ("R6 a mistyped detail key",
     "RKMCinemaTV/Core/Models/DetailModels.swift",
     'case itemID = "item_id"', 'case itemID = "id"'),
    ("R7 a detail optional read as non-optional",
     "RKMCinemaTV/Core/Models/DetailModels.swift",
     "let overview: String?", "let overview: String"),
    ("R7 a second detail optional read as non-optional",
     "RKMCinemaTV/Core/Models/DetailModels.swift",
     "let studios: [String]?", "let studios: [String]"),
]


def falsify() -> int:
    print("falsification — each rule reverted one at a time, each must go RED\n")
    baseline_failures, _ = check(REPO)
    if baseline_failures:
        print("✗ the tree is ALREADY failing — fix it before falsifying:")
        for line in baseline_failures:
            print("   ", line)
        return 1
    print("baseline: clean\n")

    survivors = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        for label, rel, old, new in MUTATIONS:
            shutil.rmtree(tmp_root / "apple", ignore_errors=True)
            shutil.rmtree(tmp_root / "docs", ignore_errors=True)
            shutil.rmtree(tmp_root / "frontend", ignore_errors=True)
            (tmp_root / "docs" / "api").mkdir(parents=True, exist_ok=True)
            shutil.copy2(CONTRACT, tmp_root / "docs" / "api" / CONTRACT.name)
            shutil.copytree(REPO / "apple" / "tvos", tmp_root / "apple" / "tvos")
            # ⚠ The SECOND shape source has to be present for every mutation, not just the TS ones: with
            # it missing, every shape-sourced model would go red for the wrong reason ("cannot be read")
            # and a genuine survivor would look like a pass.
            ts_target = tmp_root / TS_SHAPE_FILE.relative_to(REPO)
            ts_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(TS_SHAPE_FILE, ts_target)

            # ⚠ A mutation names its path relative to the REPO, because they no longer all live under
            # `apple/tvos` — R6's rules are checked against the frontend's own interfaces.
            target = tmp_root / rel if rel.startswith("frontend/") else tmp_root / "apple" / "tvos" / rel
            text = target.read_text(encoding="utf-8")
            if old not in text:
                print(f"✗ {label}: the mutation no longer applies — `{old[:40]}…` not found in {rel}")
                survivors += 1
                continue
            target.write_text(text.replace(old, new, 1), encoding="utf-8")

            failures, _ = check(tmp_root)
            if failures:
                print(f"✓ {label}: RED — {failures[0][:96]}…")
            else:
                print(f"✗ {label}: SURVIVED (still green) — the check does not cover it")
                survivors += 1

    print()
    if survivors:
        print(f"FAIL — {survivors} mutation(s) survived; the gate is not proving what it claims.")
        return 1
    print(f"PASS — {len(MUTATIONS)}/{len(MUTATIONS)} mutations went RED, each on its own rule.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--falsify", action="store_true",
                        help="revert each rule once and require the check to fail")
    args = parser.parse_args()

    if args.falsify:
        return falsify()

    failures, notes = check(REPO)
    print("tvOS models vs the frozen contract (docs/api/openapi.v1.json)\n")
    for note in notes:
        print(f"  · {note}")
    print()
    if failures:
        print(f"FAIL — {len(failures)} problem(s):\n")
        for line in failures:
            print(f"  ✗ {line}")
        return 1
    print("PASS — every model key, endpoint and optionality matches the contract.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
