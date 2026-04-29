from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup

from .constants import TOC_EXTENSIONS
from .parser import ParsedPage
from .utils import clean_text


@dataclass
class TocEntry:
    toc_id: str
    parent_id: str | None
    ordinal: int
    title: str
    page_id: str | None
    source_path: str | None
    depth: int


def build_toc(root: Path, pages: list[ParsedPage]) -> list[TocEntry]:
    page_by_source = {page.source_path.lower(): page for page in pages}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in TOC_EXTENSIONS:
            entries = parse_hhc_or_hhk(path, root, page_by_source)
            if entries:
                return entries
    return synthesize_toc(pages)


def parse_hhc_or_hhk(
    path: Path, root: Path, page_by_source: dict[str, ParsedPage]
) -> list[TocEntry]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "lxml")
    top_ul = soup.find("ul")
    if top_ul is None:
        return []
    entries: list[TocEntry] = []

    def walk_ul(ul, parent_id: str | None, depth: int) -> None:
        for li in ul.find_all("li", recursive=False):
            params = _params_from_li(li)
            title = params.get("name") or params.get("title")
            local = params.get("local")
            if not title:
                link = li.find("a")
                title = link.get_text(" ", strip=True) if link else None
                local = local or (link.get("href") if link else None)
            toc_id = f"toc_{len(entries) + 1:06d}"
            page = _page_for_local(local, page_by_source)
            if title:
                entries.append(
                    TocEntry(
                        toc_id=toc_id,
                        parent_id=parent_id,
                        ordinal=len(entries),
                        title=clean_text(title),
                        page_id=page.page_id if page else None,
                        source_path=page.source_path if page else _normalize_local(local),
                        depth=depth,
                    )
                )
                next_parent = toc_id
            else:
                next_parent = parent_id
            child_ul = li.find("ul", recursive=False)
            if child_ul is not None:
                walk_ul(child_ul, next_parent, depth + 1)

    walk_ul(top_ul, None, 0)
    return entries


def synthesize_toc(pages: list[ParsedPage]) -> list[TocEntry]:
    entries: list[TocEntry] = []
    for page in pages:
        parent_id = f"toc_{len(entries) + 1:06d}"
        entries.append(
            TocEntry(
                toc_id=parent_id,
                parent_id=None,
                ordinal=len(entries),
                title=page.title,
                page_id=page.page_id,
                source_path=page.source_path,
                depth=0,
            )
        )
        for heading in page.headings[1:4]:
            entries.append(
                TocEntry(
                    toc_id=f"toc_{len(entries) + 1:06d}",
                    parent_id=parent_id,
                    ordinal=len(entries),
                    title=heading,
                    page_id=page.page_id,
                    source_path=page.source_path,
                    depth=1,
                )
            )
    return entries


def _params_from_li(li) -> dict[str, str]:
    params: dict[str, str] = {}
    obj = li.find("object")
    if obj is None:
        return params
    for param in obj.find_all("param"):
        name = (param.get("name") or "").strip().lower()
        value = param.get("value")
        if name and value:
            params[name] = value.strip()
    return params


def _normalize_local(local: str | None) -> str | None:
    if not local:
        return None
    clean = unquote(local).replace("\\", "/")
    clean = clean.split("#", 1)[0]
    return clean.lstrip("/")


def _page_for_local(local: str | None, page_by_source: dict[str, ParsedPage]) -> ParsedPage | None:
    normalized = _normalize_local(local)
    if not normalized:
        return None
    return page_by_source.get(normalized.lower())
