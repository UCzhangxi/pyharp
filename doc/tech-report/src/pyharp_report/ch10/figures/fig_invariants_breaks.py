"""Each invariant check's measured value over its tolerance, at the pin and with the check's break mutation
(chapter 10, `_invariants.qmd`).

Reads src/pyharp_report/ch10/data/break_tests.csv, written by derivation-checks/ch10/break_tests.py --csv against
pyharp built from the pin of code_pin.yml (value_pin: the unmutated build; value_broken: the build with the mutation
that removes the term or floor the check exists for). A value of exactly 0 is drawn at the axis floor, a non-finite
value at 1e12.
"""
from pathlib import Path

import numpy as np

from pyharp_report import figstyle as fs

DATA = Path(__file__).resolve().parent.parent / "data" / "break_tests.csv"
FLOOR, CEIL = 1e-8, 1e12


def _ratio(value, tol):
    if not np.isfinite(value):
        return CEIL
    if tol == 0.0:
        return FLOOR if value == 0.0 else CEIL
    return min(max(value / tol, FLOOR), CEIL)


def make_fig():
    rows = [ln.split(",") for ln in DATA.read_text().splitlines()[1:]]
    best = {}
    for mid, check, vp, vb, tol in rows:  # one bar pair per check: its first break test
        if check not in best:
            best[check] = (mid, float(vp), float(vb), float(tol))
    checks = list(best)
    pin = np.array([_ratio(best[c][1], best[c][3]) for c in checks])
    brk = np.array([_ratio(best[c][2], best[c][3]) for c in checks])
    fig, ax = fs.new_figure("double", 2.9)
    x = np.arange(len(checks))
    w = 0.38
    ax.bar(x - w / 2, pin, w, bottom=FLOOR, color=fs.GREEN, edgecolor=fs.BLACK, lw=0.5, label="pin")
    ax.bar(x + w / 2, brk, w, bottom=FLOOR, color=fs.VERMILLION, edgecolor=fs.BLACK, hatch="//", lw=0.5,
           label="break mutation")
    ax.axhline(1.0, color=fs.BLACK, lw=1.0, ls="--", label="tolerance")
    ax.set_yscale("log")
    ax.set_ylim(FLOOR, CEIL * 1e5)  # room for the legend above the ceiling
    ax.set_xticks(x, [f"{c}\n{best[c][0]}" for c in checks])
    ax.set_ylabel("value / tolerance [-]")
    ax.legend(loc="upper left", ncols=3)
    return fig
