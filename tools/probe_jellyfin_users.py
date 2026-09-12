"""Household users: what Jellyfin offers for creating/managing accounts (READ-ONLY).

Written to SCOPE the in-app "add a household member" flow (AUTH_MULTIUSER_PLAN §6
Phase 5 optional) from measurements rather than from the docs — the same discipline the
subtitle work used. It answers three questions in one command:

1. **Who exists** and what each account may see (`IsAdministrator`, `EnableAllFolders`,
   `EnabledFolders` resolved to library names) — the per-user state the app will one day
   filter the sidebar by.
2. **What can be granted**: every library's `ItemId`, which is the value `EnabledFolders`
   holds (so "give this person Movies + TV, not Movies Kids" is expressible).
3. **What the API actually accepts**: the request-body schemas for create / policy /
   password / configuration, lifted from the RUNNING server's own
   `/api-docs/openapi.json`. Reading the live contract is what settled the subtitle
   upload shape (JSON + base64 `Data`) after the docs disagreed with the server.

It performs GETs only. It never creates, edits or deletes a user — that is the user's
server, and creating accounts is his decision, not a probe's side effect.

Usage:
    python3 tools/probe_jellyfin_users.py            # summary, all sections
    python3 tools/probe_jellyfin_users.py --schemas  # + full property lists
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rkm_common import Jellyfin, jellyfin_base, load_env  # noqa: E402

#: The endpoints the in-app flow would need, and what each one is for. These are the
#: REAL spellings on Jellyfin 10.11 (measured, not assumed): the password route takes
#: the target as a QUERY parameter (``?userId=``), and a user's own views are read from
#: ``/UserViews`` — ``/Users/{userId}/Views`` still answers today but is NOT in the
#: server's own contract, so the app must not depend on it.
WANTED = {
    "/Users": "list every account (admin only) / update one (?userId=)",
    "/Users/New": "CREATE a user: {Name, Password}",
    "/Users/{userId}": "read / DELETE one account",
    "/Users/{userId}/Policy": "grants + permissions (the whole UserPolicy is replaced)",
    "/Users/Password": "set or reset a password (?userId=, UpdateUserPassword)",
    "/UserViews": "the libraries THAT user can actually see (?userId=)",
    "/Library/VirtualFolders": "every library, with the ItemId a grant refers to",
}

#: Policy fields that decide what a household member can do/see.
POLICY_FIELDS = ("IsAdministrator", "IsDisabled", "EnableAllFolders", "EnabledFolders",
                 "EnableContentDownloading", "EnableRemoteControlOfOtherUsers",
                 "EnableLiveTvAccess", "EnableMediaPlayback", "EnableSharedDeviceControl",
                 "EnableSyncTranscoding", "EnableAudioPlaybackTranscoding",
                 "EnableVideoPlaybackTranscoding", "EnablePlaybackRemuxing",
                 "EnableCollectionManagement", "EnableSubtitleManagement")


def openapi_shapes(base: str) -> dict:
    """The RUNNING server's own contract for the endpoints above (spec-first)."""
    try:
        with urllib.request.urlopen(f"{base}/api-docs/openapi.json", timeout=30) as resp:
            spec = json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        return {"error": f"could not read the server's openapi ({type(exc).__name__})"}

    paths, schemas = spec.get("paths") or {}, (spec.get("components") or {}).get("schemas") or {}
    out: dict = {"path_count": len(paths), "endpoints": {}, "schemas": {}}

    def resolve(node):
        if isinstance(node, dict) and "$ref" in node:
            name = str(node["$ref"]).rsplit("/", 1)[-1]
            return name, schemas.get(name) or {}
        if isinstance(node, dict) and node.get("allOf"):
            # Jellyfin models the body as allOf[{$ref}] — follow it, or the schema
            # name is never printed and the tool looks like the field does not exist.
            return resolve(node["allOf"][0])
        return None, node if isinstance(node, dict) else {}

    for wanted, why in WANTED.items():
        entry = paths.get(wanted)
        found = {"why": why, "methods": []}
        if not entry:
            found["methods"] = []
        for method, op in (entry or {}).items():
            name, schema = resolve(((op.get("requestBody") or {}).get("content") or {})
                                   .get("application/json", {}).get("schema", {}))
            body = {"method": method.upper(),
                    "params": [(p.get("name"), p.get("in")) for p in (op.get("parameters") or [])]}
            if name:
                body["body_schema"] = name
                body["properties"] = sorted((schema.get("properties") or {}).keys())
                out["schemas"][name] = body["properties"]
            found["methods"].append(body)
        out["endpoints"][wanted] = found
    return out


def main() -> int:
    env = load_env()
    base = jellyfin_base(env)
    print(f"Jellyfin: {base}")
    jf = Jellyfin(env=env)
    if not jf.token:
        print("!! could not authenticate with RKM_JELLYFIN_ADMIN_USER/PASSWORD from .env")
        return 1

    folders = jf.libraries()
    names = {f.get("ItemId"): f.get("Name") for f in folders if isinstance(f, dict)}
    print(f"\n== libraries ({len(folders)}) ==")
    for folder in folders:
        if isinstance(folder, dict):
            print(f"  {folder.get('Name')!r:24} type={folder.get('CollectionType')!r:10} "
                  f"id={folder.get('ItemId')} paths={folder.get('Locations')}")

    users = jf.get("/Users")
    if not isinstance(users, list):
        print(f"\n== users ==\n  could not list users: {json.dumps(users)[:200]}")
        return 1
    print(f"\n== users ({len(users)}) ==")
    for user in users:
        policy = user.get("Policy") or {}
        granted = policy.get("EnabledFolders") or []
        visible = ("ALL" if policy.get("EnableAllFolders")
                   else ", ".join(names.get(i, str(i)) for i in granted) or "none")
        print(f"  {user.get('Name')!r:16} id={user.get('Id')} "
              f"admin={bool(policy.get('IsAdministrator'))} disabled={bool(policy.get('IsDisabled'))}")
        print(f"      sees: {visible}")
        if user.get("LastLoginDate"):
            print(f"      last login: {user['LastLoginDate']}")

    views = {}
    for user in users:
        res = jf.get(f"/Users/{user.get('Id')}/Views")
        views[user.get("Name")] = [v.get("Name") for v in res.get("Items", [])] \
            if isinstance(res, dict) else None
    print("\n== per-user /Views (what the app's sidebar could filter to) ==")
    for name, libs in views.items():
        print(f"  {name!r:16} -> {libs}")

    shapes = openapi_shapes(base)
    print("\n== the RUNNING server's contract (openapi) ==")
    if shapes.get("error"):
        print(f"  {shapes['error']}")
    else:
        print(f"  {shapes['path_count']} paths in the server's own spec")
        for path, found in shapes["endpoints"].items():
            print(f"  {path}  -- {found['why']}")
            if not found["methods"]:
                print("      !! NOT in this server's contract — do not depend on it")
            for method in found["methods"]:
                line = f"      {method['method']:6}"
                if method.get("params"):
                    line += f" params={method['params']}"
                if method.get("body_schema"):
                    line += f" body={method['body_schema']}"
                print(line)
        if "--schemas" in sys.argv:
            print("\n== request-body properties ==")
            for name, props in sorted(shapes["schemas"].items()):
                print(f"  {name}: {props}")
        else:
            print("  (re-run with --schemas for every property list)")

    print("\n== what this means for the in-app flow ==")
    print("  * a grant is a library ItemId in the user's Policy.EnabledFolders")
    print("    (with EnableAllFolders=false) -- read the policy, mutate, POST it back")
    print("  * no writes were performed by this probe: creating accounts is HIS call")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
