#!/usr/bin/env python3
"""Render gate: find inline `$...$` spans that pandoc will REFUSE to treat as math.

WHY
---
Pandoc has three rules for an inline math span. The opening `$` must not be
followed by whitespace; the closing `$` must not be preceded by whitespace; and
the closing `$` must not be followed by a digit (so that "$5 and $10" reads as
money, not maths).

Break any of them and pandoc escapes BOTH delimiters to a literal `\\$`. What
happens next depends only on which macro was inside, and the two outcomes look
nothing like each other:

  * A math-only macro (`\\hat`, `\\frac`, `\\tfrac`) meets LuaLaTeX outside math
    mode, which is a hard error: **the PDF dies**. Wave 10's ch32 wrote
    `$\\hat t = $` seven times and killed the build.

  * A macro that unicode-math defines as a CHARACTER (`\\sim` is U+223C, `\\mu`
    is U+1D707) is perfectly legal in text mode. LuaLaTeX asks the roman text
    font for that code point, does not find it, writes "Missing character" to
    `index.log` -- **and silently drops the glyph from the PDF.** The sentence
    loses a symbol in print; the HTML is fine. Nothing reaches stdout, and
    quarto deletes that log on a successful render, so the book's own G1 gate
    could not see it for nine waves (ISSUES #9).

The same defect is therefore either a loud death or a silent corruption,
decided by a detail nobody can be expected to hold in their head. Hence this
file, which checks the cause rather than either symptom.

WHY NOT A GREP
--------------
Two greps have already failed at this, and both failures are instructive.

1. `grep -nE '\\$[^$]*\\s\\$'` matches the ordinary prose BETWEEN two math spans
   on a line -- it starts at the closing `$` of the first and ends at the
   opening `$` of the second. It returned **31 hits on ch01**, a chapter that
   has shipped since wave 1.

2. A line-by-line `$`-parity check reports that same prose as a span whenever
   inline math WRAPS across the 95-column margin, which it does constantly
   (ch02's line 278 opens a span that closes on line 279): 12 false positives
   across six shipped chapters.

The only thing that works is pandoc's own scan -- left to right, consuming each
span, so that a `$` already used as a closing delimiter can never be reread as
an opening one. That is what makes `$500$--$1500$` two valid spans rather than
a violation, and it is why this is a parser and not a regex.

USAGE
-----
    python tools/check_math_spans.py book/chapters/*.qmd
    python tools/check_math_spans.py --self-test

Exit status 0 if clean, 1 if any offending span is found.
"""

import re

import yaml
import sys
import pathlib


def _strip_uncheckable(text):
    """Blank fenced code and display math, preserving line numbering.

    ⚠️ `#|` directive lines are KEPT even inside a fence. A `fig-cap:` or
    `tbl-cap:` lives inside the ```{python} block but its value is markdown
    that pandoc parses, so a broken math span in a caption breaks exactly like
    one in prose -- and captions travel independently, into figure lists and
    PDF skims. Skipping fences wholesale hid ten dropped glyphs in ch11's
    captions from the first version of this checker.
    """
    out, in_code = [], False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code = not in_code
            out.append("")
            continue
        if in_code and not stripped.startswith("#|"):
            out.append("")
            continue
        out.append(line)
    text = "\n".join(out)
    text = re.sub(r"\$\$.*?\$\$",
                  lambda m: re.sub(r"[^\n]", " ", m.group(0)),
                  text, flags=re.S)
    return text


def bad_spans(text):
    """Yield (line, span, reason) for every span pandoc will not render as math.

    A newline INSIDE a span is harmless. Only whitespace immediately inside a
    delimiter, or a digit immediately after the closing one, breaks it.
    """
    s = _strip_uncheckable(text)
    i, n = 0, len(s)
    while i < n:
        if s[i] != "$" or (i and s[i - 1] == "\\"):
            i += 1
            continue
        j = s.find("$", i + 1)
        if j == -1:
            break
        inner = s[i + 1:j]
        if not inner:
            i = j + 1
            continue
        line = s.count("\n", 0, i) + 1
        after = s[j + 1] if j + 1 < n else ""
        if inner[0].isspace():
            yield line, inner, "whitespace after the opening $"
        elif inner[-1].isspace():
            yield line, inner, "whitespace before the closing $"
        elif after.isdigit():
            yield line, inner, f"a digit ({after}) immediately after the closing $"
        i = j + 1          # consume the whole span, valid or not


