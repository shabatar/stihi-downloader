"""Dataset storage — organises downloaded poems into section folders."""

from __future__ import annotations

from pathlib import Path

from .models import Author, Poem


def save_dataset(author: Author, output_dir: Path) -> Path:
    """Save all poems organised by section.

    Layout::

        output_dir/<username>/
            metadata.json
            <section>/
                001_title.txt
                002_title.txt
    """
    root = output_dir / author.username
    root.mkdir(parents=True, exist_ok=True)

    for section in author.sections.values():
        sec_dir = root / section.dirname
        sec_dir.mkdir(exist_ok=True)

        for i, poem in enumerate(section.poems, 1):
            filepath = sec_dir / f"{i:03d}_{poem.filename}.txt"
            _write_poem_file(filepath, poem)

    author.save_metadata(root / "metadata.json")
    return root


def _write_poem_file(path: Path, poem: Poem) -> None:
    lines: list[str] = [
        poem.title,
        "=" * max(len(poem.title), 40),
        "",
    ]

    if poem.dedication:
        lines += [f"Посвящение: {poem.dedication}", ""]
    if poem.epigraph:
        lines += [f"Эпиграф: {poem.epigraph}", ""]

    lines += [poem.text, "", "---"]

    meta_parts: list[str] = []
    if poem.date:
        meta_parts.append(f"Дата: {poem.date}")
    if poem.section:
        meta_parts.append(f"Раздел: {poem.section}")
    meta_parts.append(f"URL: https://stihi.ru{poem.url}")
    lines.append("  ".join(meta_parts))

    path.write_text("\n".join(lines), encoding="utf-8")
