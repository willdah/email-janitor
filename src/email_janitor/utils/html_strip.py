"""Minimal HTML-to-text stripper used before passing email bodies to the LLM.

Why: HTML bodies embed tags, inline CSS, attribute-based payloads, and the
occasional script block. Feeding them raw both degrades classification (the
model has to ignore markup) and broadens the prompt-injection surface
(e.g. ``<meta name="instructions" content="...">``). Stripping to plain text
closes both issues at minimal cost.

Uses only ``html.parser`` from the stdlib — no new dependency.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_TAG_SNIFF = re.compile(r"<[a-zA-Z/][^>]*>")

# Elements whose contents should be discarded entirely (not just the tags).
_SKIP_CONTENT_TAGS = frozenset({"script", "style"})


class _TextExtractor(HTMLParser):
    """Collect visible text; drop markup, attributes, and script/style contents."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:  # noqa: ARG002
        if tag in _SKIP_CONTENT_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_CONTENT_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_startendtag(self, tag: str, attrs: list) -> None:  # noqa: ARG002
        # Self-closing tags (e.g. <br/>, <img/>) produce no text.
        return

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)

    def get_text(self) -> str:
        # Join chunks with whitespace so adjacent tags don't fuse tokens
        # (e.g. "<p>a</p><p>b</p>" -> "a b", not "ab"). Then collapse runs
        # of whitespace down to a single space.
        return " ".join(" ".join(self._chunks).split())


def strip_html(text: str) -> str:
    """Return the visible-text content of an HTML string with whitespace collapsed.

    Attributes (``name="..."`` etc.), ``<script>``/``<style>`` bodies, and tag
    names are discarded. Malformed HTML is handled best-effort; on parse error
    we fall back to returning the input unchanged so we never drop content.
    """
    if not text:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        return text
    return parser.get_text()


def looks_like_html(text: str) -> bool:
    """Cheap sniff for HTML-in-plain-text payloads.

    Gmail's ``msg.plain`` sometimes still contains HTML (multipart parsing
    quirks). When this returns True callers should strip before use.
    """
    if not text:
        return False
    return _TAG_SNIFF.search(text) is not None
