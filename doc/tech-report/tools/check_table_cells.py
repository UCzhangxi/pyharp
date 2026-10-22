#!/usr/bin/env python3
"""Gate for ISSUES #10: maths and cross-references written into a GENERATED TABLE CELL.

A table emitted as a bare ``pandas.DataFrame`` (the last expression of a ``{python}`` cell)
is rendered through pandas' own HTML repr, so its cell strings never reach pandoc.  A
``$...$`` span in such a cell is printed as those literal characters -- in the HTML *and*
in the PDF, because MathJax's default ``inlineMath`` does not include ``$...$`` -- and a
``(@ref)`` never resolves.

Nothing else in this repository sees that.  The source is well formed, so
``check_math_spans.py`` passes; the PDF log only notices when a macro happens to be a
character-mapping one, so ``render_gate.py`` catches a handful of ~510; and the stdout gate
sees nothing at all.  The instrument that works is a scan of the RENDERED ``<th>``/``<td>``
contents, which is what this script does.

    python tools/check_table_cells.py book/_book          # gate a build
    python tools/check_table_cells.py book/_book --list   # one line per offending cell
    python tools/check_table_cells.py --source book/chapters/*.qmd   # gate the SOURCE
    python tools/check_table_cells.py --self-test

🔴 **--source exists because fixing #10 turns a DORMANT defect class into a fatal one.**
While a cell's strings were going straight into pandas' HTML, a math span inside one that
pandoc would refuse -- a space before the closing ``$``, a digit after it -- was merely
printed wrongly.  Routed through pandoc, the delimiters are escaped, the macros land in
text mode and **LuaLaTeX dies**.  That is the wave-10 hazard, and it fired on the very
first render after the fix: ch34 carried ``$L_{\\mathrm{mix}} = $`` in a cell value.
``check_math_spans.py`` cannot see these, because they live inside code fences as string
literals and it blanks fences by design.  So run ``--source`` over any chapter whose tables
you touch, BEFORE rendering.

Exit status is 1 if any rendered table cell carries an unrendered ``$...$`` span or an
unresolved ``(@ref)``, 0 otherwise.

The fix is to emit the table as markdown so pandoc parses the cells::

    from IPython.display import Markdown
    Markdown(df.to_markdown(index=False))

Escape any literal ``|`` in a cell value, and make the index a real column.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

# A cell pandoc has processed contains ``<span class="math inline">`` or an anchor with
# class ``quarto-xref``; a cell it never saw keeps the raw source characters.
DOLLAR = re.compile(r"\$[^$\n]+\$")
XREF = re.compile(r"\(@[A-Za-z][\w:-]*\)")


class _Cells(HTMLParser):
    """Collect the text of every ``<th>``/``<td>``, ignoring nested markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cells: list[str] = []
        self._depth = 0
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("th", "td"):
            if self._depth == 0:
                self._buf = []
            self._depth += 1

    def handle_endtag(self, tag):
        if tag in ("th", "td") and self._depth:
            self._depth -= 1
            if self._depth == 0:
                self.cells.append("".join(self._buf))

    def handle_data(self, data):
        if self._depth:
            self._buf.append(data)


def scan_text(text: str) -> list[tuple[str, str]]:
    """Return ``(kind, cell)`` for every offending cell in one rendered document."""
    parser = _Cells()
    parser.feed(text)
    out: list[tuple[str, str]] = []
    for cell in parser.cells:
        if DOLLAR.search(cell):
            out.append(("math", cell))
        elif XREF.search(cell):
            out.append(("xref", cell))
    return out


def scan_path(root: Path) -> dict[Path, list[tuple[str, str]]]:
    files = sorted(root.rglob("*.html")) if root.is_dir() else [root]
    found: dict[Path, list[tuple[str, str]]] = {}
    for f in files:
        hits = scan_text(f.read_text(encoding="utf-8", errors="replace"))
        if hits:
            found[f] = hits
    return found


# ---------------------------------------------------------------- source mode

def _placeholder(node):
    """What an f-string replacement field will most likely become.

    A numeric format spec becomes a digit, because *a digit immediately after a closing
    ``$`` is itself the hazard* (pandoc reads ``$5`` as money and refuses the span).
    Anything else becomes a letter.
    """
    spec = ""
    if getattr(node, "format_spec", None) is not None:
        spec = "".join(
            v.value for v in node.format_spec.values if isinstance(v, ast.Constant)
        )
    return "0" if re.search(r"[bdeEfFgGn%]$|^\d*\.\d+$", spec) else "X"


