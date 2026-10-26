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
    rows=json.loads(DATA.read_text())['spectral']
    fs.apply()
    fig = fs.Figure(figsize=(fs.DOUBLE, 2.8), layout='constrained')
    ax = fig.subplots()
    for mode,color,marker in [('weight',fs.BLUE,'o'),('density',fs.GREEN,'^'),('wavenumber',fs.VERMILLION,'s')]:
        r=[x for x in rows if x['mode']==mode]
        ax.loglog([x['dnu'] for x in r],[x['ratio'] for x in r],color=color,marker=marker,label=mode)
    ax.axhline(1,color=fs.BLACK,linestyle='--')
    ax.set_xlabel(r'Band width [cm$^{-1}$]'); ax.set_ylabel('Flux / reference [-]')
    ax.legend()
    return fig
