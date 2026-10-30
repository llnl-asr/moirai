#!/usr/bin/env bash
#
# Build manylinux wheels for moirai with cibuildwheel, as dftracer's
# scripts/wheel/build_wheels.sh does. moirai's wheel is built against, and
# requires, the dftracer wheel (MOIRAI_DFTRACER=PACKAGE): every container
# installs it first, and the repair step keeps its libraries out of moirai's
# wheel (repair_wheel.sh).
#
#   scripts/wheel/build_wheels.sh                     # 3.9 .. 3.14, glibc 2.28
#   scripts/wheel/build_wheels.sh --python 3.12       # subset
#   scripts/wheel/build_wheels.sh --list              # show plan and exit
#
# Options:
#   --python LIST     comma/space separated python versions (default 3.9 .. 3.14)
#   --glibc VERSION   manylinux glibc baseline: 2.28 (default) | 2.34
#   --arch ARCH       x86_64 (default) | aarch64
#   --output DIR      wheel output directory (default <repo>/wheelhouse)
#   --no-test         do not test the wheels (default: every wheel is installed
#                     with the dftracer wheel and validated by test_wheel.py)
#   --list            print the resolved build plan and exit
#
# Environment:
#   MOIRAI_DFTRACER_SPEC   the dftracer to build and test against, as a pip
#                          requirement (default: dftracer's
#                          feature/generic-event-api from git, until a release
#                          has the event-type API)
#   CIBW_VERSION           cibuildwheel version (default 3.2.1)
#   CIBW_CONTAINER_ENGINE  docker (default) or podman; rootless podman gets its
#                          storage under MOIRAI_WHEEL_STATE, off an NFS $HOME
#   PIP_INDEX_URL, PIP_TRUSTED_HOST, PIP_EXTRA_INDEX_URL
#                          passed into the containers when set (a site mirror)
#   MOIRAI_WHEEL_STATE     dir for the cibuildwheel venv
#                          (default ${TMPDIR:-/tmp}/$USER/moirai-wheels)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

PYTHONS="3.9 3.10 3.11 3.12 3.13 3.14"
GLIBC="2.28"
ARCH="x86_64"
OUTPUT="$PROJECT_DIR/wheelhouse"
RUN_TESTS=1
LIST_ONLY=0
CIBW_VERSION="${CIBW_VERSION:-3.2.1}"
DFTRACER_SPEC="${MOIRAI_DFTRACER_SPEC:-dftracer @ git+https://github.com/llnl-asr/dftracer@feature/generic-event-api}"
VERSION="$(head -n1 "$PROJECT_DIR/VERSION")"

die() {
  echo "build_wheels.sh: $*" >&2
  exit 1
}
log() { echo "==> $*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --python) PYTHONS="${2//,/ }"; shift 2 ;;
    --glibc) GLIBC="$2"; shift 2 ;;
    --arch) ARCH="$2"; shift 2 ;;
    --output) OUTPUT="$2"; shift 2 ;;
    --no-test) RUN_TESTS=0; shift ;;
    --list) LIST_ONLY=1; shift ;;
    -h|--help) sed -n '2,32p' "$0"; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
done

case "$GLIBC" in
  2.28) IMAGE="manylinux_2_28" ;;
  2.34) IMAGE="manylinux_2_34" ;;
  *) die "unsupported --glibc $GLIBC (2.28 or 2.34)" ;;
esac

BUILD=""
for py in $PYTHONS; do
  BUILD="$BUILD cp${py/./}-manylinux_$ARCH"
done
BUILD="${BUILD# }"

log "wheel version $VERSION"
log "pythons: $PYTHONS"
log "image: $IMAGE ($ARCH)"
log "dftracer: $DFTRACER_SPEC"
log "output: $OUTPUT"
[ "$LIST_ONLY" = 1 ] && exit 0

STATE="${MOIRAI_WHEEL_STATE:-${TMPDIR:-/tmp}/$USER/moirai-wheels}"
mkdir -p "$STATE"
VENV="$STATE/venv"
ENGINE="${CIBW_CONTAINER_ENGINE:-docker}"
if [ "$ENGINE" = "podman" ]; then
  # Rootless podman keeps its storage under $HOME, which on NFS cannot hold
  # the xattrs image layers need; podman 4.9 ignores CONTAINERS_STORAGE_CONF
  # for it, so a wrapper on PATH passes --root/--runroot (as dftracer's
  # build_wheels.sh does).
  PODMAN_BIN="$(command -v podman)" || die "podman not found on PATH"
  mkdir -p "$STATE/bin" "$STATE/storage" "$STATE/run"
  cat >"$STATE/bin/podman" <<WRAP
#!/usr/bin/env bash
exec "$PODMAN_BIN" --root "$STATE/storage" --runroot "$STATE/run" "\$@"
WRAP
  chmod +x "$STATE/bin/podman"
  export PATH="$STATE/bin:$PATH"
  log "podman storage: $STATE/storage"