# A math-alphabet macro inside \mathrm{...}: the FOURTH member of the dropped-glyph
# family, found 2026-09-02 and previously misattributed to ISSUES #10.
_GREEK = (r"alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|vartheta|iota|kappa|"
          r"lambda|mu|nu|xi|pi|varpi|rho|varrho|sigma|varsigma|tau|upsilon|phi|varphi|chi|"
          r"psi|omega|Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Upsilon|Phi|Psi|Omega")
UPRIGHT_GREEK = re.compile(r"\\(?:mathrm|mathsf|mathtt|text|textrm)\{[^{}]*\\(" + _GREEK + r")\b")


def bad_upright_greek(text):
    r"""Yield (line, macro) for every Greek macro wrapped in an upright math alphabet.

    `\mathrm{\mu m}` asks the ROMAN TEXT font for U+1D707, which Latin Modern does not
    have -- so **LuaLaTeX drops the glyph from the PDF** and "15 micrometres" prints as
    "15 m", silently, while MathJax renders it correctly and the HTML looks fine.  Same
    symptom as ISSUES #9's three mechanisms and a different cause: not a delimiter
    problem at all, so `bad_spans` cannot see it.

    Write `\mu\mathrm{m}` instead.  ⚠️ `\upmu` is upright and correct under LuaLaTeX but is
    not in MathJax's default macro set, so it would fix the PDF and break the web edition.
    """
    for line, src in enumerate(_strip_uncheckable(text).splitlines(), 1):
        for m in UPRIGHT_GREEK.finditer(src):
            yield line, m.group(1)


# ---- captions: the quoting rule, which is genuinely ambiguous as usually stated ----
#
# COMMON says "a backslash in a double-quoted fig-cap/tbl-cap fails the render -- single-quote
# it, and double every internal apostrophe".  The apostrophe-doubling belongs to the SINGLE
# quoting; read as unconditional it produces `paper''s` on the page, which is what shipped in
# ch38 (27 of them) and ch40 (6).  So the rule is really two rules:
#
#   single-quoted caption:  double every internal apostrophe;  backslashes are fine as-is
#   double-quoted caption:  do NOT double apostrophes;  escape every backslash
#
CAPTION = re.compile(r"^#\|\s*(?:tbl-cap|fig-cap):\s*(.*)$")


def bad_captions(text):
    """Yield (line, kind, detail) for a caption whose quoting is wrong.

    Two failures, one loud and one silent. A double-quoted caption with an unescaped
    backslash **fails the render** -- YAML rejects the scalar and quarto stops. A ``''``
    inside a double-quoted caption is not an escape at all: it is two apostrophes, and they
    reach the reader.
    """
    for line, src in enumerate(text.splitlines(), 1):
        m = CAPTION.match(src.strip())
        if not m:
            continue
        val = m.group(1).strip()
        if not val.startswith('"'):
            continue                      # single-quoted: '' is correct there
        try:
            yaml.safe_load("k: " + val)
        except Exception as exc:
            yield line, "unparseable", str(exc).split("\n")[0]
        if "''" in val:
            yield line, "doubled apostrophe", (
                "'' is a SINGLE-quote escape; in a double-quoted caption it reaches the page")


def check(paths):
    total = 0
    for p in paths:
        path = pathlib.Path(p)
        src = path.read_text()
        for line, inner, why in bad_spans(src):
            short = inner if len(inner) <= 60 else inner[:57] + "..."
            print(f"{path}:{line}: {why}: ${short}$")
            total += 1
        for line, kind, detail in bad_captions(src):
            print(f"{path}:{line}: caption {kind} -- {detail}")
            total += 1
        for line, macro in bad_upright_greek(src):
            print(f"{path}:{line}: \\{macro} inside an upright math alphabet -- LuaLaTeX "
                  f"DROPS the glyph from the PDF; write \\{macro}\\mathrm{{...}} instead")
            total += 1
    return total