def _literals(code):
    """Yield (lineno, text) for every string literal in a cell, f-strings resolved.

    ⚠️ The pieces of an f-string are ``Constant`` nodes in their own right, so a naive
    ``ast.walk`` yields both the assembled string **and** each fragment -- and a fragment
    cut between two valid spans looks exactly like a broken one (``f"$p={p}$, $e={e}$"``
    splits into ``"$, $e="``, whose apparent span ends in a space).  That is a gate that
    cannot come back empty on good source, which this repository has shipped twice.  So
    the fragments are collected first and excluded.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return
    inner = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for v in node.values:
                inner.add(id(v))
    for node in ast.walk(tree):
        if id(node) in inner:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value
        elif isinstance(node, ast.JoinedStr):
            parts = []
            for v in node.values:
                if isinstance(v, ast.Constant):
                    parts.append(v.value)
                elif isinstance(v, ast.FormattedValue):
                    parts.append(_placeholder(v))
            yield node.lineno, "".join(parts)


MATH_SPAN = re.compile(r"(?<!\\)\$([^$\n]+?)(?<!\\)\$")

# A LaTeX line break inside a maths span. In a cell string literal this is written
# ``\\\\``, which the Python string turns into ``\\`` -- and ``\\`` in LaTeX MATH MODE is a
# newline, so LuaLaTeX stops with "Missing $ inserted". It reaches the reader as a dead
# render, not a wrong symbol, so it is the loudest member of this family and the only one
# with no silent variant. Found the hard way: a blanket backslash-doubling applied while
# repairing pipes-in-maths quadrupled five spans that were already escaped, and the source
# gates passed them because the SPAN is well formed -- only the render caught it.
DOUBLE_BACKSLASH = re.compile(r"\\\\\\\\")


def line_breaks_in_maths(text):
    r"""Yield every ``$...$`` span carrying a LaTeX ``\\`` (a math-mode newline).

    Written ``\\\\`` in a cell's string literal.  Nothing else in the pipeline sees it: the
    span's delimiters are correct, so ``bad_spans`` passes it, and it is not a Greek macro,
    so the upright-alphabet rule passes it too.  It kills the render.
    """
    for m in MATH_SPAN.finditer(text):
        if DOUBLE_BACKSLASH.search(m.group(1)):
            yield m.group(1)


def pipes_in_maths(text):
    r"""Yield every ``$...$`` span in a cell string that contains a ``|``.

    ``classic_papers.tables.escape_pipes`` MUST escape pipes, or a cell splits its own
    markdown row -- and it cannot tell a table delimiter from a set-builder bar.  Inside
    maths that escaping is wrong either way: ``\|`` is a *double* vertical line in LaTeX, so
    the symbol silently changes; and a pipe already written ``\|`` cannot be escaped again
    without producing ``\\|``, which markdown reads as an escaped backslash plus a live
    delimiter, so the row breaks anyway.  There is no correct escaping, which is why this is
    a gate and not a repair.  Write ``\lvert`` and ``\rvert``.
    """
    for m in MATH_SPAN.finditer(text):
        if "|" in m.group(1):
            yield m.group(1)


def scan_source(path):
    """Return (line, span, reason) for broken math spans in a table cell's strings."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_math_spans import bad_spans

    lines = Path(path).read_text().split("\n")
    out, i = [], 0
    while i < len(lines):
        if lines[i].rstrip() == "```{python}":
            j = i + 1
            while j < len(lines) and lines[j].rstrip() != "```":
                j += 1
            opts = [l for l in lines[i + 1:j] if l.startswith("#|")]
            if any(re.match(r"#\|\s*label:\s*tbl-", o) for o in opts):
                code = "\n".join("" if l.startswith("#|") else l for l in lines[i + 1:j])
                for lineno, text in _literals(code):
                    for _, span, why in bad_spans(text):
                        out.append((i + 1 + lineno, span, why))
                    for span in line_breaks_in_maths(text):
                        out.append((i + 1 + lineno, span,
                                    "a LaTeX line break (\\\\) inside a maths span -- this "
                                    "KILLS the render with 'Missing $ inserted'"))
                    for span in pipes_in_maths(text):
                        out.append((i + 1 + lineno, span,
                                    "a literal | inside a maths span -- unescapable, and "
                                    "\\| is a DOUBLE bar; write \\lvert and \\rvert"))
            i = j + 1
        else:
            i += 1
    return out


_GOOD = """<table><tr><th>quantity</th><th>value</th></tr>
<tr><td>mean molar mass <span class="math inline">\\(\\bar\\mu\\)</span></td>
<td>2.30 g mol<span class="math inline">\\(^{-1}\\)</span></td></tr>
<tr><td>equilibrium temperature
(<a href="#eq-x" class="quarto-xref">Equation&nbsp;1</a>)</td><td>1430 K</td></tr>
<tr><td>a price of 5 dollars</td><td>no maths here at all</td></tr></table>"""

# A code listing echoed on purpose: the literal dollars are correct there and live in
# <pre>/<code>, never in a table cell.  The gate must not see them.
_ECHO = """<pre class="sourceCode python"><code>rows = [("mass $\\bar\\mu$", "2.30")]
value = f"{x:.2f} g mol$^{{-1}}$"</code></pre>"""

_BAD_MATH = """<table><tr><th>mean molar mass $\\bar\\mu$</th></tr>
<tr><td>2.30 g mol$^{-1}$</td></tr></table>"""

_BAD_XREF = """<table><tr><td>equilibrium temperature (@eq-tr-teq)</td></tr></table>"""


