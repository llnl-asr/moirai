"""Registers moirai's hooks with a harness, or takes them out. Merges into its
configuration, and leaves everything else there alone; a symbolic link is not
followed into a file shared with something else, it is refused. A harness has
one set of moirai's hooks: installing replaces those there.

A hook runs in the harness's environment, not this one. So everything it needs
is resolved here and written into its command, as absolute paths: the
interpreter, the hook, the run directory, the trace prefix and the ``MOIRAI_*``
settings in effect. That is how :func:`uninstall` finds the run to clean up.
"""
import json
import os
import re
import shlex
import shutil
import sys

from moirai.agent import manifest
from moirai.agent.constants import ENV_AGENT_DIR, ENV_LOG_FILE

CLAUDE_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
                 "PostToolUseFailure", "PermissionDenied", "SubagentStop", "Stop",
                 "StopFailure", "SessionEnd")
CODEX_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
                "SubagentStop", "Stop", "SessionEnd")
# What a command of moirai's runs, wherever it was installed from.
HOOK_FILE = os.path.join("moirai", "agent", "agent.py")
# What is left of a run's hooks: their state, and the files of wrapped commands.
RUN_FOLDERS = ("sessions", "runs")

# Every hook is awaited by OpenCode, without a timeout, and what one throws
# reaches the tool: so a hook only queues, catches everything and changes
# nothing it is given. One process at a time, in order, runs behind it.
OPENCODE_PLUGIN = """// moirai: agent provenance (python -m moirai.agent install opencode).
import { spawn } from "node:child_process";

const HOOK = @HOOK@;
const ENV = @ENV@;
let queue = Promise.resolve();
const run = (line) => new Promise((done) => {
  try {
    const p = spawn(HOOK[0], HOOK.slice(1), { env: { ...process.env, ...ENV }, stdio: ["pipe", "ignore", "ignore"] });
    p.on("error", done);
    p.on("close", done);
    p.stdin.on("error", () => {});
    p.stdin.end(line);
  } catch { done(); }
});
const emit = (hook) => {
  try {
    const line = JSON.stringify(hook);
    queue = queue.then(() => run(line));
  } catch {}
};

export const MoiraiProvenance = async ({ directory }) => {
  const parts = new Map();
  let session;
  const base = (sid) => {
    session = sid ?? session;
    return { session_id: session, cwd: directory };
  };
  return {
    "chat.message": async (input, output) => {
      emit({ ...base(input.sessionID), hook_event_name: "chat.message", parts: output.parts });
    },
    "tool.execute.before": async (input, output) => {
      emit({ ...base(input.sessionID), hook_event_name: "tool.before", call: input.callID, tool: input.tool, args: output.args });
    },
    "tool.execute.after": async (input, output) => {
      emit({ ...base(input.sessionID), hook_event_name: "tool.after", call: input.callID, tool: input.tool, output: output.output, metadata: output.metadata });
    },
    "experimental.chat.system.transform": async (input, output) => {
      emit({ ...base(input.sessionID), hook_event_name: "chat.system", system: output.system });
    },
    "experimental.chat.messages.transform": async (_input, output) => {
      const last = output.messages[output.messages.length - 1];
      emit({ ...base(last?.info?.sessionID), hook_event_name: "chat.messages", messages: output.messages });
    },
    event: async ({ event }) => {
      try {
        const p = event.properties ?? {};
        if (event.type === "message.part.updated") {
          const part = p.part ?? {};
          if (!parts.has(part.messageID)) parts.set(part.messageID, new Map());
          parts.get(part.messageID).set(part.id, part);
          if (part.type === "tool" && part.state?.status === "error")
            emit({ ...base(part.sessionID), hook_event_name: "tool.error", call: part.callID, error: part.state.error });
        } else if (event.type === "message.updated") {
          const info = p.info ?? {};
          if (info.role === "assistant" && info.time?.completed) {
            const done = [...(parts.get(info.id)?.values() ?? [])];
            parts.delete(info.id);
            emit({ ...base(info.sessionID), hook_event_name: "message.done", info, time: info.time, parts: done });
          }
        } else if (event.type === "session.idle" || (event.type === "session.status" && p.status?.type === "idle")) {
          emit({ ...base(p.sessionID), hook_event_name: "session.idle" });
          // opencode run leaves now: let what is queued finish, but not for long.
          await Promise.race([queue, new Promise((done) => setTimeout(done, 3000))]);
        } else if (event.type === "session.deleted") {
          emit({ ...base(p.info?.id), hook_event_name: "session.deleted" });
        }
      } catch {}
    },
  };
};
"""


def hook_argv(harness):
    """The hook, by absolute path. The interpreter is not resolved through its
    symbolic links: that would leave a virtual environment for its base."""
    here = os.path.dirname(os.path.abspath(__file__))
    return [os.path.abspath(sys.executable), os.path.join(here, "agent.py"),
            harness]


def hook_environment():
    """The settings of this run, for a process that will not inherit them."""
    import moirai

    conf = moirai.agent_configuration()
    os.makedirs(conf.dir, mode=0o700, exist_ok=True)
    env = dict(conf.settings)
    env[ENV_AGENT_DIR] = conf.dir
    env[ENV_LOG_FILE] = os.path.abspath(conf.log_file)
    return env


