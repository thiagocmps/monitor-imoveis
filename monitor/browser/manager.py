"""Gestor de browser Playwright assíncrono reutilizável.

Abre apenas uma página por vez (concorrência padrão 1), bloqueia
recursos pesados, fecha tudo de forma garantida e tira screenshots /
snapshots de HTML em falhas.
"""

from __future__ import annotations

import logging
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from monitor.exceptions import CollectorError
from monitor.settings import PROJECT_ROOT, BrowserSettings

SCREENSHOT_DIR = PROJECT_ROOT / "screenshots"
SNAPSHOT_DIR = PROJECT_ROOT / "snapshots"

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)

_BLOCKED_RESOURCE_TYPES = {"image", "font", "media"}


class BrowserManager:
    """Cria e gere um browser Chromium único por execução."""

    def __init__(self, settings: BrowserSettings) -> None:
        self.settings = settings
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def _channels(self) -> list[str | None]:
        """Canais a tentar, por ordem. 'auto' usa Chrome instalado e só
        depois o Chromium empacotado do Playwright."""
        channel = self.settings.channel
        if channel == "auto":
            return ["chrome", "msedge", "chromium", None]
        if channel == "bundled":
            return [None]
        if channel == "chromium":
            return ["chromium", None]
        return [channel, None]

    @property
    def page(self) -> Page | None:
        return self._page

    async def start(self) -> None:
        from playwright.async_api import async_playwright

        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        launch_kwargs = dict(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        last_error: Exception | None = None
        for channel in self._channels():
            try:
                kwargs = dict(launch_kwargs)
                if channel:
                    kwargs["channel"] = channel
                self._browser = await self._pw.chromium.launch(**kwargs)
                logger.info("Browser iniciado (channel=%s)", channel or "bundled")
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "Falha ao iniciar browser (channel=%s): %s", channel or "bundled", exc
                )
                continue
        if self._browser is None:
            await self._pw.stop()
            raise CollectorError(f"Falha ao iniciar Chromium: {last_error}") from last_error
        self._context = await self._browser.new_context(
            locale="pt-PT",
            timezone_id="Europe/Lisbon",
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 800},
        )
        self._page = await self._context.new_page()
        await self._install_request_blocking(self._page)

    async def _install_request_blocking(self, page: Page) -> None:
        block = set()
        if self.settings.block_images:
            block.add("image")
        if self.settings.block_fonts:
            block.add("font")
        if self.settings.block_media:
            block.add("media")
        if not block:
            return

        async def _should_abort(route: Any) -> bool:
            request_type = getattr(route.request, "resource_type", "other") or "other"
            return request_type in block

        async def _route(route: Any) -> None:
            if await _should_abort(route):
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", _route)

    async def navigate(self, url: str) -> str:
        """Abre um URL e devolve o HTML da página."""
        if self._page is None:
            raise CollectorError("Browser não iniciado")
        try:
            await self._page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.settings.navigation_timeout_seconds * 1000,
            )
        except PlaywrightTimeoutError as exc:
            raise CollectorError(f"Timeout ao navegar para {url}") from exc
        return await self._page.content()

    async def screenshot(self, name: str) -> str:
        """Guarda screenshot de erro. Devolve o caminho relativo."""
        if self._page is None or not self.settings.save_screenshot_on_error:
            return ""
        safe = _safe(name)
        path = SCREENSHOT_DIR / f"{safe}.png"
        try:
            await self._page.screenshot(path=str(path), full_page=False)
        except Exception:
            return ""
        return str(path.relative_to(PROJECT_ROOT))

    async def snapshot_html(self, name: str, html: str | None = None) -> str:
        """Guarda snapshot de HTML em erro. Devolve o caminho relativo."""
        if not self.settings.save_html_on_error:
            return ""
        safe = _safe(name)
        path = SNAPSHOT_DIR / f"{safe}.html"
        try:
            content = html if html is not None else await self._page.content()
            path.write_text(content[:500_000], encoding="utf-8")
        except Exception:
            return ""
        return str(path.relative_to(PROJECT_ROOT))

    async def stop(self) -> None:
        """Fecha página, contexto, browser e sessão Playwright."""
        import contextlib

        for target in (self._page, self._context, self._browser):
            if target is None:
                continue
            with contextlib.suppress(Exception):
                await target.close()
        self._page = None
        self._context = None
        self._browser = None
        if getattr(self, "_pw", None) is not None:
            with contextlib.suppress(Exception):
                await self._pw.stop()
            self._pw = None  # type: ignore[attr-defined]

    async def __aenter__(self) -> BrowserManager:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()


def _safe(name: str) -> str:
    cleaned = "".join(c for c in name if c.isalnum() or c in "_-")
    return cleaned[:80] or "snapshot"
