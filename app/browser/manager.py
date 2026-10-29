"""Playwright browser lifecycle management with isolated contexts and SSRF route abortion."""

import asyncio
import os
from pathlib import Path
from typing import Optional, Set
from playwright.async_api import Browser, BrowserContext, Page, async_playwright, Route, Request

from app.config import settings
from app.logging.setup import get_logger
from app.security.url_policy import validate_url_security

logger = get_logger("browser_manager")


class PlaywrightBrowserManager:
    """Manages the Playwright lifecycle, browser instances, isolated contexts, and route-level SSRF defense."""

    def __init__(self, headless: bool = True, allow_local_test: bool = False):
        self.headless = headless
        self.allow_local_test = allow_local_test
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Start Playwright and launch Chromium."""
        async with self._lock:
            if not self._playwright:
                self._playwright = await async_playwright().start()
            if not self._browser:
                logger.info("Launching Playwright Chromium browser", extra={"headless": self.headless})
                self._browser = await self._playwright.chromium.launch(
                    headless=self.headless,
                    args=[
                        "--disable-dev-shm-usage",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                )

    async def create_isolated_context(
        self,
        task_id: str,
        domain_restrictions: Optional[Set[str]] = None,
    ) -> BrowserContext:
        """Create an isolated browser context with network-level SSRF route filtering."""
        await self.initialize()
        if not self._browser:
            raise RuntimeError("Browser failed to initialize")

        context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 AIWebAutomationAgent/1.0",
            ignore_https_errors=self.allow_local_test,
        )

        # Route handler for outbound network filtering (SSRF defense against subresources, iframes, fetches)
        async def handle_route(route: Route, request: Request) -> None:
            url = request.url
            # Allow data: and blob: URLs for inline resources
            if url.startswith("data:") or url.startswith("blob:"):
                await route.continue_()
                return

            valid, reason = validate_url_security(
                url,
                allow_local_test=self.allow_local_test,
                domain_allowlist=domain_restrictions,
            )
            if not valid:
                logger.warning(
                    f"Blocked outbound request to unsafe URL: {url} (Reason: {reason})",
                    extra={"task_id": task_id, "url": url},
                )
                await route.abort("blockedbyclient")
            else:
                await route.continue_()

        await context.route("**/*", handle_route)
        return context

    async def capture_screenshot(self, page: Page, task_id: str) -> Optional[str]:
        """Capture and save a full page screenshot for observability."""
        try:
            out_dir = Path(settings.screenshot_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            screenshot_file = out_dir / f"{task_id}.png"
            await page.screenshot(path=str(screenshot_file), full_page=False)
            return str(screenshot_file)
        except Exception as e:
            logger.error(f"Failed to capture screenshot for task {task_id}: {e}")
            return None

    async def close_context(self, context: Optional[BrowserContext]) -> None:
        """Clean up an isolated browser context."""
        if context:
            try:
                await context.close()
            except Exception as e:
                logger.warning(f"Error closing browser context: {e}")

    async def close(self) -> None:
        """Shut down browser and Playwright runtime."""
        async with self._lock:
            if self._browser:
                try:
                    await self._browser.close()
                except Exception as e:
                    logger.warning(f"Error closing browser: {e}")
                self._browser = None

            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception as e:
                    logger.warning(f"Error stopping playwright: {e}")
                self._playwright = None
