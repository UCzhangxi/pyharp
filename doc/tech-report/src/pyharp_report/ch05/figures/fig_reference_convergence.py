"""ch05 figure: convergence of DISORT in the stream count, and DISORT against Garcia & Siewert (1985) Table 22.

(a) d(N) = max |F(N) - F(2N)| / F_inc over the ch05 grid, shortwave and thermal, with the tolerance 1e-5 that
picks N_ref. (b) Max relative difference of DISORT from Table 22 for the five benchmark problems, by stream count.
Data: src/pyharp_report/ch05/data/convergence.json and gs85.json, written by derivation-checks/check_ch05_convergence.py
and check_ch05_gs85.py (--data) at the code pin of code_pin.yml.
"""
import numpy as np

from pyharp_report import figstyle as fs
from pyharp_report.ch05.figures._data import load


def make_fig():
    cv, gs = load("convergence.json"), load("gs85.json")
    fig, (a, b) = fs.new_figure("double", 2.5, 1, 2)
    n = np.array(cv["nstr"])
    a.loglog(n, cv["sw"], color=fs.ORANGE, marker="^", label="shortwave")
    a.loglog(n, cv["lw"], color=fs.SKY, marker="o", ls="--", label="thermal")
    a.axhline(cv["tol_ref"], color=fs.BLACK, lw=0.8, ls=":", label="tolerance")
    a.set_xticks(n, [str(x) for x in n])
    a.minorticks_off()
    a.set_xlabel("streams N [-]")
    a.set_ylabel("max |F(N) - F(2N)| / F_inc [-]")
    a.legend(loc="upper right")
    ns = np.array(gs["nstr"])
    marks = ["o", "s", "^", "D", "v"]
    cols = [fs.ORANGE, fs.SKY, fs.GREEN, fs.BLUE, fs.VERMILLION]
    for k in range(5):
        b.semilogy(ns, [gs["rel"][str(x)][k] for x in ns], marker=marks[k], color=cols[k], label=f"case {k + 1}")
    b.axhline(gs["tol"], color=fs.BLACK, lw=0.8, ls=":")
    b.set_xscale("log", base=2)
    b.set_xticks(ns, [str(x) for x in ns])
    b.minorticks_off()
    b.set_xlabel("streams N [-]")
    b.set_ylabel("max relative difference [-]")
    b.legend(loc="upper right", ncols=2)
    fs.panel_labels([a, b])
    return fig
