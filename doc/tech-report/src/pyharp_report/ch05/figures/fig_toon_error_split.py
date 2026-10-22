"""ch05 figure: Toon89's shortwave error on the ch05 grid, split into numerical and approximation parts, by regime.

Largest |dF| / F_inc per regime of optical depth and single-scattering albedo: the numerical part (Toon against the
exact solution of its own two-stream ODE) and the approximation part (that exact solution against DISORT at
N_ref = 64). Data: src/pyharp_report/ch05/data/toon_vs_disort.json, written by
derivation-checks/check_ch05_toon_vs_disort.py (--data) at the code pin of code_pin.yml.
"""
import numpy as np

from pyharp_report import figstyle as fs
from pyharp_report.ch05.figures._data import load

REGIMES = [("tau<=0.1, omega<=0.6", "thin\nlow"), ("tau<=0.1, omega=0.9", "thin\n0.9"),
           ("tau<=0.1, omega 0.99-0.999", "thin\nhigh"), ("0.3<=tau<=1, omega<=0.6", "mid\nlow"),
           ("0.3<=tau<=1, omega=0.9", "mid\n0.9"), ("0.3<=tau<=1, omega 0.99-0.999", "mid\nhigh"),
           ("tau>=3, omega<=0.6", "thick\nlow"), ("tau>=3, omega=0.9", "thick\n0.9"),
           ("tau>=3, omega 0.99-0.999", "thick\nhigh")]


def make_fig():
    sw = load("toon_vs_disort.json")["sw"]
    x = np.arange(len(REGIMES))
    num = [max(sw[k]["num"]["abs_max"], 1e-17) for k, _ in REGIMES]
    app = [sw[k]["app"]["abs_max"] for k, _ in REGIMES]
    med = [sw[k]["tot"]["abs_med"] for k, _ in REGIMES]
    fig, ax = fs.new_figure("double", 2.6)
    ax.bar(x - 0.2, app, 0.4, color=fs.VERMILLION, label="approximation, max")
    ax.bar(x + 0.2, num, 0.4, color=fs.GREEN, hatch="//", label="numerical, max")
    ax.plot(x - 0.2, med, ls="none", marker="o", mfc=fs.WHITE, mec=fs.BLACK, label="total, median")
    ax.set_yscale("log")
    ax.set_ylim(1e-17, 1)
    ax.set_xticks(x, [lab for _, lab in REGIMES])
    ax.set_xlabel(r"regime: optical depth (thin $\leq 0.1$, mid 0.3-1, thick $\geq 3$) and $\omega$")
    ax.set_ylabel(r"$|\Delta F|$ / $F_{\mathrm{inc}}$ [-]")
    ax.legend(loc="center right")
    return fig
