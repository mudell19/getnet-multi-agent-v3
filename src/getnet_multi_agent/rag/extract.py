"""HTML to ordered content blocks: headings, text, tables and FAQ question/answer pairs."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from bs4 import BeautifulSoup, NavigableString, Tag

DROP_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "svg", "form",
             "template", "iframe", "input", "select", "textarea"}
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}
BLOCK_TAGS = {"p", "div", "section", "article", "main", "aside", "li", "ul", "ol", "dl", "dt",
              "dd", "h5", "h6", "blockquote", "figure", "figcaption", "br", "label", "td", "th",
              "tr", "body"}
# (container class, question class, answer class) for the FAQ layouts used on the Getnet sites.
FAQ_LAYOUTS = [
    ("o-modal__content--faq", "o-modal__title", "o-modal__text"),
    ("o-faq-accordion__content__item", "o-faq-accordion__content__item__title",
     "o-faq-accordion__content__item__description"),
    ("faq-item", "faq-question", "faq-answer"),
]
REPEAT_RATIO = 0.3

_WS = re.compile(r"\s+")


def clean(text: str) -> str:
    return _WS.sub(" ", text).strip()


@dataclass
class Block:
    kind: Literal["heading", "text", "table", "faq"]
    text: str
    level: int = 0
    answer: str = ""


@dataclass
class Extracted:
    title: str
    blocks: list[Block] = field(default_factory=list)

    def visible_text(self) -> str:
        return "\n".join(f"{b.text}\n{b.answer}" if b.answer else b.text for b in self.blocks)


def _classes(tag: Tag) -> list[str]:
    return list(tag.get("class") or [])


def _faq(tag: Tag) -> Block | None:
    classes = _classes(tag)
    for container, q_cls, a_cls in FAQ_LAYOUTS:
        if container in classes:
            q, a = tag.find(class_=q_cls), tag.find(class_=a_cls)
            if q is None or a is None:
                return None
            question, answer = clean(q.get_text(" ")), clean(a.get_text(" "))
            return Block("faq", question, answer=answer) if question and answer else None
    if tag.name == "details" and tag.find("summary") is not None:
        summary = tag.find("summary")
        question = clean(summary.get_text(" "))
        summary.extract()
        answer = clean(tag.get_text(" "))
        return Block("faq", question, answer=answer) if question and answer else None
    return None


def _is_faq_trigger(tag: Tag) -> bool:
    # Links that only repeat the question text of a FAQ modal shown elsewhere on the page.
    return tag.name == "a" and any(c.endswith("__question") for c in _classes(tag))


class _Walker:
    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self.buf: list[str] = []

    def flush(self) -> None:
        text = clean(" ".join(self.buf))
        self.buf = []
        if text:
            self.blocks.append(Block("text", text))

    def walk(self, node: Tag) -> None:
        for child in node.children:
            if type(child) is NavigableString:
                self.buf.append(str(child))
                continue
            if not isinstance(child, Tag) or child.name in DROP_TAGS:
                continue
            faq = _faq(child)
            if faq is not None:
                self.flush()
                self.blocks.append(faq)
                continue
            if _is_faq_trigger(child):
                continue
            if child.name in HEADINGS:
                self.flush()
                text = clean(child.get_text(" "))
                if text:
                    self.blocks.append(Block("heading", text, level=HEADINGS[child.name]))
                continue
            if child.name == "table":
                self.flush()
                rows = []
                for tr in child.find_all("tr"):
                    cells = [clean(c.get_text(" ")) for c in tr.find_all(["td", "th"])]
                    cells = [c for c in cells if c]
                    if cells:
                        rows.append(" | ".join(cells))
                if rows:
                    self.blocks.append(Block("table", "\n".join(rows)))
                continue
            if child.name in BLOCK_TAGS:
                self.flush()
                self.walk(child)
                self.flush()
            else:
                self.walk(child)


def parse(html: str) -> Extracted:
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("title")
    title = clean(title_tag.get_text(" ")) if title_tag else ""
    for tag in soup(list(DROP_TAGS)):
        tag.decompose()
    if not title:
        h1 = soup.find("h1")
        title = clean(h1.get_text(" ")) if h1 else ""
    walker = _Walker()
    if soup.body is not None:
        walker.walk(soup.body)
        walker.flush()
    return Extracted(title=title, blocks=walker.blocks)


def repeated_texts(pages: list[Extracted], ratio: float = REPEAT_RATIO) -> set[str]:
    """Heading and text blocks present in `ratio` or more of the pages (site chrome)."""
    counts: Counter[str] = Counter()
    for page in pages:
        counts.update({b.text.lower() for b in page.blocks if b.kind in ("heading", "text")})
    limit = max(2, ratio * len(pages))
    return {t for t, n in counts.items() if n >= limit}


def strip_repeated(page: Extracted, repeated: set[str]) -> Extracted:
    blocks = [b for b in page.blocks
              if b.kind in ("faq", "table") or b.text.lower() not in repeated]
    return Extracted(title=page.title, blocks=blocks)


def extract_pages(htmls: list[str]) -> list[Extracted]:
    """Parse every page, then drop the text repeated across 30% or more of them."""
    pages = [parse(h) for h in htmls]
    repeated = repeated_texts(pages)
    return [strip_repeated(p, repeated) for p in pages]
