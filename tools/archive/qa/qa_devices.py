#!/usr/bin/env python3
import asyncio, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for name in ["iPhone 13", "Pixel 7"]:
            dev = p.devices[name]
            opts = dict(viewport=dev["viewport"], device_scale_factor=dev.get("deviceScaleFactor", 2),
                        is_mobile=dev.get("isMobile", False), has_touch=dev.get("hasTouch", False))
            page = await browser.new_page(**opts)
            await page.goto("http://127.0.0.1:8124/", wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            info = await page.evaluate("""JSON.stringify({
                innerW: innerWidth, visW: document.documentElement.clientWidth,
                dpr: devicePixelRatio, scrollW: document.documentElement.scrollWidth,
                cards: document.querySelectorAll('.card').length
            })""")
            print(name, "viewport:", dev["viewport"], "->", info)
            await page.screenshot(path=f"/tmp/rkm_shots/{name.replace(' ', '_')}.png")
        await browser.close()

asyncio.run(main())