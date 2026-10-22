"""The layered shortwave two-stream system of chapter 4 (`_shortwave.qmd`): column, unknowns, tridiagonal band.

Cartoon; no data. Mirrors `toon_mckay89_shortwave` (src/rtsolver/toon_mckay89_shortwave_impl.h) at the pin of
code_pin.yml: layers n = 1..L counted from the top, two unknowns per layer, rows ordered (top BC, 2(L-1) interface
rows, bottom BC), pyharp's array index 0 at the bottom.
"""
from matplotlib.patches import Rectangle

from pyharp_report import figstyle as fs


def make_fig():
    fig, (ax, bx) = fs.new_figure("double", 2.7, 1, 2)
    fs.cartoon(ax)
    L = 4
    for n in range(L):
        y = L - 1 - n
        fs.cell(ax, 0.0, y, 2.0, 1.0, label=f"layer $n={n + 1}$", fill=True)
        ax.text(2.15, y + 0.5, f"$k_{{1,{n + 1}}},\\,k_{{2,{n + 1}}}$", fontsize=fs.SMALL_PT, va="center")
        ax.text(-0.15, y + 0.5, f"array {L - 1 - n}", fontsize=fs.SMALL_PT, va="center", ha="right",
                family=fs.MONO)
    fs.wall_line(ax, (0.0, 0.0), (2.0, 0.0))
    ax.text(1.0, -0.25, "surface, albedo $A_s$", fontsize=fs.SMALL_PT, ha="center", va="top")
    ax.text(0.75, L + 0.1, "top: no diffuse input", fontsize=fs.SMALL_PT, ha="center", va="bottom")
    ax.annotate("", xy=(1.75, 0.05), xytext=(1.95, L + 0.0),
                arrowprops=dict(arrowstyle="-|>", color=fs.ORANGE, lw=1.2))
    ax.text(2.2, L + 0.1, "$F_{\\mathrm{dir}}$", color=fs.ORANGE, fontsize=fs.SMALL_PT, va="bottom")
    ax.set_xlim(-1.3, 3.4)
    ax.set_ylim(-0.7, L + 0.5)

    fs.cartoon(bx)
    n = 2 * L
    for i in range(n):
        for j in range(n):
            on = abs(i - j) <= 1
            bx.add_patch(Rectangle((j, n - 1 - i), 1, 1, fc=fs.GREEN if on else fs.WHITE, ec=fs.GREY, lw=0.4,
                                   alpha=0.8 if on else 1.0))
    bx.text(-0.2, n - 0.5, "top BC", fontsize=fs.SMALL_PT, ha="right", va="center")
    bx.text(-0.2, 0.5, "surface BC", fontsize=fs.SMALL_PT, ha="right", va="center")
    bx.text(-0.2, n / 2, "interface\nrows", fontsize=fs.SMALL_PT, ha="right", va="center")
    bx.text(n / 2, -0.4, f"unknowns $Y_l$, $l = 1..2L$ ($L = {L}$)", fontsize=fs.SMALL_PT, ha="center", va="top")
    bx.set_xlim(-3.2, n + 0.3)
    bx.set_ylim(-1.3, n + 0.3)
    fs.panel_labels([ax, bx])
    return fig
