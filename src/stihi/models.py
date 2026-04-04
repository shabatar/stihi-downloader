"""Data models for poems, sections, and authors."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*]')


def _safe_name(name: str, fallback: str = "untitled", max_len: int = 200) -> str:
    """Convert *name* into a filesystem-safe string."""
    safe = name.strip()
    if not safe or safe == "***":
        safe = fallback
    safe = _UNSAFE_CHARS.sub("_", safe)
    safe = "_".join(safe.split())
    return safe[:max_len]


@dataclass
class Poem:
    title: str
    url: str  # relative, e.g. /2024/01/15/1234
    text: str = ""
    section: str = ""
    date: str = ""  # DD.MM.YYYY HH:MM
    dedication: str = ""
    epigraph: str = ""

    @property
    def filename(self) -> str:
        fallback = self.url.strip("/").replace("/", "_")
        return _safe_name(self.title, fallback=fallback)


@dataclass
class Section:
    name: str
    poems: list[Poem] = field(default_factory=list)

    @property
    def dirname(self) -> str:
        return _safe_name(self.name, fallback="unsorted")


@dataclass
class Author:
    username: str
    display_name: str = ""
    poem_count: int = 0
    sections: dict[str, Section] = field(default_factory=dict)

    def add_poem(self, poem: Poem) -> None:
        sec_name = poem.section or "Без раздела"
        if sec_name not in self.sections:
            self.sections[sec_name] = Section(name=sec_name)
        self.sections[sec_name].poems.append(poem)

    @property
    def all_poems(self) -> list[Poem]:
        return [p for sec in self.sections.values() for p in sec.poems]

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "display_name": self.display_name,
            "poem_count": self.poem_count,
            "downloaded_count": len(self.all_poems),
            "sections": {
                name: {
                    "name": sec.name,
                    "poem_count": len(sec.poems),
                    "poems": [asdict(p) for p in sec.poems],
                }
                for name, sec in self.sections.items()
            },
        }

    def save_metadata(self, path: Path) -> None:
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
