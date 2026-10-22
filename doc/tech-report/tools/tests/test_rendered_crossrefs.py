"""Rendered-output check: no cross-reference of the book is left as a citation.

Quarto turns an `@sec-...`, `@eq-...`, `@fig-...` or `@tbl-...` reference it did not resolve into a citation,
`<span class="citation" data-cites="sec-...">`, and prints "Citeproc: citation ... not found". The check reads the
rendered HTML under book/_book and is skipped when the book has not been rendered (CI runs it after the render).
"""
import re
from pathlib import Path

import pytest

BOOK = Path(__file__).resolve().parents[2] / "book" / "_book"
UNRESOLVED = re.compile(r'data-cites="((?:sec|eq|fig|tbl|prp|lem)-[\w-]+)"')


def unresolved_crossrefs(html):
    return UNRESOLVED.findall(html)


def test_the_pattern_finds_an_unresolved_crossref_and_ignores_a_resolved_one():
    bad = '<span class="citation" data-cites="sec-ch04-shortwave">(<strong>sec-ch04-shortwave?</strong>)</span>'
    good = '<a href="04-toon.html#sec-ch04-shortwave" class="quarto-xref"><span>Section 4.1</span></a>'
    paper = '<span class="citation" data-cites="reading01">(Stamnes et al. 1988)</span>'
    assert unresolved_crossrefs(bad) == ["sec-ch04-shortwave"]
    assert unresolved_crossrefs(good + paper) == []


@pytest.mark.skipif(not BOOK.is_dir(), reason="the book has not been rendered")
def test_no_rendered_page_has_an_unresolved_crossref():
    found = {p.relative_to(BOOK).as_posix(): unresolved_crossrefs(p.read_text(encoding="utf-8"))
             for p in sorted(BOOK.rglob("*.html"))}
    found = {k: v for k, v in found.items() if v}
    assert not found, f"cross-references rendered as citations: {found}"
