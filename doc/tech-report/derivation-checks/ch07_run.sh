#!/bin/bash
# Regenerate every chapter 7 output, writing the outputs next to the script, and compare them with the
# committed ones.
# usage: ch07_run.sh [PYTHON]
#   PYTHON  the interpreter to use (default: python3). Chapter 7 needs Python 3.10 or later and nothing
#           outside the standard library for the record audit; the figures also need matplotlib.
# Writes: ch07_evidence_check.out, and draws the chapter's figures with tools/render_figures.py --chapters ch07.
# Runs on CPU (CUDA_VISIBLE_DEVICES is emptied); the audit runs from a fresh temporary directory.
#
# The audit reads the stored measurements of ch07/assembly and ch07/spectral; it loads no solver and starts no
# native run, so its output carries no version, host, timing or date line and is compared verbatim. "REPRODUCED"
# means the regenerated output is byte-identical to the committed one, so every recorded check result -- the
# eleven passing Planck assertions and the four recorded failures of [C4] alike -- came back unchanged.
set -u
D=$(cd "$(dirname "$0")" && pwd); R=$(cd "$D/.." && pwd)
P=${1:-python3}
export CUDA_VISIBLE_DEVICES=

W=$(mktemp -d)
(cd "$W" && "$P" -I "$D/ch07_evidence_check.py" > "$W/fresh.out" 2>&1)
status=$?
echo "ch07_evidence_check: exit $status"

(cd "$R" && PYTHONPATH="$R/src" MPLCONFIGDIR=$(mktemp -d) "$P" tools/render_figures.py --chapters ch07 > /dev/null)
echo "figures (tools/render_figures.py --chapters ch07): exit $?"

# The compare: the fresh output against the one committed in git, before the committed file is overwritten, so
# the result does not depend on the state of the working tree. The output carries no version, host, timing or
# date line, so it is compared verbatim and needs no normalisation.
clean=1
if git -C "$R" show "HEAD:./derivation-checks/ch07_evidence_check.out" > "$W/committed.out" 2>/dev/null; then
  if diff -u "$W/committed.out" "$W/fresh.out" > "$W/compare.diff"; then
    echo "compare ch07_evidence_check.out: unchanged"
  else
    echo "compare ch07_evidence_check.out: DIFFERS"; head -40 "$W/compare.diff"; clean=0
  fi
else
  echo "compare ch07_evidence_check.out: no committed output at HEAD"; clean=0
fi
cp "$W/fresh.out" "$D/ch07_evidence_check.out"
rm -rf "$W"

[ $status -eq 0 ] || clean=0
if [ $clean -eq 1 ]; then echo "ch07: REPRODUCED"; else echo "ch07: NOT REPRODUCED"; exit 1; fi
