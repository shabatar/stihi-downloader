"""Tests for HTML parsers."""

from stihi.parser import parse_author_page, parse_poem_listing, parse_poem_page


AUTHOR_PAGE_HTML = """
<html><body>
<div class="maintext"><index>
<h1>Иван Петров</h1>
<p>Произведений: <b>42</b><br>
<a href="/readers.html?testuser">Читателей</a>: <b>10</b></p>

<h2>Произведения</h2>
<ul type="square">
  <li><a href="/2024/01/15/100" class="poemlink">Утро</a>
      <small>- лирика, 15.01.2024 08:30</small></li>
  <li><a href="/2024/02/20/200" class="poemlink">Вечер</a>
      <small>- философская лирика, 20.02.2024 19:00</small></li>
  <li><a href="/2024/03/01/300" class="poemlink">***</a>
      <small>- без раздела, 01.03.2024 12:00</small></li>
</ul>

<div id="bookheader"><a href="/avtor/testuser&amp;book=1#1">Книга 2024</a>
    <font color="#404040"><small>(15)</small></font></div>
</index></div>
</body></html>
"""

LISTING_PAGE_HTML = """
<html><body>
<ul type="square">
  <li><a href="/2023/05/10/50" class="poemlink">Весна</a>
      <small>- природа, 10.05.2023 10:00</small></li>
  <li><a href="/2023/06/15/60" class="poemlink">Лето</a>
      <small>- природа, 15.06.2023 14:30</small></li>
</ul>
</body></html>
"""

POEM_PAGE_HTML = """
<html><body>
<div class="maintext"><index>
<h1>Утро в горах</h1>
<div class="titleauthor"><em><a href="/avtor/testuser">Иван Петров</a></em></div>

<div class="text">
Туман клубится у подножья гор,<br>
И солнце медленно встаёт.<br>
<br>
Вдали виднеется простор,<br>
Река спокойная течёт.
</div>

<div class="copyright">&copy; Иван Петров, 2024</div>
</index></div>
</body></html>
"""

POEM_WITH_DEDICATION_HTML = """
<html><body>
<div class="maintext"><index>
<h1>Посвящение</h1>
<div class="subtitle">Маме</div>
<div class="epigraph">Из всех чудес на свете<br>одно лишь постоянно...</div>
<div class="text">
Строка первая<br>
Строка вторая
</div>
</index></div>
</body></html>
"""


class TestParseAuthorPage:
    def test_extracts_display_name(self):
        author, _ = parse_author_page(AUTHOR_PAGE_HTML, "testuser")
        assert author.display_name == "Иван Петров"

    def test_extracts_poem_count(self):
        author, _ = parse_author_page(AUTHOR_PAGE_HTML, "testuser")
        assert author.poem_count == 42

    def test_extracts_username(self):
        author, _ = parse_author_page(AUTHOR_PAGE_HTML, "testuser")
        assert author.username == "testuser"

    def test_extracts_poems(self):
        _, poems = parse_author_page(AUTHOR_PAGE_HTML, "testuser")
        assert len(poems) == 3

    def test_poem_fields(self):
        _, poems = parse_author_page(AUTHOR_PAGE_HTML, "testuser")
        p = poems[0]
        assert p.title == "Утро"
        assert p.url == "/2024/01/15/100"
        assert p.section == "лирика"
        assert p.date == "15.01.2024 08:30"

    def test_deduplicates_urls(self):
        html = AUTHOR_PAGE_HTML.replace(
            "</ul>",
            '<li><a href="/2024/01/15/100" class="poemlink">Утро дубль</a>'
            "<small>- лирика, 15.01.2024 08:30</small></li></ul>",
        )
        _, poems = parse_author_page(html, "testuser")
        urls = [p.url for p in poems]
        assert urls.count("/2024/01/15/100") == 1


class TestParsePoemListing:
    def test_extracts_poems(self):
        poems = parse_poem_listing(LISTING_PAGE_HTML)
        assert len(poems) == 2

    def test_poem_fields(self):
        poems = parse_poem_listing(LISTING_PAGE_HTML)
        assert poems[0].title == "Весна"
        assert poems[0].section == "природа"
        assert poems[1].url == "/2023/06/15/60"


class TestParsePoemPage:
    def test_extracts_title(self):
        data = parse_poem_page(POEM_PAGE_HTML)
        assert data["title"] == "Утро в горах"

    def test_extracts_text(self):
        data = parse_poem_page(POEM_PAGE_HTML)
        assert "Туман клубится у подножья гор," in data["text"]
        assert "Река спокойная течёт." in data["text"]

    def test_preserves_stanza_break(self):
        data = parse_poem_page(POEM_PAGE_HTML)
        assert "\n\n" in data["text"]

    def test_no_html_tags_in_text(self):
        data = parse_poem_page(POEM_PAGE_HTML)
        assert "<br>" not in data["text"]
        assert "<div" not in data["text"]

    def test_extracts_dedication(self):
        data = parse_poem_page(POEM_WITH_DEDICATION_HTML)
        assert data["dedication"] == "Маме"

    def test_extracts_epigraph(self):
        data = parse_poem_page(POEM_WITH_DEDICATION_HTML)
        assert "Из всех чудес" in data["epigraph"]

    def test_empty_fields_when_absent(self):
        data = parse_poem_page(POEM_PAGE_HTML)
        assert data["dedication"] == ""
        assert data["epigraph"] == ""

    def test_minimal_html(self):
        data = parse_poem_page("<html><body></body></html>")
        assert data["title"] == ""
        assert data["text"] == ""
