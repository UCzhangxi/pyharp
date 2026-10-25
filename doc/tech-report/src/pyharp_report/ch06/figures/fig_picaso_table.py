"""ch06 figure: the axes of a pre-mixed correlated-k table and how a layer is looked up (a cartoon; no data).

From PicasoCKImpl::reset and ::forward (src/opacity/picaso_ck.cpp) at the code pin of code_pin.yml: the table is
tabulated on pressure and on the temperature offset from a nominal temperature that depends on pressure; a layer at
(p, T) is placed at (ln p, T - T_nom(p)) and ln kappa is interpolated linearly in both, and in wavenumber.
"""
import numpy as np

from pyharp_report import figstyle as fs


def make_fig():
    fig, ax = fs.new_figure("single", 2.6)
    lnp = np.array([0.0, 1.0, 2.0])
    tnom = np.array([200.0, 250.0, 300.0])
    for off in (-50.0, 0.0, 50.0):
        ax.plot(lnp, tnom + off, color=fs.SKY if off else fs.BLUE, lw=1.0 if off else 1.4,
                ls="-" if off == 0 else "--", marker="o", ms=3)
    for xp in lnp:
        ax.axvline(xp, color=fs.GREY, lw=0.6, ls=":")
    q = (1.35, 228.0)
    tn = np.exp(np.interp(q[0], lnp, np.log(tnom)))
    ax.plot([q[0]], [q[1]], marker="*", ms=9, color=fs.VERMILLION, ls="none")
    ax.annotate("", xy=(q[0], tn), xytext=q, arrowprops=dict(arrowstyle="<->", color=fs.VERMILLION, lw=0.8))
    ax.text(q[0] - 0.06, 0.5 * (q[1] + tn), r"$T - T_{\mathrm{nom}}(p)$", fontsize=fs.SMALL_PT, va="center",
            ha="right", color=fs.VERMILLION)
    ax.text(2.05, 300, r"$T_{\mathrm{nom}}$", fontsize=fs.SMALL_PT, va="center", color=fs.BLUE)
    ax.text(2.05, 350, "+50 K", fontsize=fs.SMALL_PT, va="center", color=fs.SKY)
    ax.text(2.05, 250, "-50 K", fontsize=fs.SMALL_PT, va="center", color=fs.SKY)
    ax.set_xticks(lnp, ["$p_1$", "$p_2$", "$p_3$"])
    ax.set_xlabel(r"pressure grid, uniform in $\ln p$")
    ax.set_ylabel("temperature $T$ [K]")
    ax.set_xlim(-0.15, 2.45)
    return fig
