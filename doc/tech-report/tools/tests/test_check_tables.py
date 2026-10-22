"""tools/check_tables.py: pipe tables against STYLE 10.5 and the Code/Tests headers of STYLE 2, per chapter, ratchet.

Each test writes a small .qmd source; nothing is rendered. Run from the report directory:
`python3 -m pytest tools/tests`.
"""

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import check_tables  # noqa: E402

GOOD = """## A scheme {#sec-ch01-a}

### Code

| what | code link | symbol | switch |
|---|---|---|---|
| entry | `f` | `f` | |

: Code map of the scheme. {#tbl-ch01-a-code}

### Tests

| test (ctest name) | what it asserts | tolerance | where the tolerance comes from |
|---|---|---|---|
| `t` | it works | exact | contract |

: Tests of the scheme, with a caption that runs
onto a second line. {#tbl-ch01-a-tests}
"""

BAD = """### Code

| what | code link | symbol |
|---|---|---|
| entry | `f` | `f` |

: Code map. {#tbl-ch02-b-code}

| a second | table |
|---|---|
| in | Code |

### Limits

| 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|
| a | b | c | d | e | f |

```markdown
| inside | a fence |
|---|---|
```
<!--
| inside | a comment |
|---|---|
-->
"""


def kinds(text):
    return sorted(kind for _, kind, _ in check_tables.scan_text(text))


def test_a_scheme_in_the_template_has_no_findings():
    assert kinds(GOOD) == []


def test_each_kind_is_found_once_and_fences_and_comments_are_skipped():
    hits = check_tables.scan_text(BAD)
    assert sorted(k for _, k, _ in hits) == ["caption", "caption", "columns", "extra", "header"]
    assert {line for line, k, _ in hits if k == "columns"} == {15}


def test_chapter_names():
    assert check_tables.chapter_of("book/chapters/06-kinetics/_part.qmd") == "ch06"
    assert check_tables.chapter_of("book/chapters/06-kinetics.qmd") == "ch06"
    assert check_tables.chapter_of("book/chapters/appa-notation/_part.qmd") == "appa"
    assert check_tables.chapter_of("book/chapters/appendices/_appb-derivation-index.qmd") == "appb"


def tree(tmp_path, text):
    q = tmp_path / "book" / "chapters" / "02-demo" / "_b.qmd"
    q.parent.mkdir(parents=True)
    q.write_text(text)
    (tmp_path / "tools").mkdir()
    return tmp_path, tmp_path / "tools" / "table-baseline.json"


def test_the_ratchet_fails_both_ways_and_update_only_lowers(tmp_path):
    root, base = tree(tmp_path, BAD)
    assert check_tables.main(["--report", str(root), "--baseline", str(base), "--update"]) == 0
    assert check_tables.check(root, base)[0] == 0
    data = json.loads(base.read_text())
    assert data["chapters"] == {"ch02": {"caption": 2, "columns": 1, "extra": 1, "header": 1}}
    (root / "book" / "chapters" / "02-demo" / "_b.qmd").write_text(GOOD)  # every table fixed
    status, msgs = check_tables.check(root, base)
    assert status == 1 and all("lower the baseline" in m for m in msgs)
    assert check_tables.main(["--report", str(root), "--baseline", str(base), "--update"]) == 0
    (root / "book" / "chapters" / "02-demo" / "_b.qmd").write_text(BAD)  # the debt comes back
    assert check_tables.check(root, base)[0] == 1
    assert check_tables.main(["--report", str(root), "--baseline", str(base), "--update"]) == 1


def test_the_report_is_at_its_committed_baseline():
    status, msgs = check_tables.check()
    assert status == 0, msgs
