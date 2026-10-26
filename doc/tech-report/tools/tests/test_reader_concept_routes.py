"""Every concept claim in the registry is one the book itself makes.

The skeleton shipped with an empty registry and this file asserted that emptiness, so that no claim could be
inherited from outside the book. Chapter 7 is the first chapter to show a YAML block, and STYLE.md N4 makes the
registry the single source for its keys' first-use notes and the glossary appendix, so the registry is now
populated by the chapters. The emptiness assertion is retired; what guards against an inherited claim is that
every entry must resolve to a defining section of this book, which is what `registry_problems` checks.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import glossary_registry as registry

def test_every_registry_claim_resolves_in_the_book():
    data = json.loads((registry.REPORT / registry.REGISTRY).read_text())
    assert data["version"] == 1
    assert isinstance(data["entries"], list)
    assert registry.registry_problems(registry.REPORT, data) == []
