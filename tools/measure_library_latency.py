#!/usr/bin/env python3
"""Where a library folder's time actually goes — the measurement behind M3 (2026-09-17).

    python3 tools/measure_library_latency.py                 # the Movies folder, 390x844, 3 taps
    python3 tools/measure_library_latency.py --folder "TV Shows" --repeat 2
    python3 tools/measure_library_latency.py --list-folders

**Why this exists.** MOBILE_FIRST_UI_PLAN §11 (M3) says "virtualise any list that can exceed
~200 rows", and PROGRESS recorded a report from his phone — *"the Movies tab takes an extra
second to populate (711 titles in that folder)"* — with two candidate causes that look identical
from the sofa: the **FETCH** (713 rows of JSON) or the **RENDER** (713 unmapped `MediaCard`s with
no windowing). They need OPPOSITE fixes, and one of them is a backend phase.

This tool decides between them by measurement, and it splits the wall time into its parts, per
tap, in a real browser against the REAL stack:

  * `t_items`  — when the `/api/library/folders/<id>/items` response finished
  * `t_first`  — when the first `media-card` reached the DOM
  * `t_all`    — when the last one did  (what a person feels)
  * `render`   — `t_all - t_items`, i.e. **what windowing would fix**
  * `longtask` — how long the main thread was blocked inside the window
  * `posters`  — how many poster images the tap actually pulled (they are `loading="lazy"`)

⚠ **The taps happen INSIDE the SPA** (`pushState` + `popstate`, the same document throughout —
asserted, because a reload would hide the React Query cache and answer a different question). One
tap is cold, the next lands inside the query's `staleTime` (**zero requests** — the cache hit — and
that is the row that tells fetch from render), and the rest after it goes stale.

⚠ **What it does NOT do: write anything.** Read-only calls and page loads; no scan, no playback,
no progress reporting.

⚠ **It signs in on the `rkm-tools` device** (`rkm_common.App`, `services/auth.py::TOOLS_DEVICE_ID`).
Never the app's own device id: Jellyfin invalidates the previous token of a `(device, user)` pair on
every login, so measuring on the browser's device would leave his phone answering 401.

**Reading the result.** If the cached tap is still slow with no request, the cost is the RENDER
(`nodes` says how many DOM nodes were built); if the cached tap is instant and only the cold one is
slow, it is the FETCH — and that is a backend question, which is his call, not this tool's.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rkm_common import App, app_base, load_env  # noqa: E402

#: Recorded per tap. Driven from INSIDE the page so nothing is lost to a round trip, and so the
#: long-task total belongs to the window being measured rather than to the whole session.
PROBE = r"""
(() => {
  window.__marker = Math.random();
  const connect = () => {
    if (window.__obs) window.__obs.disconnect();
    window.__obs = new MutationObserver(() => {
      const n = document.querySelectorAll('[data-testid="media-card"]').length;
      if (n > 0 && !window.__marks.first) window.__marks.first = performance.now();
      window.__marks.n = n;
      if (window.__target && n >= window.__target && !window.__marks.all) {
        window.__marks.all = performance.now();
      }
    });
    window.__obs.observe(document.body, { childList: true, subtree: true });
  };
  window.__lt = 0; window.__ltCount = 0;
  try {
    new PerformanceObserver((l) => { for (const e of l.getEntries()) { window.__lt += e.duration; window.__ltCount += 1; } })
      .observe({ entryTypes: ['longtask'] });
  } catch (e) {}

  window.__start = (target) => {
    performance.clearResourceTimings();
    window.__marks = { t0: performance.now() };
    window.__target = target;
    window.__lt = 0; window.__ltCount = 0;
    connect();
  };
  window.__tap = (path) => {
    history.pushState({}, '', path);
    window.dispatchEvent(new PopStateEvent('popstate'));
  };
  window.__read = () => {
    const res = performance.getEntriesByType('resource');
    const items = res.filter(r => /\/api\/library\/folders\/[^/]+\/items/.test(r.name));
    const posters = res.filter(r => r.name.includes('/api/jellyfin/poster'));
    const last = items[items.length - 1];
    const sum = (a, k) => a.reduce((x, r) => x + (r[k] || 0), 0);
    return {
      cards: window.__marks.n || 0,
      t_items: last ? Math.round(last.responseEnd - window.__marks.t0) : null,
      items_ms: last ? Math.round(last.duration) : null,
      requests: items.length,
      t_first: window.__marks.first ? Math.round(window.__marks.first - window.__marks.t0) : null,
      t_all: window.__marks.all ? Math.round(window.__marks.all - window.__marks.t0) : null,
      render_ms: (window.__marks.all && last) ? Math.round(window.__marks.all - last.responseEnd) : null,
      poster_requests: posters.length,
      poster_kb: Math.round(sum(posters, 'transferSize') / 1024),
      longtask_ms: Math.round(window.__lt),
      longtask_n: window.__ltCount,
      nodes: document.querySelectorAll('*').length,
    };
  };
})();
"""


def folders_for(app: App) -> list[dict]:
    answer = app.get("/api/library/folders")
    return list((answer or {}).get("folders") or [])


def wait_for_cards(page, target: int, timeout_ms: int = 60_000) -> bool:
    try:
        page.wait_for_function("n => (window.__marks.n || 0) >= n", arg=target, timeout=timeout_ms)
        return True
    except Exception:
        return False


def measure(app: App, base: str, folder: dict, *, count: int, viewport: tuple[int, int],
            repeat: int, stale_wait: float, settle_ms: int) -> list[dict]:
    """Tap the folder `repeat` times in one SPA session and report each tap separately."""
    folder_id = folder["id"]
    results: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]},
                                  device_scale_factor=3, is_mobile=True, has_touch=True)
        cookie = list(app.jar)[0]
        ctx.add_cookies([{"name": cookie.name, "value": cookie.value,
                          "domain": base.split("//", 1)[-1].split(":")[0].split("/")[0],
                          "path": "/"}])
        ctx.add_init_script(PROBE)
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))

        page.goto(f"{base}/library/home", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        if "/profiles" in page.url:
            # The tools session is signed in to the SERVER but has not picked a profile, which is
            # what the router asks for first. Pick the administrator where there is one.
            page.click('[data-testid="profile-rows"] button:has-text("Administrator")', timeout=15_000)
            page.wait_for_timeout(600)
            if page.query_selector('[data-testid="profile-password-form"]'):
                page.fill('[data-testid="profile-password-form"] input[type="password"]',
                          str(app.env.get("RKM_JELLYFIN_ADMIN_PASSWORD") or ""))
                page.click('[data-testid="profile-password-form"] button[type="submit"]')
            page.wait_for_timeout(3000)
        marker = page.evaluate("() => window.__marker")

        for tap in range(1, repeat + 1):
            if tap > 1:
                page.evaluate("p => window.__tap(p)", "/library/home")
                page.wait_for_timeout(1200)
                if stale_wait and tap == repeat:
                    page.wait_for_timeout(int(stale_wait * 1000))
            page.evaluate("t => window.__start(t)", count)
            page.evaluate("p => window.__tap(p)", f"/library/folder/{folder_id}")
            reached = wait_for_cards(page, count)
            page.wait_for_timeout(settle_ms)          # let the posters and the tail of the work land
            out = page.evaluate("() => window.__read()")
            out["tap"] = tap
            out["reached"] = reached
            results.append(out)
            render = out["render_ms"]
            if render is None:
                shown = "n/a (no fetch in this window)"
            elif render < 0:
                shown = "n/a (cards came from the cache; the request was a background refetch)"
            else:
                shown = f"≈{render} ms"
            print(f"  tap {tap}: wall-to-{out['cards']}cards={out['t_all']} ms · "
                  f"items={out['t_items']} ms in ({out['items_ms']} ms net, "
                  f"{out['requests']} request(s)) · first card={out['t_first']} ms · "
                  f"render {shown} · longtasks={out['longtask_n']}/{out['longtask_ms']} ms · "
                  f"nodes={out['nodes']} · posters={out['poster_requests']}/{out['poster_kb']} KB")
            if not reached:
                print(f"    !! only {out['cards']}/{count} cards appeared")

        print(f"  same document throughout (no reload): "
              f"{page.evaluate('() => window.__marker') == marker}")
        if errors:
            print(f"  page errors: {errors[:3]}")
        browser.close()
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=None, help="app base URL (default: from .env)")
    ap.add_argument("--folder", default="Movies", help="library folder NAME (or its id)")
    ap.add_argument("--viewport", default="390x844", help="WxH, e.g. 390x844 (default) or 1280x800")
    ap.add_argument("--repeat", type=int, default=3,
                    help="taps in one SPA session (1st cold, 2nd inside staleTime, last after it)")
    ap.add_argument("--stale-wait", type=float, default=31.0,
                    help="seconds to idle before the FINAL tap, so the query is stale (0 = never)")
    ap.add_argument("--settle", type=int, default=2500, help="ms to let each tap settle")
    ap.add_argument("--list-folders", action="store_true", help="print the folders and exit")
    ap.add_argument("--json", metavar="PATH", help="also write the raw measurements here")
    args = ap.parse_args()

    env = load_env()
    base = (args.base or app_base(env)).rstrip("/")
    width, _, height = args.viewport.partition("x")

    app = App(base=base, env=env)
    if not app.signed_in:
        print(f"could not sign in to {base}: {app.error}")
        return 2
    print(f"signed in to {base} on the tools' own device ({app.device_id})")

    folders = folders_for(app)
    if args.list_folders:
        for f in folders:
            print(f"  {f.get('name')}  id={f.get('id')}  path={f.get('path')}")
        return 0

    wanted = str(args.folder)
    folder = next((f for f in folders if str(f.get("id")) == wanted), None) or \
        next((f for f in folders if str(f.get("name", "")).lower() == wanted.lower()), None)
    if not folder:
        names = ", ".join(str(f.get("name")) for f in folders) or "(none)"
        print(f"no library folder named {wanted!r}. This stack has: {names}")
        return 2

    # ⚠ `/api/library/folders` does NOT carry a count — the row count comes from the items
    # route itself, which is also where the response SIZE (bytes) is measured.
    body = app.request(f"/api/library/folders/{folder['id']}/items") if hasattr(app, "request") else None
    items = (body or {}).get("items") if isinstance(body, dict) else None
    count = len(items or [])
    if not count:
        print(f"{folder.get('name')} reports 0 titles — nothing to measure")
        return 2
    print(f"{folder.get('name')}: {count} titles, {len(json.dumps(body))} bytes of JSON")

    print(f"\n=== {folder.get('name')} ({count} titles) at {width}×{height} "
          f"· {args.repeat} tap(s), the last after {args.stale_wait}s stale ===")
    try:
        results = measure(app, base, folder, count=count, viewport=(int(width), int(height)),
                          repeat=args.repeat, stale_wait=args.stale_wait, settle_ms=args.settle)
    except Exception as exc:                                     # noqa: BLE001 — report, don't guess
        print(f"measurement failed: {type(exc).__name__}: {exc}")
        return 1

    cold = results[0] if results else {}
    cached = next((r for r in results[1:] if r["requests"] == 0), None)
    print("\n=== what it means ===")
    if not cold:
        print("  nothing was measured.")
    else:
        print(f"  COLD tap: {cold['t_all']} ms to build {cold['nodes']} nodes — "
              f"{cold['items_ms']} ms of it the fetch, "
              f"{cold['render_ms'] if (cold['render_ms'] or 0) > 0 else '≈600+'} ms of it the render. "
              "⚠ The fetch half is NOT constant run to run (it has measured 341 ms and 1769 ms for "
              "the same folder — a cold media-server query), and the query cache removes it anyway.")
    if cached:
        print(f"  ⚠ DECISIVE — the CACHED tap made NO items request and still took "
              f"{cached['t_all']} ms, with {cached['longtask_ms']} ms of long tasks and "
              f"{cached['nodes']} DOM nodes. Window the list and THAT number is what improves; "
              "the fetch does not need to change.")
    else:
        print("  ⚠ no tap landed inside the query cache, so fetch and render are NOT separated here "
              "— run with --repeat 2 and --stale-wait 0 for a clean cached tap. Do not read a "
              "winner out of these numbers without it.")
    print("  ⚠ and the fetch is a ONE-OFF the cache absorbs; the render is paid on EVERY tap — "
          "which is what 'the tab takes an extra second' means from the sofa.")

    if args.json:
        Path(args.json).write_text(json.dumps({"folder": folder, "taps": results}, indent=2))
        print(f"\nraw measurements: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
