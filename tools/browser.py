"""
Chrome browser automation via Playwright (sync API).

A single persistent browser context is reused across calls so pages
stay open between tool invocations within a session.
"""

from __future__ import annotations

import base64
import os
from typing import Optional

# Lazy-import so missing playwright doesn't break the whole app at startup
_browser = None
_page = None


def _get_page():
    global _browser, _page
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "Playwright not installed. Run: pip install playwright && playwright install chromium"

    if _page is None or _page.is_closed():
        pw = sync_playwright().start()
        _browser = pw.chromium.launch(
            headless=False,
            channel="chrome",  # uses system Chrome; falls back to Chromium if not found
            args=["--start-maximized"],
        )
        _page = _browser.new_page()
    return _page, None


def browser_navigate(url: str) -> dict:
    """Navigate to a URL."""
    page, err = _get_page()
    if err:
        return {"success": False, "error": err}
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        return {
            "success": True,
            "url": page.url,
            "title": page.title(),
            "status": response.status if response else None,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def browser_get_text(selector: str = "body") -> dict:
    """Extract visible text from the current page or a CSS selector."""
    page, err = _get_page()
    if err:
        return {"success": False, "error": err}
    try:
        el = page.locator(selector).first
        text = el.inner_text(timeout=10_000)
        # Truncate to avoid flooding the context
        if len(text) > 8000:
            text = text[:8000] + "\n… [truncated]"
        return {"success": True, "url": page.url, "selector": selector, "text": text}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def browser_click(selector: str = "", text: str = "") -> dict:
    """Click an element by CSS selector or by visible text."""
    page, err = _get_page()
    if err:
        return {"success": False, "error": err}
    try:
        if text:
            page.get_by_text(text, exact=False).first.click(timeout=10_000)
        elif selector:
            page.locator(selector).first.click(timeout=10_000)
        else:
            return {"success": False, "error": "Provide 'selector' or 'text'"}
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
        return {"success": True, "url": page.url, "title": page.title()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def browser_fill(selector: str, value: str, submit: bool = False) -> dict:
    """Fill an input field. Optionally press Enter to submit."""
    page, err = _get_page()
    if err:
        return {"success": False, "error": err}
    try:
        page.locator(selector).first.fill(value, timeout=10_000)
        if submit:
            page.keyboard.press("Enter")
            page.wait_for_load_state("domcontentloaded", timeout=10_000)
        return {"success": True, "url": page.url}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def browser_screenshot(path: str = "") -> dict:
    """Take a screenshot. Returns base64 if no path given, else saves to path."""
    page, err = _get_page()
    if err:
        return {"success": False, "error": err}
    try:
        if path:
            page.screenshot(path=path, full_page=False)
            return {"success": True, "saved_to": os.path.abspath(path)}
        else:
            data = page.screenshot(full_page=False)
            return {
                "success": True,
                "base64": base64.b64encode(data).decode(),
                "url": page.url,
            }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def browser_close() -> dict:
    """Close the browser."""
    global _browser, _page
    try:
        if _browser:
            _browser.close()
            _browser = None
            _page = None
        return {"success": True, "message": "Browser closed"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def browser_current_url() -> dict:
    """Return the current page URL and title."""
    page, err = _get_page()
    if err:
        return {"success": False, "error": err}
    try:
        return {"success": True, "url": page.url, "title": page.title()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
