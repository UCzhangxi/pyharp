"""tools/check_fig_output.py: the drawn figures against STYLE 6.2, per chapter, ratchet.

Each test builds a small report tree: a chapter source with figure cells and a module `demo_figs` in its `src/`,
one figure per kind of finding. The figures are drawn with Agg; needs matplotlib and `pyharp_report.figstyle`
(for the house widths and the 8 pt floor). Run from the report directory: `python3 -m pytest tools/tests`.
"""

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("pyharp_report.figstyle")

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import check_fig_output  # noqa: E402

FIGS = '''
import warnings
from matplotlib.figure import Figure
from pyharp_report import figstyle as fs

_calls = [0]


def good():
    fig, ax = fs.new_figure("double", 2.0)
    ax.text(0.2, 0.5, "label", fontsize=fs.SMALL_PT)
    return fig


def small_font():
    fig, ax = fs.new_figure("single", 2.0)
    ax.set_axis_off()
    ax.text(0.2, 0.5, "tiny", fontsize=6)
    return fig


def wide():
    fig = Figure(figsize=(7.0, 2.0))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_axis_off()
    ax.plot([0, 1], [0, 1])
    return fig


def overlap():
    fig, ax = fs.new_figure("single", 2.0)
    ax.set_axis_off()
    ax.text(0.5, 0.5, "first label", fontsize=fs.SMALL_PT)
    ax.text(0.52, 0.5, "second label", fontsize=fs.SMALL_PT)
    return fig


def warns():
    warnings.warn("drawn with a warning")
    fig, ax = fs.new_figure("single", 2.0)
    ax.set_axis_off()
    return fig


def drifts():
    _calls[0] += 1
    fig, ax = fs.new_figure("single", 2.0)
    ax.set_axis_off()
    ax.text(0.1, 0.5, "call %d" % _calls[0], fontsize=fs.SMALL_PT)
    return fig
'''

CELL = '''```{{python}}
#| label: fig-ch01-{name}
#| fig-cap: "A figure."
#| fig-alt: "A figure."
#| echo: false
from demo_figs import {fn}
{fn}()
```
'''


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "demo_figs.py").write_text(FIGS)
    q = tmp_path / "book" / "chapters" / "01-demo" / "_demo.qmd"
    q.parent.mkdir(parents=True)
    q.write_text("".join(CELL.format(name=fn.replace("_", "-"), fn=fn)
                         for fn in ("good", "small_font", "wide", "overlap", "warns", "drifts")))
    (tmp_path / "tools").mkdir()
    yield tmp_path
    sys.modules.pop("demo_figs", None)
    sys.path[:] = [p for p in sys.path if p != str(tmp_path / "src")]


def test_figure_cells_are_found_with_their_chapter(tree):
    cells = check_fig_output.figure_cells(tree)
    assert [c.label for c in cells][:2] == ["fig-ch01-good", "fig-ch01-small-font"]
    assert {c.chapter for c in cells} == {"ch01"}


def test_each_figure_has_its_own_finding(tree):
    rows = check_fig_output.scan(tree)["ch01"]
    by_label = {}
    for label, kind, _ in rows:
        by_label.setdefault(label, []).append(kind)
    assert "fig-ch01-good" not in by_label
    assert by_label["fig-ch01-small-font"] == ["font"]
    assert by_label["fig-ch01-wide"] == ["width", "overflow"]
    assert by_label["fig-ch01-overlap"] == ["overlap"]
    assert by_label["fig-ch01-warns"] == ["warning"]
    assert by_label["fig-ch01-drifts"] == ["redraw"]


def test_the_ratchet_and_update(tree):
    base = tree / "tools" / "figoutput-baseline.json"
    assert check_fig_output.main(["--report", str(tree), "--baseline", str(base), "--update"]) == 0
    assert json.loads(base.read_text())["chapters"]["ch01"] == {
        "font": 1, "overflow": 1, "overlap": 1, "redraw": 1, "warning": 1, "width": 1}
    assert check_fig_output.check(tree, base)[0] == 0
    q = tree / "book" / "chapters" / "01-demo" / "_demo.qmd"
    q.write_text(q.read_text().replace("from demo_figs import small_font\nsmall_font()",
                                       "from demo_figs import good\ngood()"))
    status, msgs = check_fig_output.check(tree, base)
    assert status == 1 and msgs == ["ch01 font: 0, baseline 1: lower the baseline with --update"]


def test_a_figure_that_cannot_be_drawn_always_fails(tree):
    q = tree / "book" / "chapters" / "01-demo" / "_demo.qmd"
    q.write_text(CELL.format(name="missing", fn="not_there"))
    base = tree / "tools" / "figoutput-baseline.json"
    status, msgs = check_fig_output.check(tree, base)
    assert status == 1 and msgs[0].startswith("ch01 error: 1 figure(s) could not be drawn")


def test_the_committed_baseline_names_known_kinds_only():
    data = json.loads((TOOLS / "figoutput-baseline.json").read_text())
    assert {k for kinds in data["chapters"].values() for k in kinds} <= set(check_fig_output.KINDS)
