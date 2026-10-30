#!/usr/bin/env bash
#
# Build the dftracer wheel moirai's wheel is built and tested against, from a
# pip requirement (e.g. dftracer from git), and make it relocatable.
# Runs in cibuildwheel's before_build (scripts/wheel/build_wheels.sh).
#
#   bash scripts/wheel/build_dftracer_wheel.sh <pip requirement> <out dir>
#
# 1. DFTRACER_WHEEL=1: dftracer's setup.py then installs its CMake part --
#    libdftracer_core and its dependencies, dftracer_service, the headers --
#    into the wheel. Without it they go straight into the build environment's
#    site-packages, and the wheel carries only the Python code.
# 2. dftracer's binaries carry absolute RPATHs into its build tree; dftracer's
#    own wheel build rewrites them in its repair step. This sets short
#    relative RPATHs with patchelf, and nothing else: no renamed libraries,
#    so the executables keep their layout (dftracer's bundle_wheel.py).
#    dftracer's libraries are split between dftracer/lib64 and dftracer/lib
#    (its dependency build installs some, e.g. yaml-cpp, into lib/), so every
#    binary searches both.

set -euo pipefail

spec="$1"
out="$2"
python=${PYTHON:-python}
log() { echo "[dftracer-wheel] $*"; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

log "building $spec"
DFTRACER_WHEEL=1 "$python" -m pip wheel --no-deps -w "$work/built" "$spec"

"$python" -m wheel unpack "$work"/built/dftracer-*.whl -d "$work/unpacked"
tree=$(echo "$work"/unpacked/*)
pkg="$tree/dftracer"
[ -d "$pkg/lib64" ] || [ -d "$pkg/lib" ] ||
  { log "no lib64/ in the dftracer wheel: was DFTRACER_WHEEL honoured?"; exit 1; }

is_elf() { [ "$(head -c4 "$1" 2>/dev/null | od -An -c | tr -d ' ')" = "177ELF" ]; }
relocate() {  # <dir> <rpath>
  local f
  for f in "$1"/*; do
    [ -f "$f" ] && [ ! -L "$f" ] && is_elf "$f" || continue
    patchelf --force-rpath --set-rpath "$2" "$f"
    log "${f#"$pkg"/}: RPATH $2"
  done
}
for d in lib64 lib; do
  [ -d "$pkg/$d" ] && relocate "$pkg/$d" '$ORIGIN:$ORIGIN/../lib64:$ORIGIN/../lib'
done
[ -d "$pkg/bin" ] && relocate "$pkg/bin" '$ORIGIN/../lib64:$ORIGIN/../lib'
# dftracer's own Python extension modules, next to lib64/.
relocate "$pkg" '$ORIGIN/lib64:$ORIGIN/lib'

mkdir -p "$out"
"$python" -m wheel pack "$tree" -d "$out"
log "wrote $(ls "$out"/dftracer-*.whl)"
