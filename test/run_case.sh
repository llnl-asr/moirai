#!/bin/bash
# Run one traced test application as a moirai user would: settings are
# MOIRAI_* only, and in "service" mode a moirai-service of its own runs
# around it; in "spill" mode none does, so events go to the spill file.
#
# Usage: run_case.sh <service|spill> <moirai-service> <work dir> <command...>
# The trace prefix is <work dir>/trace, the application's data directory
# <work dir>/data (MOIRAI_TEST_DATA).
#
# MOIRAI_TEST_VALGRIND=c|py runs the application -- only the application,
# not this script or the service -- under valgrind's memcheck, with
# dftracer's flags. For C/C++ any error, or definite or possible leak, fails
# the run (exit 99). For Python (PYTHONMALLOC=malloc) the interpreter's own
# reports are not moirai's: only a context with a moirai or dftracer frame
# fails it (valgrind/check_valgrind_log.py, as dftracer's Python runner).
# Suppressions are MOIRAI_TEST_SUPPRESSIONS (colon separated); the log is
# <work dir>/valgrind.log.
set -u
MODE=${1:?service or spill}
SERVICE=${2:?moirai-service binary}
WORK=${3:?work dir}
shift 3

rm -rf "$WORK"
mkdir -p "$WORK/data"
export MOIRAI_LOG_FILE="$WORK/trace"
export MOIRAI_SERVICE_SHM="/moirai-test-$$"
export MOIRAI_DATA_DIR="$WORK/data"
export MOIRAI_TEST_DATA="$WORK/data"
# A 16 MiB ring (16 x 1 MiB blocks) instead of dftracer's 1 GiB default: the
# tests run several services at once, and a CI runner's /dev/shm cannot hold
# a gigabyte for each. Set as a moirai setting, it also exercises the
# MOIRAI_<X> -> DFTRACER_<X> translation for both the service and the app.
export MOIRAI_PC_BLOCKS="${MOIRAI_PC_BLOCKS:-16}"

app() {
  local vg=()
  case "${MOIRAI_TEST_VALGRIND:-}" in
    c) vg=(valgrind --tool=memcheck --leak-check=full
           --show-leak-kinds=definite,possible --track-origins=yes
           --num-callers=40 --error-exitcode=99
           --log-file="$WORK/valgrind.log") ;;
    py) export PYTHONMALLOC=malloc
        vg=(valgrind --tool=memcheck --leak-check=full
            --show-leak-kinds=definite --errors-for-leak-kinds=definite
            --track-origins=no --num-callers=40 --error-exitcode=99
            --log-file="$WORK/valgrind.log") ;;
  esac
  if [ ${#vg[@]} -gt 0 ]; then
    local supp
    IFS=: read -ra supp <<<"${MOIRAI_TEST_SUPPRESSIONS:-}"
    for s in "${supp[@]}"; do [ -n "$s" ] && vg+=(--suppressions="$s"); done
  fi
  "${vg[@]}" "$@"
  local rc=$?
  if [ "${MOIRAI_TEST_VALGRIND:-}" = "py" ] && [ $rc -eq 99 ]; then
    python3 "$(dirname "$0")/valgrind/check_valgrind_log.py" "$WORK/valgrind.log"
    return $?
  fi
  if [ $rc -eq 99 ]; then
    echo "valgrind found errors: $WORK/valgrind.log"
    grep -A20 "ERROR SUMMARY\|definitely lost\|Invalid\|uninitialised" \
      "$WORK/valgrind.log" | head -60
  fi
  return $rc
}

if [ "$MODE" = "service" ]; then
  "$SERVICE" start >"$WORK/service.out" 2>&1
  for _ in $(seq 100); do
    [ -s "/dev/shm$MOIRAI_SERVICE_SHM" ] && break
    sleep 0.1
  done
  if [ ! -s "/dev/shm$MOIRAI_SERVICE_SHM" ]; then
    echo "moirai-service did not come up"
    cat "$WORK/service.out" "$WORK"/trace_*.log 2>/dev/null
    exit 1
  fi
fi

app "$@"
rc=$?

if [ "$MODE" = "service" ]; then
  "$SERVICE" stop >>"$WORK/service.out" 2>&1
  for _ in $(seq 300); do
    [ -e "/dev/shm$MOIRAI_SERVICE_SHM" ] || break
    sleep 0.1
  done
  if [ -e "/dev/shm$MOIRAI_SERVICE_SHM" ]; then
    echo "moirai-service did not stop"
    exit 1
  fi
fi
exit $rc
