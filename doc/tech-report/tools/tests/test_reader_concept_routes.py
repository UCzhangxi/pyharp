"""The skeleton has no inherited scientific glossary claims."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import glossary_registry as registry

def test_skeleton_registry_has_no_inherited_claims():
    data = json.loads((registry.REPORT / registry.REGISTRY).read_text())
    assert data == {"version": 1, "entries": []}
    assert registry.registry_problems(registry.REPORT, data) == []
