"""A small JSON file per recorded session, for whoever lists them.

Importing this needs no native module. A consumer that wants "which sessions
are there, what did each start with, is one still running" would otherwise read
the whole node trace. The hooks keep this instead, one file per session, at
``<dir>/manifests/<safe session id>.json``, rewritten atomically (temporary file
and rename, mode 0600) by every hook event of the session::

    {"session_id": "6f1c...", "entity": "9def37c72d49ea94",
     "harness": "codex", "cwd": "/work/project", "model": "gpt-5.2",
     "name": "sort data.csv by the second column",
     "state": "running", "turns": 2, "activities": 14,
     "started_us": 1793391263263874, "updated_us": 1793391263616315,
     "updated_at": "2026-10-30T12:34:23.616315+00:00"}

``entity`` is the id of the ``agent.session`` entity in the trace (16 hex
digits), ``name`` the first prompt on one line, at most 120 characters and
redacted like everything stored, ``activities`` how many the recorder has
written so far.

Writing is for the hooks (:func:`write`, :func:`update`); reading is for
consumers (:func:`list_sessions`, :func:`read`, :func:`recording`) and reads
only these files. Each takes the run directory; without one it is
``moirai.agent_configuration().dir``.
"""
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone

FIELDS = ("session_id", "entity", "harness", "cwd", "model", "name", "state",
          "turns", "activities", "started_us", "updated_us", "updated_at")


def agent_dir(directory=None):
    """``directory``, absolute, else this run's."""
    if directory:
        return os.path.normpath(
            os.path.abspath(os.path.expanduser(str(directory))))
    import moirai

    return moirai.agent_configuration().dir


def safe_name(session_id):
    """A file name for a session id, which comes from a harness: a name, not a
    path. Ids that are already safe are kept; others are made safe and told
    apart by a digest."""
    sid = str(session_id)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", sid).lstrip(".")[:80] or "session"
    if safe != sid:
        safe += "-" + hashlib.sha256(sid.encode("utf-8", "replace")
                                     ).hexdigest()[:8]
    return safe


def path(session_id, directory=None):
    return os.path.join(agent_dir(directory), "manifests",
                        safe_name(session_id) + ".json")


def iso(microseconds):
    """ISO-8601 UTC for a time in microseconds since the epoch."""
    return datetime.fromtimestamp(microseconds / 1e6, tz=timezone.utc
                                  ).isoformat()


def write(directory, manifest):
    """Write ``manifest`` (a dict with ``session_id``), atomically, mode 0600;
    its path. Only the known :data:`FIELDS` are kept."""
    data = {k: manifest[k] for k in FIELDS if k in manifest}
    target = path(data["session_id"], directory)
    os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
    tmp = f"{target}.tmp{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return target


def update(directory, session_id, **fields):
    """Merge ``fields`` into the session's manifest (made if there is none) and
    stamp ``updated_us`` / ``updated_at`` (unless ``updated_us`` is given); the
    manifest."""
    current = read(session_id, directory) or {
        "session_id": str(session_id), "entity": "", "harness": "", "cwd": "",
        "model": "", "name": "", "state": "running", "turns": 0,
        "activities": 0, "started_us": 0}
    current.update({k: v for k, v in fields.items() if k in FIELDS})
    current["session_id"] = str(session_id)
    now = int(time.time() * 1e6)
    current["started_us"] = current["started_us"] or now
    if "updated_us" not in fields:
        current["updated_us"] = now
    current["updated_at"] = iso(current["updated_us"])
    write(directory, current)
    return current


def read(session_id, directory=None):
    """The manifest of a session, or ``None`` if it has none."""
    return _load(path(session_id, directory))


def list_sessions(directory=None):
    """Every manifest, the most recently updated first."""
    folder = os.path.join(agent_dir(directory), "manifests")
    try:
        names = sorted(n for n in os.listdir(folder) if n.endswith(".json"))
    except OSError:
        return []
    found = [m for m in (_load(os.path.join(folder, n)) for n in names) if m]
    return sorted(found, key=lambda m: m.get("updated_us") or 0, reverse=True)


def recording(directory=None):
    """Whether a session has work in flight: a hook's state file exists
    (``<dir>/sessions/*.json``; the hooks remove it when no session is left)."""
    folder = os.path.join(agent_dir(directory), "sessions")
    try:
        return any(n.endswith(".json") for n in os.listdir(folder))
    except OSError:
        return False


def _load(file):
    try:
        with open(file) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def from_session(session, state):
    """The manifest fields of a recorder session dict
    (``moirai.agent.recorder``) in ``state`` ("running" or "ended")."""
    fields = {
        "session_id": session["sid"],
        "entity": format(int(session["entity"]), "016x"),
        "state": state,
        "turns": session.get("turns", 0),
        "activities": session.get("activities", 0),
        "started_us": session.get("start", 0),
    }
    for key in ("harness", "cwd", "model", "name"):
        if session.get(key) is not None:
            fields[key] = session[key]
    return fields
