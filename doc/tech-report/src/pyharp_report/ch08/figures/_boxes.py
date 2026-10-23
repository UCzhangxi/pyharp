"""Shared drawing helpers of the chapter 8 cartoons: a rounded node box and a labelled arrow (figstyle only)."""
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from pyharp_report import figstyle as fs


def box(ax, x, y, text, color=fs.BLACK, w=2.3, h=0.76, ls="-"):
    ax.add_patch(FancyBboxPatch((x - 0.5 * w, y - 0.5 * h), w, h, boxstyle="round,pad=0.05", fc=fs.WHITE,
                                ec=color, lw=1.2, ls=ls))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs.SMALL_PT)


def arrow(ax, p0, p1, label="", color=fs.BLACK, dx=0.0, dy=0.0, ls="-"):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=9, lw=1.1, color=color, ls=ls))
    if label:
        ax.text(0.5 * (p0[0] + p1[0]) + dx, 0.5 * (p0[1] + p1[1]) + dy, label, ha="center", va="center",
                fontsize=fs.SMALL_PT, color=color, bbox=dict(boxstyle="round,pad=0.1", fc=fs.WHITE, ec="none"))
