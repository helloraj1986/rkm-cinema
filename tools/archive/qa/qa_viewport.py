#!/usr/bin/env python3
import asyncio, json
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8124"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for label, opts in [("desktop", dict(viewport={"width": 1440, "height": 900})),
                            ("mobile", dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True))]:
            page = await browser.new_page(**opts)
            await page.goto(BASE + "/", wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1500)
            info = await page.evaluate("""() => ({
                meta: document.querySelector('meta[name=viewport]')?.content || null,
                innerW: window.innerWidth, outerW: window.outerWidth,
                dpr: window.devicePixelRatio,
                docScrollW: document.documentElement.scrollWidth,
                bodyScrollW: document.body.scrollWidth,
                visW: document.documentElement.clientWidth,
                screen: window.screen.width + 'x' + window.screen.height,
                shellW: document.querySelector('.shell')?.getBoundingClientRect().width || null
            })""")
            print(label, json.dumps(info, indent=1))
        await browser.close()

asyncio.run(main())