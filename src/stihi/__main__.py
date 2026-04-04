"""CLI entry point for stihi.ru poetry downloader."""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from .crawler import CancelledError, Crawler
from .models import Author, Poem
from .parser import parse_author_page, parse_poem_listing, parse_poem_page
from .storage import save_dataset

console = Console()


async def run(
    username: str,
    output_dir: Path,
    delay: tuple[float, float],
    headless: bool,
) -> None:
    console.print(f"\n[bold cyan]stihi.ru downloader[/] — [bold]{username}[/]\n")

    crawler = Crawler(delay_range=delay, headless=headless)

    # Graceful shutdown on Ctrl-C
    def _on_sigint(*_):
        console.print("\n[yellow]Stopping — saving downloaded poems...[/]")
        crawler.cancel()

    signal.signal(signal.SIGINT, _on_sigint)

    author: Author | None = None

    try:
        async with crawler:
            # ── Phase 1: Discover structure ──────────────────────────
            console.print("[yellow]Phase 1:[/] Discovering author structure...")
            display_name, poem_count, books = await crawler.discover_books(username)

            if display_name == "Автор не найден":
                console.print(f"[red]Author «{username}» not found.[/]")
                sys.exit(1)

            author = Author(username=username, display_name=display_name, poem_count=poem_count)
            console.print(f"  Author: [bold]{display_name}[/] ({poem_count} poems)")
            if books:
                console.print(f"  Books:  {len(books)}")
                for b in books:
                    console.print(f"          {b.name} ({b.poem_count})")

            # ── Phase 2: Collect poem stubs ──────────────────────────
            console.print("\n[yellow]Phase 2:[/] Scanning poem listings...")
            all_poems: list[Poem] = []

            # Main listing
            page_num = 0
            async for html in crawler.fetch_all_author_pages(username):
                page_num += 1
                if page_num == 1:
                    _, poems = parse_author_page(html, username)
                else:
                    poems = parse_poem_listing(html)
                all_poems.extend(poems)
                console.print(f"  Main listing page {page_num}: {len(poems)} poems")

            # Each book
            for book in books:
                page_num = 0
                async for html in crawler.fetch_book_pages(book):
                    page_num += 1
                    poems = parse_poem_listing(html)
                    all_poems.extend(poems)
                console.print(f"  Book «{book.name}»: {page_num} pages")

            # Deduplicate
            seen: set[str] = set()
            unique: list[Poem] = []
            for p in all_poems:
                if p.url not in seen:
                    seen.add(p.url)
                    unique.append(p)

            console.print(f"\n  [green]Total unique poems: {len(unique)}[/]\n")

            if not unique:
                console.print("[red]No poems found. Check the username.[/]")
                sys.exit(1)

            # ── Phase 3: Download each poem ──────────────────────────
            console.print("[yellow]Phase 3:[/] Downloading poem texts...\n")
            failed: list[tuple[Poem, str]] = []

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Downloading", total=len(unique))

                for poem in unique:
                    crawler.check_cancelled()
                    try:
                        html = await crawler.fetch(poem.url)
                        data = parse_poem_page(html)
                        poem.text = data["text"]
                        poem.dedication = data["dedication"]
                        poem.epigraph = data["epigraph"]
                        if poem.title in ("***", "...") and data["title"]:
                            poem.title = data["title"]
                        author.add_poem(poem)
                    except CancelledError:
                        raise
                    except Exception as exc:
                        failed.append((poem, str(exc)))
                    progress.update(task, advance=1)

    except CancelledError:
        pass  # fall through to save

    # ── Phase 4: Save ────────────────────────────────────────────────
    if author and author.all_poems:
        console.print(f"\n[yellow]Saving...[/]")
        dataset_path = save_dataset(author, output_dir)
        console.print(f"\n[bold green]Done![/]")
        console.print(f"  Poems downloaded: [bold]{len(author.all_poems)}[/]")
        console.print(f"  Sections:         [bold]{len(author.sections)}[/]")
        console.print(f"  Dataset:          [bold]{dataset_path}[/]")
        if failed:
            console.print(f"  [red]Failed: {len(failed)}[/]")
    else:
        console.print("[red]Nothing to save.[/]")

    console.print()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="stihi",
        description="Download all poetry from a stihi.ru author profile.",
    )
    parser.add_argument(
        "username",
        help="Author username or full profile URL",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("./output"),
        help="Output directory (default: ./output)",
    )
    parser.add_argument(
        "--delay-min",
        type=float,
        default=1.0,
        help="Minimum delay between requests in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--delay-max",
        type=float,
        default=3.0,
        help="Maximum delay between requests in seconds (default: 3.0)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Show the browser window (useful for debugging)",
    )

    args = parser.parse_args()

    # Accept full URLs
    username = args.username.strip().rstrip("/")
    if "/avtor/" in username:
        username = username.split("/avtor/")[-1].split("&")[0].split("?")[0].strip()

    asyncio.run(
        run(
            username=username,
            output_dir=args.output,
            delay=(args.delay_min, args.delay_max),
            headless=not args.no_headless,
        )
    )


if __name__ == "__main__":
    main()
