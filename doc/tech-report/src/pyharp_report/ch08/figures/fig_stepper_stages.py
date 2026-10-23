"""The three stages of one rk3 step of the column model (a cartoon, no data).

Each stage forms u^(s) = w0 u^n + w1 u^(s-1) + w2 dt L(u^(s-1)) with the weights of IntegratorImpl at the pin of
code_pin.yml; L is the temperature tendency RadiationModelImpl::forward computes from the radiation and diffusion
fluxes. Code facts are cited in the chapter text.
"""
from pyharp_report import figstyle as fs
from pyharp_report.ch08.figures._boxes import arrow, box


def make_fig():
    fig, ax = fs.new_figure("double", 2.2)
    fs.cartoon(ax)
    box(ax, 0.9, 1.0, "$T^n$, $T_s^n$\n(stage registers)", w=1.7)
    box(ax, 3.4, 1.0, "stage 0\n(0, 1, 1)", fs.GREEN, w=1.5)
    box(ax, 5.7, 1.0, "stage 1\n(3/4, 1/4, 1/4)", fs.GREEN, w=1.5)
    box(ax, 8.0, 1.0, "stage 2\n(1/3, 2/3, 2/3)", fs.GREEN, w=1.5)
    arrow(ax, (1.75, 1.0), (2.65, 1.0))
    arrow(ax, (4.15, 1.0), (4.95, 1.0))
    arrow(ax, (6.45, 1.0), (7.25, 1.0))
    arrow(ax, (8.75, 1.0), (9.6, 1.0), "$T^{n+1}$", dy=0.3)
    for x in (3.4, 5.7, 8.0):
        ax.text(x, 0.25, "radiation, $\\Delta z$,\ndiffusion, clamp", ha="center", va="center",
                fontsize=fs.SMALL_PT)
    ax.text(5.7, 1.85, "weights $(w_0, w_1, w_2)$: $u^{(s)} = w_0 u^n + w_1 u^{(s-1)} + w_2\\,\\Delta t\\,L(u^{(s-1)})$",
            ha="center", va="center", fontsize=fs.SMALL_PT)
    ax.set_xlim(0.0, 10.2)
    ax.set_ylim(-0.1, 2.15)
    return fig
