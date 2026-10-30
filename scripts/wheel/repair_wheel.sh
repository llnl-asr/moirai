#!/usr/bin/env bash
#
# cibuildwheel's CIBW_REPAIR_WHEEL_COMMAND, as dftracer's.
#
#   bash scripts/wheel/repair_wheel.sh <wheel> <dest_dir>
#
# moirai's wheel runs on the dftracer wheel: its libraries come from
# site-packages/dftracer/lib64 (RPATH $ORIGIN/../dftracer/lib64), so
# auditwheel must not vendor them. And as dftracer found, auditwheel's
# patchelf pass can leave a native executable unloadable, so moirai's
# executables (moirai/bin) are lifted out around it and put back unchanged:
# they already carry their $ORIGIN RPATH.
#
# 1. unpack the wheel and lift moirai/bin out
# 2. auditwheel repair, excluding every library of the dftracer wheel, with
#    that wheel's lib64 on LD_LIBRARY_PATH so the rest resolves
# 3. unpack the repaired wheel, put moirai/bin back, repack

set -euo pipefail

wheel="$1"
dest="$2"
log() { echo "[repair] $*"; }

python=${PYTHON:-python}
dftracer_pkg=$("$python" -c "import dftracer, os; print(os.path.dirname(dftracer.__file__))")
dftracer_lib="$dftracer_pkg/lib64"
[ -d "$dftracer_lib" ] || dftracer_lib="$dftracer_pkg/lib"
export LD_LIBRARY_PATH="$dftracer_lib:${LD_LIBRARY_PATH:-}"
log "dftracer wheel libraries: $dftracer_lib"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# 1.
"$python" -m wheel unpack "$wheel" -d "$work/unpacked"
tree=$(echo "$work"/unpacked/*)
mkdir -p "$work/stash"
mv "$tree/moirai/bin" "$work/stash/bin"
mkdir -p "$work/lifted"
"$python" -m wheel pack "$tree" -d "$work/lifted"

# 2.
excludes=()
for lib in "$dftracer_lib"/*.so*; do
  excludes+=(--exclude "$(basename "$lib")")
done
auditwheel repair "${excludes[@]}" -w "$work/repaired" "$work"/lifted/*.whl

# 3.
"$python" -m wheel unpack "$work"/repaired/*.whl -d "$work/final"
final=$(echo "$work"/final/*)
mv "$work/stash/bin" "$final/moirai/bin"
mkdir -p "$dest"
"$python" -m wheel pack "$final" -d "$dest"
log "repaired: $(ls "$dest")"
