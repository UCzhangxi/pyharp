"""Options per C++ option struct and their binding and stub gaps (chapter 10, `_bindings.qmd`).

Reads src/pyharp_report/ch10/data/bindings_gaps.csv, written by derivation-checks/ch10/bindings_diff.py --csv
against pyharp built from the pin of code_pin.yml.
"""
from pathlib import Path

import numpy as np

from pyharp_report import figstyle as fs

DATA = Path(__file__).resolve().parent.parent / "data" / "bindings_gaps.csv"


def make_fig():
    rows = [ln.split(",") for ln in DATA.read_text().splitlines()[1:]]
    rows.sort(key=lambda r: -int(r[1]))
    names = [r[0] + ("" if r[4] == "1" else " (unbound)") for r in rows]
    n, mb, ms = (np.array([int(r[i]) for r in rows]) for i in (1, 2, 3))
    fig, ax = fs.new_figure("double", 2.8)
    y = np.arange(len(rows))
    h = 0.27
    ax.barh(y - h, n, h, color=fs.GREY, edgecolor=fs.BLACK, lw=0.5, label="options")
    ax.barh(y, mb, h, color=fs.VERMILLION, edgecolor=fs.BLACK, hatch="//", lw=0.5, label="no Python binding")
    ax.barh(y + h, ms, h, color=fs.ORANGE, edgecolor=fs.BLACK, lw=0.5, label="no stub declaration")
    ax.set_yticks(y, names)
    ax.invert_yaxis()
    ax.set_xlabel("options [count]")
    ax.legend(loc="lower right")
    return fig
