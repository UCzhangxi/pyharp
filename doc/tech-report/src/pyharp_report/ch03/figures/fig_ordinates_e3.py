"""E3 grey-slab check: relative deviation of the DISORT band fluxes from the analytic solution.

Shows, per stream count, the larger of the top upward and bottom downward flux deviations against the slab
optical depth. Data: derivation-checks/ch03_e3_slab.pydisort-1.7.1.out (check ch03_e3_slab.py, pyharp at the
code_pin.yml pin, pydisort 1.7.1, CPU, double).
"""
from pyharp_report import figstyle as fs
from pyharp_report.ch03.data import e3_rows

STYLE = {4: (fs.ORANGE, "o", "-"), 8: (fs.SKY, "s", "--"), 16: (fs.GREEN, "^", "-."), 32: (fs.BLACK, "D", ":")}


def make_fig():
    rows = e3_rows()
    fig, ax = fs.new_figure("double", 2.4)
    for n, (c, m, ls) in STYLE.items():
        pts = sorted((t, max(u, d)) for k, t, u, d in rows if k == n)
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=c, marker=m, ls=ls, label=f"{n} streams")
    ax.axhline(2e-4, color=fs.VERMILLION, lw=0.9, ls=(0, (1, 1)), label="tolerance, 32 streams")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_ylim(1e-6, 1e-1)
    ax.set_xlabel(r"slab optical depth $\tau$ [-]")
    ax.set_ylabel("relative deviation [-]")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    return fig
