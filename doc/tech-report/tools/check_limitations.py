#!/usr/bin/env python3
"""N9 warning lint: included prose preflight and rendered PDF evidence.

Warnings never change the build verdict. The phrase list is deliberately data;
this is a deferral detector, not a check of the scientific completeness of a note.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

from check_reader_hygiene import sources

DATA = Path(__file__).with_name("limitation-phrases.json")


def findings(text, source=True, data=DATA):
    """Return (line, phrase) warnings, preserving source line numbers."""
    if source:
        # Ignore non-reader comments and fenced examples, preserving newlines.
        blank = lambda m: re.sub(r"[^\n]", " ", m.group())
        text = re.sub(r"<!--.*?-->", blank, text, flags=re.S)
        text = re.sub(r"(?m)^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1\s*$",
                      blank, text, flags=re.S)
    phrases = json.loads(data.read_text())["phrases"]
    result = []
    for paragraph in re.finditer(r"\S.*?(?=\n\s*\n|\Z)", text, re.S):
        value = paragraph.group()
        # A structured note can explain why something is beyond scope. Do not
        # exempt arbitrary links or an unrelated note later in the paragraph.
        lead = re.sub(r"^\s*(?:>\s*)*(?:(?:[-*+]|\d+[.)])\s+)?", "",
                      value.replace("**", ""))
        if re.match(r"not provided:\s*\S", lead, re.I):
            continue
        for phrase in phrases:
            pattern = r"\b" + r"\s+".join(map(re.escape, phrase.split())) + r"\b"
            for match in re.finditer(pattern, value, re.I):
                # A task question may precede its structured limitation note.
                # Only phrases after that marker belong to the note.
                prefix = value[:match.start()].replace("**", "")
                if re.search(r"\bnot provided:\s*\S", prefix, re.I):
                    continue
                line = text.count("\n", 0, paragraph.start() + match.start()) + 1
                result.append((line, phrase))
    return sorted(result)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--book", type=Path)
    group.add_argument("--pdf", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.book:
            units = [(str(p.relative_to(args.book.resolve())), p.read_text())
                     for p in sources(args.book)]
        else:
            text = subprocess.run(["pdftotext", "-layout", str(args.pdf), "-"],
                                  check=True, capture_output=True, text=True).stdout
            units = [(f"page {i}", t) for i, t in enumerate(text.split("\f"), 1)]
        count = 0
        for name, text in units:
            for line, phrase in findings(text, source=bool(args.book)):
                print(f"WARNING N9 {name}:{line}: {phrase}; use answered at <anchor> / not provided: <reason>")
                count += 1
        print(f"[N9 limitation lint] {count} warning(s); {'source preflight' if args.book else 'rendered PDF'}; advisory only")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"WARNING N9 lint unavailable: {exc}; advisory only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
