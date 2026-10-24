"""Band fluxes of the quick-start column (chapter 1, `_quickstart.qmd`).

Reads src/pyharp_report/ch01/data/quickstart_fluxes.csv, written by derivation-checks/check_ch01_quickstart.py --data
on pyharp built at the pin of code_pin.yml: upward and downward flux [W m-2] of the shortwave and the longwave band at
the five levels of the quick-start column, level 0 being the surface.
"""
from pathlib import Path

import numpy as np

from pyharp_report import figstyle as fs

DATA = Path(__file__).resolve().parent.parent / "data" / "quickstart_fluxes.csv"


def make_fig():
    lev, sw_up, sw_dn, lw_up, lw_dn = np.loadtxt(DATA, delimiter=",", skiprows=1, unpack=True)
    fig, axes = fs.new_figure("double", 2.4, ncols=2, sharey=True)
    for ax, up, dn, name in ((axes[0], sw_up, sw_dn, "shortwave"), (axes[1], lw_up, lw_dn, "longwave")):
        ax.plot(dn, lev, color=fs.BLUE, marker="o", ls="-", label="downward")
        ax.plot(up, lev, color=fs.ORANGE, marker="^", ls="--", label="upward")
        ax.set_xlabel(f"{name} flux [W m$^{{-2}}$]")
        ax.set_xlim(left=0.0)
        ax.legend(loc="upper right" if name == "longwave" else "center right")
    axes[0].set_ylabel("level (0 = surface) [-]")
    axes[0].set_yticks(lev)
    fs.panel_labels(axes)
    return fig
