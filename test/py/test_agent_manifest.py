#!/usr/bin/env python3
"""Against the real native module: the installed hook writes the session
manifest, the sensitive-paths setting reaches agent_configuration and the hook
command, a sensitive file is not copied, install and uninstall work on each
harness, and read_text reads a stored payload."""
import glob
import json
import os
import shlex
import subprocess
import sys

import moirai
from moirai.agent import artifacts, manifest, redact

work = os.environ["MOIRAI_TEST_DATA"]
os.environ["MOIRAI_AGENT_DIR"] = os.path.join(work, "run")
SENSITIVE = "# mine\nprivate*\n!*token*"
os.environ["MOIRAI_AGENT_SENSITIVE_PATHS"] = SENSITIVE
os.environ.pop("MOIRAI_LOG_FILE", None)
prefix = os.path.join(work, "run", "trace")
SECRET = "sk-" + "a" * 30


def expect(condition, what):
    if not condition:
        sys.exit(f"agent manifest test failed: {what}")


from moirai.agent.install import hook_command  # noqa: E402

expect(moirai.agent_configuration().sensitive_paths == SENSITIVE,
       "agent_configuration().sensitive_paths")
expect(redact.is_sensitive_path("/w/private.txt")
       and not redact.is_sensitive_path("/w/tokenizer.json"),
       "the default globs are the setting's")
command = hook_command("claude")
expect(f"MOIRAI_AGENT_SENSITIVE_PATHS={SENSITIVE}" in shlex.split(command),
       "the setting is baked into the hook command")


def hook(payload):
    env = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/")}
    # The loader's settings are the platform's, not moirai's.
    env.update({k: v for k, v in os.environ.items()
                if k in ("LD_LIBRARY_PATH", "LD_PRELOAD")})
    r = subprocess.run(shlex.split(command), env=env, cwd="/",
                       input=json.dumps(payload).encode(), capture_output=True)
    expect(r.returncode == 0 and not r.stdout and not r.stderr, f"hook: {r}")


secret_file = os.path.join(work, "private.txt")
with open(secret_file, "w") as fh:
    fh.write("hunter2-content\n")
common = {"session_id": "m1", "transcript_path": os.path.join(work, "t.jsonl"),
          "cwd": work}
open(common["transcript_path"], "w").close()
hook(dict(common, hook_event_name="SessionStart", source="startup"))
m = manifest.read("m1", os.path.join(work, "run"))
expect(m and m["state"] == "running" and m["harness"] == "claude", f"start {m}")
expect(manifest.recording(), "a session is in flight")
hook(dict(common, hook_event_name="UserPromptSubmit",
          prompt=f"read it  {SECRET}"))
hook(dict(common, hook_event_name="PreToolUse", tool_name="Bash",
          tool_use_id="t1", tool_input={"command": f"cat {secret_file}"}))
hook(dict(common, hook_event_name="PostToolUse", tool_name="Bash",
          tool_use_id="t1", tool_input={"command": f"cat {secret_file}"},
          tool_response={"stdout": "x"}))
m = manifest.read("m1")
expect(m["turns"] == 1 and m["name"] == "read it [REDACTED:api-key]", f"{m}")
expect(len(m["entity"]) == 16 and m["activities"] >= 1, f"{m}")
hook(dict(common, hook_event_name="SessionEnd"))
m = manifest.read("m1")
expect(m["state"] == "ended", f"end {m}")
expect(not manifest.recording(), "nothing in flight")
expect([x["session_id"] for x in manifest.list_sessions()] == ["m1"], "list")

# Installed for real, installing again leaves one set, and uninstall takes it.
from moirai.agent.install import config_path, install, uninstall  # noqa: E402

for harness in ("claude", "codex", "opencode"):
    install(harness, root=work)
    path = install(harness, root=work)
    if harness != "opencode":
        with open(path) as fh:
            hooks = json.load(fh)["hooks"]
        expect(all(len(groups) == 1 for groups in hooks.values()),
               f"{harness}: one set of hooks")
    expect(path == config_path(harness, root=work), f"{harness}: path")
    expect(uninstall(harness, root=work) == (path, [os.path.join(work, "run")]),
           f"{harness}: uninstall found the run")
    expect(not os.path.exists(path), f"{harness}: nothing left")

# A stored payload is readable in process (the active store: prefix "").
moirai.initialize()
text = artifacts.read_text(moirai.store_artifact("hello \u00e9").uri + "@x", "")
expect(text == "hello \u00e9", f"read_text {text!r}")
expect(artifacts.read_text("artifact://0000000000000000", "") is None,
       "absent is None")
moirai.finalize()
