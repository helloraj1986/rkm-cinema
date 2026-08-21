#!/usr/bin/env python3
import asyncio, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        await page.goto("about:blank")
        print("blank:", await page.evaluate("JSON.stringify({innerW: innerWidth, visW: document.documentElement.clientWidth, dpr: devicePixelRatio})"))
        await page.goto("http://127.0.0.1:8124/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)
        print("app:", await page.evaluate("""JSON.stringify({
            innerW: innerWidth, visW: document.documentElement.clientWidth,
            dpr: devicePixelRatio, scrollW: document.documentElement.scrollWidth,
            wide: [...document.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > innerWidth + 1).slice(0,5).map(e => e.tagName+'.'+(e.className||'').toString().slice(0,30)+' right='+e.getBoundingClientRect().right.toFixed(0))
        })"""))
        await page.screenshot(path="/tmp/rkm_shots/mobile-blank.png")
        await browser.close()

asyncio.run(main())