"""Where the quantities of one band live: the column grid and the tensor shapes of the pipeline (chapter 1).

Cartoon; no data. Shapes as `RadiationBandImpl::forward` (src/radiation/radiation_band.cpp) and
`RadiationImpl::forward` (src/radiation/radiation.cpp) hold them at the pin of code_pin.yml: the opacity output and
the solver input `prop` are (nwave, ncol, nlyr, nprop) per layer; the solver output `spectrum` is (nwave, ncol, nlev,
channels) per level; the band output is (ncol, nlev, 4) after the sum over spectral points. Levels are numbered from
the surface (level 0) to the top (level nlyr).
"""
from pyharp_report import figstyle as fs


def make_fig():
    fig, ax = fs.new_figure("double", 2.3)
    ax.set_axis_off()                                   # a cartoon panel; no equal aspect, the table is in axes units
    nlyr = 4
    for i in range(nlyr):
        fs.cell(ax, 1.0, i * 0.6, 1.4, 0.6, label=f"layer {i}", fill=True)
    for k in range(nlyr + 1):
        ax.plot([2.4, 2.7], [k * 0.6, k * 0.6], color=fs.ORANGE, lw=1.4)
        ax.text(2.8, k * 0.6, f"level {k}" + (" (surface)" if k == 0 else " (top)" if k == nlyr else ""),
                va="center", fontsize=fs.SMALL_PT)
    ax.text(0.85, 1.2, "$\\Delta z$, $\\Delta\\tau$, $\\omega$,\nmoments\nper layer", ha="right", va="center",
            fontsize=fs.SMALL_PT, color=fs.SKY)
    ax.set_xlim(-0.6, 13.0)
    ax.set_ylim(-0.3, 2.7)
    rows = [("opacity output", "(nwave, ncol, nlyr, nprop)", fs.SKY),
            ("solver input prop", "(nwave, ncol, nlyr, nprop)", fs.SKY),
            ("solver output spectrum", "(nwave, ncol, nlev, 2 or 4)", fs.ORANGE),
            ("band flux", "(ncol, nlev, 4)", fs.ORANGE),
            ("Radiation.forward", "(ncol, nlev), (ncol), (ncol)", fs.ORANGE)]
    for r, (name, shape, color) in enumerate(rows):
        y = 0.86 - r * 0.17
        ax.text(0.42, y, name, ha="left", va="center", fontsize=fs.SMALL_PT, color=color, transform=ax.transAxes)
        ax.text(0.68, y, shape, ha="left", va="center", fontsize=fs.SMALL_PT, family=fs.MONO, transform=ax.transAxes)
    return fig
