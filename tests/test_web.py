"""Tests for Flask web UI routes."""

from pathlib import Path

import pytest

from stihi.models import Author, Poem
from stihi.storage import save_dataset
from stihi.web import _clean_username, app


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    app.secret_key = "test-secret-key"
    with app.test_client() as c:
        # Seed a CSRF token in the session for POST requests
        with c.session_transaction() as sess:
            sess["_csrf_token"] = "test-csrf-token"
        yield c


@pytest.fixture()
def populated_output(tmp_path: Path):
    """Create a test dataset and point the web app at it."""
    import stihi.web as web_mod

    original = web_mod.OUTPUT_DIR
    web_mod.OUTPUT_DIR = tmp_path

    a = Author(username="testuser", display_name="Test Author", poem_count=2)
    a.add_poem(Poem(title="Poem A", url="/2024/01/01/1", text="Line 1\nLine 2", section="sec"))
    a.add_poem(Poem(title="Poem B", url="/2024/01/02/2", text="Hello", section="sec"))
    save_dataset(a, tmp_path)

    yield tmp_path

    web_mod.OUTPUT_DIR = original


class TestCleanUsername:
    def test_plain(self):
        assert _clean_username("someauthor") == "someauthor"

    def test_full_url(self):
        assert _clean_username("https://stihi.ru/avtor/someauthor") == "someauthor"

    def test_url_with_trailing_slash(self):
        assert _clean_username("https://stihi.ru/avtor/someauthor/") == "someauthor"

    def test_url_with_params(self):
        assert _clean_username("https://stihi.ru/avtor/someauthor&s=50") == "someauthor"

    def test_bare_domain(self):
        assert _clean_username("stihi.ru/avtor/user123") == "user123"

    def test_empty(self):
        assert _clean_username("") == ""

    def test_whitespace(self):
        assert _clean_username("  someauthor  ") == "someauthor"


class TestIndexRoute:
    def test_returns_200(self, client):
        r = client.get("/")
        assert r.status_code == 200

    def test_contains_form(self, client):
        r = client.get("/")
        assert b"username" in r.data
        assert b"preview" in r.data

    def test_shows_downloaded_authors(self, client, populated_output):
        r = client.get("/")
        assert b"Test Author" in r.data


class TestBrowseRoutes:
    def test_browse_author(self, client, populated_output):
        r = client.get("/browse/testuser")
        assert r.status_code == 200
        assert "Test Author" in r.data.decode("utf-8")

    def test_browse_author_not_found(self, client):
        r = client.get("/browse/nonexistent")
        assert r.status_code == 302  # redirect to index

    def test_browse_section(self, client, populated_output):
        r = client.get("/browse/testuser/sec")
        assert r.status_code == 200
        assert "Poem A" in r.data.decode("utf-8")
        assert "Poem B" in r.data.decode("utf-8")

    def test_browse_section_not_found(self, client, populated_output):
        r = client.get("/browse/testuser/nonexistent")
        assert r.status_code == 302

    def test_view_poem(self, client, populated_output):
        # Find the actual filename
        sec_dir = populated_output / "testuser" / "sec"
        filename = sorted(sec_dir.glob("*.txt"))[0].name
        r = client.get(f"/poem/testuser/sec/{filename}")
        assert r.status_code == 200
        assert "Poem A" in r.data.decode("utf-8")

    def test_view_poem_not_found(self, client, populated_output):
        r = client.get("/poem/testuser/sec/nonexistent.txt")
        assert r.status_code == 302


class TestStopRoute:
    def test_stop_no_active_download(self, client):
        r = client.post("/stop/testuser", data={"_csrf_token": "test-csrf-token"})
        assert r.status_code == 302  # redirect to progress page

    def test_stop_rejects_missing_csrf(self, client):
        r = client.post("/stop/testuser")
        assert r.status_code == 403


class TestProgressAPI:
    def test_unknown_download(self, client):
        r = client.get("/api/progress/nobody")
        assert r.status_code == 200
        assert "text/event-stream" in r.content_type
        # Should contain "unknown" status
        data = r.data.decode("utf-8")
        assert '"unknown"' in data
