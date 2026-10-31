"""The real file I/O of a shell tool's command, in the same trace.

Opt-in (``MOIRAI_AGENT_TRACE_IO=1``): the PreToolUse hook of a shell tool
rewrites the command so that it runs under :mod:`moirai.agent.run`, which starts
it with dftracer's preload library (``libdftracer_preload.so``) writing through
the same ``moirai-service`` ring and trace prefix as the hooks. Every process the
command starts then records its POSIX and STDIO calls as ordinary dftracer
events.

Which call a process belongs to is the ``tool.process`` entity the call's
``tool.<name>`` activity generated: its key and URI name the pid of the process
the command ran as (the wrapper ``exec``s into the shell, so that pid is the
shell's), and ``docs/agents.rst`` says how to walk down from it.

Returning ``updatedInput`` with ``permissionDecision: allow`` is what makes the
harness run the rewritten command, and it also skips the harness's own approval
of it: this is why it is never on by default.
"""
import hashlib
import json
import os
import re
import shlex
import socket
import sys
import time

from moirai.agent.constants import (ENV_AGENT_PRELOAD, ENV_AGENT_TRACE_IO,
                                    ENV_ENABLE)

HARNESSES = ("claude", "codex")
# Codex names its command tools variously; Claude Code's is Bash.
SHELL_TOOLS = ("bash", "shell", "shell_command", "exec_command", "local_shell",
               "container.exec", "unified_exec")
KEYS = ("command", "cmd")
STALE = 24 * 3600


def command_key(tool_input):
    """The field of a tool's input holding its command (a line, or an argv
    list), or ``None``: then the call is not a command."""
    if not isinstance(tool_input, dict):
        return None
    for key in KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) or (isinstance(value, list) and value and
                                      all(isinstance(w, str) for w in value)):
            return key
    return None


def enabled(conf):
    """Whether this run traces the I/O of shell commands: the setting, off by
    default, read from the settings the hook was installed with."""
    settings = dict(conf.settings)
    off = ("", "0", "false", "off", "no")
    return (settings.get(ENV_AGENT_TRACE_IO, "").strip().lower() not in off
            and settings.get(ENV_ENABLE, "1").strip().lower() not in off)


def preload_library(conf):
    """dftracer's preload library: ``MOIRAI_AGENT_PRELOAD``, else the one beside
    the dftracer core library this process runs on (the build, or the install,
    that moirai was linked with). ``None`` if there is none."""
    explicit = dict(conf.settings).get(ENV_AGENT_PRELOAD)
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    try:
        with open("/proc/self/maps") as fh:
            maps = fh.read()
    except OSError:
        return None
    for path in dict.fromkeys(re.findall(r"(/\S*libdftracer_core\S*\.so\S*)",
                                         maps)):
        name = os.path.basename(path)
        suffix = "_dbg" if name.startswith("libdftracer_core_dbg") else ""
        here = os.path.dirname(path)
        for folder in (here, os.path.join(here, "..", "lib64"),
                       os.path.join(here, "..", "lib")):
            candidate = os.path.normpath(
                os.path.join(folder, f"libdftracer_preload{suffix}.so"))
            if os.path.isfile(candidate):
                return candidate
    return None


def child_environment(conf):
    """dftracer's settings for the processes of a command: those
    ``ConfigurationManager`` translated, except that the command is traced by
    preload and its I/O is traced whatever ``MOIRAI_TRACE_IO`` says about the
    hooks."""
    env = dict(conf.dftracer_settings)
    env.update(DFTRACER_ENABLE="1", DFTRACER_ENABLE_PC_MODE="1",
               DFTRACER_INIT="PRELOAD", DFTRACER_DISABLE_IO="0",
               DFTRACER_LOG_FILE=os.path.abspath(conf.log_file))
    env.setdefault("DFTRACER_DATA_DIR", "all")
    return env


def runs_dir(conf):
    path = os.path.join(conf.dir, "runs")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _sweep(folder):
    horizon = time.time() - STALE
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        try:
            if os.stat(path).st_mtime < horizon:
                os.unlink(path)
        except OSError:
            pass


def prepare(conf, session, call, command):
    """``(run file, rewritten command)`` for ``command``, or ``None`` when it
    cannot be traced (no preload library): the command then runs as it was."""
    library = preload_library(conf)
    if library is None:
        return None
    folder = runs_dir(conf)
    _sweep(folder)
    token = hashlib.sha256(
        f"{session}/{call}/{time.time_ns()}".encode()).hexdigest()[:20]
    run = os.path.join(folder, token + ".json")
    spec = {"preload": library, "env": child_environment(conf),
            # What made moirai load in the hook is what its library needs.
            "ld_library_path": os.environ.get("LD_LIBRARY_PATH", ""),
            "ld_preload": os.environ.get("LD_PRELOAD", "")}
    fd = os.open(run, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(spec, fh)
    runner = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.py")
    line = command if isinstance(command, str) else shlex.join(command)
    argv = [os.path.abspath(sys.executable), runner, run, "--", line]
    return run, (shlex.join(argv) if isinstance(command, str) else argv)


def reply(tool_input, command):
    """The hook's answer that makes the harness run ``command`` instead (a
    line, or an argv list where the tool's own was one)."""
    updated = dict(tool_input)
    updated[command_key(tool_input)] = command
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "allow",
        "permissionDecisionReason":
            "moirai: MOIRAI_AGENT_TRACE_IO runs this command under dftracer",
        "updatedInput": updated}}


def process(run):
    """What the wrapper recorded of the command it ran, ``None`` if it did not
    run (refused, or not started). Removes the run's files."""
    info = None
    try:
        with open(run[:-len(".json")] + ".pid") as fh:
            info = json.load(fh)
    except (OSError, ValueError):
        pass
    for path in (run, run[:-len(".json")] + ".pid"):
        try:
            os.unlink(path)
        except OSError:
            pass
    if isinstance(info, dict) and isinstance(info.get("pid"), int):
        info["host"] = socket.gethostname()
        return info
    return None
