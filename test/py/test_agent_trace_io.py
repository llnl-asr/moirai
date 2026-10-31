#!/usr/bin/env python3
"""MOIRAI_AGENT_TRACE_IO end to end, against a running moirai-service (run by
run_case.sh in service mode): the PreToolUse hook of a Codex shell tool rewrites
the command to run under dftracer's preload; the command's own processes write
their POSIX calls into the node trace, and the ``tool.process`` entity of the
call's activity names the process they descend from. Without the setting the
hook answers nothing."""
import gzip
import json
import os
import shlex
import socket
import subprocess
import sys
import time
import zlib

import moirai
from moirai.agent import trace_io
from moirai.agent.install import hook_command

work = os.environ["MOIRAI_TEST_DATA"]
prefix = os.environ["MOIRAI_LOG_FILE"]
trace = f"{prefix}_{socket.gethostname()}.pfw.gz"
os.environ["MOIRAI_AGENT_DIR"] = os.path.join(work, "run")
os.environ["MOIRAI_AGENT_TRACE_IO"] = "1"
os.environ["MOIRAI_TRACE_IO"] = "0"  # the hooks themselves are not traced


def expect(condition, what):
    if not condition:
        sys.exit(f"agent trace_io test failed: {what}")


if trace_io.preload_library(moirai.agent_configuration()) is None:
    print("no libdftracer_preload.so beside the dftracer core library")
    sys.exit(77)

ON = shlex.split(hook_command("codex"))
# The settings are read once per process: the same installation without it.
OFF = [w for w in ON if w != "MOIRAI_AGENT_TRACE_IO=1"]
expect("MOIRAI_AGENT_TRACE_IO=1" in ON and len(OFF) == len(ON) - 1,
       "the setting is baked into the installed command")

# What the harness's processes inherit, as far as moirai needs it to load.
BARE = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/")}
for name in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
    if name in os.environ:
        BARE[name] = os.environ[name]


def hook(command, payload):
    r = subprocess.run(command, env=BARE, cwd=work, capture_output=True,
                       input=json.dumps(payload).encode(), check=False)
    expect(r.returncode == 0 and not r.stderr, f"hook failed: {r}")
    return r.stdout


gen = os.path.join(work, "gen.py")
with open(gen, "w") as f:
    f.write("import sys\nopen(sys.argv[1], 'w').write('hello\\n' * 1000)\n")
SPAWN = "sh -c 'python3 gen.py out.txt; cat out.txt | wc -l'"
common = {"session_id": "t1", "cwd": work, "model": "gpt-x",
          "transcript_path": os.path.join(work, "rollout.jsonl")}


def tool(command, call, line):
    payload = dict(common, tool_name="Bash", tool_use_id=call,
                   tool_input={"command": line})
    return payload


# -- With the setting off, a shell tool is not touched.
hook(OFF, dict(common, hook_event_name="SessionStart"))
hook(OFF, dict(common, hook_event_name="UserPromptSubmit", prompt="plain"))
expect(not hook(OFF, dict(tool(OFF, "p1", "true"), hook_event_name="PreToolUse")),
       "an answer with the setting off")
hook(OFF, dict(tool(OFF, "p1", "true"), hook_event_name="PostToolUse",
               tool_response="ok"))
hook(OFF, dict(common, hook_event_name="Stop"))
hook(OFF, dict(common, hook_event_name="SessionEnd"))

# -- With it on: the answer, the rewritten command, and its run.
common["session_id"] = "t2"
hook(ON, dict(common, hook_event_name="SessionStart"))
hook(ON, dict(common, hook_event_name="UserPromptSubmit", prompt="make out.txt"))
answer = json.loads(hook(ON, dict(tool(ON, "c1", SPAWN),
                                  hook_event_name="PreToolUse")))
out = answer["hookSpecificOutput"]
expect(out["hookEventName"] == "PreToolUse" and
       out["permissionDecision"] == "allow", f"the answer: {answer}")
rewritten = out["updatedInput"]["command"]
words = shlex.split(rewritten)
expect(words[1].endswith("moirai/agent/run.py") and words[3] == "--"
       and words[4] == SPAWN, f"the rewritten command: {rewritten}")
r = subprocess.run(["bash", "-c", rewritten], env=BARE, cwd=work,
                   capture_output=True, check=False)
expect(r.returncode == 0 and r.stdout.strip() == b"1000",
       f"the command ran as it was: {r}")
hook(ON, dict(tool(ON, "c1", SPAWN), hook_event_name="PostToolUse",
              tool_response={"stdout": "1000", "exit_code": 0}))
hook(ON, dict(common, hook_event_name="Stop"))
hook(ON, dict(common, hook_event_name="SessionEnd"))

# Codex's other command tools: a "cmd" line, an argv list; not a file tool.
for name, key, value in (("exec_command", "cmd", "echo a | wc -c"),
                         ("shell", "command", ["bash", "-lc", "echo a"])):
    payload = dict(common, session_id="t4", hook_event_name="PreToolUse",
                   tool_name=name, tool_use_id="x" + name,
                   tool_input={key: value, "workdir": work})
    updated = json.loads(hook(ON, payload))["hookSpecificOutput"][
        "updatedInput"]
    new = updated[key]
    expect(updated["workdir"] == work and
           type(new) is type(value) and (shlex.split(new) if isinstance(
               new, str) else new)[3:] == ["--", shlex.join(value) if
                                          isinstance(value, list) else value],
           f"{name}: {updated}")
    hook(ON, dict(payload, hook_event_name="PostToolUse", tool_response="ok"))
