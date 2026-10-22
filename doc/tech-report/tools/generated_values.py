#!/usr/bin/env python3
"""Render-time values of the generated appendices (README, "Generated files and rebasing").

A generated fragment that is committed holds nothing that an edit to one chapter changes in a line another
chapter's edit also changes: no total, no count summed over chapters, no "first used" that is the earliest of
several chapters. Those values are written as `{{< generated <name> <key> >}}` (book/_shortcodes/generated.lua)
and filled in at render from `book/_generated/<name>.json`, which the generator writes in the pre-render step
from the chapters as they are, and which is not committed (book/.gitignore). Two pull requests that edit
different chapters therefore touch different committed lines, and git merges them; the values are current at
every render because they are computed there.

The tools that read the book's sources (render_gate's cross-references, and through it the ratchet) see the
values through `expand`, computed in memory from the same generators, so they count what the reader sees.
"""

from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

SHORTCODE = re.compile(r"\{\{<\s*generated\s+(\S+)\s+(\S+)\s*>\}\}")
_INCLUDE = re.compile(r"^\{\{<\s*include\s+(\S+)\s*>\}\}\s*$", re.M)


def shortcode(name: str, key: str) -> str:
    return f"{{{{< generated {name} {key} >}}}}"


def path(book: Path, name: str) -> Path:
    return book / "_generated" / f"{name}.json"


def write(file: Path, values: dict[str, str]) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(values, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def sync(directory: Path, files: dict[str, str], tool: str, check: bool, orphans: str | None = None) -> int:
    """Write `files` into `directory` (and delete files matching the glob `orphans` that are no longer
    generated), or with `check` compare them: 0 when current, 1 with a diff when not."""
    stale = sorted(p.name for p in directory.glob(orphans)) if orphans and directory.is_dir() else []
    stale = [n for n in stale if n not in files]
    if check:
        bad = 0
        for name, want in files.items():
            have = (directory / name).read_text(encoding="utf-8") if (directory / name).exists() else ""
            if have != want:
                bad += 1
                print("\n".join(list(difflib.unified_diff(have.splitlines(), want.splitlines(), f"committed {name}",
                                                          "sources", lineterm=""))[:60]))
        for name in stale:
            bad += 1
            print(f"{directory / name}: no longer generated; delete it")
        if bad:
            print(f"{tool}: {bad} generated file(s) in {directory} are stale; run python3 tools/{tool}.py",
                  file=sys.stderr)
            return 1
        print(f"{tool}: {len(files)} generated file(s) are current", file=sys.stderr)
        return 0
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        if not (directory / name).exists() or (directory / name).read_text(encoding="utf-8") != text:
            (directory / name).write_text(text, encoding="utf-8")
    for name in stale:
        (directory / name).unlink()
    return 0


def expand(text: str, values: dict[str, dict[str, str]], strict: bool = False) -> str:
    """`text` with every generated shortcode replaced by its value; an unknown one stays as it is unless
    `strict`, which raises KeyError."""
    def sub(m):
        v = values.get(m.group(1), {}).get(m.group(2))
        if v is None:
            if strict:
                raise KeyError(f"{m.group(1)} {m.group(2)}")
            return m.group(0)
        return v
    return SHORTCODE.sub(sub, text)


def inline_includes(text: str, chapters: Path) -> str:
    """`text` with each `{{< include path >}}` line replaced by the file (paths relative to book/chapters, as
    Quarto resolves a nested include against the top-level document)."""
    return _INCLUDE.sub(lambda m: (chapters / m.group(1)).read_text(encoding="utf-8").rstrip("\n"), text)


def computed(book: Path) -> dict[str, dict[str, str]]:
    """The values the render would write, computed in memory from the sources of the tree `book` belongs to."""
    import gen_derivation_index as gd  # noqa: PLC0415  (both import this module's helpers)
    import gen_notation_index as gn  # noqa: PLC0415

    report = book.parent
    stmts = gd.load_statements(report / "tools" / "derivation-statements")
    out = {"appb": gd.outputs(gd.collect(book, stmts, report / "src" / "pyharp_report"))[1]}
    notation = report / "NOTATION.md"
    if notation.exists():
        out["appa"] = gn.outputs(notation.read_text(encoding="utf-8"), book)[1]
    return out
