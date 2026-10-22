#!/bin/bash
# Chapter 10 check: what changes in pydisort's DisortImpl header between the two wheels pyharp may be built against.
# usage: header_diff.sh <env 1.7.1> <env 1.8.13>   (directories made by setup_env.sh)
# Prints [H1] the data members of DisortImpl declared only in one version (diff of the installed
# disort/disort.hpp, restricted to the class) and [H2] the newest pydisort release on PyPI when it ran.
site() { "$1/venv/bin/python" -c 'import pydisort, os; print(os.path.dirname(pydisort.__file__))'; }
A=$(site "$1"); B=$(site "$2")
for e in "$1" "$2"; do "$e/venv/bin/python" -c 'import pydisort; print("[H0] pydisort", pydisort.__version__)'; done
cls() { awk '/^class DisortImpl/,/^};/' "$1/disort/disort.hpp" | grep -E '^\s+[A-Za-z_:<>]+[ *&]+[A-Za-z_]+_?;' | sed 's/^ *//'; }
diff <(cls "$A") <(cls "$B") | grep -E '^[<>]' | sed 's/^</[H1] only in the first:/; s/^>/[H1] only in the second:/'
echo "[H2] newest pydisort on PyPI: $("$1/venv/bin/python" -m pip index versions pydisort 2>/dev/null | head -1)"
