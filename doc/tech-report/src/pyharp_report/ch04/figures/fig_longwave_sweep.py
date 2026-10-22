"""The longwave source-function method of chapter 4 (`_longwave.qmd`): two-stream solve, then angular sweeps.

Cartoon; no data. Mirrors `toon_mckay89_longwave` (src/rtsolver/toon_mckay89_longwave_impl.h) at the pin of
code_pin.yml: a tridiagonal hemispheric-mean solve fixes the source function, then for each of five angles the
intensity is integrated down from the top and up from the surface, and fluxes are the weighted sums.
"""
from pyharp_report import figstyle as fs


def make_fig():
    fig, ax = fs.new_figure("double", 2.4)
    fs.cartoon(ax)
    L = 4
    for n in range(L):
        fs.cell(ax, 0.0, L - 1 - n, 3.0, 1.0, label=f"$n={n + 1}$: $B_{{0n}} + B_{{1n}}\\tau$", fill=True)
    fs.wall_line(ax, (0.0, 0.0), (3.0, 0.0))
    ax.text(1.5, -0.2, "surface", fontsize=fs.SMALL_PT, ha="center", va="top")
    ax.text(-0.1, L + 0.15, "step 1: tridiagonal solve\nfor $k_{1n}, k_{2n}$", fontsize=fs.SMALL_PT, ha="left",
            va="bottom")
    mus = [0.0985, 0.3045, 0.5620, 0.8020, 0.9602]
    for m, mu in enumerate(mus):
        x0 = 4.0 + 0.55 * m
        ax.annotate("", xy=(x0 + 0.15 * (1 - mu), 0.05), xytext=(x0, L - 0.05),
                    arrowprops=dict(arrowstyle="-|>", color=fs.ORANGE, lw=1.0))
        ax.annotate("", xy=(x0 + 3.2, L - 0.05), xytext=(x0 + 3.2 + 0.15 * (1 - mu), 0.05),
                    arrowprops=dict(arrowstyle="-|>", color=fs.GREEN, lw=1.0, ls="--"))
    ax.text(5.1, L + 0.15, "step 2: down,\n5 angles $\\mu_i$", fontsize=fs.SMALL_PT, ha="center", va="bottom",
            color=fs.ORANGE)
    ax.text(8.3, L + 0.15, "step 3: up\nfrom surface", fontsize=fs.SMALL_PT, ha="center", va="bottom",
            color=fs.GREEN)
    ax.text(11.0, L / 2, "$F^{\\pm} = \\sum_i w_i I^{\\pm}(\\mu_i)$\n$\\sum_i w_i = 1/2$", fontsize=fs.SMALL_PT,
            ha="left", va="center")
    ax.set_xlim(-0.3, 14.0)
    ax.set_ylim(-0.6, L + 1.2)
    return fig
