"""Delta-M on and off: flux errors of a one-layer DISORT run against a 128-stream reference.

Panel (a): Henyey-Greenstein g = 0.9; panel (b): the Garcia-Siewert cloud; both tau = 1, omega = 0.99, mu0 = 0.5.
The error shown is the larger of the reflected-flux and bottom-total-downward-flux relative errors.
Data: derivation-checks/ch03_delta_m.pydisort-1.7.1.out (check ch03_delta_m.py, label [C4]; pydisort 1.7.1, CPU,
double).
"""
from pyharp_report import figstyle as fs
from pyharp_report.ch03.data import delta_m_rows


def make_fig():
    rows = delta_m_rows()
    fig, axes = fs.new_figure("double", 2.4, ncols=2, sharey=True)
    for ax, phase, title in zip(axes, ("henyey-greenstein", "cloud-garcia-siewert"),
                                ("Henyey-Greenstein, g = 0.9", "Garcia-Siewert cloud")):
        sel = sorted((r for r in rows if r[0] == phase and r[1] == 1.0), key=lambda r: r[2])
        n = [r[2] for r in sel]
        on = [max(abs(r[3]), abs(r[5])) for r in sel]
        off = [max(abs(r[4]), abs(r[6])) for r in sel]
        ax.plot(n, off, color=fs.VERMILLION, marker="s", ls="--", label="delta-M off")
        ax.plot(n, on, color=fs.GREEN, marker="o", ls="-", label="delta-M on")
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        ax.set_xticks(n, [str(k) for k in n])
        ax.set_xlabel("number of streams [-]")
        ax.set_title(title, fontsize=fs.SMALL_PT)
    axes[0].set_ylabel("relative flux error [-]")
    axes[0].legend(loc="lower left")
    fs.panel_labels(axes)
    return fig
