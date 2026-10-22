"""Block structure of the boundary-value system the discrete-ordinate solution solves (a cartoon, no data).

For L layers and 2N streams the unknowns are the 2N constants of integration of every layer; the rows are the N
top-boundary conditions, 2N continuity conditions at each of the L - 1 interfaces and the N bottom-boundary
conditions. Drawn for L = 3, N = 2; every nonzero block lies within 3N - 1 diagonals of the main one, so the
system is banded with 6N - 1 diagonals (Stamnes et al. 1988, p. 2506), solved by cdisort's c_sgbco/c_sgbsl.
"""
from matplotlib.patches import Rectangle

from pyharp_report import figstyle as fs


def make_fig(L=3, N=2):
    fig, ax = fs.new_figure("single", 2.9)
    fs.cartoon(ax)
    n = 2 * N * L
    ax.add_patch(Rectangle((0, 0), n, n, fc=fs.WHITE, ec=fs.BLACK, lw=0.8))
    rows = [("top", 0, N, 0)]                               # (label, first row, nrows, first layer)
    for p in range(L - 1):
        rows.append((f"interface {p + 1}", N + 2 * N * p, 2 * N, p))
    rows.append(("bottom", n - N, N, L - 1))
    for label, r0, nr, lay in rows:
        width = 2 * N if label in ("top", "bottom") else 4 * N
        ax.add_patch(Rectangle((2 * N * lay, n - r0 - nr), width, nr, fc=fs.SKY if label not in ("top", "bottom")
                               else fs.ORANGE, ec=fs.BLACK, lw=0.6, hatch=None if label not in ("top", "bottom")
                               else "//"))
        ax.text(n + 0.3, n - r0 - 0.5 * nr, label, ha="left", va="center", fontsize=fs.SMALL_PT)
    for p in range(L):
        ax.text(2 * N * p + N, n + 0.3, f"layer {p + 1}", ha="center", va="bottom", fontsize=fs.SMALL_PT)
    ax.text(0.5 * n, -0.4, "constants of integration (2N per layer)", ha="center", va="top", fontsize=fs.SMALL_PT)
    ax.set_xlim(-0.3, n + 4.2)
    ax.set_ylim(-1.4, n + 1.2)
    return fig
