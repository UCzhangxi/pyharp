"""Where Radiation.forward puts its outputs on a column of nlyr = 4 layers (a cartoon, no data).

Levels q = 0 (surface) to 4 (top) carry channels 0 and 1 of every band; channels 2 and 3 are copies of them for a
DISORT band and layer-midpoint values for a Toon band (zero at q = 0). Code facts: RadiationImpl::forward and
flux_utils.cpp at the pin of code_pin.yml, and ch08_radiation.py [C5].
"""
from pyharp_report import figstyle as fs

H = 0.55


def make_fig():
    fig, ax = fs.new_figure("double", 2.6)
    fs.cartoon(ax)
    for k in range(4):
        fs.cell(ax, 0.0, H * k, w=1.6, h=H, fill=True)
        ax.text(0.8, H * (k + 0.5), f"layer {k}", ha="center", va="center", fontsize=fs.SMALL_PT)
        fs.cell_marker(ax, 3.2, H * (k + 0.5))
    for q in range(5):
        ax.plot([0.0, 1.6], [H * q, H * q], color=fs.BLACK, lw=1.0)
        fs.face_marker(ax, 1.95, H * q)
        ax.text(-0.15, H * q, f"q = {q}", ha="right", va="center", fontsize=fs.SMALL_PT)
    ax.text(1.95, 4 * H + 0.3, "levels:\nchannels 0, 1", ha="center", va="bottom", fontsize=fs.SMALL_PT)
    ax.text(3.3, 4 * H + 0.3, "Toon\nmidpoints", ha="center", va="bottom", fontsize=fs.SMALL_PT)
    notes = ["net flux $F^{\\mathrm{net}}_q = \\sum_b (F^{\\uparrow}_{b,q} - F^{\\downarrow}_{b,q})$, q = 0 ... 4",
             "surface output: $\\sum_b F^{\\downarrow}_{b,0}$; top output: $\\sum_b F^{\\uparrow}_{b,4}$",
             "net_flux_midpt, entry q: DISORT bands add level q,",
             "Toon bands add the midpoint of layer q - 1 (nothing at q = 0)"]
    for i, t in enumerate(notes):
        ax.text(4.1, 2.15 - 0.55 * i, t, ha="left", va="center", fontsize=fs.SMALL_PT)
    ax.set_xlim(-1.0, 10.6)
    ax.set_ylim(-0.3, 4 * H + 1.0)
    return fig