_SRC_OK = ["good", "1977 kinetics, $L_{\\mathrm{mix}} = H_\\rho$", "$T$ at $2\\times10^{8}$ K"]
_SRC_BAD = ["$L_{\\mathrm{mix}} = $", "$ x$", "a span then a digit"]

# A pipe inside a maths span cannot be escaped correctly in either direction, so the gate
# must catch it. Controls: the safe spelling, a pipe outside maths (which escape_pipes DOES
# handle), and prose with no maths. Decoys: a bare pipe in maths, and one already written
# ``\|``, which is the shape that produces ``\\|`` and breaks the row anyway.
_PIPE_OK = [r"$\lvert a - b\rvert$ is fine", "no maths, a|b is fine",
            r"$x$ then a|b outside the span"]
_PIPE_BAD = [r"$|c{=}5 - x|$", r"$\|a\|$ already escaped"]

# A LaTeX line break inside maths kills the render outright. Controls: a correctly escaped
# span (one backslash per macro in the FILE, i.e. two in the python literal that produces it),
# and a genuine row break outside any maths span.
_BREAK_OK = [r'"$\\lvert\\Delta R_p\\rvert$"', r"a row ends here \\ but not inside maths"]
_BREAK_BAD = [r'"$\\lvert\\\\Delta R_p\\rvert$"']


def _source_self_test() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_math_spans import bad_spans
    bad = 0
    for s in _SRC_OK:
        hits = list(bad_spans(s))
        if hits:
            print(f"self-test FAILED: source control {s!r} flagged {hits}")
            bad += 1
    for s in _SRC_BAD[:2]:
        if not list(bad_spans(s)):
            print(f"self-test FAILED: source decoy {s!r} not flagged")
            bad += 1
    for s in _BREAK_OK:
        if list(line_breaks_in_maths(s)):
            print(f"self-test FAILED: line-break control {s!r} flagged")
            bad += 1
    for s in _BREAK_BAD:
        if not list(line_breaks_in_maths(s)):
            print(f"self-test FAILED: line-break decoy {s!r} not flagged")
            bad += 1
    for s in _PIPE_OK:
        if list(pipes_in_maths(s)):
            print(f"self-test FAILED: pipe control {s!r} flagged")
            bad += 1
    for s in _PIPE_BAD:
        if not list(pipes_in_maths(s)):
            print(f"self-test FAILED: pipe decoy {s!r} not flagged")
            bad += 1
    return bad


def self_test() -> int:
    controls = {"rendered table": _GOOD, "echoed source listing": _ECHO}
    decoys = {"literal math in cells": (_BAD_MATH, 2), "unresolved xref": (_BAD_XREF, 1)}
    bad = 0
    for name, text in controls.items():
        hits = scan_text(text)
        if hits:
            print(f"self-test FAILED: control {name!r} produced {len(hits)} hit(s): {hits}")
            bad += 1
    for name, (text, want) in decoys.items():
        hits = scan_text(text)
        if len(hits) != want:
            print(f"self-test FAILED: decoy {name!r} gave {len(hits)} hit(s), expected {want}")
            bad += 1
    bad += _source_self_test()
    if bad:
        return 1
    print(
        f"self-test passed: {len(controls) + len(_SRC_OK)} controls clean "
        f"(a resolved table, an echoed source listing and three valid source spans among "
        f"them), {sum(w for _, w in decoys.values()) + 2 + len(_PIPE_BAD)} violations caught in rendered "
        f"cells and in cell source"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("path", nargs="?", help="rendered book directory, or one .html file")
    ap.add_argument("--list", action="store_true", help="print every offending cell")
    ap.add_argument("--source", nargs="+", metavar="QMD",
                    help="scan table-cell STRING LITERALS in .qmd sources instead")
    ap.add_argument("--self-test", action="store_true", help="check the checker")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if args.source:
        n = 0
        for q in args.source:
            for line, span, why in scan_source(q):
                print(f"{Path(q).name}:{line}: {why}\n    ${span}$")
                n += 1
        print(f"\n{'CLEAN' if not n else f'{n} broken math spans in table-cell strings'}")
        return 1 if n else 0
    if not args.path:
        ap.error("give a path, or --self-test")

    root = Path(args.path)
    if not root.exists():
        print(f"{root}: not found -- render the book first")
        return 1

    found = scan_path(root)
    if not found:
        print(f"{root}: clean -- no rendered table cell carries unrendered maths or an unresolved ref")
        return 0

    total = Counter()
    for f, hits in sorted(found.items()):
        kinds = Counter(k for k, _ in hits)
        total.update(kinds)
        print(f"{f.name}: {kinds['math']} cells with literal $...$, {kinds['xref']} with an unresolved (@ref)")
        if args.list:
            for kind, cell in hits:
                print(f"    [{kind}] {' '.join(cell.split())[:120]}")
    print(
        f"\nTOTAL: {total['math']} cells with literal $...$ and {total['xref']} with an "
        f"unresolved (@ref), across {len(found)} of "
        f"{len(list(root.rglob('*.html'))) if root.is_dir() else 1} rendered files."
    )
    print("Fix: emit the table as Markdown(df.to_markdown(index=False)), not as a bare DataFrame.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
