"""Tests for dataset storage."""

import json
from pathlib import Path

from stihi.models import Author, Poem
from stihi.storage import save_dataset


def _make_author() -> Author:
    a = Author(username="testuser", display_name="Test Author", poem_count=3)
    a.add_poem(Poem(
        title="Утро", url="/2024/01/01/1", text="Строка первая\nСтрока вторая",
        section="лирика", date="01.01.2024 08:00",
    ))
    a.add_poem(Poem(
        title="Вечер", url="/2024/01/02/2", text="Тихо всё вокруг",
        section="лирика", date="02.01.2024 20:00",
    ))
    a.add_poem(Poem(
        title="Ночь", url="/2024/01/03/3", text="Звёзды в небе",
        section="философия", date="03.01.2024 23:00",
    ))
    return a


class TestSaveDataset:
    def test_creates_directory_structure(self, tmp_path: Path):
        author = _make_author()
        root = save_dataset(author, tmp_path)
        assert root == tmp_path / "testuser"
        assert root.is_dir()
        assert (root / "лирика").is_dir()
        assert (root / "философия").is_dir()

    def test_creates_poem_files(self, tmp_path: Path):
        author = _make_author()
        root = save_dataset(author, tmp_path)
        lyric_files = sorted((root / "лирика").glob("*.txt"))
        assert len(lyric_files) == 2
        philo_files = sorted((root / "философия").glob("*.txt"))
        assert len(philo_files) == 1

    def test_poem_file_contains_text(self, tmp_path: Path):
        author = _make_author()
        root = save_dataset(author, tmp_path)
        files = sorted((root / "лирика").glob("*.txt"))
        content = files[0].read_text(encoding="utf-8")
        assert "Утро" in content
        assert "Строка первая" in content
        assert "Строка вторая" in content

    def test_poem_file_contains_metadata(self, tmp_path: Path):
        author = _make_author()
        root = save_dataset(author, tmp_path)
        files = sorted((root / "лирика").glob("*.txt"))
        content = files[0].read_text(encoding="utf-8")
        assert "Дата: 01.01.2024 08:00" in content
        assert "Раздел: лирика" in content
        assert "URL: https://stihi.ru/2024/01/01/1" in content

    def test_creates_metadata_json(self, tmp_path: Path):
        author = _make_author()
        root = save_dataset(author, tmp_path)
        meta_path = root / "metadata.json"
        assert meta_path.exists()
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        assert data["username"] == "testuser"
        assert data["downloaded_count"] == 3
        assert len(data["sections"]) == 2

    def test_file_numbering(self, tmp_path: Path):
        author = _make_author()
        root = save_dataset(author, tmp_path)
        files = sorted(f.name for f in (root / "лирика").glob("*.txt"))
        assert files[0].startswith("001_")
        assert files[1].startswith("002_")

    def test_poem_with_dedication(self, tmp_path: Path):
        a = Author(username="test")
        a.add_poem(Poem(
            title="Test", url="/1", text="body",
            section="s", dedication="Маме",
        ))
        root = save_dataset(a, tmp_path)
        content = list((root / "s").glob("*.txt"))[0].read_text(encoding="utf-8")
        assert "Посвящение: Маме" in content

    def test_idempotent(self, tmp_path: Path):
        author = _make_author()
        save_dataset(author, tmp_path)
        save_dataset(author, tmp_path)  # should not fail
        files = sorted((tmp_path / "testuser" / "лирика").glob("*.txt"))
        assert len(files) == 2
