"""HTML parsers for stihi.ru author pages, listings, and poem pages."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag

from .models import Author, Poem


def parse_author_page(html: str, username: str) -> tuple[Author, list[Poem]]:
    """Parse an author listing page.

    Returns an ``Author`` with basic metadata and a list of poem stubs
    (no full text — only title, URL, section, date).
    """
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    display_name = h1.get_text(strip=True) if h1 else username

    poem_count = 0
    m = re.search(r"Произведений:\s*<b>(\d+)</b>", html)
    if m:
        poem_count = int(m.group(1))

    author = Author(username=username, display_name=display_name, poem_count=poem_count)
    poems = _extract_poem_stubs(soup)
    return author, poems


def parse_poem_listing(html: str) -> list[Poem]:
    """Parse a paginated listing page and return poem stubs."""
    soup = BeautifulSoup(html, "html.parser")
    return _extract_poem_stubs(soup)


def parse_poem_page(html: str) -> dict[str, str]:
    """Parse an individual poem page.

    Returns ``{"title", "text", "dedication", "epigraph"}``.
    """
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""

    dedication = ""
    subtitle_div = soup.find("div", class_="subtitle")
    if subtitle_div:
        dedication = subtitle_div.get_text(strip=True)

    epigraph = ""
    epigraph_div = soup.find("div", class_="epigraph")
    if epigraph_div:
        epigraph = epigraph_div.get_text("\n", strip=True)

    text = ""
    text_div = soup.find("div", class_="text")
    if text_div:
        text = _extract_poem_text(text_div)

    return {"title": title, "text": text, "dedication": dedication, "epigraph": epigraph}


# ── Internal helpers ─────────────────────────────────────────────────


def _extract_poem_stubs(soup: BeautifulSoup) -> list[Poem]:
    """Extract poem stubs (title, url, section, date) from a listing."""
    poems: list[Poem] = []
    seen_urls: set[str] = set()

    for link in soup.find_all("a", class_="poemlink"):
        href = link.get("href", "")
        if not href or href in seen_urls:
            continue
        seen_urls.add(href)

        title = link.get_text(strip=True)

        section = ""
        date = ""
        small = link.find_next_sibling("small")
        if not small:
            parent = link.parent
            if parent:
                small = parent.find("small")

        if small:
            raw = small.get_text(strip=True).lstrip("- ").strip()
            m = re.match(r"(.+?),\s*(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})$", raw)
            if m:
                section = m.group(1).strip()
                date = m.group(2).strip()
            else:
                section = raw

        poems.append(Poem(title=title, url=href, section=section, date=date))

    return poems


def _extract_poem_text(div: Tag) -> str:
    """Extract clean poem text from ``<div class="text">``, preserving line breaks."""
    lines: list[str] = []
    current: list[str] = []

    for child in div.children:
        if isinstance(child, NavigableString):
            current.append(str(child))
        elif isinstance(child, Tag):
            if child.name == "br":
                lines.append("".join(current).rstrip())
                current = []
            elif child.name == "div":
                if current:
                    lines.append("".join(current).rstrip())
                    current = []
                inner = _extract_poem_text(child)
                if inner:
                    lines.append(inner)
            else:
                current.append(child.get_text())

    if current:
        lines.append("".join(current).rstrip())

    result = "\n".join(lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()
