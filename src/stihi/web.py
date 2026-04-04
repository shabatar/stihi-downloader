"""Flask web UI for downloading and browsing stihi.ru poetry."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import threading
import time
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    redirect,
    render_template,
    request,
    session,
    stream_with_context,
    url_for,
)

from .crawler import CancelledError, Crawler
from .models import Author, Poem, Section
from .parser import parse_author_page, parse_poem_listing, parse_poem_page
from .storage import save_dataset

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

OUTPUT_DIR = Path("./output")

# In-memory state keyed by username
_downloads: dict[str, dict] = {}
_crawlers: dict[str, Crawler] = {}
_lock = threading.Lock()


# ── CSRF ─────────────────────────────────────────────────────────────


def _generate_csrf_token() -> str:
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def _check_csrf() -> None:
    token = session.get("_csrf_token")
    form_token = request.form.get("_csrf_token")
    if not token or not form_token or not secrets.compare_digest(token, form_token):
        abort(403)


app.jinja_env.globals["csrf_token"] = _generate_csrf_token


# ── Helpers ──────────────────────────────────────────────────────────


def _clamp_float(raw: str, lo: float, hi: float, default: float) -> float:
    """Parse a float from form input, clamping to [lo, hi]."""
    try:
        val = float(raw)
    except (ValueError, TypeError):
        return default
    if not (lo <= val <= hi):  # also catches NaN
        return max(lo, min(hi, val)) if val == val else default
    return val


def _clean_username(raw: str) -> str:
    raw = raw.strip().rstrip("/")
    if "/avtor/" in raw:
        raw = raw.split("/avtor/")[-1].split("&")[0].split("?")[0].strip()
    # Reject path traversal in usernames
    if not raw or "/" in raw or "\\" in raw or ".." in raw:
        return ""
    return raw


def _get_downloaded_authors() -> list[dict]:
    """List all previously downloaded authors from the output directory."""
    authors: list[dict] = []
    if not OUTPUT_DIR.exists():
        return authors
    for meta_path in sorted(OUTPUT_DIR.glob("*/metadata.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            authors.append(meta)
        except Exception:
            pass
    return authors


def _load_author_meta(username: str) -> dict | None:
    meta_path = _safe_resolve(OUTPUT_DIR, username, "metadata.json")
    if meta_path is None or not meta_path.exists():
        return None
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _safe_resolve(base: Path, *parts: str) -> Path | None:
    """Resolve path parts under base, returning None if traversal is detected."""
    resolved = (base / Path(*parts)).resolve()
    if not resolved.is_relative_to(base.resolve()):
        return None
    return resolved


def _read_poem_file(username: str, section_dir: str, filename: str) -> str | None:
    path = _safe_resolve(OUTPUT_DIR, username, section_dir, filename)
    if path is None or not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _resolve_section_name(meta: dict, section_dir: str) -> str:
    """Map a filesystem section dirname back to its display name."""
    if meta and meta.get("sections"):
        for sec_name in meta["sections"]:
            if Section(name=sec_name).dirname == section_dir:
                return sec_name
    return section_dir


# ── Download engine ──────────────────────────────────────────────────


def _run_download(
    username: str,
    delay_min: float,
    delay_max: float,
    selected_book_ids: list[int],
    include_main: bool,
) -> None:
    state = _downloads[username]
    state.update(
        status="running",
        phase="Запуск браузера...",
        progress=0,
        total=0,
        current="",
        error=None,
    )

    async def _do() -> None:
        crawler = Crawler(delay_range=(delay_min, delay_max))
        _crawlers[username] = crawler
        author = Author(username=username)

        try:
            async with crawler:
                # Discover structure
                state["phase"] = "Сканирование автора..."
                display_name, poem_count, books = await crawler.discover_books(username)
                state["author_name"] = display_name

                author.display_name = display_name
                author.poem_count = poem_count

                all_poems: list[Poem] = []

                # Main listing
                if include_main:
                    page_num = 0
                    async for html in crawler.fetch_all_author_pages(username):
                        page_num += 1
                        state["phase"] = f"Основной список (стр. {page_num})..."
                        poems = parse_poem_listing(html)
                        all_poems.extend(poems)

                # Selected books
                if selected_book_ids:
                    selected = [b for b in books if b.book_id in selected_book_ids]
                    for bi, book in enumerate(selected, 1):
                        page_num = 0
                        async for html in crawler.fetch_book_pages(book):
                            page_num += 1
                            state["phase"] = f"«{book.name}» (стр. {page_num})..."
                            poems = parse_poem_listing(html)
                            all_poems.extend(poems)

                # Deduplicate
                seen: set[str] = set()
                unique: list[Poem] = []
                for p in all_poems:
                    if p.url not in seen:
                        seen.add(p.url)
                        unique.append(p)

                state["total"] = len(unique)
                state["phase"] = "Скачивание стихов..."

                if not unique:
                    state["status"] = "error"
                    state["error"] = "Стихов не найдено"
                    return

                # Download each poem
                for i, poem in enumerate(unique):
                    crawler.check_cancelled()
                    state["progress"] = i
                    state["current"] = poem.title
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
                    except Exception:
                        pass

                state["progress"] = len(unique)
                state["phase"] = "Сохранение..."
                save_dataset(author, OUTPUT_DIR)

                state["status"] = "done"
                state["phase"] = "Готово!"

        except CancelledError:
            if author.all_poems:
                save_dataset(author, OUTPUT_DIR)
            state["status"] = "stopped"
            state["phase"] = f"Остановлено (сохранено {len(author.all_poems)} стихов)"
        except Exception as exc:
            if author.all_poems:
                save_dataset(author, OUTPUT_DIR)
            state["status"] = "error"
            state["error"] = str(exc)
        finally:
            _crawlers.pop(username, None)

    asyncio.run(_do())


# ── Routes ───────────────────────────────────────────────────────────


@app.route("/")
def index():
    return render_template("index.html", authors=_get_downloaded_authors())


@app.route("/preview", methods=["POST"])
def preview():
    _check_csrf()
    username = _clean_username(request.form.get("username", ""))
    if not username:
        return redirect(url_for("index"))

    delay_min = _clamp_float(request.form.get("delay_min", "1.0"), 0.5, 60.0, 1.0)
    delay_max = _clamp_float(request.form.get("delay_max", "3.0"), 0.5, 60.0, 3.0)
    if delay_max < delay_min:
        delay_max = delay_min

    try:

        async def _discover():
            async with Crawler(delay_range=(0.3, 0.5)) as c:
                return await c.discover_books(username)

        display_name, poem_count, books = asyncio.run(_discover())
    except Exception:
        return render_template(
            "index.html",
            authors=_get_downloaded_authors(),
            error="Не удалось загрузить профиль. Проверьте имя автора.",
        )

    if display_name == "Автор не найден":
        return render_template(
            "index.html",
            authors=_get_downloaded_authors(),
            error=f"Автор «{username}» не найден",
        )

    books_data = [
        {"book_id": b.book_id, "name": b.name, "poem_count": b.poem_count}
        for b in books
    ]
    main_count = max(poem_count - sum(b.poem_count for b in books), 0) or 50

    return render_template(
        "preview.html",
        username=username,
        display_name=display_name,
        poem_count=poem_count,
        books=books_data,
        main_count=main_count,
        delay_min=delay_min,
        delay_max=delay_max,
    )


@app.route("/download", methods=["POST"])
def start_download():
    _check_csrf()
    username = _clean_username(request.form.get("username", ""))
    if not username:
        return redirect(url_for("index"))

    delay_min = _clamp_float(request.form.get("delay_min", "1.0"), 0.5, 60.0, 1.0)
    delay_max = _clamp_float(request.form.get("delay_max", "3.0"), 0.5, 60.0, 3.0)
    if delay_max < delay_min:
        delay_max = delay_min
    include_main = request.form.get("include_main") == "1"

    selected_book_ids: list[int] = []
    for x in request.form.getlist("books"):
        try:
            selected_book_ids.append(int(x))
        except ValueError:
            continue

    if not include_main and not selected_book_ids:
        return redirect(url_for("index"))

    with _lock:
        if username in _downloads and _downloads[username].get("status") == "running":
            return redirect(url_for("download_progress", username=username))
        _downloads[username] = {"status": "starting"}

    threading.Thread(
        target=_run_download,
        args=(username, delay_min, delay_max, selected_book_ids, include_main),
        daemon=True,
    ).start()
    return redirect(url_for("download_progress", username=username))


@app.route("/stop/<username>", methods=["POST"])
def stop_download(username: str):
    _check_csrf()
    with _lock:
        crawler = _crawlers.get(username)
        if crawler:
            crawler.cancel()
    return redirect(url_for("download_progress", username=username))


@app.route("/download/<username>")
def download_progress(username: str):
    return render_template("progress.html", username=username)


@app.route("/api/progress/<username>")
def api_progress(username: str):
    """Server-Sent Events stream for download progress."""

    def generate():
        while True:
            state = _downloads.get(username, {"status": "unknown"})
            yield f"data: {json.dumps(state, ensure_ascii=False)}\n\n"
            if state.get("status") in ("done", "error", "unknown", "stopped"):
                break
            time.sleep(0.5)

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/browse/<username>")
def browse_author(username: str):
    meta = _load_author_meta(username)
    if not meta:
        return redirect(url_for("index"))

    author_dir = OUTPUT_DIR / username
    sections = []
    for sec_name, sec_data in (meta.get("sections") or {}).items():
        sec_dir = author_dir / Section(name=sec_name).dirname
        file_count = len(list(sec_dir.glob("*.txt"))) if sec_dir.exists() else 0
        sections.append({
            "name": sec_name,
            "dirname": Section(name=sec_name).dirname,
            "count": sec_data.get("poem_count", file_count),
        })

    return render_template("browse.html", meta=meta, username=username, sections=sections)


@app.route("/browse/<username>/<section_dir>")
def browse_section(username: str, section_dir: str):
    meta = _load_author_meta(username)
    if not meta:
        return redirect(url_for("index"))

    sec_path = _safe_resolve(OUTPUT_DIR, username, section_dir)
    if sec_path is None or not sec_path.is_dir():
        return redirect(url_for("browse_author", username=username))

    poems = []
    for f in sorted(sec_path.glob("*.txt")):
        first_line = f.read_text(encoding="utf-8").split("\n", 1)[0]
        poems.append({"filename": f.name, "title": first_line})

    return render_template(
        "section.html",
        meta=meta,
        username=username,
        section_dir=section_dir,
        section_name=_resolve_section_name(meta, section_dir),
        poems=poems,
    )


@app.route("/poem/<username>/<section_dir>/<filename>")
def view_poem(username: str, section_dir: str, filename: str):
    meta = _load_author_meta(username)
    content = _read_poem_file(username, section_dir, filename)
    if content is None:
        return redirect(url_for("browse_author", username=username))

    title = content.split("\n", 1)[0] if content else filename

    return render_template(
        "poem.html",
        meta=meta,
        username=username,
        section_dir=section_dir,
        section_name=_resolve_section_name(meta, section_dir),
        filename=filename,
        title=title,
        content=content,
    )


def run_web(host: str = "127.0.0.1", port: int = 5000, output_dir: str = "./output") -> None:
    """Start the web UI server."""
    global OUTPUT_DIR
    OUTPUT_DIR = Path(output_dir)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Starting at http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)