expect(not hook(ON, dict(common, session_id="t4", hook_event_name="PreToolUse",
                         tool_name="apply_patch", tool_use_id="p",
                         tool_input={"input": "x"})), "a file tool is left alone")
hook(ON, dict(common, session_id="t4", hook_event_name="SessionEnd"))

# Claude Code answers in the same form and keeps the rest of the input; a call
# that never ran (refused) leaves no process and no run file.
claude = dict(common, session_id="t3", hook_event_name="PreToolUse",
              tool_name="Bash", tool_use_id="k1",
              tool_input={"command": "true", "description": "d", "timeout": 5})
updated = json.loads(hook(ON[:-1] + ["claude"], claude))[
    "hookSpecificOutput"]["updatedInput"]
expect(updated["description"] == "d" and updated["timeout"] == 5 and
       updated["command"].endswith("-- true"), f"claude's input: {updated}")
hook(ON[:-1] + ["claude"], dict(claude, hook_event_name="PermissionDenied",
                                error="refused"))
hook(ON[:-1] + ["claude"], dict(common, session_id="t3",
                                hook_event_name="SessionEnd"))
expect(not os.listdir(os.path.join(work, "run", "runs")),
       "no run files left behind")
expect(not os.listdir(os.path.join(work, "run", "runs")),
       "no run files left behind")


# -- The node trace, while the service runs: whole gzip members.
def records():
    with open(trace, "rb") as fh:
        data = fh.read()
    out, used = [], 0
    while used < len(data):
        d = zlib.decompressobj(zlib.MAX_WBITS | 16)
        try:
            text = d.decompress(data[used:])
        except zlib.error:
            break
        if not d.eof:
            break
        used = len(data) - len(d.unused_data)
        for line in text.splitlines():
            line = line.strip().rstrip(b",")
            if line.startswith(b"{"):
                out.append(json.loads(line))
    return out


def wanted(recs):
    names = [r["name"] for r in recs if r.get("cat") == "moirai"]
    ends = [r for r in recs if r["name"] == "end" and r.get("cat") == "dftracer"
            and r.get("pid", 0) != 0]
    return names.count("tool.Bash") == 3 and len(ends) >= 3 and any(
        r["name"] == "write" for r in recs)


deadline = time.monotonic() + 30
while True:
    recs = records()
    if wanted(recs) or time.monotonic() > deadline:
        break
    time.sleep(0.2)

entities = {r["args"]["id"]: r["args"] for r in recs if r["name"] == "EH"}
calls = [r for r in recs if r["name"] == "tool.Bash"]
expect(len(calls) == 3, f"three tool.Bash activities: {len(calls)}")



def generated(activity):
    return [entities[e] for e in
            (activity["args"].get("relations") or {}).get("generated", ())
            if e in entities]


procs = [e for a in calls for e in generated(a) if e["type"] == "tool.process"]
expect(len(procs) == 1, f"one tool.process, for the one traced call: {procs}")
span = [a for a in calls if procs[0]["id"] in
        a["args"]["relations"]["generated"]][0]["args"]
host, root = procs[0]["uri"][len("process://"):].split("/")
root = int(root)
expect(host == socket.gethostname(), "the process is on this host")

# The processes under the root: dftracer's start record of each has its ppid.
parents = {r.get("pid", 0): r["args"]["ppid"] for r in recs
           if r["name"] == "start" and r.get("cat") == "dftracer"
           and r.get("pid", 0) != 0}
mine = {root}
while True:
    more = {p for p, parent in parents.items() if parent in mine} - mine
    if not more:
        break
    mine |= more
expect(root in parents, "the root process was traced by the preload")
starts = [r["ts"] for r in recs if r["name"] == "start" and r.get("pid") == root]
expect(starts and all(span["start_us"] <= t <= span["end_us"] for t in starts),
       "the root started within the activity's span")
expect(len(mine) >= 3, f"the command's children were traced: {sorted(mine)}")

# Files are named by FH records: hash -> path.
names = {r["args"]["value"]: r["args"]["name"] for r in recs
         if r["name"] == "FH"}
target = os.path.join(work, "out.txt")
# dftracer names the path as the program opened it: the real one (MOIRAI_DATA_DIR
# has both spellings of a directory reached through a symbolic link).
ours = [h for h, n in names.items() if n in (target, os.path.realpath(target))]
expect(len(ours) == 1, "out.txt is named in the trace")
seen = {}
for r in recs:
    if (r.get("cat") in ("POSIX", "STDIO") and r.get("pid", 0) in mine
            and r["args"].get("fhash") == ours[0]):
        seen.setdefault(r.get("pid", 0), set()).add(r["name"])
writers = [p for p, n in seen.items() if n & {"write", "fwrite", "write64"}]
readers = [p for p, n in seen.items() if n & {"read", "fread"}]
expect(writers and readers and set(writers).isdisjoint(readers),
       f"a child wrote out.txt and another read it: {seen}")
# And no process outside the call touched it.
elsewhere = {r.get("pid", 0) for r in recs
             if r.get("cat") in ("POSIX", "STDIO")
             and r["args"].get("fhash") == ours[0]} - mine
expect(not elsewhere, f"only the call's processes: {elsewhere}")
print("agent trace_io ok:", root, sorted(seen))
