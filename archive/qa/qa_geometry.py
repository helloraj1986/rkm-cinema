#!/usr/bin/env python3
"""Geometry/layout QA — catches overlaps, clipping, overflow, broken elements."""
import asyncio, json
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8124"

CHECKS = """
() => {
  const out = { issues: [], stats: {} };
  const rects = (sel) => [...document.querySelectorAll(sel)];
  const overlap = (a, b) => !(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top) && (a.width>0 && b.width>0);
  const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };

  // 1. text clipping: elements with overflow hidden + scrollWidth > clientWidth
  rects('.ci-title, .hero-title, .modal-title, .sr-title, .si-title, .dlp-title, .nav button').forEach(el => {
    if (el.scrollWidth > el.clientWidth + 2) out.issues.push(`TEXT CLIP: .${el.className.split(' ')[0]} "${el.textContent.slice(0,30)}" sw=${el.scrollWidth} cw=${el.clientWidth}`);
  });

  // 2. buttons with tiny hit areas (a11y)
  rects('button, a.btn').forEach(el => {
    const r = el.getBoundingClientRect();
    if (vis(el) && (r.width < 24 || r.height < 24)) out.issues.push(`TINY BUTTON ${r.width.toFixed(0)}x${r.height.toFixed(0)}: ${el.className.slice(0,30)}`);
  });

  // 3. overlapping interactive elements
  const els = rects('button, a, .card, .sr-item').filter(vis);
  for (let i = 0; i < els.length; i++) for (let j = i+1; j < els.length; j++) {
    const a = els[i].getBoundingClientRect(), b = els[j].getBoundingClientRect();
    if (a === b) continue;
    if (overlap(a, b) && Math.min(a.width,b.width) > 40 && Math.min(a.height,b.height) > 20) {
      out.issues.push(`OVERLAP: ${els[i].tagName}.${els[i].className.slice(0,20)} (${a.width.toFixed(0)}x${a.height.toFixed(0)}) <-> ${els[j].tagName}.${els[j].className.slice(0,20)} (${b.width.toFixed(0)}x${b.height.toFixed(0)})`);
      break;
    }
  }

  // 4. horizontal overflow
  out.stats.docScrollW = document.documentElement.scrollWidth;
  out.stats.winW = window.innerWidth;
  if (document.documentElement.scrollWidth > window.innerWidth + 2) out.issues.push(`H-OVERFLOW: doc ${document.documentElement.scrollWidth} > win ${window.innerWidth}`);

  // 5. cards rendered
  out.stats.cards = document.querySelectorAll('.card').length;
  out.stats.hero = !!document.querySelector('.hero');
  out.stats.imgsBroken = [...document.querySelectorAll('img')].filter(im => im.complete && im.naturalWidth === 0 && im.src).length;

  // 6. images loading
  const imgs = [...document.querySelectorAll('.card img, .hero-bg img')];
  out.stats.images = imgs.length;
  out.stats.imagesLoaded = imgs.filter(im => im.complete && im.naturalWidth > 0).length;

  // 7. status pill text
  out.stats.pill = document.getElementById('statusTxt')?.textContent || null;

  // 8. computed accent
  out.stats.bg = getComputedStyle(document.body).backgroundColor;
  return out;
}
"""

async def check(label, page, selector=None):
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1500)
    res = await page.evaluate(CHECKS)
    print(f"=== {label} ===")
    print("stats:", json.dumps(res["stats"]))
    if res["issues"]:
        print("ISSUES:")
        for i in res["issues"][:20]: print("  -", i)
    else:
        print("ISSUES: none")
    print()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))
        await page.goto(BASE + "/", wait_until="networkidle", timeout=30000)
        await check("discover (desktop)", page)

        await page.click('[data-nav="watchlist"]')
        await check("watchlist (desktop)", page)

        await page.click('[data-nav="movies"]')
        await check("movies (desktop)", page)

        await page.click('[data-nav="discover"]')
        await page.click(".card", position={"x": 20, "y": 20})
        await check("modal open", page)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)

        await page.click("#searchInput")
        await page.type("#searchInput", "arrival", delay=30)
        await page.wait_for_timeout(1200)
        await check("search result panel", page)

        # mobile
        mp = await browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        mp.on("pageerror", lambda e: errors.append(f"[m] {str(e)[:200]}"))
        await mp.goto(BASE + "/", wait_until="networkidle", timeout=30000)
        await check("discover (mobile)", mp)
        await mp.click('[data-nav="watchlist"]')
        await check("watchlist (mobile)", mp)
        await mp.click("[data-nav='discover']")
        await mp.click(".card")
        await check("modal (mobile)", mp)

        print("PAGEERRORS:", json.dumps(errors, indent=1) if errors else "none")
        await browser.close()

asyncio.run(main())