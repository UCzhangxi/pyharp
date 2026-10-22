"""Map of chapter 10: its sections and what each examines.

Cartoon; no data. The sections of `book/chapters/10-verification/` and the parts of the pyharp tree at the pin of
code_pin.yml they examine.
"""
from matplotlib.patches import FancyBboxPatch

from pyharp_report import figstyle as fs


def _box(ax, x, y, text, color, w=2.7):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - 0.3), w, 0.6, boxstyle="round,pad=0.04", fc=fs.WHITE, ec=color,
                                lw=1.3))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs.SMALL_PT)


def make_fig():
    fig, ax = fs.new_figure("double", 2.0)
    fs.cartoon(ax)
    secs = [("test suite and CI", "tests/, ci.yml"), ("pydisort dependency", "pyproject, FindDisort"),
            ("bindings and stubs", "python/csrc, *.pyi"), ("verification index", "report checks")]
    for k, (s, src) in enumerate(secs):
        x = 3.2 * k
        _box(ax, x, 1.0, s, fs.GREEN)
        _box(ax, x, 0.0, src, fs.GREY)
        ax.annotate("", xy=(x, 0.32), xytext=(x, 0.68), arrowprops=dict(arrowstyle="-|>", color=fs.BLACK, lw=1.0))
    ax.text(4.8, 1.55, "sections (green) examine parts of the pyharp tree (grey)", ha="center", fontsize=fs.SMALL_PT)
    ax.set_xlim(-1.6, 11.2)
    ax.set_ylim(-0.5, 1.8)
    return fig
