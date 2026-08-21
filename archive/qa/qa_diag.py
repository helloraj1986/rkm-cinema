#!/usr/bin/env python3
import asyncio, json
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8124"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        msgs = []
        page.on("console", lambda m: msgs.append(f"[{m.type}] {m.text[:300]}"))
        page.on("pageerror", lambda e: msgs.append(f"[pageerror] {str(e)[:500]}"))
        page.on("requestfailed", lambda r: msgs.append(f"[reqfail] {r.url[:120]} {r.failure}"))
        await page.goto(BASE + "/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        print("URL:", page.url)
        print("APP HTML LEN:", await page.evaluate("document.getElementById('app').innerHTML.length"))
        print("HAS HEADER:", await page.evaluate("!!document.querySelector('header')"))
        print("CARDS:", await page.evaluate("document.querySelectorAll('.card').length"))
        print("HAS HERO:", await page.evaluate("!!document.querySelector('.hero')"))
        print("BODY TEXT (first 300):", (await page.evaluate("document.body.innerText"))[:300])
        print("--- msgs ---")
        for m in msgs[:25]:
            print(m)
        await browser.close()

asyncio.run(main())