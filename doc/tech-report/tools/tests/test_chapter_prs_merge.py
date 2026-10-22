"""Two pull requests that edit different chapters merge without a conflict (README, "Generated files and rebasing").

On a copy of this report, two branches from the same base each edit one chapter (ch04 and ch05): a labelled
equation in a Derivation layer, written in a NOTATION.md symbol that no chapter uses yet, a given statement for
that equation, and the removal of a change-history phrase that the ratchet counts. Each branch runs the
generators and `ratchet_gate.py update`, as an author does, and commits. `git merge` of the two must be
conflict-free, and the generators and the ratchet on the merged tree must reproduce the committed files exactly.

The statements go where chapter blocks meet: ch04's ends its chapter's
entries and ch05's starts its chapter's, so in one shared statements file the two edits touch the same place,
and in one file per chapter they touch different files.
"""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parent.parent.parent
SYMBOL = r"\Delta_\pm"                       # added to NOTATION.md section 1 of the copy; first used by these edits
PHRASE = "This sentence is now history."     # a ratchet `history` hit (HISTORY_PATTERNS: "is now")


def _run(tree, *cmd, ok=True):
    p = subprocess.run(cmd, cwd=tree, capture_output=True, text=True)
    if ok:
        assert p.returncode == 0, f"{' '.join(map(str, cmd))}\n{p.stdout}\n{p.stderr}"
    return p


def _git(tree, *args, ok=True):
    return _run(tree, "git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args, ok=ok)


def _regenerate(tree):
    """What an author runs before committing a chapter edit."""
    for tool in ("gen_derivation_index.py", "gen_notation_index.py"):
        _run(tree, sys.executable, f"tools/{tool}")
    _run(tree, sys.executable, "tools/ratchet_gate.py", "update")


def _derivation_file(tree, chapter):
    """The first scheme file of `chapter` (e.g. "04") with a Derivation layer."""
    return next(f for f in sorted((tree / "book" / "chapters").glob(f"{chapter}-*/_*.qmd"))
                if re.search(r"^### Derivation\s*$", f.read_text(), re.M))


def _add_statement(tree, chapter, label, text, last):
    """Give `label` a statement, after (or before) the first run of its chapter's entries, in the file the tree
    keeps it in: the chapter's own tools/derivation-statements/chNN.json, or the one shared file of the older
    layout, where that run is followed by the next chapter's entries."""
    split = tree / "tools" / "derivation-statements"
    f = split / f"ch{chapter}.json" if split.is_dir() else tree / "tools" / "derivation-statements.json"
    given = list(json.loads(f.read_text(encoding="utf-8")).items()) if f.exists() else []
    own = [i for i, (k, _) in enumerate(given) if k.startswith(f"eq-ch{chapter}-")]
    at = own[0] if own else len(given)
    while last and own and at in own:
        at += 1
    given.insert(at, (label, text))
    f.write_text(json.dumps(dict(given), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _copy_report(dst):
    skip = shutil.ignore_patterns("_book", "_freeze", ".quarto", "_generated", "__pycache__", "*.pyc", "tests")
    for d in ("book", "tools", "src/pyharp_report", "reviews"):
        shutil.copytree(REPORT / d, dst / d, ignore=skip)
    for f in ("NOTATION.md", "code_pin.yml"):
        shutil.copy2(REPORT / f, dst / f)


def _scaffold_schemes(tree):
    """Give the copy what the edits need when the report does not have it yet: SYMBOL in NOTATION.md section 1, and
    in ch04 and ch05 a scheme file with a Derivation layer, included from the chapter file."""
    notation = tree / "NOTATION.md"
    lines = notation.read_text().split("\n")
    if SYMBOL not in notation.read_text():
        sec = next(i for i, l in enumerate(lines) if l.startswith("## 1. "))
        sep = next(i for i in range(sec, len(lines)) if lines[i].startswith("|---"))
        ncol = lines[sep].count("|") - 1
        lines.insert(sep + 1, "| $" + SYMBOL + "$ | the merge test's spacing [m] |" + " |" * (ncol - 2))
        notation.write_text("\n".join(lines))
    for ch in ("04", "05"):
        chapters = tree / "book" / "chapters"
        if any(re.search(r"^### Derivation\s*$", f.read_text(), re.M) for f in chapters.glob(f"{ch}-*/_*.qmd")):
            continue
        parent = next(chapters.glob(f"{ch}-*.qmd"))
        (chapters / f"{ch}-mergetest").mkdir()
        (chapters / f"{ch}-mergetest" / "_scheme.qmd").write_text(
            f"## Merge test scheme {{#sec-ch{ch}-mergetest}}\n\n### Derivation\n\nThe layer the test edits.\n")
        parent.write_text(parent.read_text() + f"\n{{{{< include {ch}-mergetest/_scheme.qmd >}}}}\n")


def test_prs_on_different_chapters_merge_and_stay_current(tmp_path):
    tree = tmp_path / "report"
    _copy_report(tree)
    _scaffold_schemes(tree)
    _git(tree, "init", "-q", "-b", "base")
    # the base: a history phrase in each chapter, counted into a fresh baseline
    for ch in ("04", "05"):
        f = _derivation_file(tree, ch)
        f.write_text(f.read_text().rstrip("\n") + f"\n\n{PHRASE}\n")
    (tree / "tools" / "ratchet-baseline.json").unlink()
    _regenerate(tree)
    _git(tree, "add", "-A")
    _git(tree, "commit", "-q", "-m", "base")

    for ch in ("04", "05"):
        _git(tree, "checkout", "-q", "-b", f"ch{ch}", "base")
        f = _derivation_file(tree, ch)
        added = f"\nThe merge test adds the stencil spacing relation\n\n$$\n{SYMBOL} = h_i\n$$ {{#eq-ch{ch}-mergetest}}\n"
        text = re.sub(r"^### Derivation\s*\n", lambda m: m.group(0) + added, f.read_text(), count=1, flags=re.M)
        f.write_text(text.replace(f"\n\n{PHRASE}\n", "\n"))
        _add_statement(tree, ch, f"eq-ch{ch}-mergetest", f"The merge test's statement for chapter {ch}.", ch == "04")
        _regenerate(tree)
        _git(tree, "add", "-A")
        _git(tree, "commit", "-q", "-m", f"ch{ch} edit")

    merge = _git(tree, "merge", "--no-edit", "-q", "ch04", ok=False)
    conflicts = _git(tree, "diff", "--name-only", "--diff-filter=U").stdout.split()
    assert merge.returncode == 0 and not conflicts, f"the chapter PRs conflict in {conflicts}\n{merge.stdout}"

    _regenerate(tree)
    assert _git(tree, "status", "--porcelain").stdout == "", "the merged tree's generated files are stale"
    for tool in ("gen_derivation_index.py", "gen_notation_index.py"):
        _run(tree, sys.executable, f"tools/{tool}", "--check")
    _run(tree, sys.executable, "tools/ratchet_gate.py", "check")
    # both equations and the symbol's first use reach the reader (values the pre-render step writes)
    appb = json.loads((tree / "book/_generated/appb.json").read_text())
    appa = json.loads((tree / "book/_generated/appa.json").read_text())
    assert appb["ch04.equations"] != "0" and appb["ch05.equations"] != "0"
    for ch in ("04", "05"):
        rows = (tree / f"book/chapters/appendices/_appb-ch{ch}.qmd").read_text()
        assert f"@eq-ch{ch}-mergetest" in rows and f"The merge test's statement for chapter {ch}." in rows
    assert appa["first-" + hashlib.sha1(SYMBOL.encode()).hexdigest()[:12]].startswith("@sec-ch04-")
