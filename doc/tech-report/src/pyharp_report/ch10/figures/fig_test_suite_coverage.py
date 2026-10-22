"""Test files at the pin by category: existing, registered with ctest, run by CI (chapter 10, `_test-suite.qmd`).

Reads src/pyharp_report/ch10/data/test_inventory.csv, written by derivation-checks/ch10/test_inventory.py --csv from
the pyharp tree at the pin of code_pin.yml.
"""
from pathlib import Path

import numpy as np

from pyharp_report import figstyle as fs

DATA = Path(__file__).resolve().parent.parent / "data" / "test_inventory.csv"


def make_fig():
    rows = [ln.split(",") for ln in DATA.read_text().splitlines()[1:]]
    names = [r[0] for r in rows]
    files, ctest, ci = (np.array([int(r[i]) for r in rows]) for i in (1, 2, 3))
    fig, ax = fs.new_figure("double", 2.3)
    y = np.arange(len(names))
    h = 0.26
    ax.barh(y - h, files, h, color=fs.SKY, edgecolor=fs.BLACK, lw=0.5, label="files in the tree")
    ax.barh(y, ctest, h, color=fs.WHITE, edgecolor=fs.BLACK, hatch="//", lw=0.5, label="registered with ctest")
    ax.barh(y + h, ci, h, color=fs.BLUE, edgecolor=fs.BLACK, lw=0.5, label="run by the CI job")
    for yy, vals in zip(y, zip(files, ctest, ci)):
        for off, v in zip((-h, 0, h), vals):
            ax.text(v + 0.3, yy + off, str(v), va="center", fontsize=fs.SMALL_PT)
    ax.set_yticks(y, names)
    ax.invert_yaxis()
    ax.set_xlabel("test files [count]")
    ax.set_xlim(0, max(files) + 4)
    ax.legend(loc="lower right")
    return fig
