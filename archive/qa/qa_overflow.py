#!/usr/bin/env python3
import asyncio, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        dev = p.devices["iPhone 13"]
        page = await browser.new_page(viewport=dev["viewport"], device_scale_factor=2, is_mobile=True, has_touch=True)
        await page.goto("http://127.0.0.1:8124/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        res = await page.evaluate("""() => {
          const bad = [...document.querySelectorAll('body *')].map(e => {
            const r = e.getBoundingClientRect();
            return { el: e.tagName + (e.id ? '#'+e.id : '') + '.' + String(e.className).split(' ').slice(0,2).join('.'),
                     left: Math.round(r.left), right: Math.round(r.right), w: Math.round(r.width) };
          }).filter(x => x.right > window.innerWidth + 2 || x.left < -2)
            .sort((a,b) => b.right - a.right).slice(0, 12);
          return { winW: window.innerWidth, scrollW: document.documentElement.scrollWidth, bad };
        }""")
        print(json.dumps(res, indent=1))
        # also: which row overflows its own box
        rows = await page.evaluate("""[...document.querySelectorAll('.row')].map(r => {
          const pr = r.getBoundingClientRect();
          const kids = [...r.children].map(c => c.getBoundingClientRect().right);
          return { left: Math.round(pr.left), right: Math.round(pr.right), lastKid: Math.round(Math.max(...kids)) };
        })""")
        print("rows:", json.dumps(rows, indent=1))
        await browser.close()

asyncio.run(main())