"""Minutes HTML (mostly saved from Word) to plain text, keeping paragraphs and list items as lines."""

from __future__ import annotations

import html
import re

from lxml import etree
from lxml import html as lhtml

_BLOCK = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "br", "table", "ol", "ul", "blockquote"}
_SPACE = re.compile(r"[ \t    ​]+")


def to_text(fragment: str | None) -> str:
    """The text of an HTML fragment, one paragraph per line. Table cells in a row are joined with " | "."""
    if not fragment or not fragment.strip():
        return ""
    raw = html.unescape(fragment) if "&lt;" in fragment else fragment
    try:
        root = lhtml.fragment_fromstring(raw, create_parent="div")
    except (etree.ParserError, ValueError):
        return _tidy(re.sub(r"<[^>]+>", " ", raw))
    for bad in root.xpath("//script|//style|//comment()"):
        bad.drop_tree()
    parts: list[str] = []

    def walk(el: etree._Element) -> None:
        tag = el.tag if isinstance(el.tag, str) else ""
        tag = tag.lower().split("}")[-1]
        if tag in _BLOCK:
            parts.append("\n")
        if tag == "td" or tag == "th":
            parts.append(" | ")
        if el.text:
            parts.append(el.text)
        for child in el:
            walk(child)
            if child.tail:
                parts.append(child.tail)
        if tag in _BLOCK:
            parts.append("\n")

    walk(root)
    return _tidy("".join(parts))


def _tidy(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        line = _SPACE.sub(" ", line).strip(" |")
        line = line.strip()
        if line:
            lines.append(line)
    return "\n".join(lines)
