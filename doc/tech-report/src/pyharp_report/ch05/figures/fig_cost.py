"""ch05 figure: CPU wall time per column of DISORT against the stream count, with Toon89 for comparison.

Shortwave DISORT and Toon89 shortwave and thermal, 50 layers, 256 columns per call, best of 3, one thread and the
default thread count. Data: src/pyharp_report/ch05/data/cost.json, written by derivation-checks/check_ch05_cost.py
(--data) at the code pin of code_pin.yml; one host.
"""
import numpy as np

from pyharp_report import figstyle as fs
from pyharp_report.ch05.figures._data import load


def make_fig():
    d = load("cost.json")
    n = np.array(d["nstr"])
    fig, ax = fs.new_figure("single", 2.5)
    keys = sorted(d["threads"], key=int)
    for th, c, m, ls in zip(keys, [fs.BLUE, fs.ORANGE], ["o", "s"], ["-", "--"]):
        t = d["threads"][th]
        ax.loglog(n, [t[f"DISORT SW nstr={x}"] * 1e6 for x in n], color=c, marker=m, ls=ls,
                  label=f"DISORT, {th} thread{'s' if th != '1' else ''}")
        ax.axhline(t["Toon SW"] * 1e6, color=c, lw=0.8, ls=":")
    ax.set_xticks(n, [str(x) for x in n])
    ax.minorticks_off()
    ax.set_xlabel("streams N [-]")
    ax.set_ylabel(r"time per column [$\mu$s]")
    ax.legend(loc="upper left")
    return fig
