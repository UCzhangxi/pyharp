"""ch05 figure: error of the downward flux at the bottom of a grey isothermal slab, against pi B (1 - 2 E3(tau0)).

Toon89 (five-point source-function quadrature) and DISORT at 4, 16 and 64 streams, |error| / (pi B) against the
slab optical depth. Data: src/pyharp_report/ch05/data/analytic.json, written by
derivation-checks/check_ch05_analytic.py (--data) at the code pin of code_pin.yml.
"""
import numpy as np

from pyharp_report import figstyle as fs
from pyharp_report.ch05.figures._data import load


def make_fig():
    d = load("analytic.json")["e3"]
    tau = np.array(d["tau"])
    fig, ax = fs.new_figure("single", 2.4)
    style = {"Toon": (fs.GREEN, "s", "-"), "DISORT nstr=4": (fs.VERMILLION, "v", "--"),
             "DISORT nstr=16": (fs.ORANGE, "^", "-."), "DISORT nstr=64": (fs.BLUE, "o", ":")}
    for k, (c, m, ls) in style.items():
        ax.loglog(tau, np.maximum(np.abs(d[k]), 1e-12), color=c, marker=m, ls=ls, label=k.replace("nstr=", "N = "))
    ax.set_xlabel(r"slab optical depth $\tau_0$ [-]")
    ax.set_ylabel(r"|error| / $\pi B$ [-]")
    ax.legend(loc="lower left")
    return fig
