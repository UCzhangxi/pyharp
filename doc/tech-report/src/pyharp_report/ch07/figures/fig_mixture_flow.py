"""Chapter 7 figure from pyharp f34506f9d14ee7b1f2e1222775baa5093ae6967f.
Historical data: ../data/historical.json, selected from committed native records;
no solver is run. See derivation-checks/ch07/provenance.json for runtime limits.
"""
import json
from pathlib import Path
import numpy as np
from pyharp_report import figstyle as fs

DATA = Path(__file__).resolve().parents[1] / 'data' / 'historical.json'

def make_fig():
    fs.apply()
    fig = fs.Figure(figsize=(fs.DOUBLE, 2.1), layout='constrained')
    ax = fig.subplots()
    ax.set_axis_off()
    labels = ['Source coefficients\n$k_a,\\omega_a,\\chi_{a,l}$', 'Add numerators\n$k,s,\\sum s_a\\chi_{a,l}$', 'Normalize; scale\n$\\omega,\\chi_l,\\Delta\\tau$', 'Cap albedo\ntransfer solver']
    for i, label in enumerate(labels):
        x = 0.12 + 0.25*i
        ax.text(x, .5, label, ha='center', va='center', transform=ax.transAxes,
                bbox=dict(boxstyle='round', facecolor=fs.CELL_FILL if i==0 else fs.WHITE,
                          edgecolor=[fs.BLUE,fs.GREEN,fs.GREEN,fs.ORANGE][i]))
        if i<3: ax.annotate('', xy=(x+.14,.5), xytext=(x+.10,.5), xycoords='axes fraction',
                            arrowprops=dict(arrowstyle='->', color=fs.BLACK))
    return fig