def self_test():
    """A gate that cannot fail is not a gate. Controls first, then decoys."""
    ok = [
        ("plain prose with no maths at all.\n", "no maths"),
        ("The value is $x = 3$ and another is $y = 4$, both fine.\n", "two spans"),
        ("we get $0.12$. At most $0.03$ deep down.\n", "two spans, one line"),
        ("leaving at $500$--$1500~\\mathrm{km\\,s^{-1}}$ in all\n",
         "a RANGE: $500$ closes before the dashes, so the next $ OPENS a new "
         "span. This is the case that defeated the previous scanner"),
        ("ratio $s \\approx 0.7$--$0.8$. Two consequences\n",
         "range followed by a period"),
        ("(ii) angles: $\\bar\\Theta(0) =\n\\Theta_0\\theta^4$ and then $D = 0$.\n",
         "a span WRAPPED across source lines"),
        ("```python\nx = 1  # $ not math $\n```\n", "fenced code is exempt"),
        ("$$\n\\hat t = 1\n$$\n", "display math is exempt"),
        ("costs \\$5 and \\$10 in escaped dollars\n",
         "escaped dollars are not delimiters"),
    ]
    for src, why in ok:
        hits = list(bad_spans(src))
        assert not hits, f"false positive on {why}: {hits}"

    bad = [
        ("not reached until $\\hat t = $ 4.2 later.\n",
         "whitespace before the closing $ -- wave 10, killed the PDF"),
        ("the ratio $ a/b$ is small.\n", "whitespace after the opening $"),
        ("a lower bound of $\\sim$50,000 derived from\n",
         "a DIGIT after the closing $ -- wave 11, drops the glyph silently"),
        ("multiply by $\\sim$2.6, and $\\sim$3.5 for Uranus\n",
         "two digit-after-close violations on one line"),
    ]
    counts = [len(list(bad_spans(src))) for src, _ in bad]
    assert counts == [1, 1, 1, 2], f"decoys not caught as expected: {counts}"

    up_ok = [
        (r"a pixel of $15\,\mu\mathrm{m}$ across", "the correct spelling"),
        (r"the mass $\bar\mu$ and $\mathrm{N_2}$ nearby", "no Greek inside \\mathrm"),
        (r"```python" "\n" r"s = '$\mathrm{\mu m}$'" "\n```", "inside a code fence"),
    ]
    for src, why in up_ok:
        hits = list(bad_upright_greek(src))
        assert not hits, f"false positive on {why}: {hits}"
    cap_ok = [
        r"#| fig-cap: 'the paper" + "''" + r"s own numbers, at $30^\circ$'",
        r'#| tbl-cap: "no backslash and no apostrophes at all"',
        r'#| tbl-cap: "an escaped one: $30^\\circ$ and $\\bar\\mu$"',
        r"some prose that merely mentions tbl-cap: in passing",
    ]
    for src in cap_ok:
        hits = list(bad_captions(src))
        assert not hits, f"false positive on {src!r}: {hits}"
    cap_bad = [
        (r'#| tbl-cap: "an unescaped $30^\circ$ kills the render"', "unparseable"),
        (r'#| tbl-cap: "the paper' + "''" + r's own numbers"', "doubled apostrophe"),
    ]
    for src, kind in cap_bad:
        kinds = [k for _, k, _ in bad_captions(src)]
        assert kind in kinds, f"decoy not caught ({kind}): {src!r} gave {kinds}"

    up_bad = [
        (r"a CCD with $15\,\mathrm{\mu m}$ pixels", 1),
        (r"$\mathrm{\alpha}$ and $\text{\Omega}$ both", 2),
    ]
    up_counts = [len(list(bad_upright_greek(s))) for s, _ in up_bad]
    assert up_counts == [n for _, n in up_bad], f"upright-Greek decoys: {up_counts}"

    print(f"self-test passed: {len(ok) + len(up_ok) + len(cap_ok)} controls clean "
          f"(ranges, wrapped spans, escaped dollars, a correct upright-micron and four "
          f"well-formed captions among them), "
          f"{sum(counts) + sum(up_counts) + len(cap_bad)} violations caught across "
          f"{len(bad) + len(up_bad) + len(cap_bad)} decoys")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "--self-test":
        sys.exit(self_test())
    sys.exit(1 if check(args) else 0)
