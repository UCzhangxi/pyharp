"""Dependency map of chapter 4: the schemes of the Toon solver and how they connect.

Cartoon; no data. Drawn from `ToonMcKay89Impl::forward` (src/rtsolver/toon_mckay89.cpp) at the pin of code_pin.yml:
the `planck` flag selects the longwave kernel, which requires the band Planck function; without it the shortwave
kernel runs; both use the tridiagonal solve; `zenith_correction` is accepted and reaches nothing.
"""
from matplotlib.patches import FancyBboxPatch

from pyharp_report import figstyle as fs


def _node(ax, x, y, text, color):
    ax.add_patch(FancyBboxPatch((x - 1.05, y - 0.32), 2.1, 0.64, boxstyle="round,pad=0.04", fc=fs.WHITE, ec=color,
                                lw=1.4))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs.SMALL_PT)


def _edge(ax, p0, p1, label, at, color=fs.BLACK, ls="-", ha="center"):
    ax.annotate("", xy=p1, xytext=p0, arrowprops=dict(arrowstyle="-|>", color=color, lw=1.0, ls=ls))
    ax.text(at[0], at[1], label, fontsize=fs.SMALL_PT, color=color, ha=ha, va="center")


def make_fig():
    fig, ax = fs.new_figure("double", 2.3)
    fs.cartoon(ax)
    _node(ax, 0.0, 2.0, "solver: toon", fs.BLACK)
    _node(ax, -2.6, 0.6, "shortwave", fs.GREEN)
    _node(ax, 2.6, 0.6, "longwave", fs.GREEN)
    _node(ax, 5.4, 2.0, "band Planck", fs.GREEN)
    _node(ax, 0.0, -0.8, "tridiagonal solve", fs.GREY)
    _node(ax, -5.4, 2.0, "zenith_correction", fs.VERMILLION)
    _edge(ax, (-0.6, 1.68), (-2.1, 0.92), "no planck", (-1.5, 1.45), ha="right")
    _edge(ax, (0.6, 1.68), (2.1, 0.92), "planck", (1.5, 1.45), ha="left")
    _edge(ax, (3.2, 0.92), (4.8, 1.68), "requires", (4.1, 1.05), ha="left")
    _edge(ax, (-2.0, 0.28), (-0.6, -0.48), "requires", (-1.4, -0.25), ha="right")
    _edge(ax, (2.0, 0.28), (0.6, -0.48), "requires", (1.4, -0.25), ha="left")
    _edge(ax, (-4.35, 2.0), (-1.1, 2.0), "accepted, unused", (-2.7, 2.35), fs.VERMILLION, "--")
    ax.set_xlim(-6.8, 6.8)
    ax.set_ylim(-1.4, 2.6)
    return fig