fi
# (cibuildwheel 3 has no --version: ask pip.)
if [ ! -x "$VENV/bin/cibuildwheel" ] ||
  ! "$VENV/bin/python" -m pip show cibuildwheel 2>/dev/null |
    grep -qx "Version: $CIBW_VERSION"; then
  log "creating cibuildwheel $CIBW_VERSION venv in $VENV"
  mkdir -p "$STATE"
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet "cibuildwheel==$CIBW_VERSION"
fi

export CIBW_PLATFORM=linux
export CIBW_ARCHS="$ARCH"
export CIBW_BUILD="$BUILD"
export CIBW_CONTAINER_ENGINE="$ENGINE"
export CIBW_ENVIRONMENT_PASS_LINUX="PIP_INDEX_URL PIP_TRUSTED_HOST PIP_EXTRA_INDEX_URL"
export CIBW_MANYLINUX_X86_64_IMAGE="$IMAGE"
export CIBW_MANYLINUX_AARCH64_IMAGE="$IMAGE"
# A dftracer built from source in the container (a git MOIRAI_DFTRACER_SPEC)
# builds its own dependencies, which need boost's headers, as in dftracer's
# own wheel build (scripts/wheel/build_deps.sh there).
export CIBW_BEFORE_ALL="if command -v dnf >/dev/null; then dnf install -y boost-devel git; else yum install -y boost-devel git; fi"
# Built against the dftracer wheel, so not in an isolated environment: the
# build environment gets moirai's build requirements and that wheel first.
# before_build installs everything the build needs, including cmake and
# ninja, which scikit-build-core would otherwise ask for and a
# non-isolated build reports as missing; build's own check of the declared
# requirements is skipped (-x), since the dftracer from git is a local
# build -- moirai's configure still checks it has the event-type API.
export CIBW_BUILD_FRONTEND="build; args: --no-isolation --skip-dependency-check"
# The dftracer wheel moirai builds against is built (or downloaded) once per
# interpreter into /tmp/dftracer-wheel, which lasts as long as the container,
# and installed from there both for the build and, in before_test, for the
# test -- cibuildwheel installs moirai's wheel into the test environment
# before CIBW_TEST_REQUIRES, so the dftracer it requires must already be
# there (a git build is not on PyPI).
# One directory per interpreter, and the file itself is installed: by name,
# pip would prefer dftracer's final releases on PyPI, which lack the API.
# Its own dependencies (pydftracer, dftracer-utils) still come from PyPI.
DFTRACER_WHEELS='/tmp/dftracer-wheel/$(python -c "import sys; print(sys.implementation.cache_tag)")'
INSTALL_DFTRACER="pip install $DFTRACER_WHEELS/dftracer-*.whl"
export CIBW_BEFORE_BUILD="pip install scikit-build-core pybind11 wheel auditwheel patchelf 'cmake>=3.24' ninja && bash /project/scripts/wheel/build_dftracer_wheel.sh '$DFTRACER_SPEC' $DFTRACER_WHEELS && $INSTALL_DFTRACER"
export CIBW_ENVIRONMENT="CMAKE_BUILD_PARALLEL_LEVEL=${CMAKE_BUILD_PARALLEL_LEVEL:-4}"
# Show the build's own output: a failing CMake configure is otherwise only
# an exit code.
export CIBW_BUILD_VERBOSITY=1
# The repair command gets only {wheel} and {dest_dir}; the project is
# mounted at /project in the container (as in dftracer's build_wheels.sh).
# The test command does get {project}.
export CIBW_REPAIR_WHEEL_COMMAND="bash /project/scripts/wheel/repair_wheel.sh {wheel} {dest_dir}"
if [ "$RUN_TESTS" = 1 ]; then
  export CIBW_BEFORE_TEST="$INSTALL_DFTRACER"
  export CIBW_TEST_COMMAND="python {project}/scripts/wheel/test_wheel.py {project}"
fi

# cibuildwheel copies the project into every container: stage the files git
# tracks (or would track), not build trees and virtualenvs.
SOURCE="$STATE/src"
rm -rf "$SOURCE"
mkdir -p "$SOURCE"
(cd "$PROJECT_DIR" && git ls-files -z --cached --others --exclude-standard) |
  tar -C "$PROJECT_DIR" --null -T - --ignore-failed-read -cf - |
  tar -C "$SOURCE" -xf -
log "source: $SOURCE"

mkdir -p "$OUTPUT"
OUTPUT="$(cd "$OUTPUT" && pwd)"
cd "$SOURCE"
"$VENV/bin/cibuildwheel" --output-dir "$OUTPUT" .
log "wheels:"
ls -1 "$OUTPUT"
