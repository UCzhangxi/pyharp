"""Regressions for the consolidated appendix corrections: the notation index prints the current code pin."""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gen_notation_index as n


def test_notation_generator_uses_current_pin():
    pin = re.search(r"^sha:\s*([0-9a-f]{40})", (n.REPORT / "code_pin.yml").read_text(), re.M)[1]
    text = n.fragment(n.NOTATION.read_text(), n.BOOK)
    assert pin in text
    assert set(re.findall(r"\b[0-9a-f]{40}\b", text)) == {pin}
