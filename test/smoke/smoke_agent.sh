#!/bin/bash
# One real session of a harness with moirai's hooks, through moirai-service: it
# runs a script that writes a file, and check_agent.py looks at what was left.
# Not in ctest: it needs the harness, and claude's run is a real model call.
#
# Usage: smoke_agent.sh <claude|codex> <build dir> <python> [work dir]
set -u
HARNESS=${1:?claude or codex}
BUILD=$(cd "${2:?build dir}" && pwd)
PYTHON=${3:?python}
WORK=${4:-$BUILD/smoke/$HARNESS}
HERE=$(cd "$(dirname "$0")" && pwd)

rm -rf "${WORK:?}"
mkdir -p "$WORK/project"
cd "$WORK/project" || exit 1
printf 'import sys\nopen(sys.argv[1], "w").write("smoke %s\\n")\n' "$HARNESS" >gen.py

export PYTHONPATH=$BUILD/python
export MOIRAI_AGENT_DIR=$WORK/run MOIRAI_TRACE_IO=0 MOIRAI_PC_BLOCKS=16
export MOIRAI_SERVICE_SHM=/moirai-smoke-$$
export MOIRAI_LOG_FILE=$WORK/run/trace
"$PYTHON" -m moirai.agent install "$HARNESS" >/dev/null || exit 1
"$BUILD/moirai-service" start >"$WORK/service.out" 2>&1
sleep 1

# The harness gets no MOIRAI_* and no PYTHONPATH: the hook has what it needs.
clean=(env -i "HOME=$HOME" "PATH=$PATH")
for v in NO_PROXY no_proxy; do clean+=("$v=127.0.0.1"); done
case "$HARNESS" in
  claude)
    timeout 150 "${clean[@]}" claude -p \
      "Run exactly: python3 gen.py out.txt   then reply with just the word done." \
      --allowedTools "Bash(python3 gen.py*)" --max-turns 4 </dev/null \
      >"$WORK/harness.out" 2>&1
    rc=$? ;;
  codex)
    python3 "$HERE/fake_responses.py" 18470 "python3 gen.py out.txt" &
    model=$!
    sleep 1
    mkdir -p "$WORK/home"
    cat >"$WORK/home/config.toml" <<TOML
model = "fake"
model_provider = "fake"
[model_providers.fake]
name = "fake"
base_url = "http://127.0.0.1:18470/v1"
wire_api = "responses"
TOML
    # Hooks in CODEX_HOME: they must have been trusted to run.
    mv .codex/hooks.json "$WORK/home/hooks.json"
    timeout 90 "${clean[@]}" "CODEX_HOME=$WORK/home" codex exec \
      --skip-git-repo-check --sandbox workspace-write "Run gen.py" </dev/null \
      >"$WORK/harness.out" 2>&1
    rc=$?
    kill "$model" ;;
  *) echo "unknown harness $HARNESS"; exit 2 ;;
esac
"$BUILD/moirai-service" stop >>"$WORK/service.out" 2>&1
sleep 2

echo "$HARNESS: exit $rc, out.txt: $(cat out.txt 2>/dev/null || echo missing)"
grep -v DFTRACER "$WORK/run/hook.log" 2>/dev/null | tail -3
MOIRAI_ENABLE=0 "$PYTHON" "$HERE/check_agent.py" "$WORK/run/trace" \
  "smoke $HARNESS"$'\n' 2>&1 | grep -v DFTRACER
exit "${PIPESTATUS[0]}"
