#!/usr/bin/env bash
# One command that installs what this report needs to render and to pass its gates, at pinned versions.
#
#     bash setup.sh                 # Quarto, TinyTeX (LuaLaTeX), Universal Ctags and the Python environment
#
# Everything lands under one prefix (default ./.report-env); nothing is installed system-wide: no package manager,
# no sudo, no write outside the prefix and the repository. Every download is checked against the sha256 committed in
# tools/env-pins.json before it is unpacked. Versions: tools/env-pins.json (Quarto 1.10.19 as in CI, TinyTeX and the
# dated TeX Live snapshot its packages come from, Universal Ctags 6.2.1) and the Python packages CI installs.
# Adapted from the snapy technical report's setup.sh (the same pins); the derivation-check environments are built by
# the per-chapter derivation-checks/*setup*.sh scripts instead.
#
# When it finishes it writes <prefix>/activate. Source that and every command in README.md works as written:
#
#     source .report-env/activate
#     python3 tools/render_gate.py book/
#
# activate also points every cache (TeX, Jupyter, matplotlib, pip, XDG) inside the prefix, so nothing needs a
# writable $HOME: LuaTeX stops with "no writeable cache path" without one.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="$HERE/.report-env"
PRINT_DIGESTS=0
JOBS="$( (command -v nproc >/dev/null && nproc) || sysctl -n hw.ncpu 2>/dev/null || echo 4)"

usage() {
  sed -n '2,/^[^#]/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'
  cat <<'EOF'

Options:
  --prefix DIR       where to install (default: doc/tech-report/.report-env)
  --jobs N           parallel compile jobs for Universal Ctags (default: all cores)
  --print-digests    download every artifact and print its sha256, then stop
  -h, --help         this text
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="$(mkdir -p "$2" && cd "$2" && pwd)"; shift 2 ;;
    --jobs) JOBS="$2"; shift 2 ;;
    --print-digests) PRINT_DIGESTS=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "setup.sh: unknown option $1 (try --help)" >&2; exit 2 ;;
  esac
done

PINS="$HERE/tools/env-pins.json"
DL="$PREFIX/downloads"
SRC="$PREFIX/src"
CACHE="$PREFIX/cache"
LOGS="$PREFIX/logs"

# Progress goes to stderr so that `$(fetch ...)` captures only the path fetch prints.
step()  { printf '\n\033[1m==> %s\033[0m\n' "$*" >&2; }
info()  { printf '    %s\n' "$*" >&2; }
die()   { printf '\n\033[31msetup.sh: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- preflight --

step "Preflight"
for t in curl tar make git; do
  command -v "$t" >/dev/null || die "\`$t\` is not on PATH"
done
command -v cc >/dev/null || command -v gcc >/dev/null || die "no C compiler on PATH (Universal Ctags is built from source)"

PY_MIN="$(python3 -c "import json;print(json.load(open('$PINS'))['python']['minimum'])" 2>/dev/null || echo 3.11)"
PY_MAX="$(python3 -c "import json;print(json.load(open('$PINS'))['python']['below'])" 2>/dev/null || echo 3.14)"
PYTHON=""
for c in python3.12 python3.13 python3.11 python3; do
  command -v "$c" >/dev/null || continue
  if "$c" - "$PY_MIN" "$PY_MAX" <<'EOF' >/dev/null 2>&1
import sys
lo = tuple(int(p) for p in sys.argv[1].split("."))
hi = tuple(int(p) for p in sys.argv[2].split("."))
sys.exit(0 if lo <= sys.version_info[:2] < hi else 1)
EOF
  then PYTHON="$(command -v "$c")"; break; fi
done
[ -n "$PYTHON" ] || die "no Python in [$PY_MIN, $PY_MAX) on PATH"
info "python      $("$PYTHON" -V 2>&1) at $PYTHON"

case "$(uname -s)" in
  Linux)  OS=linux ;;
  Darwin) OS=darwin ;;
  *) die "unsupported OS $(uname -s); add its artifacts to tools/env-pins.json" ;;
