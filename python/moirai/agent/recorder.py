"""Agent events to provenance, on moirai's own API.

The harness-neutral core. An event is a dict with a ``kind`` and a ``session``;
the adapters (:mod:`moirai.agent.adapters`) make them from a harness's hooks,
and :class:`moirai.agent.AgentSession` from any other program.

=============== ==============================================================
kind            fields
=============== ==============================================================
session.start   harness, cwd, model
session.end
turn.start      prompt
turn.end        reply
llm.start       call, model
llm.end         call, model, request (the new messages), response, tool_calls
                ([{id, name, input}]), tool_results ([id]), usage, stop_reason,
                started, ended
tool.start      call, name, input, and command (a shell line), reads, writes;
                run (a trace_io run file: the command runs under dftracer)
tool.end        call, output, error, exit_code
=============== ==============================================================

The graph, so that a file walks back to the prompt with moirai's activity
relations alone::

    agent.prompt -> llm.call -> llm.response, tool.input -> tool.<name>
                       ^                                      |
                       +------- tool.output <-----------------+-> file

Each hook is a process of its own, so nothing here lives between events but the
plain ``sessions`` dict, which :mod:`moirai.agent.agent` keeps in a file. An
activity is written when it ends, with what it spanned (:meth:`Activity.span`).

Entities that belong to one event are keyed by the session and the call, so a
tool's input has the same id whether its hook or its transcript line comes
first. Scripts and files are keyed by content: the same script is one entity.
"""
import os
import re
import time

from moirai.agent.constants import SESSION_NAME_CHARS
from moirai.agent.content import Content, render
from moirai.agent.redact import redact_text
from moirai.agent.shell import shell_files

TYPES = {
    "agent.session": ("PARAMETER", "one run of an agent harness"),
    "agent.prompt": ("INPUT", "what the user asked"),
    "llm.request": ("INTERMEDIATE", "what was sent to the model"),
    "llm.response": ("INTERMEDIATE", "what the model answered"),
    "tool.input": ("INTERMEDIATE", "arguments the model gave a tool"),
    "tool.output": ("INTERMEDIATE", "what a tool returned"),
    "tool.script": ("INTERMEDIATE", "a script a tool ran"),
    "tool.process": ("INTERMEDIATE", "the process a traced shell tool ran as"),
    "file": ("INTERMEDIATE", "a file a tool read or wrote"),
}
# Larger files are named, not digested: a hook must stay quick.
MAX_FILE = 256 << 20
# Scratch space does not outlive the run: keep the content, not a link.
TRANSIENT_PREFIXES = ("/tmp/", "/var/tmp/", "/dev/shm/")


def named_uri(artifact, path):
    """An artifact's URI followed by the path it came from. An id is a hash, so
    this is where a reader of the trace finds the path; the artifact stays first
    because a URI is cut at a fixed length, and ``read_artifact`` ignores what
    follows the ``@``."""
    return f"{artifact}@{path}"


def activity_name(name):
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", str(name))[:64] or "unknown"


def now_us():
    return int(time.time() * 1e6)


