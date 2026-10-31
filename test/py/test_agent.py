#!/usr/bin/env python3
"""The agent interface end to end, as a harness drives it: the installed hook
command, by absolute path and with nothing inherited, with payloads of each
harness's shape, into a trace; then the walk from a file the agent wrote back to
the prompt, and the content of each step out of the artifact store."""
import glob
import gzip
import json
import os
import subprocess
import shlex
import sys

import moirai
from moirai.agent.install import hook_command

work = os.environ["MOIRAI_TEST_DATA"]
os.environ["MOIRAI_AGENT_DIR"] = os.path.join(work, "run")
os.environ.pop("MOIRAI_LOG_FILE", None)
prefix = os.path.join(work, "run", "trace")
SECRET = "sk-" + "a" * 30


def expect(condition, what):
    if not condition:
        sys.exit(f"agent test failed: {what}")


COMMANDS = {h: hook_command(h) for h in ("claude", "codex", "opencode")}
for command in COMMANDS.values():
    words = shlex.split(command)
    for path in [w for w in words if "=" not in w and not w.isalpha()]:
        expect(os.path.isabs(path), f"not absolute: {path}")
    expect(f"MOIRAI_AGENT_DIR={os.environ['MOIRAI_AGENT_DIR']}" in words,
           "the run directory is in the command")


def hook(harness, payload):
    # What the harness runs: no PYTHONPATH, another working directory.
    env = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/")}
    r = subprocess.run(shlex.split(COMMANDS[harness]), env=env, cwd="/",
                       input=json.dumps(payload).encode(), capture_output=True,
                       check=False)
    expect(r.returncode == 0 and not r.stdout and not r.stderr,
           f"hook output: {r}")


def assistant(request, content, model="claude-x"):
    return {"type": "assistant", "requestId": request, "timestamp": "t",
            "message": {"model": model, "content": content, "id": request,
                        "stop_reason": "tool_use",
                        "usage": {"input_tokens": 5}}}


# -- Claude Code: hooks, and the transcript for what the model said.
transcript = os.path.join(work, "claude.jsonl")
out = os.path.join(work, "out.txt")
script = os.path.join(work, "gen.py")
with open(script, "w") as f:
    f.write("print('generated')\n")
common = {"session_id": "s1", "transcript_path": transcript, "cwd": work}
line = f"python3 {script} > {out}"
hook("claude", dict(common, hook_event_name="SessionStart", source="startup"))
hook("claude", dict(common, hook_event_name="UserPromptSubmit",
                    prompt="make out.txt"))
with open(transcript, "a") as f:
    for r in ({"type": "user", "message": {"content": "make out.txt"}},
              assistant("r1", [{"type": "thinking", "thinking": "plan"}]),
              assistant("r1", [{"type": "tool_use", "id": "t1", "name": "Bash",
                                "input": {"command": line}}])):
        f.write(json.dumps(r) + "\n")
hook("claude", dict(common, hook_event_name="PreToolUse", tool_name="Bash",
                    tool_use_id="t1", tool_input={"command": line}))
with open(out, "w") as f:
    f.write("generated\n")
hook("claude", dict(common, hook_event_name="PostToolUse", tool_name="Bash",
                    tool_use_id="t1", tool_input={"command": line},
                    tool_response={"stdout": f"key={SECRET}", "exit_code": 0}))
with open(transcript, "a") as f:
    for r in ({"type": "user", "message": {"content": [
                  {"type": "tool_result", "tool_use_id": "t1",
                   "content": "ok"}]}},
              assistant("r2", [{"type": "text", "text": "done"}])):
        f.write(json.dumps(r) + "\n")
hook("claude", dict(common, hook_event_name="Stop",
                    last_assistant_message="done"))
hook("claude", dict(common, hook_event_name="SessionEnd", reason="other"))

# -- Codex: the same hooks, a rollout of its own.
rollout = os.path.join(work, "rollout.jsonl")
with open(rollout, "w") as f:
    # In the order of a rollout of codex-cli 0.146: a tool's output is written
    # before the token_count that ends the response which called it.
    for r in ({"type": "session_meta", "payload": {
                  "base_instructions": "codex system prompt"}},
              {"type": "response_item", "payload": {
                  "type": "message", "role": "developer", "content": "rules"}},
              {"type": "turn_context", "payload": {"model": "gpt-x"}},
              {"type": "response_item", "payload": {
                  "type": "message", "role": "user", "content": "hi"}},
              {"type": "response_item", "payload": {
                  "type": "function_call", "name": "exec_command",
                  "call_id": "c1", "arguments": "{}"}},
              {"type": "response_item", "payload": {
                  "type": "function_call_output", "call_id": "c1",
                  "output": "ok"}},
              {"type": "event_msg", "payload": {
                  "type": "token_count",
                  "info": {"last_token_usage": {"input_tokens": 3}}}},
              {"type": "response_item", "payload": {
                  "type": "message", "role": "assistant", "content": "done"}},
              {"type": "event_msg", "payload": {
                  "type": "token_count",
                  "info": {"last_token_usage": {"input_tokens": 4}}}}):
        f.write(json.dumps(r) + "\n")
codex = {"session_id": "s2", "transcript_path": rollout, "cwd": work,
         "model": "gpt-x"}
