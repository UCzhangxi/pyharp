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

Install the local `src` package, Jupyter, pytest and PyYAML in a workspace environment. Rendering needs Quarto 1.10.19, LuaLaTeX and Universal Ctags 6.2.1.

Code shortcodes accept `repo=pyharp` (default) or `repo=pydisort`, using the full pins in `code_pin.yml`. For example `{{< code src/disort.cpp repo=pydisort >}}`. Symbols and overloads use the same resolver for both repositories. Cache locations can be set with `PYHARP_REPORT_CACHE` and `CHECK_CITATIONS_CACHE`.

Generated report PDFs and HTML are CI artifacts, never source files. Contributor assignments are omitted; scholarly attribution remains in the bibliography. The authoritative defect titles are still required; see DEFECTS.md.
