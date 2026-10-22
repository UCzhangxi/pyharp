#!/usr/bin/env python3
"""Put each field of an "At a glance" box on its own paragraph (STYLE 2).

Inside every `::: {.callout-note title="At a glance"}` block, a blank line is inserted before each line that starts
with a bold field label (`**Purpose.**`, `**Data.**`, `**Guarantee / limits.**`, any `**Word(s).**`), so the
fields render one per paragraph instead of running together. Nothing else changes: no rewording, no other line
moves. A label directly after the opening fence needs no blank line. Fenced code inside a box and nested divs are
skipped over, labels outside an At-a-glance box are left alone, and a run on fixed text changes nothing.

    python3 tools/fix_glance_boxes.py                # every .qmd under book/
    python3 tools/fix_glance_boxes.py FILE.qmd ...   # the files given

`tools/check_glance_boxes.py` is the gate that fails on a box this script would change.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OPEN = re.compile(r'^\s*(:{3,})\s*\{[^}]*\.callout-note\b[^}]*title="At a glance"[^}]*\}\s*$')
DIV = re.compile(r"^\s*(:{3,})(.*)$")
CODE = re.compile(r"^\s*(`{3,}|~{3,})")
LABEL = re.compile(r"^\*\*[^*\n]+?\.\*\*")


def label_lines(lines: list[str]) -> list[tuple[int, bool]]:
    """(index, needs a blank line) for every field-label line inside an At-a-glance box."""
    out = []
    i = 0
    while i < len(lines):
        if not OPEN.match(lines[i]):
            i += 1
            continue
        depth, fence, j = 1, None, i + 1
        while j < len(lines):
            line = lines[j]
            c = CODE.match(line)
            if fence:
                if c and c.group(1)[0] == fence[0] and len(c.group(1)) >= len(fence) and not line.strip()[len(c.group(1)):].strip():
                    fence = None
            elif c:
                fence = c.group(1)
            else:
                d = DIV.match(line)
                if d:
                    if d.group(2).strip():
                        depth += 1
                    else:
                        depth -= 1
                        if depth == 0:
                            break
                elif LABEL.match(line):
                    out.append((j, j - 1 != i and lines[j - 1].strip() != ""))
            j += 1
        i = j + 1
    return out


def fix_text(text: str) -> str:
    lines = text.split("\n")
    for j, needs in reversed(label_lines(lines)):
        if needs:
            lines.insert(j, "")
    return "\n".join(lines)


def targets(argv: list[str]) -> list[pathlib.Path]:
    return [pathlib.Path(a) for a in argv] if argv else sorted((ROOT / "book").rglob("*.qmd"))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    files = boxes = inserted = 0
    for path in targets(argv):
        text = path.read_text()
        new = fix_text(text)
        boxes += sum(1 for line in text.split("\n") if OPEN.match(line))
        if new != text:
            path.write_text(new)
            files += 1
            inserted += new.count("\n") - text.count("\n")
    print(f"fix_glance_boxes: {inserted} blank lines inserted in {files} files ({boxes} At-a-glance boxes read)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