hook("codex", dict(codex, hook_event_name="UserPromptSubmit", prompt="hi"))
hook("codex", dict(codex, hook_event_name="PreToolUse", tool_name="Bash",
                   tool_use_id="c1", tool_input={"command": "true"}))
hook("codex", dict(codex, hook_event_name="PostToolUse", tool_name="Bash",
                   tool_use_id="c1", tool_input={"command": "true"},
                   tool_response="ok"))
hook("codex", dict(codex, hook_event_name="Stop"))
hook("codex", dict(codex, hook_event_name="SessionEnd"))

# -- OpenCode: its plugin's payloads.
open_common = {"session_id": "s3", "cwd": work}
for payload in (
        {"hook_event_name": "chat.message",
         "parts": [{"type": "text", "text": "hey"}]},
        {"hook_event_name": "chat.system",
         "system": ["opencode system prompt"]},
        {"hook_event_name": "chat.messages",
         "messages": [{"info": {"id": "u1", "role": "user"},
                       "parts": [{"type": "text",
                                  "text": "opencode history"}]}]},
        {"hook_event_name": "tool.before", "call": "o2", "tool": "bash",
         "args": {"command": "true"}},
        {"hook_event_name": "tool.error", "call": "o2", "error": "rejected"},
        {"hook_event_name": "tool.before", "call": "o1", "tool": "bash",
         "args": {"command": "true"}},
        {"hook_event_name": "tool.after", "call": "o1", "tool": "bash",
         "output": "ok", "metadata": {"exit": 0}},
        {"hook_event_name": "message.done",
         "info": {"id": "m1", "modelID": "o-x"},
         "time": {"created": 1, "completed": 2},
         "parts": [{"type": "text", "text": "hello"}]},
        {"hook_event_name": "session.idle"},
        {"hook_event_name": "session.deleted"}):
    hook("opencode", dict(open_common, **payload))

records = []
for path in glob.glob(prefix + "*.pfw.gz"):
    with gzip.open(path, "rt", errors="replace") as fh:
        for raw in fh:
            raw = raw.strip().rstrip(",")
            if raw.startswith("{"):
                records.append(json.loads(raw))
text = json.dumps(records)
expect(SECRET not in text, "a secret in the trace")
expect("make out.txt" not in text, "a prompt in the trace")

entities = {r["args"]["id"]: r["args"] for r in records if r["name"] == "EH"}
activities = [r for r in records if r.get("cat") == "moirai"]
for a in activities:
    args = a["args"]
    expect(0 < args["start_us"] <= args["end_us"], f"the span of {a['name']}")
expect(os.listdir(prefix + ".artifacts") == [os.uname().nodename],
       "the hooks share the node's artifact store")
expect(not os.listdir(os.path.join(work, "run", "sessions")) or all(
    n.endswith(".lock")
    for n in os.listdir(os.path.join(work, "run", "sessions"))),
       "no session left open")
names = sorted(a["name"] for a in activities)
for name, count in (("agent.session", 3), ("agent.turn", 3), ("llm.call", 5),
                    ("tool.Bash", 2), ("tool.bash", 2)):
    expect(names.count(name) == count, f"{name}: {names}")
expect(names.count(name) == count, f"{name}: {names}")
requests = [e for e in entities.values() if e["type"] == "llm.request"]
expect(len(requests) == names.count("llm.call"),
       f"a request for each call: {len(requests)}")


def relations(kind):
    return [(a, e) for a in activities
            for e in (a["args"].get("relations") or {}).get(kind, ())]


# Back from the file the agent wrote to the prompt.
generated = {}
for a, e in relations("generated"):
    generated.setdefault(e, []).append(a)
files = [i for i, e in entities.items() if e["type"] == "file"]
written = [i for i in files if i in generated]
expect(len(written) == 1, f"one file written: {written}")
seen, frontier, kinds = set(), written, set()
while frontier:
    entity = frontier.pop()
    if entity in seen:
        continue
    seen.add(entity)
    kinds.add(entities[entity]["type"])
    for a in generated.get(entity, ()):
        frontier += (a["args"].get("relations") or {}).get("used", [])
for kind in ("file", "tool.input", "llm.request", "agent.prompt", "tool.script"):
    expect(kind in kinds, f"{kind} not in the lineage: {kinds}")

# Usage is of the response it closes, also when a tool's output came between.
responses = [json.loads(c) for c in (
    moirai.read_artifact(e["uri"], prefix) for e in entities.values()
    if e["type"] == "llm.response")]
expect({"input_tokens": 3} in [r.get("usage") for r in responses],
       "the usage of a Codex response that called a tool")

# And each step's content out of the store.
contents = [moirai.read_artifact(e["uri"], prefix) for e in entities.values()
            if e["uri"].startswith("artifact://")]
blob = b"\n".join(c for c in contents if c)
for needle in (b"make out.txt", b"print('generated')", b"[REDACTED:api-key]",
               b"plan", line.encode(), b"codex system prompt",
               b"opencode system prompt", b"opencode history", b"rejected"):
    expect(needle in blob, f"{needle} is not in the store")
expect(SECRET.encode() not in blob, "a secret in the store")
