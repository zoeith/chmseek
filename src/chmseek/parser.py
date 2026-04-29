from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup

from .constants import ALLOWED_CONTENT_EXTENSIONS, TOC_EXTENSIONS, UNSAFE_HTML_TAGS
from .errors import ChmseekError
from .utils import clean_text, safe_relative_posix


@dataclass
class ParsedPage:
    page_id: str
    source_path: str
    title: str
    text: str
    headings: list[str] = field(default_factory=list)
    raw_html_path: str | None = None


def parse_help_tree(root: Path) -> list[ParsedPage]:
    root = root.resolve()
    pages: list[ParsedPage] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in TOC_EXTENSIONS:
            continue
        if suffix not in ALLOWED_CONTENT_EXTENSIONS:
            continue
        rel = safe_relative_posix(path, root)
        page = parse_content_file(path, rel, page_index=len(pages) + 1)
        if page.text.strip():
            pages.append(page)
    if not pages:
        raise ChmseekError(
            "NO_PARSEABLE_HELP_CONTENT",
            "No parseable help pages were found after extraction.",
            ["Expected allowlisted text or HTML help files."],
        )
    return pages


def parse_content_file(path: Path, rel_path: str, page_index: int) -> ParsedPage:
    suffix = path.suffix.lower()
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    if suffix == ".txt":
        title = path.stem.replace("_", " ").replace("-", " ").title()
        return ParsedPage(
            page_id=f"p_{page_index:06d}",
            source_path=rel_path,
            title=title,
            text=clean_text(text),
            headings=[title],
            raw_html_path=None,
        )
    return parse_html(text, rel_path, page_index)


def parse_html(html: str, rel_path: str, page_index: int) -> ParsedPage:
    soup = BeautifulSoup(html, "lxml")
    for tag_name in UNSAFE_HTML_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    for tag in soup.find_all(["br"]):
        tag.replace_with("\n")
    for tag in soup.find_all(["li"]):
        tag.insert_before("\n- ")
    for tag in soup.find_all(["tr"]):
        tag.insert_before("\n")
    for tag in soup.find_all(["td", "th"]):
        tag.insert_after(" | ")
    for tag in soup.find_all(["pre", "code"]):
        tag.insert_before("\n")
        tag.insert_after("\n")

    headings = [
        clean_text(tag.get_text(" ", strip=True))
        for tag in soup.find_all(["h1", "h2", "h3"])
    ]
    headings = [heading for heading in headings if heading]
    title = _extract_title(soup, headings, rel_path)
    body = soup.body if soup.body else soup
    text = clean_text(body.get_text("\n", strip=True))
    return ParsedPage(
        page_id=f"p_{page_index:06d}",
        source_path=rel_path,
        title=title,
        text=text,
        headings=headings,
        raw_html_path=rel_path,
    )


def _extract_title(soup: BeautifulSoup, headings: list[str], rel_path: str) -> str:
    if soup.title:
        title = clean_text(soup.title.get_text(" ", strip=True))
        if title:
            return title
    if headings:
        return headings[0]
    return Path(rel_path).stem.replace("_", " ").replace("-", " ").title()
