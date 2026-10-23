"""Convergence of the column model in time: largest temperature error against the step size, rk1 and rk3.

8-layer grey longwave column, t = 2e5 s, 2 to 16 steps, against 256 rk3 steps. Data:
derivation-checks/ch08_stepper.pydisort-1.7.1.out, lines 'conv' (check ch08_stepper.py [C6], the C++ RadiationModel
at the code_pin.yml pin through a compiled wrapper, pydisort 1.7.1, CPU, double).
"""
from pyharp_report import figstyle as fs
from pyharp_report.ch08.data import stepper_convergence

STYLE = {"rk1": (fs.ORANGE, "o", "-"), "rk3": (fs.GREEN, "s", "--")}


def make_fig():
    data = stepper_convergence()
    fig, ax = fs.new_figure("single", 2.4)
    for t, (c, m, ls) in STYLE.items():
        rows = sorted(data[t], key=lambda r: r[1])
        ax.plot([r[1] for r in rows], [r[2] for r in rows], color=c, marker=m, ls=ls, label=t)
    r1 = sorted(data["rk1"], key=lambda r: r[1])
    r3 = sorted(data["rk3"], key=lambda r: r[1])
    fs.slope_guide(ax, r1[0][1], r1[0][2] * 0.4, r1[-1][1] * 0.6, -1, label="order 1")
    fs.slope_guide(ax, r3[0][1], r3[0][2] * 0.3, r3[-1][1] * 0.6, -3, label="order 3")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ticks = [r[1] for r in r1]
    ax.set_xticks(ticks, [f"{t:.3g}" for t in ticks])
    ax.minorticks_off()
    ax.set_xlabel(r"step $\Delta t$ [s]")
    ax.set_ylabel("max $|T - T_{\\mathrm{ref}}|$ [K]")
    ax.legend(loc="lower right")
    return fig
