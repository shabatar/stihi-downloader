"""Playwright-based headless browser crawler for stihi.ru."""

from __future__ import annotations

import asyncio
import re
import random
from dataclasses import dataclass
from typing import AsyncIterator

from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext, Page, async_playwright

BASE_URL = "https://stihi.ru"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


@dataclass
class BookInfo:
    """A book/collection on an author's profile."""

    book_id: int
    name: str
    poem_count: int
    href: str


class CancelledError(Exception):
    """Raised when a download is cancelled by the user."""


class Crawler:
    """Headless Chromium crawler with configurable delays and cancellation support."""

    def __init__(
        self,
        delay_range: tuple[float, float] = (1.0, 3.0),
        headless: bool = True,
        timeout: int = 30_000,
    ) -> None:
        self.delay_range = delay_range
        self.headless = headless
        self.timeout = timeout
        self.cancelled = False
        self._pw = None
        self._browser = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def cancel(self) -> None:
        """Signal the crawler to stop after the current request."""
        self.cancelled = True

    def check_cancelled(self) -> None:
        """Raise CancelledError if cancellation was requested."""
        if self.cancelled:
            raise CancelledError("Download cancelled by user")

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self.headless,
        )
        self._context = await self._browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            java_script_enabled=True,
        )
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru', 'en']});"
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self.timeout)

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def __aenter__(self) -> Crawler:
        await self.start()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.stop()

    async def _human_delay(self) -> None:
        lo, hi = self.delay_range
        await asyncio.sleep(random.uniform(lo, hi))

    async def fetch(self, url: str) -> str:
        """Navigate to *url* and return the full page HTML."""
        self.check_cancelled()
        assert self._page is not None, "Call start() first"
        if url.startswith("http"):
            if not url.startswith(BASE_URL):
                raise ValueError(f"URL outside stihi.ru: {url}")
            full = url
        else:
            full = f"{BASE_URL}{url}"
        await self._human_delay()
        self.check_cancelled()
        resp = await self._page.goto(full, wait_until="domcontentloaded")
        if resp and resp.status >= 400:
            raise RuntimeError(f"HTTP {resp.status} for {full}")
        await self._page.wait_for_selector("body", timeout=self.timeout)
        return await self._page.content()

    # ── Discovery ────────────────────────────────────────────────────

    async def discover_books(self, username: str) -> tuple[str, int, list[BookInfo]]:
        """Fetch the author page and return (display_name, poem_count, books).

        This is a lightweight preview — no poem bodies are downloaded.
        """
        html = await self.fetch(f"/avtor/{username}")
        soup = BeautifulSoup(html, "html.parser")

        h1 = soup.find("h1")
        display_name = h1.get_text(strip=True) if h1 else username

        poem_count = 0
        m = re.search(r"Произведений:\s*<b>(\d+)</b>", html)
        if m:
            poem_count = int(m.group(1))

        books: list[BookInfo] = []
        for div in soup.find_all("div", id="bookheader"):
            link = div.find("a")
            if not link:
                continue
            href = link.get("href", "")
            name = link.get_text(strip=True)
            bm = re.search(r"book=(\d+)", href)
            book_id = int(bm.group(1)) if bm else 0
            small = div.find("small")
            count = 0
            if small:
                cm = re.search(r"\d+", small.get_text())
                count = int(cm.group()) if cm else 0
            books.append(BookInfo(book_id=book_id, name=name, poem_count=count, href=href))

        return display_name, poem_count, books

    # ── Pagination ───────────────────────────────────────────────────

    async def fetch_paginated(self, start_url: str) -> AsyncIterator[str]:
        """Yield HTML pages following ``&s=`` pagination links."""
        visited: set[int] = {0}
        current_url: str | None = start_url

        while current_url:
            self.check_cancelled()
            html = await self.fetch(current_url)
            yield html

            assert self._page is not None
            pagination = await self._page.evaluate(
                """
                () => {
                    const results = [];
                    for (const a of document.querySelectorAll('a[href]')) {
                        const href = a.getAttribute('href');
                        const m = href && href.match(/&s=(\\d+)/);
                        if (m) results.push({href, offset: parseInt(m[1])});
                    }
                    return results;
                }
                """
            )

            next_page = None
            for entry in sorted(pagination, key=lambda e: e["offset"]):
                if entry["offset"] not in visited:
                    next_page = entry
                    break

            if next_page:
                visited.add(next_page["offset"])
                current_url = next_page["href"]
            else:
                current_url = None

    async def fetch_all_author_pages(self, username: str) -> AsyncIterator[str]:
        """Yield HTML from the main (non-book) listing pages."""
        async for html in self.fetch_paginated(f"/avtor/{username}"):
            yield html

    async def fetch_book_pages(self, book: BookInfo) -> AsyncIterator[str]:
        """Yield HTML from all paginated pages of a specific book."""
        async for html in self.fetch_paginated(book.href):
            yield html
