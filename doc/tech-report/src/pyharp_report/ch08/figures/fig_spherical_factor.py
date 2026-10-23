"""Spherical flux scaling: the factor on each level, as the code computes it and as its docstring defines it.

Two panels: (a) plane-parallel geometry (A constant, V = A dz), where the documented factor is 1; (b) a spherical
shell of radius 6.4e6 m. Data: derivation-checks/ch08_spherical.pydisort-1.7.1.out, lines 'level' (check
ch08_spherical.py, pyharp at the code_pin.yml pin, pydisort 1.7.1, CPU, double).
"""
from pyharp_report import figstyle as fs
from pyharp_report.ch08.data import spherical_factors


def make_fig():
    data = spherical_factors()
    fig, axes = fs.new_figure("double", 2.4, ncols=2, sharey=True)
    for ax, kind in zip(axes, ("plane-parallel", "shell")):
        rows = data[kind]
        q = [r[0] for r in rows]
        ax.plot(q, [r[1] for r in rows], color=fs.VERMILLION, marker="s", ls="-", label="code at the pin")
        ax.plot(q, [r[2] for r in rows], color=fs.BLUE, marker="o", ls="--", label="documented recursion")
        ax.set_yscale("log")
        ax.set_xticks(q)
        ax.set_xlabel("level $q$ (0 = surface) [-]")
        ax.set_title(kind, fontsize=fs.LABEL_PT)
    axes[0].set_ylabel("scaling factor [-]")
    axes[1].legend(loc="upper right")
    fs.panel_labels(axes)
    return fig
