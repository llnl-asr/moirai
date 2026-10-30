#!/usr/bin/env python3
"""Runs one shell command with dftracer's preload library, for
``MOIRAI_AGENT_TRACE_IO`` (:mod:`moirai.agent.trace_io`).

``run.py <run file> -- <command>``. A standalone script by design: it imports
nothing of moirai and does nothing but set up an environment, so that it adds
nothing to the I/O it is there to record, and then replaces itself by the
shell: the command runs as this process, with this pid, and its exit status is
this one's. Whatever goes wrong here, the command still runs, untraced.
"""
import json
import os
import socket
import sys
import time


def shell():
    """The shell the harness would have used, which understands the line."""
    names = ("bash", "zsh", "sh", "dash", "ksh")
    mine = os.environ.get("SHELL", "")
    if os.path.basename(mine) in names and os.access(mine, os.X_OK):
        return mine
    for path in ("/bin/bash", "/usr/bin/bash", "/bin/sh"):
        if os.access(path, os.X_OK):
            return path
    return "/bin/sh"


def merge(first, *rest):
    out = []
    for part in (first,) + rest:
        for item in part.split(":") if part else ():
            if item and item not in out:
                out.append(item)
    return ":".join(out)


def main():
    run, command = sys.argv[1], sys.argv[3]
    sh = shell()
    env = dict(os.environ)
    try:
        with open(run) as fh:
            spec = json.load(fh)
        env.update(spec["env"])
        env["LD_PRELOAD"] = merge(spec["preload"], spec.get("ld_preload", ""),
                                  env.get("LD_PRELOAD", ""))
        path = merge(env.get("LD_LIBRARY_PATH", ""),
                     spec.get("ld_library_path", ""))
        if path:
            env["LD_LIBRARY_PATH"] = path
        info = {"pid": os.getpid(), "start_us": int(time.time() * 1e6),
                "host": socket.gethostname(), "shell": sh}
        pid = run[:-len(".json")] + ".pid"
        with open(pid + ".tmp", "w") as fh:
            json.dump(info, fh)
        os.replace(pid + ".tmp", pid)
    except Exception:  # noqa: BLE001
        env = dict(os.environ)
    os.execve(sh, [sh, "-c", command], env)


if __name__ == "__main__":
    main()
