# stihi-downloader

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Playwright](https://img.shields.io/badge/browser-Playwright-45ba4b?logo=playwright&logoColor=white)](https://playwright.dev/python/)
[![Flask](https://img.shields.io/badge/web_ui-Flask-000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Tests](https://img.shields.io/badge/tests-63%20passed-brightgreen?logo=pytest&logoColor=white)](#)

Download and browse all poetry from a [stihi.ru](https://stihi.ru) author profile.

Uses a headless Chromium browser (Playwright) to navigate the site like a real user, discovers all books and paginated listings, and saves poems as a structured dataset organized by sections.

## Features

- **Headless browser** — Playwright-based Chromium with Russian locale and timezone
- **Book-aware** — discovers all books/collections on an author's profile and paginates through each
- **Web UI** — Flask app with live download progress (SSE), book preview & selection, stop button
- **CLI** — rich progress bar, Ctrl-C graceful save
- **Structured output** — poems saved as text files in section folders with a `metadata.json` index

## Installation

```bash
# Clone and set up
git clone https://github.com/shabatar/stihi-downloader.git
cd stihi-downloader

python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Install browser (one-time)
playwright install chromium
```

## Usage

### Web UI

```bash
stihi-web                        # http://127.0.0.1:5000
stihi-web --port 8080            # custom port
```

1. Enter an author username or paste a full `stihi.ru/avtor/...` URL
2. Preview books/collections, select which to download
3. Watch live progress, stop anytime — partial results are saved

### CLI

```bash
stihi username                              # download all poems
stihi https://stihi.ru/avtor/username       # full URL works too
stihi username -o ./my_dataset              # custom output dir
stihi username --delay-min 2 --delay-max 5  # slower crawling
stihi username --no-headless                # watch the browser
```

Press Ctrl-C to stop — already downloaded poems are saved.

## Output structure

```
output/<username>/
    metadata.json
    <section_name>/
        001_poem_title.txt
        002_poem_title.txt
    <section_name>/
        001_poem_title.txt
```

Each `.txt` file contains the poem title, text, and metadata footer. `metadata.json` contains the full index of all downloaded poems with their sections, dates, and URLs.

## Requirements

- Python 3.10+
- Chromium (installed via `playwright install chromium`)

## License

MIT
