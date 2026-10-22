#!/bin/bash
# Build the cdisort 2.1.3 test driver (disotest) that pydisort bundles, with every c_disort() call
# routed through dump_shim.c, plus planck_probe, against one pydisort source tree.
# usage: build.sh PYDISORT_SRC OUTDIR     -> OUTDIR/test_cdisort, OUTDIR/planck_probe
#
# The driver is PYDISORT_SRC/tests/cdisort213/test_cdisort.c with its c_disort() calls renamed
# dump_c_disort(); dump_shim.c replaces print_test.c. pydisort's copy runs only case 9a (ncase = 1)
# although the 9b/9c reference values are in the file; upstream cdisort 2.1.3 runs all three, so the
# copy made here sets ncase = 3 for test 9. pydisort 1.7.x ships cdisort213/cdisort.c (C); 1.8.x
# ships a header-only C++ cdisort (cdisort213/cdisort.hpp).
set -euo pipefail
S=$1; O=$2; D=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$O"
L=$(grep -n "ncase = 1;" "$S/tests/cdisort213/test_cdisort.c" | cut -d: -f1)
[ "$(echo "$L" | wc -w)" = 1 ] || { echo "build.sh: expected one 'ncase = 1;' (test 9)" >&2; exit 1; }
sed -e "${L}s/ncase = 1;/ncase = 3;/" -e 's/\bc_disort(&/dump_c_disort(\&/' \
  "$S/tests/cdisort213/test_cdisort.c" > "$O/test_cdisort.c"
if [ -f "$S/cdisort213/cdisort.c" ]; then
  gcc -O2 -w -I"$S/cdisort213" -o "$O/test_cdisort" -include "$D/dump_proto.h" "$O/test_cdisort.c" \
    "$D/dump_shim.c" "$S/cdisort213/cdisort.c" "$S/cdisort213/locate.c" -lm
  gcc -O2 -w -I"$S/cdisort213" -o "$O/planck_probe" "$D/planck_probe.c" \
    "$S/cdisort213/cdisort.c" "$S/cdisort213/locate.c" -lm
else
  g++ -O2 -w -fpermissive -I"$S" -I"$S/src" -I"$S/cdisort213" -DCDISORT_HEADER_ONLY -o "$O/test_cdisort" \
    -include "$D/dump_proto.h" -x c++ "$O/test_cdisort.c" "$D/dump_shim.c" -lm
  g++ -O2 -w -fpermissive -I"$S" -I"$S/src" -I"$S/cdisort213" -DCDISORT_HEADER_ONLY -o "$O/planck_probe" \
    -x c++ "$D/planck_probe.c" -lm
fi
