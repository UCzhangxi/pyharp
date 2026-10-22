"""Nakajima-Tanaka intensity correction on and off: largest relative radiance error against a 128-stream reference.

One layer, Henyey-Greenstein g = 0.9, tau = 1, omega = 0.99, mu0 = 0.5. Three groups of directions: the aureole
(bottom, within 10 degrees of the beam), the other downward directions at the bottom, and upward at the top.
Data: derivation-checks/ch03_intensity_correction.pydisort-1.7.1.out (check ch03_intensity_correction.py, label
[C2]; pydisort 1.7.1, CPU, double).
"""
from pyharp_report import figstyle as fs
from pyharp_report.ch03.data import intensity_correction_rows

GROUPS = (("aureole", 1, fs.ORANGE, "o"), ("other downward", 3, fs.SKY, "s"), ("upward at top", 5, fs.BLACK, "^"))


def make_fig():
    rows = intensity_correction_rows()
    n = [r[0] for r in rows]
    fig, ax = fs.new_figure("single", 2.6)
    for label, i, c, m in GROUPS:
        ax.plot(n, [r[i] for r in rows], color=c, marker=m, ls="--", mfc="none")
        ax.plot(n, [r[i + 1] for r in rows], color=c, marker=m, ls="-", label=label)
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xticks(n, [str(k) for k in n])
    ax.set_xlabel("number of streams [-]")
    ax.set_ylabel("max relative radiance error [-]")
    ax.legend(loc="lower left", title="solid: on, dashed: off", title_fontsize=fs.SMALL_PT)
    return fig