esac
case "$(uname -m)" in
  x86_64|amd64)  ARCH=x86_64 ;;
  arm64|aarch64) ARCH=aarch64 ;;
  *) die "unsupported CPU $(uname -m); add its artifacts to tools/env-pins.json" ;;
esac
if [ "$OS" = darwin ]; then PLATFORM=darwin; else PLATFORM="$OS-$ARCH"; fi
info "platform    $PLATFORM"
info "prefix      $PREFIX"

mkdir -p "$DL" "$SRC" "$LOGS" "$PREFIX/bin" \
         "$CACHE"/{pip,xdg,matplotlib,ipython,jupyter/runtime,jupyter/data,tmp,pyharp-report,texmf-var,texmf-config}
export MPLCONFIGDIR="$CACHE/matplotlib" XDG_CACHE_HOME="$CACHE/xdg" TMPDIR="$CACHE/tmp"

pin() { "$PYTHON" -c "
import json,sys
d=json.load(open('$PINS'))
for k in sys.argv[1:]:
    d = d[int(k)] if isinstance(d, list) else d[k]
print(' '.join(d) if isinstance(d,list) else d)" "$@"; }

# pin_artifact <section> <name> -> 'url sha256 strip' for this platform, else the 'source' artifact
pin_artifact() {
  "$PYTHON" -c "
import json,sys
sec,name,plat = sys.argv[1],sys.argv[2],sys.argv[3]
a = json.load(open('$PINS'))[sec][name]['artifacts']
e = a.get(plat) or a.get('source')
if e is None:
    sys.exit('no artifact for %s/%s on %s' % (sec,name,plat))
print(e['url'], e['sha256'], e.get('strip',1))" "$1" "$2" "$3"
}

# fetch <url> <sha256> -> downloads once into $DL and verifies, or dies; prints the path
fetch() {
  local url="$1" want="$2" out="$DL/$(basename "$1")" got
  if [ ! -f "$out" ]; then
    info "download  $(basename "$url")"
    curl -fsSL --retry 3 -o "$out.part" "$url" || die "could not download $url"
    mv "$out.part" "$out"
  fi
  got="$(sha256sum "$out" 2>/dev/null | cut -d' ' -f1 || shasum -a 256 "$out" | cut -d' ' -f1)"
  if [ "$PRINT_DIGESTS" = 1 ]; then printf '    %s  %s\n' "$got" "$(basename "$url")" >&2; return 0; fi
  [ "$got" = "$want" ] || die "sha256 mismatch for $url
    committed in tools/env-pins.json: $want
    the file that was served:         $got
  Refusing to unpack it."
  echo "$out"
}

unpack() { mkdir -p "$2"; tar -x -f "$1" -C "$2" --strip-components="$3"; }

if [ "$PRINT_DIGESTS" = 1 ]; then
  step "Digests of every pinned artifact on $PLATFORM"
  for spec in "render quarto" "render tinytex" "render universal-ctags"; do
    read -r u s _ <<<"$(pin_artifact ${spec% *} ${spec#* } "$PLATFORM")"
    fetch "$u" "$s" >/dev/null
  done
  exit 0
fi

# ------------------------------------------------------------------- quarto --

QV="$(pin render quarto version)"
step "Quarto $QV"
if [ ! -x "$PREFIX/quarto/bin/quarto" ]; then
  read -r URL SHA STRIP <<<"$(pin_artifact render quarto "$PLATFORM")"
  unpack "$(fetch "$URL" "$SHA")" "$PREFIX/quarto" "$STRIP"
fi
ln -sf "$PREFIX/quarto/bin/quarto" "$PREFIX/bin/quarto"
got="$("$PREFIX/bin/quarto" --version 2>/dev/null || echo '?')"
[ "$got" = "$QV" ] || die "the installed Quarto reports '$got', tools/env-pins.json pins $QV"
info "quarto $got"

# ------------------------------------------------------------------ tinytex --

step "TinyTeX $(pin render tinytex version) ($(pin render tinytex scheme))"
if [ ! -d "$PREFIX/tinytex/bin" ]; then
  read -r URL SHA STRIP <<<"$(pin_artifact render tinytex "$PLATFORM")"
  unpack "$(fetch "$URL" "$SHA")" "$PREFIX/tinytex" "$STRIP"
fi
TEXBIN="$(dirname "$(find "$PREFIX/tinytex/bin" -name lualatex -type f -o -name lualatex -type l | head -1)")"
[ -n "$TEXBIN" ] || die "the TinyTeX tarball carried no lualatex"
for b in "$TEXBIN"/*; do ln -sf "$b" "$PREFIX/bin/$(basename "$b")"; done

export TEXMFVAR="$CACHE/texmf-var" TEXMFCACHE="$CACHE/texmf-var" TEXMFCONFIG="$CACHE/texmf-config"
export TEXMFHOME="$CACHE/texmf-home" PATH="$PREFIX/bin:$PATH"
mkdir -p "$TEXMFVAR" "$TEXMFCONFIG" "$TEXMFHOME"

# Pinning the tarball does not pin TeX: scheme 1 has no KOMA-Script, so the class the book is built on would come
# from a rolling mirror on the day of the render. tools/env-pins.json names a dated, immutable tlnet snapshot; tlmgr
# updates itself from it first (the tarball's tlmgr is older and refuses to install until it matches). Any failure
# here is fatal: carrying on would let the render pull TeX from a rolling mirror.
TLNET="$(pin render tinytex tlnet_repository)"
info "package repository pinned to $TLNET"
"$PREFIX/bin/tlmgr" option repository "$TLNET" >"$LOGS/tlmgr.log" 2>&1 \
  || die "could not point tlmgr at the pinned snapshot $TLNET; see $LOGS/tlmgr.log"
"$PREFIX/bin/tlmgr" update --self >>"$LOGS/tlmgr.log" 2>&1 \
  || die "tlmgr could not update itself from the pinned snapshot $TLNET; see $LOGS/tlmgr.log"
in_effect="$("$PREFIX/bin/tlmgr" option repository 2>/dev/null | sed -n 's/.*:[[:space:]]*\(https\{0,1\}:.*\)$/\1/p' | tail -1)"
case "$in_effect" in
  "$TLNET"*) : ;;
  *) die "tlmgr reports its repository as '$in_effect', not the pinned $TLNET" ;;
esac
info "adding the LaTeX packages the book loads"
# tlmgr exits non-zero when a name is already part of the scheme; kpsewhich answers the real question afterwards.
"$PREFIX/bin/tlmgr" install $(pin render tinytex tlmgr_packages) >>"$LOGS/tlmgr.log" 2>&1 || true
missing=""
for probe in scrreprt.cls fontspec.sty caption.sty tcolorbox.sty unicode-math.sty luacolor.sty; do
  "$PREFIX/bin/kpsewhich" "$probe" >/dev/null 2>&1 || missing="$missing $probe"
done
[ -z "$missing" ] || die "the pinned snapshot did not provide:$missing; see $LOGS/tlmgr.log"
"$PREFIX/bin/tlmgr" option autobackup 0 >>"$LOGS/tlmgr.log" 2>&1 || true
# What TeX holds now, so "the render fetched nothing" can be checked afterwards:
#   diff .report-env/tex-packages.lock <(tlmgr list --only-installed | sort)
"$PREFIX/bin/tlmgr" list --only-installed 2>/dev/null | sort > "$PREFIX/tex-packages.lock" || true
info "$(wc -l < "$PREFIX/tex-packages.lock") TeX packages recorded in tex-packages.lock"
"$PREFIX/bin/luaotfload-tool" --update >"$LOGS/luaotfload.log" 2>&1 || true
info "$("$PREFIX/bin/lualatex" --version 2>/dev/null | head -1)"

# ------------------------------------------------------------------- ctags --

step "Universal Ctags $(pin render universal-ctags version)"
if [ ! -x "$PREFIX/uctags/bin/ctags" ]; then
  read -r URL SHA STRIP <<<"$(pin_artifact render universal-ctags "$PLATFORM")"
  unpack "$(fetch "$URL" "$SHA")" "$SRC/ctags" "$STRIP"
  ( cd "$SRC/ctags" \
    && ./configure --prefix="$PREFIX/uctags" $(pin render universal-ctags configure) \
    && make -s -j"$JOBS" && make -s install ) >"$LOGS/ctags.log" 2>&1 \
    || die "Universal Ctags did not build; see $LOGS/ctags.log"
fi
ln -sf "$PREFIX/uctags/bin/ctags" "$PREFIX/bin/ctags"
info "$("$PREFIX/bin/ctags" --version | head -1)"

# ------------------------------------------------------- python environment --

step "Python environment"
export PIP_CACHE_DIR="$CACHE/pip"
[ -x "$PREFIX/venv/bin/python" ] || "$PYTHON" -m venv "$PREFIX/venv"
VPY="$PREFIX/venv/bin/python"
"$VPY" -m pip install --quiet --upgrade pip >"$LOGS/pip.log" 2>&1
info "pip install $(pin python_packages install) (as CI)"
( cd "$HERE" && "$VPY" -m pip install --quiet $(pin python_packages install) ) >>"$LOGS/pip.log" 2>&1 \
  || die "the Python environment did not install; see $LOGS/pip.log"
info "$("$VPY" -c 'import numpy,sympy,matplotlib,yaml;print("numpy",numpy.__version__,"sympy",sympy.__version__,"matplotlib",matplotlib.__version__)')"

# ------------------------------------------------------------------ activate --

step "Writing $PREFIX/activate"
cat > "$PREFIX/activate" <<EOF
# Written by doc/tech-report/setup.sh. Source it, do not run it:
#     source $(basename "$PREFIX")/activate
export PYHARP_REPORT_ENV="$PREFIX"
export PATH="$PREFIX/venv/bin:$PREFIX/bin:\$PATH"
export CTAGS="$PREFIX/uctags/bin/ctags"
# Quarto runs the {python} cells with this interpreter, not the first one it finds.
export QUARTO_PYTHON="$PREFIX/venv/bin/python"
export TEXMFVAR="$CACHE/texmf-var"
export TEXMFCACHE="$CACHE/texmf-var"
export TEXMFCONFIG="$CACHE/texmf-config"
export TEXMFHOME="$CACHE/texmf-home"
export PYHARP_REPORT_CACHE="$CACHE/pyharp-report"
export XDG_CACHE_HOME="$CACHE/xdg"
export XDG_DATA_HOME="$CACHE/xdg/data"
export XDG_CONFIG_HOME="$CACHE/xdg/config"
export MPLCONFIGDIR="$CACHE/matplotlib"
export JUPYTER_RUNTIME_DIR="$CACHE/jupyter/runtime"
export JUPYTER_DATA_DIR="$CACHE/jupyter/data"
export JUPYTER_PLATFORM_DIRS=1
export IPYTHONDIR="$CACHE/ipython"
export PIP_CACHE_DIR="$CACHE/pip"
export TMPDIR="$CACHE/tmp"
export MPLBACKEND=Agg
EOF
info "done"

cat <<EOF

$(printf '\033[32mReady.\033[0m') Start every session with

    source $("$PYTHON" -c "import os.path,sys;print(os.path.relpath(sys.argv[1]))" "$PREFIX")/activate

and then, from doc/tech-report:

    python3 -m pytest -q tools/tests
    python3 tools/code_anchors.py check
    python3 tools/render_gate.py book/ --release     # the source gates, the HTML and the PDF
EOF
