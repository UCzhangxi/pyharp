"""Where the report's numbers come from (chapter 10, `_verification-index.qmd`).

Cartoon; no data. pyharp's tests (tests/, run by ctest and the CI workflow of the pin of code_pin.yml) and the
report's own checks (src/pyharp_report/chNN/checks/ and derivation-checks/chNN/) with their committed outputs.
"""
from matplotlib.patches import FancyBboxPatch

from pyharp_report import figstyle as fs


def _box(ax, x, y, text, color, w=2.6):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - 0.3), w, 0.6, boxstyle="round,pad=0.04", fc=fs.WHITE, ec=color,
                                lw=1.3))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs.SMALL_PT)


def _arrow(ax, p0, p1, color=fs.BLACK):
    ax.annotate("", xy=p1, xytext=p0, arrowprops=dict(arrowstyle="-|>", color=color, lw=1.0))


def make_fig():
    fig, ax = fs.new_figure("double", 2.4)
    fs.cartoon(ax)
    _box(ax, 0.0, 2.0, "pyharp tests (tests/)", fs.BLACK)
    _box(ax, 0.0, 1.0, "ctest, pytest", fs.BLACK)
    _box(ax, 0.0, 0.0, "CI job build-and-test", fs.BLACK)
    _arrow(ax, (0.0, 1.68), (0.0, 1.32))
    _arrow(ax, (0.0, 0.68), (0.0, 0.32))
    _box(ax, 4.2, 2.0, "derivation checks\n(numpy, sympy)", fs.GREEN)
    _box(ax, 7.4, 2.0, "checks that run pyharp", fs.GREEN)
    _box(ax, 5.8, 1.0, "committed .out files", fs.ORANGE)
    _box(ax, 5.8, 0.0, "Tests layers of the chapters", fs.BLUE, w=3.0)
    _arrow(ax, (4.4, 1.68), (5.4, 1.32), fs.GREEN)
    _arrow(ax, (7.2, 1.68), (6.2, 1.32), fs.GREEN)
    _arrow(ax, (5.8, 0.68), (5.8, 0.32), fs.ORANGE)
    _arrow(ax, (1.3, 0.0), (4.5, 0.0), fs.GREY)
    ax.text(2.9, 0.12, "test names cited", fontsize=fs.SMALL_PT, ha="center", va="bottom", color=fs.GREY)
    ax.set_xlim(-1.5, 9.0)
    ax.set_ylim(-0.5, 2.5)
    return fig
