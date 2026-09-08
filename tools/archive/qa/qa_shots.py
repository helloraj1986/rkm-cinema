#!/usr/bin/env python3
"""Screenshot + console-error QA harness for RKM Cinema (dev server on 8124)."""
import asyncio, json, sys
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8124"
SHOTS = "/tmp/rkm_shots"

async def main():
    await asyncio.to_thread(lambda: __import__("os").makedirs(SHOTS, exist_ok=True))
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        console_errors = []
        page.on("console", lambda m: console_errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"[pageerror] {e}"))

        await page.goto(BASE + "/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2500)
        await page.screenshot(path=f"{SHOTS}/desktop-top.png", full_page=True)

        # scroll to rows
        await page.evaluate("window.scrollTo(0, 700)")
        await page.wait_for_timeout(800)
        await page.screenshot(path=f"{SHOTS}/desktop-rows.png")

        # open a card modal
        await page.click(".card")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=f"{SHOTS}/desktop-modal.png")

        # open trailer in modal
        await page.click('[data-role="trailer"]')
        await page.wait_for_timeout(2500)
        await page.screenshot(path=f"{SHOTS}/desktop-trailer.png")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)

        # search
        await page.click("#searchInput")
        await page.wait_for_timeout(400)
        await page.type("#searchInput", "villeneuve", delay=40)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=f"{SHOTS}/desktop-search.png")

        # watchlist view
        await page.click('[data-nav="watchlist"]')
        await page.wait_for_timeout(1200)
        await page.screenshot(path=f"{SHOTS}/desktop-watchlist.png")

        # mobile
        mp = await browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        mp.on("console", lambda m: console_errors.append(f"[m:{m.type}] {m.text}") if m.type == "error" else None)
        mp.on("pageerror", lambda e: console_errors.append(f"[m:pageerror] {e}"))
        await mp.goto(BASE + "/", wait_until="networkidle", timeout=30000)
        await mp.wait_for_timeout(2500)
        await mp.screenshot(path=f"{SHOTS}/mobile-top.png", full_page=True)
        # overflow check
        overflow = await mp.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        print("MOBILE HORIZONTAL OVERFLOW:", overflow)
        await mp.click(".card")
        await mp.wait_for_timeout(1200)
        await mp.screenshot(path=f"{SHOTS}/mobile-modal.png")

        print("CONSOLE ERRORS:", json.dumps(console_errors, indent=1) if console_errors else "none")
        await browser.close()

asyncio.run(main())