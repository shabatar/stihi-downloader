"""Tests for crawler module (unit tests only — no network access)."""

import pytest

from stihi.crawler import BookInfo, CancelledError, Crawler


class TestCrawlerCancel:
    def test_cancel_sets_flag(self):
        c = Crawler()
        assert c.cancelled is False
        c.cancel()
        assert c.cancelled is True

    def test_check_cancelled_raises(self):
        c = Crawler()
        c.cancel()
        with pytest.raises(CancelledError, match="cancelled"):
            c.check_cancelled()

    def test_check_cancelled_ok_when_not_cancelled(self):
        c = Crawler()
        c.check_cancelled()  # should not raise


class TestBookInfo:
    def test_fields(self):
        b = BookInfo(book_id=3, name="Книга 2024", poem_count=42, href="/avtor/test&book=3#3")
        assert b.book_id == 3
        assert b.name == "Книга 2024"
        assert b.poem_count == 42
        assert b.href == "/avtor/test&book=3#3"


class TestCrawlerDefaults:
    def test_default_delay(self):
        c = Crawler()
        assert c.delay_range == (1.0, 3.0)

    def test_default_headless(self):
        c = Crawler()
        assert c.headless is True

    def test_custom_params(self):
        c = Crawler(delay_range=(0.5, 1.5), headless=False, timeout=10_000)
        assert c.delay_range == (0.5, 1.5)
        assert c.headless is False
        assert c.timeout == 10_000
