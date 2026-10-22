"""Frozen bank coverage: navigation repair must not lose or rewrite questions."""
import json
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from pathlib import Path
import gen_reader_tasks as reader
import gen_task_map as bank


def test_frozen_reader_inventory_is_fully_routed():
    inventory = json.loads((bank.DATA.parent / 'reader-navigation-inventory.json').read_text())
    original = inventory['questions']
    assert original == []
    assert not any(q['excluded'] for q in original)
    assert inventory['followup_ids'] == []
    assert sum(not q['excluded'] for q in original) == 0
    tasks = bank.load(bank.DATA.read_text())['tasks']
    assert len(tasks) == len(original)
    by_id = {t['original_id']: t for t in tasks}
    for q in original:
        t = by_id[q['id']]
        assert t['question'] == q['question']
        assert t['lookup_grade'] == q['frozen_grade']
        assert t['paired_eligible'] == ('no' if q['excluded'] else 'yes')
        assert t['dest'] in bank.labels(bank.BOOK)
    rows = reader.load(reader.DATA.read_text())
    assert len(rows) == len(original)
    assert {r['sources'] for r in rows} == {q['id'] for q in original}
    assert set(inventory['followup_ids']) <= {r['sources'] for r in rows}
    assert reader.problems(rows, bank.labels(bank.BOOK), bank.BOOK, reader.bank_records(reader.REPORT)) == []
