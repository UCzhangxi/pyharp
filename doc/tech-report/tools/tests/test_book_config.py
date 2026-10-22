"""Tests of book/_quarto.yml (STYLE 10) and tools/book_chapters.py, which writes its chapter list.

Run from the report directory: `python3 -m pytest tools/tests`.
"""

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
BOOK = TOOLS.parent / "book"
sys.path.insert(0, str(TOOLS))

import book_chapters  # noqa: E402
import render_gate  # noqa: E402


def test_the_book_config_follows_style_10():
    import yaml
    cfg = yaml.safe_load((BOOK / "_quarto.yml").read_text())
    assert cfg["project"]["type"] == "book"
    assert cfg["execute"]["freeze"] == "auto"
    assert cfg["format"]["html"]["html-math-method"] == "mathml"
    assert cfg["format"]["html"]["code-overflow"] == "wrap"
    pdf = cfg["format"]["pdf"]
    assert pdf["documentclass"] == "scrreprt"
    assert {"a4paper", "oneside", "openany", "DIV=12", "numbers=noenddot"} <= set(pdf["classoption"])
    assert pdf["fontsize"] == "10pt" and pdf["toc-depth"] == 2 and pdf["fig-width"] == 6.2
    assert pdf["include-in-header"] == [{"file": "_tex/inline-code-breaks.tex"}, {"file": "_tex/theme.tex"}]
    assert (BOOK / "_tex" / "theme.tex").exists() and (BOOK / "_filters" / "codemap-widths.lua").exists()
    tex = (BOOK / "_tex" / "inline-code-breaks.tex").read_text()
    assert "\\automark[chapter]{chapter}" in tex            # running heads: the chapter title only
    assert "pre_linebreak_filter" in tex                     # long hex strings break inside
    assert cfg["format"]["html"]["css"] == "report.css"
    assert "code { overflow-wrap: anywhere; }" in (BOOK / "report.css").read_text()
    assert cfg["book"]["chapters"][0] == "index.qmd" and (BOOK / "index.qmd").exists()
    # no math macros: nothing defines \newcommand for the HTML or the PDF
    assert "newcommand" not in (BOOK / "_quarto.yml").read_text()
    assert "include-before-body" not in cfg["format"]["html"]


def test_the_gate_no_longer_reports_the_book_as_pending(capsys):
    status = render_gate.main([str(BOOK), "--labels-only"])
    out = capsys.readouterr().out
    assert "[book gate]" not in out and "pending: book" not in out
    assert "[chapter-list gate] the list in _quarto.yml is the chapter files that exist" in out
    # the chapters on tech-report have findings of their own; only the book itself must not be pending
    assert status in (0, 1, render_gate.PENDING_EXIT)


@pytest.fixture
def layout(tmp_path):
    (tmp_path / "OUTLINE.md").write_text("## Chapter 5. Five\n\n## Chapter 6. Six\n\n## Chapter 7. Seven\n")
    book = tmp_path / "book"
    (book / "chapters" / "06-six").mkdir(parents=True)
    (book / "_quarto.yml").write_text("book:\n  title: t\n" + book_chapters.chapter_block([], []) + "\n")
    for f in ("07b-seven-b.qmd", "06-six.qmd", "05-five.qmd", "appa-notation.qmd", "06-six/_scheme.qmd"):
        (book / "chapters" / f).write_text("# x\n")
    return book


def test_the_list_follows_outline_order_and_keeps_appendices_apart(layout):
    assert book_chapters.check(layout, write=True)[0] == 0
    block = book_chapters.current_block((layout / "_quarto.yml").read_text())
    assert block.splitlines()[1:] == [
        "  chapters:", "    - index.qmd", "    - chapters/05-five.qmd", "    - chapters/06-six.qmd",
        "    - chapters/07b-seven-b.qmd", "  appendices:", "    - chapters/appa-notation.qmd",
        book_chapters.END]
    assert book_chapters.check(layout) == (0, [])


def test_an_unlisted_chapter_and_a_bad_id_fail_the_gate(layout, capsys):
    book_chapters.check(layout, write=True)
    (layout / "chapters" / "07-seven.qmd").write_text("# x\n")
    (layout / "chapters" / "99-nine.qmd").write_text("# x\n")
    status, msgs = book_chapters.check(layout)
    assert status == 1
    assert "chapters/07-seven.qmd: exists but is not in _quarto.yml" in msgs
    assert any(m.startswith("chapters/99-nine.qmd: not an OUTLINE chapter id") for m in msgs)
    assert render_gate.gate_chapter_list(layout) == 2


def test_callout_fields_get_the_body_paragraph_gap_and_nothing_else_does():
    # The PDF body has a half-line paragraph skip (classoption parskip=half-), but tcolorbox resets \parskip to 0
    # inside a box, so the fields of a callout ran together. One setting in the callout style restores the gap;
    # it lives only in Quarto's callout style ("enhanced jigsaw"; code blocks do not use it), and theme.tex sets
    # \parskip nowhere else, so body text keeps its spacing.
    import re
    import yaml
    cfg = yaml.safe_load((BOOK / "_quarto.yml").read_text())
    assert "parskip=half-" in cfg["format"]["pdf"]["classoption"]
    theme = (BOOK / "_tex" / "theme.tex").read_text()
    style = re.search(r"\\tcbset\{enhanced jigsaw/\.style=\{(.*?)\}\}\n", theme, re.S)
    assert style, "the callout style is defined in theme.tex"
    assert "before upper={\\setlength{\\parskip}{0.5\\baselineskip}}" in style.group(1)
    outside = re.sub(r"(?<!\\)%.*", "", theme[:style.start()] + theme[style.end():])  # TeX comments set nothing
    assert "parskip" not in outside