class Recorder:
    """Applies events to moirai and to ``sessions``."""

    def __init__(self, api, sessions=None):
        self.api = api
        self.content = Content(api)
        self.sessions = {} if sessions is None else sessions
        # The final state of each session that ended in this process, for the
        # manifest (moirai.agent.manifest).
        self.finished = {}

    def handle(self, ev):
        session = self._session(ev)
        method = getattr(self, "_" + ev.get("kind", "").replace(".", "_"), None)
        if method is not None:
            method(session, ev)

    def close(self):
        for sid in list(self.sessions):
            self.handle({"kind": "session.end", "session": sid})

    def _activity(self, session, name, start, used=(), generated=(),
                  updated=()):
        api = self.api
        session["activities"] = session.get("activities", 0) + 1
        activity = api.Activity(name).begin()
        activity.span(start, now_us())
        for relation, entities in ((api.Relation.USED, used),
                                   (api.Relation.GENERATED, generated),
                                   (api.Relation.UPDATED, updated)):
            for e in entities:
                activity.relate(relation, e)
        activity.end()

    def _session(self, ev):
        sid = str(ev.get("session") or "unknown")
        session = self.sessions.get(sid)
        if session is None:
            api = self.api
            for name, (role, description) in TYPES.items():
                api.entity_type(name, getattr(api.Role, role), description)
            record = {k: ev.get(k) for k in ("harness", "cwd", "model")}
            entity = api.entity(
                "agent.session", sid, api.Store.DATABASE,
                self.content.put(dict(record, session=sid)))
            session = self.sessions[sid] = {
                "sid": sid, "entity": int(entity), "start": now_us(),
                "turn": None, "turns": 0, "pending": [], "request": None,
                "tools": {}, "calls": {}, "files": {}, "closed": [],
                "outputs": {}, "activities": 0, "name": "", **record}
        return session

    def _name(self, prompt):
        """What a session is picked by: its first prompt, redacted like what is
        stored, on one line."""
        text, _ = redact_text(render(prompt or ""), self.content.patterns)
        return re.sub(r"\s+", " ", text).strip()[:SESSION_NAME_CHARS]

    def _entity(self, session, type, key, value):
        api = self.api
        e = api.entity(type, f"{session['sid']}/{key}", api.Store.DATABASE,
                       self.content.put(value))
        e.relate(api.Relation.PART_OF, api.Entity(session["entity"]))
        return int(e)

    def _session_end(self, session, ev):
        self._end_turn(session)
        for call in list(session["tools"]):
            self._tool_end(session, {"call": call,
                                     "error": "the session ended first"})
        self._activity(session, "agent.session", session["start"],
                       used=[session["entity"]])
        self.finished[session["sid"]] = self.sessions.pop(session["sid"])

    def _turn_start(self, session, ev):
        self._end_turn(session)
        session["turns"] += 1
        prompt = self._entity(session, "agent.prompt", f"p{session['turns']}",
                              ev.get("prompt", ""))
        if not session.get("name"):
            session["name"] = self._name(ev.get("prompt"))
        session["turn"] = {"start": now_us(), "prompt": prompt}
        session["pending"].append(prompt)

    def _turn_end(self, session, ev):
        self._end_turn(session)

    def _end_turn(self, session):
        turn, session["turn"] = session["turn"], None
        if turn is not None:
            self._activity(session, "agent.turn", turn["start"],
                           used=[turn["prompt"]])

    def _llm_start(self, session, ev):
        session["calls"].setdefault(ev["call"], now_us())

    def _llm_end(self, session, ev):
        api = self.api
        call = ev["call"]
        start = session["calls"].pop(call, now_us())
        model = ev.get("model")
        request = self._entity(session, "llm.request", f"{call}/request", {
            "model": model, "messages": ev.get("request"),
            "previous": session["request"]})
        used = [request] + session["pending"]
        session["pending"] = []
        for tool_id in ev.get("tool_results") or ():
            if tool_id in session["tools"]:  # no hook will end it: refused
                self._tool_end(session, {"call": tool_id,
                                         "error": "ended without a result"})
                session["closed"].append(tool_id)
                session["pending"].pop()
            if tool_id in session["outputs"]:
                used.append(session["outputs"][tool_id])
        response = self._entity(session, "llm.response", f"{call}/response", {
            k: ev.get(k) for k in ("model", "response", "tool_calls", "usage",
                                   "stop_reason", "started", "ended")})
        api.Entity(response).relate(api.Relation.DERIVED_FROM,
                                    api.Entity(request))
        if session["request"] is not None:
            api.Entity(request).relate(api.Relation.REVISION_OF,
                                       api.Entity(session["request"]))
        session["request"] = request
        generated = [response] + [
            self._tool_input(session, tool.get("id"), tool.get("input"))
            for tool in ev.get("tool_calls") or ()]
        self._activity(session, "llm.call", start, used=used,
                       generated=generated)

    def _tool_input(self, session, call, value):
        return self._entity(session, "tool.input", f"{call}/input", value)

    def _tool_start(self, session, ev):
        api = self.api
        call = ev["call"]
        used = [self._tool_input(session, call, ev.get("input"))]
        scripts, reads, writes = [], list(ev.get("reads") or ()), []
        writes.extend(ev.get("writes") or ())
        command = ev.get("command")
        if command:
            cwd = ev.get("cwd") or os.getcwd()
            scripts, named, targets = shell_files(command, cwd)
            reads += named
            writes += targets
        for path in scripts:
            if self.content.sensitive(path):
                continue  # neither its name nor its content is kept
            artifact = self.content.file(path, api.Lifetime.TRANSIENT)
            if artifact:
                used.append(int(api.entity("tool.script", artifact.uri,
                                           api.Store.DATABASE,
                                           named_uri(artifact.uri, path))))
        used += [e for e in (self._file(session, p) for p in reads)
                 if e is not None]
        session["tools"][call] = {
            "name": activity_name(ev.get("name")), "start": now_us(),
            "used": used, "run": ev.get("run"),
            "before": {p: self._stamp(p) for p in set(reads + writes)}}

    def _tool_end(self, session, ev):
        api = self.api
        call = ev["call"]
        state = session["tools"].pop(call, None)
        if state is None and call in session["closed"]:
            return
        if state is None:  # no start was seen: a tool still happened
            self._tool_start(session, dict(ev, input=None, command=None))
            state = session["tools"].pop(call)
        output = self._entity(session, "tool.output", f"{call}/output", {
            k: ev.get(k) for k in ("output", "error", "exit_code")})
        session["pending"].append(output)
        session["outputs"][call] = output
        generated, updated = [output], []
        if state.get("run"):
            process = self._process(session, call, state["run"])
            if process is not None:
                generated.append(process)
        for path, before in state["before"].items():
            after = self._stamp(path)
            if after is None or after == before:
                continue
            previous = session["files"].get(path)
            e = self._file(session, path)
            if e is None:
                continue
            (updated if before else generated).append(e)
            if previous is not None:
                api.Entity(e).relate(api.Relation.REVISION_OF,
                                     api.Entity(previous))
        self._activity(session, "tool." + state["name"], state["start"],
                       used=state["used"], generated=generated, updated=updated)

    def _process(self, session, call, run):
        """The process a traced shell tool ran as: an entity whose key is
        ``<host>/<pid>`` and whose URI ``process://<host>/<pid>`` (the pid in
        the dftracer events of the command's processes). One per call."""
        from moirai.agent import trace_io

        info = trace_io.process(run)
        if info is None:
            return None
        api = self.api
        where = f"{info['host']}/{info['pid']}"
        e = api.entity("tool.process", f"{session['sid']}/{call}/{where}",
                       api.Store.DATABASE, "process://" + where)
        e.relate(api.Relation.PART_OF, api.Entity(session["entity"]))
        return int(e)

    @staticmethod
    def _stamp(path):
        try:
            st = os.stat(path)
        except OSError:
            return None
        return [st.st_size, st.st_mtime_ns]

    def _file(self, session, path):
        api = self.api
        try:
            size = os.path.getsize(path)
        except OSError:
            return None
        shown = self.content.path(path)  # no secret in a name, no sensitive one
        if size > MAX_FILE or self.content.sensitive(path):
            # Named, not kept: too large to digest, or not to be copied.
            return int(api.entity("file", shown, api.Store.PARALLEL_FS,
                                  "file://" + shown))
        lifetime = (api.Lifetime.TRANSIENT if path.startswith(TRANSIENT_PREFIXES)
                    else api.Lifetime.PERSISTENT)
        artifact = self.content.file(path, lifetime)
        if not artifact:
            return None
        e = int(api.entity("file", f"{shown}@{artifact.uri}", api.Store.DATABASE,
                           named_uri(artifact.uri, shown)))
        session["files"][path] = e
        return e
