# pyharp technical report

This skeleton ports the report tools and STYLE rules from the verified report infrastructure source. Scientific chapter content remains pending.

Run from this directory:

```sh
python -m pytest -q tools/tests
python tools/check_citations.py book OUTLINE.md
python tools/code_anchors.py check
python tools/render_gate.py book --release
python tools/ratchet_gate.py check
```

Set up a fresh machine with one command, which installs Quarto 1.10.19, TinyTeX (LuaLaTeX, its packages from a dated TeX Live snapshot), Universal Ctags 6.2.1 and the Python packages CI installs (the local `src` package, Jupyter, pytest, PyYAML), each download checked against the sha256 in `tools/env-pins.json`, all under `.report-env/` and nothing system-wide:

```sh
bash setup.sh
source .report-env/activate
python3 tools/render_gate.py book/ --release
```

Host prerequisites: curl, tar, make, git, a C compiler, Python 3.11 to 3.13, and `pdftotext` (poppler) for the rendered-output tests.

Each `derivation-checks/chNN_run.sh` regenerates its chapter's outputs in place and then compares them with the committed ones (`tools/compare_outputs.py`): version, host, timing and date lines are normalised, every other line must match, and the script prints `chNN: REPRODUCED` (exit 0) or `chNN: NOT REPRODUCED` with the diff (exit 1).

Code shortcodes accept `repo=pyharp` (default) or `repo=pydisort`, using the full pins in `code_pin.yml`. For example `{{< code src/disort.cpp repo=pydisort >}}`. Symbols and overloads use the same resolver for both repositories. Cache locations can be set with `PYHARP_REPORT_CACHE` and `CHECK_CITATIONS_CACHE`.

Generated report PDFs and HTML are CI artifacts, never source files. Contributor assignments are omitted; scholarly attribution remains in the bibliography. The authoritative defect titles are still required; see DEFECTS.md.
