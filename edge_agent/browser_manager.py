"""Persistent Playwright Chromium context (per user).

Uses a *persistent* user_data_dir so cookies + logins survive across sessions.
Spotify / Google / etc only need to authenticate once — subsequent runs reuse
the session, so a simple `browser_navigate` to open.spotify.com is enough to
play music without the user's password ever leaving their machine.

Credentials can be fetched from the JARVIS cloud vault only for the first-time
login flow (browser_login command).
"""
from __future__ import annotations
import os
import asyncio
import base64
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from playwright.async_api import async_playwright, BrowserContext, Page
    HAS_PLAYWRIGHT = True
except Exception:
    HAS_PLAYWRIGHT = False


JARVIS_HOME = Path(os.getenv("JARVIS_HOME", str(Path.home() / ".jarvis")))
JARVIS_HOME.mkdir(parents=True, exist_ok=True)
USER_DATA_DIR = JARVIS_HOME / "chrome_profile"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)


class BrowserManager:
    def __init__(self):
        self._pw = None
        self._ctx: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._lock = asyncio.Lock()

    def available(self) -> bool:
        return HAS_PLAYWRIGHT

    async def ensure(self) -> Optional[BrowserContext]:
        if not HAS_PLAYWRIGHT:
            return None
        async with self._lock:
            if self._ctx:
                return self._ctx
            self._pw = await async_playwright().start()
            self._ctx = await self._pw.chromium.launch_persistent_context(
                str(USER_DATA_DIR),
                headless=False,
                viewport={"width": 1440, "height": 900},
                args=["--disable-blink-features=AutomationControlled"],
            )
            # Reuse first page if any
            if self._ctx.pages:
                self._page = self._ctx.pages[0]
            else:
                self._page = await self._ctx.new_page()
            return self._ctx

    async def close(self):
        if self._ctx:
            try: await self._ctx.close()
            except Exception: pass
        if self._pw:
            try: await self._pw.stop()
            except Exception: pass
        self._ctx = None; self._page = None; self._pw = None

    async def get_page(self) -> Optional[Page]:
        await self.ensure()
        if self._page and not self._page.is_closed():
            return self._page
        if self._ctx:
            self._page = await self._ctx.new_page()
            return self._page
        return None

    # ---------- Actions ----------
    async def open(self, url: str) -> Dict[str, Any]:
        page = await self.get_page()
        if not page:
            return {"ok": False, "error": "playwright indisponível"}
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return {"ok": True, "output": {"url": page.url, "title": await page.title()}}

    async def navigate(self, url: str) -> Dict[str, Any]:
        return await self.open(url)

    async def evaluate(self, script: str) -> Dict[str, Any]:
        page = await self.get_page()
        if not page:
            return {"ok": False, "error": "playwright indisponível"}
        result = await page.evaluate(script)
        return {"ok": True, "output": result}

    async def screenshot(self) -> Dict[str, Any]:
        page = await self.get_page()
        if not page:
            return {"ok": False, "error": "playwright indisponível"}
        buf = await page.screenshot(full_page=False)
        return {"ok": True, "output": {"b64": base64.b64encode(buf).decode("ascii"), "mime": "image/png"}}

    async def search(self, engine: str, query: str) -> Dict[str, Any]:
        engines = {
            "google": "https://www.google.com/search?q=",
            "bing": "https://www.bing.com/search?q=",
            "duckduckgo": "https://duckduckgo.com/?q=",
            "youtube": "https://www.youtube.com/results?search_query=",
        }
        base = engines.get((engine or "google").lower(), engines["google"])
        return await self.open(base + query.replace(" ", "+"))

    async def login(self, site: str, url: str, username: str, password: str,
                    username_selector: Optional[str] = None,
                    password_selector: Optional[str] = None,
                    submit_selector: Optional[str] = None) -> Dict[str, Any]:
        page = await self.get_page()
        if not page:
            return {"ok": False, "error": "playwright indisponível"}
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Best-effort default selectors
        us = username_selector or 'input[type="email"], input[name*="user" i], input[name*="email" i], input[autocomplete="username"]'
        ps = password_selector or 'input[type="password"], input[autocomplete="current-password"]'
        ss = submit_selector or 'button[type="submit"], input[type="submit"], button:has-text("Entrar"), button:has-text("Log In")'
        try:
            await page.wait_for_selector(us, timeout=8000)
            await page.fill(us, username)
        except Exception:
            return {"ok": False, "error": "campo de usuário não encontrado"}
        try:
            await page.fill(ps, password)
        except Exception:
            # Some sites require clicking "Next" between email and password
            try:
                await page.locator(ss).first.click()
                await page.wait_for_selector(ps, timeout=8000)
                await page.fill(ps, password)
            except Exception:
                return {"ok": False, "error": "campo de senha não encontrado"}
        try:
            await page.locator(ss).first.click()
        except Exception:
            pass
        await page.wait_for_timeout(3000)
        return {"ok": True, "output": {"site": site, "url": page.url, "title": await page.title()}}

    async def spotify_play(self, query: str, username: Optional[str] = None,
                            password: Optional[str] = None) -> Dict[str, Any]:
        page = await self.get_page()
        if not page:
            return {"ok": False, "error": "playwright indisponível"}
        await page.goto("https://open.spotify.com/", wait_until="domcontentloaded", timeout=30000)
        # If not signed in, try login (best-effort)
        try:
            login_btn = page.locator('a[href*="/login"], button:has-text("Log in"), button:has-text("Entrar")').first
            if await login_btn.count() > 0 and username and password:
                await login_btn.click()
                await page.wait_for_selector('#login-username, input[name="username"]', timeout=15000)
                await page.fill('#login-username, input[name="username"]', username)
                await page.fill('#login-password, input[name="password"]', password)
                await page.locator('#login-button, button[type="submit"]').first.click()
                await page.wait_for_timeout(5000)
        except Exception:
            pass
        # Search
        await page.goto(f"https://open.spotify.com/search/{query.replace(' ', '%20')}", wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        # Try to click the first result's play button
        try:
            await page.locator('[data-testid="play-button"]').first.click(timeout=5000)
            return {"ok": True, "output": {"query": query, "status": "tocando"}}
        except Exception:
            return {"ok": True, "output": {"query": query, "status": "resultado aberto, clique manualmente se autoplay bloqueado"}}


BROWSER = BrowserManager()
