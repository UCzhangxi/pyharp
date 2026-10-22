"""Shortwave error of one thick layer against its optical thickness (chapter 4, `_shortwave.qmd`).

Reads src/pyharp_report/ch04/data/shortwave_thick_layer.csv, written by
derivation-checks/ch04/toon_pyharp_check.py --data on pyharp at the pin of code_pin.yml (the file header records
the versions): max |pyharp - 40-to-150-digit reference| / (F0 mu0) for one layer with w = 0.3, g = 0, mu0 = 0.6, A = 0.
"""
from pathlib import Path

import numpy as np

from pyharp_report import figstyle as fs

DATA = Path(__file__).resolve().parent.parent / "data" / "shortwave_thick_layer.csv"


def make_fig():
    x, e = np.loadtxt(DATA, delimiter=",", comments="#", skiprows=3, unpack=True)
    fig, ax = fs.new_figure("single", 2.4)
    ax.semilogy(x, e, ls="-", marker="o", color=fs.VERMILLION, label="pyharp, one layer")
    eps = np.finfo(float).eps
    xs = np.linspace(5, 35, 50)
    ax.semilogy(xs, np.exp(xs) * eps * 0.4, ls="--", color=fs.BLUE, label=r"$0.4\,e^{\lambda\Delta\tau}\,\epsilon_{\mathrm{mach}}$")
    ax.axvline(35.0, color=fs.BLACK, ls=":", lw=0.8)
    ax.text(36.0, 1e-4, "cap $e^{35}$", fontsize=fs.SMALL_PT, va="center")
    ax.set_xlabel(r"$\lambda\,\Delta\tau$ [-]")
    ax.set_ylabel(r"max $|\Delta F|/(F_0\mu_0)$ [-]")
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 0.08))
    return fig
