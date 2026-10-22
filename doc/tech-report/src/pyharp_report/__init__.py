"""Figures and algebra checks for the pyharp Technical Report.

Executable report figures and independent checks.
"""

# Package defaults for every figure, whichever style module a chapter uses (STYLE 10.10): fonts embedded as
# TrueType (Type 42) instead of Type 3, STIX for mathtext, 9 pt serif text. figstyle.apply() sets the rest.
import matplotlib as _mpl

_mpl.rcParams.update({
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "mathtext.fontset": "stix",
    "font.family": "serif",
    "font.serif": ["STIXGeneral", "DejaVu Serif"],
    "font.size": 9,
})
