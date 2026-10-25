"""ch06 figure: Mie extinction efficiency of water droplets and the error of pyharp against the reference.

Data: src/pyharp_report/ch06/data/mie_accuracy.json, written by derivation-checks/check_ch06_mie.py (--data) at the
code pin of code_pin.yml: Q_ext and g of the mpmath reference (Bohren & Huffman 1983) and the relative error of
pyharp.opacity.MieWaterLiquid against it, for m = 1.33 - ki, k = 1e-8, 1e-4 and 0.1, on 33 size parameters.
"""
import numpy as np

from pyharp_report import figstyle as fs
from pyharp_report.ch06.figures._data import load

STYLES = [(fs.BLUE, "o", "-"), (fs.ORANGE, "s", "--"), (fs.GREEN, "^", "-.")]


def make_fig():
    d = load("mie_accuracy.json")
    x = np.array(d["x"])
    fig, (a, b) = fs.new_figure("double", 2.5, 1, 2)
    for case, (c, m, ls) in zip(d["cases"], STYLES):
        lab = rf"$k$ = {case['k']:g}"
        a.loglog(x, case["qext_ref"], color=c, ls=ls, marker=m, ms=2.5, lw=1.0, label=lab)
        err = np.maximum(np.array(case["qext_rel_err"]), 1e-17)
        b.loglog(x, err, color=c, ls=ls, marker=m, ms=2.5, lw=1.0, label=lab)
    b.axhline(1e-9, color=fs.BLACK, ls=":", lw=0.8)
    b.text(0.012, 1.6e-9, "tolerance of [C1]", fontsize=fs.SMALL_PT, va="bottom")
    a.set_xlabel("size parameter $x$ [-]")
    a.set_ylabel(r"$Q_{\mathrm{ext}}$, reference [-]")
    b.set_xlabel("size parameter $x$ [-]")
    b.set_ylabel(r"$|Q_{\mathrm{ext}}$ / reference $-$ 1$|$ [-]")
    b.set_ylim(1e-17, 1e-2)
    a.legend(loc="lower right")
    fs.panel_labels([a, b])
    return fig
