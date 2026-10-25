"""ch06 figure: the H2 Rayleigh cross section of pyharp against wavelength, and the share of its higher terms.

Data: src/pyharp_report/ch06/data/rayleigh_sigma.json, written by derivation-checks/check_ch06_rayleigh.py (--data)
at the code pin of code_pin.yml: sigma = k / (c N_A 1e-4) of pyharp.opacity.Rayleigh for pure H2, and the leading
term 8.14e-13 / lambda^4 (lambda in Angstrom) of the Dalgarno-Williams sum.
"""
import numpy as np

from pyharp_report import figstyle as fs
from pyharp_report.ch06.figures._data import load


def make_fig():
    d = load("rayleigh_sigma.json")
    lam = np.array(d["wavelength_um"])
    sig, lead = np.array(d["sigma_cm2"]), np.array(d["lambda4_cm2"])
    fig, (a, b) = fs.new_figure("double", 2.4, 1, 2)
    a.loglog(lam, sig, color=fs.GREEN, lw=1.4, label="pyharp, H$_2$")
    a.loglog(lam, lead, color=fs.BLUE, ls="--", lw=1.0, label=r"leading term $\propto\lambda^{-4}$")
    a.set_xlabel(r"wavelength $\lambda$ [$\mu$m]")
    a.set_ylabel(r"$\sigma$ [cm$^2$ molecule$^{-1}$]")
    a.legend(loc="upper right")
    b.semilogx(lam, sig / lead - 1, color=fs.VERMILLION, marker="o", ms=2.5, lw=1.0)
    b.set_xlabel(r"wavelength $\lambda$ [$\mu$m]")
    b.set_ylabel(r"$\sigma$ / leading term $-$ 1 [-]")
    for ax in (a, b):
        ax.set_xticks([0.2, 0.5, 1.0, 2.0], ["0.2", "0.5", "1", "2"])
        ax.minorticks_off()
    fs.panel_labels([a, b])
    return fig