def hook_command(harness):
    settings = [f"{k}={v}" for k, v in sorted(hook_environment().items())]
    return shlex.join(["/usr/bin/env"] + settings + hook_argv(harness))


def hook_words(hook):
    """The words of a hook's command, ``[]`` if it has none that parse."""
    try:
        return shlex.split(str(hook.get("command", "")))
    except ValueError:
        return []


def is_moirai_hook(hook):
    return any(word.endswith(HOOK_FILE) for word in hook_words(hook))


def read_config(path):
    if os.path.islink(path):
        raise SystemExit(f"{path} is a symbolic link; change the hooks by hand")
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        return json.load(fh)


def write_config(path, config):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path + ".moirai-tmp", "w") as fh:
        json.dump(config, fh, indent=2)
        fh.write("\n")
    os.replace(path + ".moirai-tmp", path)


def drop_hooks(config):
    """Take moirai's hooks, however they were installed, out of ``config``, and
    what that leaves empty; the hooks taken."""
    taken = []
    hooks = config.get("hooks", {})
    for event in list(hooks):
        kept = []
        for group in hooks[event]:
            mine = [h for h in group.get("hooks", ()) if is_moirai_hook(h)]
            if mine:
                taken += mine
                group["hooks"] = [h for h in group["hooks"]
                                  if not is_moirai_hook(h)]
            if group.get("hooks") or not mine:
                kept.append(group)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if "hooks" in config and not hooks:
        del config["hooks"]
    return taken


def merge_hooks(path, events, command, handler, timeouts=None):
    """Make ``command`` moirai's hook in the JSON file ``path``."""
    config = read_config(path)
    drop_hooks(config)
    hooks = config.setdefault("hooks", {})
    for event in events:
        groups = hooks.setdefault(event, [])
        hook = dict(handler, command=command)
        hook["timeout"] = (timeouts or {}).get(event, hook["timeout"])
        groups.append({"matcher": "*", "hooks": [hook]})
    write_config(path, config)
    return path


def config_path(harness, scope="project", root="."):
    """Where ``harness`` keeps moirai's hooks."""
    home = os.path.expanduser("~")
    base = home if scope == "user" else os.path.abspath(root)
    if harness == "claude":
        return os.path.join(base, ".claude",
                            "settings.json" if scope == "user"
                            else "settings.local.json")
    if harness == "codex":
        return os.path.join(base, ".codex", "hooks.json")
    if harness == "opencode":
        folder = (os.path.join(home, ".config", "opencode") if scope == "user"
                  else os.path.join(base, ".opencode"))
        return os.path.join(folder, "plugin", "moirai-provenance.js")
    raise SystemExit(f"unknown harness {harness!r}")


def install(harness, scope="project", root="."):
    path = config_path(harness, scope, root)
    if harness == "claude":
        return merge_hooks(path, CLAUDE_EVENTS, hook_command("claude"),
                           {"type": "command", "timeout": 10})
    if harness == "codex":
        return merge_hooks(path, CODEX_EVENTS, hook_command("codex"),
                           {"type": "command", "timeout": 10},
                           timeouts={"SessionEnd": 3})  # Codex's limit
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(OPENCODE_PLUGIN
                 .replace("@HOOK@", json.dumps(hook_argv("opencode")))
                 .replace("@ENV@", json.dumps(hook_environment())))
    return path


def clean_run(directory):
    """Clear what the hooks of the run in ``directory`` leave behind: a session
    the harness never ended is ended. The trace, the artifacts, the manifests
    and ``hook.log`` are the record, and stay."""
    for folder in RUN_FOLDERS:
        shutil.rmtree(os.path.join(directory, folder), ignore_errors=True)
    for session in manifest.list_sessions(directory):
        if session.get("state") == "running":
            manifest.update(directory, session["session_id"], state="ended")


def remove_hooks(path):
    """Take moirai's hooks out of the JSON file ``path``, and the file if that
    empties it; the run directories they recorded to."""
    config = read_config(path)
    prefix = ENV_AGENT_DIR + "="
    directories = {word[len(prefix):] for hook in drop_hooks(config)
                   for word in hook_words(hook) if word.startswith(prefix)}
    if config:
        write_config(path, config)
    elif os.path.exists(path):
        os.unlink(path)
    return directories


def remove_plugin(path):
    """Remove the plugin ``path``, all moirai's; the run it recorded to."""
    try:
        with open(path) as fh:
            found = re.search(r"^const ENV = (.*);$", fh.read(), re.M)
    except OSError:
        return set()
    os.unlink(path)
    env = json.loads(found.group(1)) if found else {}
    return {env[ENV_AGENT_DIR]} if ENV_AGENT_DIR in env else set()


def uninstall(harness, scope="project", root="."):
    """Stop recording ``harness``: take out what :func:`install` put in, and
    clean up each run its hooks recorded to. ``(path, run directories)``."""
    path = config_path(harness, scope, root)
    directories = (remove_plugin(path) if harness == "opencode"
                   else remove_hooks(path))
    for directory in sorted(directories):
        clean_run(directory)
    return path, sorted(directories)
