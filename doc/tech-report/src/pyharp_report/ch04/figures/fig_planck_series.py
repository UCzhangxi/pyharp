"""The two series of the band-integrated Planck function of chapter 4 (`_planck.qmd`).

Cartoon of the branch logic of `bbflux_wavenumber(wn1, wn2, temp)` (src/radiation/bbflux.cpp) at the pin of
code_pin.yml, drawn from the formulas: the fraction of sigma T^4/pi below v = c2 nu / T, from the power series for
v < 1.5 and from the six-term exponential series for v > 1.5; the band value is a difference of two such fractions.
"""
import math

import numpy as np

from pyharp_report import figstyle as fs

CONC = 15.0 / math.pi ** 4


def below(v):
    """fraction of the integrated Planck function below v (power series)"""
    a = (1 / 3, -1 / 8, 1 / 60, -1 / 5040, 1 / 272160, -1 / 13305600)
    vsq = v * v
    return CONC * vsq * v * (a[0] + v * (a[1] + v * (a[2] + vsq * (a[3] + vsq * (a[4] + vsq * a[5])))))


def above(v):
    """fraction above v (exponential series, six terms)"""
    d = np.zeros_like(v)
    for m in range(1, 7):
        mv = m * v
        d += np.exp(-m * v) * (6.0 + mv * (6.0 + mv * (3.0 + mv))) / m ** 4
    return CONC * d


def make_fig():
    fig, ax = fs.new_figure("single", 2.4)
    v1 = np.linspace(0.02, 1.5, 80)
    v2 = np.linspace(1.5, 12.0, 120)
    ax.plot(v1, below(v1), color=fs.GREEN, ls="-", label=r"power series, $v<1.5$")
    ax.plot(v2, 1.0 - above(v2), color=fs.ORANGE, ls="--", label=r"$1-$ exponential series, $v>1.5$")
    ax.axvline(1.5, color=fs.BLACK, ls=":", lw=0.8)
    ax.set_xlabel(r"$v = c_2\,\nu/T$ [-]")
    ax.set_ylabel(r"fraction of $\sigma T^4/\pi$ below $v$ [-]")
    ax.legend(loc="lower right")
    return fig
