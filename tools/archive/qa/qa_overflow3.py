#!/usr/bin/env python3
import asyncio, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        # Force a clean 390 width, no isMobile quirk
        page = await browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        await page.goto("http://127.0.0.1:8124/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        res = await page.evaluate("""() => {
          const winW = window.innerWidth;
          const sc = (el) => { const s=getComputedStyle(el); return s.overflowX==='auto'||s.overflowX==='scroll'||s.overflowX==='hidden'; };
          const inScroller = (el) => { let p=el.parentElement; while(p){ if(sc(p)) return true; p=p.parentElement;} return false; };
          const bad = [];
          for (const el of document.body.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            if (r.right > winW + 2 && !inScroller(el)) {
              const cs = getComputedStyle(el);
              bad.push({ el: el.tagName+(el.id?(' #'+el.id):'')+'.'+String(el.className).split(' ').slice(0,2).join('.'),
                         right: Math.round(r.right), w: Math.round(r.width),
                         mw: cs.minWidth, pl: cs.paddingLeft, pr: cs.paddingRight, ml: cs.marginLeft });
            }
          }
          const seen={}; for (const b of bad){ if(!seen[b.el]||b.right>seen[b.el].right) seen[b.el]=b; }
          return { winW, scrollW: document.documentElement.scrollWidth,
                   bad: Object.values(seen).sort((a,b)=>b.right-a.right).slice(0,15) };
        }""")
        print(json.dumps(res, indent=1))
        await browser.close()

asyncio.run(main())
