#!/usr/bin/env python3
"""Figure-style gate: figure code styles only through `pyharp_report.figstyle` (STYLE.md 6.1, 6.2, 10.4).

A static check, in ratchet mode. It reads the Python files of the report's figure code (`src/pyharp_report/`, and a
`chapters/` planning tree if one exists) without importing them and counts, per file, three kinds of styling done outside the one figure-style
module:

  * `import`: a style module other than `pyharp_report.figstyle` (a chapter's `_style.py`, a planning tree's
    `chapters/common/figstyle.py` imported as `figstyle`, `matplotlib.style`, seaborn);
  * `rc`: a write to matplotlib's settings (`rcParams[...] = ...`, `rcParams.update`, `rc(...)`, `rc_context`,
    `style.use`);
  * `font`: a font set inline (a `fontsize`, `fontfamily`, `family`, `fontname`, `fontproperties` or `labelsize`
    argument, `size=` in a text call, a legend `prop` with a size or family, `FontProperties(...)`,
    `set_fontsize`/`set_family`/`set_fontfamily`). A value read from `pyharp_report.figstyle`
    (`fontsize=fs.SMALL_PT`, with `fs` bound to that module, or `fontsize=SMALL_PT` after
    `from pyharp_report.figstyle import SMALL_PT`) is not counted: that is styling through figstyle.

`src/pyharp_report/figstyle.py` itself is exempt. Counts are summed per chapter (`ch05`, `appa`, ...; `package` for
files directly in `src/pyharp_report/`, `common` for `chapters/common/`) and compared with the committed baseline
`tools/figstyle-baseline.json`. The ratchet: a chapter above its baseline fails, and so does a chapter below it,
so that the baseline is lowered in the same commit that removes the debt (`--update` writes the lower counts and
refuses to raise any). A chapter missing from the baseline has a baseline of 0.

    python3 tools/check_figstyle.py            # gate: exit 1 if any chapter differs from its baseline
    python3 tools/check_figstyle.py --list     # also print every counted site, file:line kind detail
    python3 tools/check_figstyle.py --update   # lower the baseline to the current counts (never raises one)

Exit status 0 when every chapter equals its baseline, 1 otherwise, 2 for a usage error. What the rendered
figures look like (font, sizes in points, figure widths) is not checked here; that needs a render.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parent.parent
BASELINE = REPORT / "tools" / "figstyle-baseline.json"
ROOTS = ("src/pyharp_report", "chapters")
FIGSTYLE = "pyharp_report.figstyle"
EXEMPT = {"src/pyharp_report/figstyle.py"}

FONT_KW = {"fontsize", "fontfamily", "family", "fontname", "fontproperties", "labelsize"}
TEXT_CALLS = {"text", "annotate", "set_xlabel", "set_ylabel", "set_zlabel", "set_title", "suptitle", "supxlabel",
              "supylabel", "xlabel", "ylabel", "title", "figtext", "set_xticklabels", "set_yticklabels", "legend",
              "table", "clabel", "label_outer"}
FONT_CALLS = {"FontProperties", "set_fontsize", "set_family", "set_fontfamily", "set_fontname"}
RC_CALLS = {"rc", "rc_context", "rcdefaults", "use_style"}


def chapter_of(rel: str) -> str:
    parts = rel.split("/")
    if rel.startswith("src/pyharp_report/"):
        return parts[2] if len(parts) > 3 else "package"
    if rel.startswith("chapters/"):
        m = re.match(r"(\d\d)", parts[1])
        return f"ch{m.group(1)}" if m else parts[1]
    return parts[0]


def _dotted(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


class _Scan(ast.NodeVisitor):
    def __init__(self):
        self.hits: list[tuple[int, str, str]] = []
        self.figstyle_names: set[str] = set()   # names bound to the module (`fs`)
        self.figstyle_values: set[str] = set()  # names imported from it (`SMALL_PT`)

    # imports -----------------------------------------------------------------------------------------------------
    def _style_module(self, module: str, name: str) -> bool:
        full = f"{module}.{name}" if module and name else (module or name)
        if full == FIGSTYLE or (module == "pyharp_report" and name == "figstyle"):
            return False
        leaf = full.rsplit(".", 1)[-1]
        return (leaf in ("_style", "figstyle") or full.startswith("matplotlib.style") or full == "seaborn"
                or full.startswith("seaborn."))

    def visit_Import(self, node):
        for a in node.names:
            if a.name == FIGSTYLE:
                self.figstyle_names.add(a.asname or a.name)
            elif self._style_module(a.name, ""):
                self.hits.append((node.lineno, "import", a.name))

    def visit_ImportFrom(self, node):
        module = node.module or ""
        if module == FIGSTYLE:  # names taken from figstyle itself
            self.figstyle_values.update(a.asname or a.name for a in node.names)
            return
        styled = []
        for a in node.names:
            if module == "pyharp_report" and a.name == "figstyle":
                self.figstyle_names.add(a.asname or a.name)
            elif self._style_module(module, a.name) or module.endswith("_style"):
                styled.append(a.name)
        if styled:  # one count per import statement
            where = ("." * node.level) + module
            self.hits.append((node.lineno, "import", f"from {where} import {', '.join(styled)}"))

    # rc writes ---------------------------------------------------------------------------------------------------
    def visit_Assign(self, node):
        for t in node.targets:
            if isinstance(t, ast.Subscript) and _dotted(t.value).endswith("rcParams"):
                self.hits.append((node.lineno, "rc", f"{_dotted(t.value)}[...] ="))
        self.generic_visit(node)

    # calls -------------------------------------------------------------------------------------------------------
    def _from_figstyle(self, value) -> bool:
        base = value
        while isinstance(base, ast.Attribute):
            base = base.value
        if isinstance(base, ast.Name) and base is value:
            return base.id in self.figstyle_values
        return isinstance(base, ast.Name) and base.id in self.figstyle_names

    def visit_Call(self, node):
        name = _dotted(node.func)
        leaf = name.rsplit(".", 1)[-1]
        if name.endswith("rcParams.update") or (leaf in RC_CALLS and (name.startswith(("matplotlib", "mpl", "plt"))
                                                                      or name == leaf)):
            self.hits.append((node.lineno, "rc", name))
        elif name.endswith("style.use"):
            self.hits.append((node.lineno, "rc", name))
        if leaf in FONT_CALLS:
            self.hits.append((node.lineno, "font", name))
        for kw in node.keywords:
            if kw.arg is None:
                continue
            if kw.arg in FONT_KW or (kw.arg == "size" and leaf in TEXT_CALLS):
                if not self._from_figstyle(kw.value):
                    self.hits.append((node.lineno, "font", f"{kw.arg}= in {leaf or name}()"))
            elif kw.arg == "prop" and isinstance(kw.value, ast.Dict):
                keys = {k.value for k in kw.value.keys if isinstance(k, ast.Constant)}
                if keys & {"size", "family"}:
                    self.hits.append((node.lineno, "font", f"prop={{{', '.join(sorted(keys))}}} in {leaf}()"))
        self.generic_visit(node)


def scan_file(path: Path, rel: str) -> list[tuple[int, str, str]]:
    try:
        tree = ast.parse(path.read_text(), filename=rel)
    except SyntaxError as e:
        return [(e.lineno or 0, "parse", str(e.msg))]
    s = _Scan()
    # bind the figstyle names first, so a use before the import line is still recognised
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            s.visit(node)
    s.hits.clear()
    s.visit(tree)
    return sorted(s.hits)


def scan(report: Path = REPORT) -> dict[str, list[tuple[str, int, str, str]]]:
    """Every counted site, by chapter: (file, line, kind, detail)."""
    out: dict[str, list] = {}
    for root in ROOTS:
        base = report / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(report).as_posix()
            if rel in EXEMPT:
                continue
            hits = scan_file(path, rel)
            ch = chapter_of(rel)
            out.setdefault(ch, [])
            out[ch] += [(rel, ln, kind, detail) for ln, kind, detail in hits]
    return out


def counts(sites: dict) -> dict[str, int]:
    return {ch: len(v) for ch, v in sorted(sites.items()) if v}


def load_baseline(path: Path = BASELINE) -> dict[str, int]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {k: int(v) for k, v in data.get("chapters", {}).items()}


def compare(current: dict[str, int], baseline: dict[str, int]) -> list[str]:
    msgs = []
    for ch in sorted(set(current) | set(baseline)):
        c, b = current.get(ch, 0), baseline.get(ch, 0)
        if c > b:
            msgs.append(f"{ch}: {c} styling site(s) outside figstyle, baseline {b}: style through "
                        f"pyharp_report.figstyle instead (--list shows the sites)")
        elif c < b:
            msgs.append(f"{ch}: {c} styling site(s), baseline {b}: lower the baseline with "
                        f"`python3 tools/check_figstyle.py --update` in this commit")
    return msgs


def write_baseline(current: dict[str, int], baseline: dict[str, int], path: Path = BASELINE) -> list[str]:
    """Lower the baseline to `current`; refuse (and write nothing) if any chapter would go up."""
    up = [f"{ch}: {current[ch]} > baseline {baseline.get(ch, 0)}" for ch in current
          if current[ch] > baseline.get(ch, 0)]
    if up and path.exists():
        return up
    data = {"about": "per-chapter count of figure styling outside pyharp_report.figstyle; may only shrink "
                     "(tools/check_figstyle.py)",
            "chapters": {ch: n for ch, n in sorted(current.items()) if n}}
    path.write_text(json.dumps(data, indent=2) + "\n")
    return []


def check(report: Path = REPORT, baseline_path: Path = BASELINE) -> tuple[int, list[str]]:
    """(status, messages) for the render gate: 0 when every chapter equals its baseline."""
    msgs = compare(counts(scan(report)), load_baseline(baseline_path))
    return (1 if msgs else 0), msgs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--list", action="store_true", help="print every counted site")
    ap.add_argument("--update", action="store_true", help="lower the baseline to the current counts")
    ap.add_argument("--report", type=Path, default=REPORT, help=argparse.SUPPRESS)
    ap.add_argument("--baseline", type=Path, default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    bpath = args.baseline or (args.report / "tools" / "figstyle-baseline.json")
    sites = scan(args.report)
    current = counts(sites)
    baseline = load_baseline(bpath)
    if args.list:
        for ch in sorted(sites):
            for rel, ln, kind, detail in sites[ch]:
                print(f"{rel}:{ln}: {kind}: {detail}")
    if args.update:
        up = write_baseline(current, baseline, bpath)
        if up:
            print("check_figstyle: not written, the baseline may only shrink: " + "; ".join(up))
            return 1
        print(f"check_figstyle: baseline written, {sum(current.values())} site(s) in {len(current)} chapter(s)")
        return 0
    msgs = compare(current, baseline)
    total = sum(current.values())
    print(f"check_figstyle: {total} styling site(s) outside figstyle in {len(current)} chapter(s); "
          f"baseline {sum(baseline.values())}" + ("" if not msgs else f"; {len(msgs)} chapter(s) differ"))
    for m in msgs:
        print(f"  {m}")
    return 1 if msgs else 0


if __name__ == "__main__":
    sys.exit(main())
