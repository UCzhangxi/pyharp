"""Chapter map of the report along pyharp's band and column pipeline (chapter 1, opening).

Cartoon; no data. The pipeline follows `RadiationImpl::forward` (src/radiation/radiation.cpp) and
`RadiationBandImpl::forward` (src/radiation/radiation_band.cpp) at the pin of code_pin.yml: opacity modules, the
assembly of the solver input, the solver (DISORT through pydisort, or Toon), the sum over spectral points, and the sum
over bands. Each box names the chapter that documents the step; the figure states no chapter's status, so it stays
true as chapters are written. The caption carries the chapter references.
"""
from matplotlib.patches import FancyBboxPatch

from pyharp_report import figstyle as fs


def _box(ax, x, y, w, text, color, ls="-", h=0.72):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.04", fc=fs.WHITE, ec=color,
                                lw=1.4, ls=ls))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs.SMALL_PT)


def _arrow(ax, p0, p1, color=fs.BLACK, ls="-"):
    ax.annotate("", xy=p1, xytext=p0, arrowprops=dict(arrowstyle="-|>", color=color, lw=1.0, ls=ls))


def make_fig():
    fig, ax = fs.new_figure("double", 2.8)
    fs.cartoon(ax)
    xs = [-6.0, -3.0, 0.0, 3.0, 6.0]
    steps = ["opacities\n(opacity chapter)", "solver input:\n$\\Delta\\tau$, $\\omega$, moments\n(assembly chapter)",
             "solver\nDISORT or Toon\n(two chapters)", "sum over\nspectral points\n(assembly chapter)",
             "sum over bands,\nnet flux\n(API chapter)"]
    for x, t in zip(xs, steps):
        _box(ax, x, 1.2, 2.7, t, fs.GREEN, h=1.2)
    for a, b in zip(xs[:-1], xs[1:]):
        _arrow(ax, (a + 1.42, 1.2), (b - 1.42, 1.2))
    _box(ax, 0.0, 3.25, 4.6, "two-stream theory: equations, closures,\ndelta scaling, conservation", fs.GREEN, h=0.9)
    _arrow(ax, (0.0, 2.75), (0.0, 1.85))
    ax.plot([-7.35, -7.35, 7.35, 7.35], [0.42, 0.25, 0.25, 0.42], color=fs.BLACK, lw=0.8)
    ax.text(0.0, 0.0, "across the whole pipeline", ha="center", va="center", fontsize=fs.SMALL_PT)
    for x, t in [(-4.6, "solver accuracy"), (0.0, "GPU and batching"), (4.6, "tests, CI, bindings")]:
        _box(ax, x, -0.75, 3.4, t, fs.GREEN)
    ax.set_xlim(-7.5, 7.5)
    ax.set_ylim(-1.3, 3.85)
    return fig
