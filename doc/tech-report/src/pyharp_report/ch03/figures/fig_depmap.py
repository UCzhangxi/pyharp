"""Chapter 3 dependency map: the four schemes and how they switch each other on or off (a cartoon, no data).

Nodes are the schemes of chapter 3; an arrow is labelled "requires", "implies" or "turns off". Code facts behind
each edge are cited in the chapter text (pydisort and cdisort at the pin of code_pin.yml).
"""
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from pyharp_report import figstyle as fs

NODES = {
    "band": (1.6, 2.2, "DISORT band\n(solver: disort)"),
    "ord": (5.2, 2.2, "discrete-ordinate\nsolution"),
    "dm": (5.2, 0.5, "delta-M scaling\n(no option)"),
    "ic": (1.6, 0.5, "intensity correction\n(intensity_correction)"),
}


def _box(ax, x, y, text, color):
    ax.add_patch(FancyBboxPatch((x - 1.15, y - 0.38), 2.3, 0.76, boxstyle="round,pad=0.05", fc=fs.WHITE,
                                ec=color, lw=1.2))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs.SMALL_PT)


def _arrow(ax, p0, p1, label, color, dx=0.0, dy=0.0, ls="-"):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=9, lw=1.1, color=color, ls=ls))
    ax.text(0.5 * (p0[0] + p1[0]) + dx, 0.5 * (p0[1] + p1[1]) + dy, label, ha="center", va="center",
            fontsize=fs.SMALL_PT, color=color, bbox=dict(boxstyle="round,pad=0.1", fc=fs.WHITE, ec="none"))


def make_fig():
    fig, ax = fs.new_figure("double", 2.0)
    fs.cartoon(ax)
    for key, (x, y, t) in NODES.items():
        _box(ax, x, y, t, fs.GREEN if key == "ord" else fs.BLACK)
    _arrow(ax, (2.8, 2.2), (4.0, 2.2), "requires", fs.BLACK, dy=0.22)
    _arrow(ax, (5.2, 1.78), (5.2, 0.92), "implies when\n$\\chi_{2N} \\neq 0$", fs.BLACK, dx=1.05)
    _arrow(ax, (2.8, 0.5), (4.0, 0.5), "requires", fs.BLACK, dy=0.22)
    _arrow(ax, (1.6, 1.78), (1.6, 0.92), "turns off\n(onlyfl)", fs.VERMILLION, dx=-0.8, ls="--")
    ax.set_xlim(0.2, 7.2)
    ax.set_ylim(-0.05, 2.75)
    return fig
