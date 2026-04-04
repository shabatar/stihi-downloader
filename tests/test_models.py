"""Tests for data models."""

import json
from pathlib import Path

from stihi.models import Author, Poem, Section


class TestPoem:
    def test_filename_normal(self):
        p = Poem(title="Весенний дождь", url="/2024/01/01/1")
        assert p.filename == "Весенний_дождь"

    def test_filename_unsafe_chars(self):
        p = Poem(title='Test / Poem: "Hello"', url="/2024/01/01/1")
        assert "/" not in p.filename
        assert '"' not in p.filename
        assert ":" not in p.filename

    def test_filename_stars_fallback(self):
        p = Poem(title="***", url="/2024/03/15/42")
        assert p.filename == "2024_03_15_42"

    def test_filename_empty_fallback(self):
        p = Poem(title="", url="/2024/03/15/42")
        assert p.filename == "2024_03_15_42"

    def test_filename_truncated(self):
        p = Poem(title="A" * 300, url="/2024/01/01/1")
        assert len(p.filename) <= 200


class TestSection:
    def test_dirname(self):
        s = Section(name="философская лирика")
        assert s.dirname == "философская_лирика"

    def test_dirname_empty(self):
        s = Section(name="")
        assert s.dirname == "unsorted"

    def test_dirname_unsafe(self):
        s = Section(name='test/section:"hello"')
        assert "/" not in s.dirname
        assert '"' not in s.dirname


class TestAuthor:
    def test_add_poem_creates_section(self):
        a = Author(username="test")
        p = Poem(title="Test", url="/1", section="лирика")
        a.add_poem(p)
        assert "лирика" in a.sections
        assert len(a.sections["лирика"].poems) == 1

    def test_add_poem_default_section(self):
        a = Author(username="test")
        p = Poem(title="Test", url="/1", section="")
        a.add_poem(p)
        assert "Без раздела" in a.sections

    def test_add_poem_groups_by_section(self):
        a = Author(username="test")
        a.add_poem(Poem(title="A", url="/1", section="sec1"))
        a.add_poem(Poem(title="B", url="/2", section="sec1"))
        a.add_poem(Poem(title="C", url="/3", section="sec2"))
        assert len(a.sections) == 2
        assert len(a.sections["sec1"].poems) == 2
        assert len(a.sections["sec2"].poems) == 1

    def test_all_poems(self):
        a = Author(username="test")
        a.add_poem(Poem(title="A", url="/1", section="s1"))
        a.add_poem(Poem(title="B", url="/2", section="s2"))
        assert len(a.all_poems) == 2

    def test_to_dict(self):
        a = Author(username="test", display_name="Test Author", poem_count=5)
        a.add_poem(Poem(title="A", url="/1", section="s1", text="hello"))
        d = a.to_dict()
        assert d["username"] == "test"
        assert d["display_name"] == "Test Author"
        assert d["poem_count"] == 5
        assert d["downloaded_count"] == 1
        assert "s1" in d["sections"]

    def test_save_metadata(self, tmp_path: Path):
        a = Author(username="test", display_name="Test")
        a.add_poem(Poem(title="A", url="/1", section="s"))
        meta_path = tmp_path / "metadata.json"
        a.save_metadata(meta_path)
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        assert data["username"] == "test"
        assert data["downloaded_count"] == 1
