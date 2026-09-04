#!/usr/bin/env python3
"""One-time + idempotent migration: watchlist.json (JSON store) -> SQLite.

Reads the canonical JSON file and writes it into the SqliteWatchlistRepository
(current WATCHLIST_DB_PATH). Round-trip verifies entry counts, carries the
recommendation seen-set across, re-exports watchlist.json as a one-time mirror,
then rebuilds the dashboard so the frontend serves from SQLite immediately.

After this, the authoritative store is SQLite (WATCHLIST_STORE=sqlite). The JSON
file is kept only as a historical/mirror export for the surrounding media stack —
it is no longer authoritative for the app.

Safe to run repeatedly (idempotent); backs up an existing SQLite DB first.

Usage:  python3 scripts/migrate_json_to_sqlite.py
"""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime

# Make the project root importable regardless of CWD.
PROJECT_ROOT = "/workspace/projects/rkm-cinema"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import get_config
from infrastructure.database.repository import (  # noqa: E402
    JsonWatchlistRepository,
    SqliteWatchlistRepository,
)


def _n(raw: dict, key: str) -> int:
    return len(raw.get(key) or [])


def main() -> None:
    cfg = get_config()
    src = JsonWatchlistRepository()          # the canonical JSON file (media volume)
    raw = src.load()

    pending, recommended = _n(raw, "pending"), _n(raw, "recommended")
    if pending == 0 and recommended == 0:
        print("JSON store is empty - aborting (nothing to migrate).")
        sys.exit(1)

    dst = SqliteWatchlistRepository()        # WATCHLIST_DB_PATH (permanent media volume)
    db_path = dst.db.path
    print(f"Source (JSON): {src.path}")
    print(f"Target (SQLite): {db_path}  [store={cfg.WATCHLIST_STORE!r}]")

    if cfg.WATCHLIST_STORE != "sqlite":
        print("WARNING: WATCHLIST_STORE is not 'sqlite'. Flip it in /workspace/.env "
              "or the app will keep reading the JSON store after this migration.")

    # Back up an existing SQLite DB so a re-run never destroys prior data.
    if db_path != ":memory:" and os.path.exists(db_path):
        bak = f"{db_path}.bak-{datetime.now():%Y%m%d-%H%M%S}"
        shutil.copy2(db_path, bak)
        print(f"Backed up existing SQLite DB -> {bak}")

    print(f"Migrating {pending} pending + {recommended} recommended ...")
    dst.save(raw)

    # Carry the recommendation seen-set across (sidecar json -> sqlite), so the
    # auto-add pipeline does not re-see already-considered titles after the flip.
    hist = src.list_recommendation_history(limit=99999)
    n_hist = 0
    for h in hist:
        dst.record_recommendation(
            media_id=h.get("media_id", ""),
            decision=h.get("decision") or "",
            score=float(h.get("score") or 0),
            payload=h.get("payload") or None,
        )
        n_hist += 1

    # Round-trip verify.
    back = dst.load()
    if _n(back, "pending") != pending or _n(back, "recommended") != recommended:
        print(f"VERIFY FAILED: pending {pending}->{_n(back, 'pending')}, "
              f"recommended {recommended}->{_n(back, 'recommended')}. Aborting.")
        sys.exit(1)
    print(f"Verified round-trip: {_n(back, 'pending')} pending + "
          f"{_n(back, 'recommended')} recommended in SQLite. "
          f"({n_hist} history rows carried across)")

    # Re-export the current raw to watchlist.json as a one-time mirror for any
    # external media-stack consumer that still reads the file directly.
    src.save(back)
    print(f"Mirrored current raw back to {src.path} (generated export, not authoritative).")

    # Rebuild the dashboard so the frontend (dashboard-data.json) serves SQLite now.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "rebuild_dashboard", os.path.join(PROJECT_ROOT, "scripts", "rebuild_dashboard.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # noqa
    n_cards = mod.build()
    print(f"Dashboard rebuilt: {n_cards} cards from SQLite.")

    print("\nDone. Authoritative store = SQLite at " + db_path)
    print("Deploy on RKM-HP to switch the container:  .\\run-rkm-cinema.ps1")


if __name__ == "__main__":
    main()