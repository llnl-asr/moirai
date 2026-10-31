#!/usr/bin/env python3
"""The entry point of moirai.agent.

A harness runs this file for each event: ``<python> <this file> <harness>``, the
event's JSON on stdin. Installed by absolute path, so it finds moirai from where
it is, whatever the harness's environment and working directory. Any other
program uses :class:`AgentSession`.

A hook is a moirai process like any other: it initializes, writes through
moirai-service (or its spill file) and leaves. What must outlive it -- activities
under way, how far the transcripts were read -- is in
``<dir>/sessions/<session>.json``, under a lock, so the hooks of one session take
turns; a summary for whoever lists sessions is ``<dir>/manifests/<session>.json``
(:mod:`moirai.agent.manifest`). Nothing a hook does may reach its agent:
no output, and always exit 0.
"""
import hashlib
import json
import os
import sys
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))


class _Call:
    def __init__(self):
        self.fields = {}

    def done(self, **fields):
        self.fields = fields


class AgentSession:
    """One agent session, recorded in this process."""

    def __init__(self, harness, session, api=None, **fields):
        import moirai

        from moirai.agent.recorder import Recorder

        self.recorder = Recorder(api or moirai)
        self.base = {"harness": harness, "session": session}
        self.fields = fields

    def _emit(self, kind, **fields):
        self.recorder.handle(dict(self.base, kind=kind, **fields))

    def __enter__(self):
        self._emit("session.start", **self.fields)
        return self

    def __exit__(self, *exc):
        self._emit("session.end")
        return False

    @contextmanager
    def turn(self, prompt):
        self._emit("turn.start", prompt=prompt)
        try:
            yield
        finally:
            self._emit("turn.end")

    @contextmanager
    def llm(self, call, request=None, model=None):
        self._emit("llm.start", call=call, model=model)
        c = _Call()
        try:
            yield c
        finally:
            self._emit("llm.end", call=call, model=model, request=request,
                       **c.fields)

    @contextmanager
    def tool(self, call, name, input=None, **fields):
        self._emit("tool.start", call=call, name=name, input=input, **fields)
        c = _Call()
        try:
            yield c
        finally:
            self._emit("tool.end", call=call, **c.fields)


def state_paths(directory, sid):
    # Session ids come from the harness: a name, not a path.
    name = hashlib.sha256(str(sid).encode()).hexdigest()[:32]
    folder = os.path.join(directory, "sessions")
    os.makedirs(folder, mode=0o700, exist_ok=True)
    return os.path.join(folder, name + ".json"), os.path.join(folder,
                                                              name + ".lock")


def load(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save(path, state):
    fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(state, fh)
    os.replace(path + ".tmp", path)


def trace_io(conf, harness, hook, event):
    """For a shell tool, when ``MOIRAI_AGENT_TRACE_IO`` is on: the command
    rewritten to run under dftracer's preload (``event`` learns its run), and
    the reply that has the harness run it. ``None`` leaves the command as it is."""
    from moirai.agent import trace_io as tio

    tool_input = event.get("input")
    if (harness not in tio.HARNESSES or event.get("kind") != "tool.start"
            or str(hook.get("tool_name")).lower() not in tio.SHELL_TOOLS
            or tio.command_key(tool_input) is None
            or not tio.enabled(conf)):
        return None
    prepared = tio.prepare(conf, hook.get("session_id"), event.get("call"),
                           tool_input[tio.command_key(tool_input)])
    if prepared is None:
        return None
    event["run"] = prepared[0]
    return tio.reply(tool_input, prepared[1])


def write_manifests(directory, recorder, sessions):
    """Update the manifest of each session this hook touched (see
    :mod:`moirai.agent.manifest`). A manifest is a convenience: it never costs
    the hook its record."""
    from moirai.agent import manifest

    for state, group in (("running", sessions), ("ended", recorder.finished)):
        for session in list(group.values()):
            try:
                fields = manifest.from_session(session, state)
                manifest.update(directory, fields.pop("session_id"), **fields)
            except Exception as e:  # noqa: BLE001
                print(f"moirai hook: manifest: {e!r}", file=sys.stderr)


def record(harness, hook):
    """Records the hook; returns what the harness is to be told, if anything."""
    import fcntl

    import moirai

    from moirai.agent.adapters import ADAPTERS
    from moirai.agent.recorder import Recorder

    conf = moirai.agent_configuration()
    path, lock = state_paths(conf.dir, hook.get("session_id"))
    answer = None
    with open(lock, "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        state = load(path)
        moirai.initialize(conf.log_file)
        try:
            adapter = ADAPTERS[harness](state.get("adapter"))
            sessions = state.get("sessions", {})
            recorder = Recorder(moirai, sessions=sessions)
            for event in adapter.translate(hook):
                answer = trace_io(conf, harness, hook, event) or answer
                recorder.handle(event)
        finally:
            moirai.finalize()
        write_manifests(conf.dir, recorder, sessions)
        if sessions:
            save(path, {"sessions": sessions, "adapter": adapter.state()})
        else:
            try:
                os.unlink(path)
            except OSError:
                pass
    return answer


def main():
    # dftracer reports on stdout and stderr, which would reach the harness: they
    # are the log's, and only an answer the harness asked for goes to its own.
    log = None
    try:
        import moirai

        directory = moirai.agent_configuration().dir
        os.makedirs(directory, mode=0o700, exist_ok=True)
        log = os.open(os.path.join(directory, "hook.log"),
                      os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        out = os.dup(1)
        os.dup2(log, 1)
        os.dup2(log, 2)
        answer = record(sys.argv[1], json.load(sys.stdin))
        if answer is not None:
            os.write(out, json.dumps(answer).encode())
    except Exception as e:  # noqa: BLE001
        if log is not None:
            os.write(log, f"moirai hook: {e!r}\n".encode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
