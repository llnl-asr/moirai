"""A harness's hooks to :mod:`moirai.agent.recorder` events.

No harness hooks its model calls, so each adapter also follows where the
exchanges are written: Claude Code's transcript, Codex's rollout, and for
OpenCode the message events its plugin forwards. A hook's ``hook_event_name``
selects what it means; anything else is ignored, so a harness can add events.
"""
import json
import re
import sys


def _blocks(content):
    """A message's content blocks; plain text has none."""
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, dict)]


class Tail:
    """New whole lines of a JSONL file, which may not exist yet."""

    def __init__(self, path):
        self.path = path
        self.pos = 0

    def lines(self):
        try:
            with open(self.path, "rb") as fh:
                fh.seek(self.pos)
                data = fh.read()
        except OSError:
            return
        end = data.rfind(b"\n") + 1
        self.pos += end
        for line in data[:end].splitlines():
            try:
                yield json.loads(line)
            except ValueError:
                continue


class Exchanges:
    """Groups a transcript's lines into model calls; what it has read so far is
    plain data, kept between hooks."""

    def __init__(self, path, state=None):
        self.tail = Tail(path)
        self.request = []
        self.results = []
        self.response = None
        self.setup()
        for name, value in (state or {}).items():
            if name == "pos":
                self.tail.pos = value
            else:
                setattr(self, name, value)

    def setup(self):
        pass

    def state(self):
        return dict({k: v for k, v in vars(self).items() if k != "tail"},
                    pos=self.tail.pos)

    def flush(self):
        r, self.response = self.response, None
        if r is None:
            return []
        ev = dict(r, kind="llm.end", request=self.request,
                  tool_results=self.results)
        self.request, self.results = [], []
        return [ev]


class ClaudeExchanges(Exchanges):
    """One API response is several ``assistant`` lines with a ``requestId``,
    one per content block; ``user`` lines are what the next request adds."""

    def poll(self):
        out = []
        for r in self.tail.lines():
            kind = r.get("type")
            message = r.get("message") or {}
            if kind == "assistant":
                call = r.get("requestId") or message.get("id")
                if self.response and self.response["call"] != call:
                    out += self.flush()
                if self.response is None:
                    self.response = {
                        "call": call, "model": message.get("model"),
                        "response": [], "tool_calls": [],
                        "started": r.get("timestamp")}
                for block in _blocks(message.get("content")):
                    self.response["response"].append(block)
                    if block.get("type") == "tool_use":
                        self.response["tool_calls"].append({
                            k: block.get(k) for k in ("id", "name", "input")})
                self.response.update(
                    usage=message.get("usage"), ended=r.get("timestamp"),
                    stop_reason=message.get("stop_reason"))
            elif kind == "user":
                out += self.flush()
                content = message.get("content")
                self.request.append(content)
                for block in _blocks(content):
                    if block.get("type") == "tool_result":
                        self.results.append(block.get("tool_use_id"))
        return out


class CodexExchanges(Exchanges):
    """A rollout's ``response_item`` lines. A response ends at its
    ``token_count`` event, which comes after the output of the tools it called:
    those are input of the next request. The system prompt is in
    ``session_meta``. The rollout format is not a stable interface."""

    def setup(self):
        self.model = None
        self.instructions = None
        self.calls = 0
        self.next_request = []
        self.next_results = []

    def poll(self):
        out = []
        for r in self.tail.lines():
            kind, p = r.get("type"), r.get("payload") or {}
            if kind == "session_meta":
                self.instructions = p.get("base_instructions")
            elif kind == "turn_context":
                self.model = p.get("model")
            elif kind == "event_msg" and p.get("type") == "token_count":
                if self.response:
                    self.response["usage"] = (p.get("info") or {}).get(
                        "last_token_usage")
                out += self.flush()
            elif kind == "response_item":
                self._item(p, r.get("timestamp"))
        return out

    def flush(self):
        out = super().flush()
        if out:
            self.request, self.next_request = self.next_request, []
            self.results, self.next_results = self.next_results, []
        return out

    def _input(self, p):
        waiting = self.response is not None
        (self.next_request if waiting else self.request).append(p)
        if p.get("type") == "function_call_output":
            (self.next_results if waiting else self.results).append(
                p.get("call_id"))

    def _item(self, p, ts):
        kind = p.get("type")
        if kind == "function_call_output" or (
                kind == "message" and p.get("role") != "assistant"):
            self._input(p)
        elif kind in ("message", "reasoning", "function_call",
                      "local_shell_call", "custom_tool_call",
                      "web_search_call"):
            if self.response is None:
                if self.instructions:
                    self.request.insert(0, {"role": "system",
                                            "content": self.instructions})
                    self.instructions = None
                self.calls += 1
                self.response = {
                    "call": f"c{self.calls}", "model": self.model,
                    "response": [], "tool_calls": [], "started": ts}
            self.response["response"].append(p)
            self.response["ended"] = ts
            if kind == "function_call":
                self.response["tool_calls"].append({
                    "id": p.get("call_id"), "name": p.get("name"),
                    "input": p.get("arguments")})


def _tool_files(ev, name, tool_input):
    """A file tool's paths: a shell line is parsed by the recorder."""
    if not isinstance(tool_input, dict):
        return ev
    path = tool_input.get("file_path") or tool_input.get("filePath") or (
        tool_input.get("path") if isinstance(tool_input.get("path"), str)
        else None)
    command = tool_input.get("command") or tool_input.get("cmd")
    if isinstance(command, str):
        ev["command"] = command
    if path:
        lowered = str(name).lower()
        writes = any(w in lowered for w in ("write", "edit", "patch"))
        ev["writes" if writes else "reads"] = [path]
    return ev


class Adapter:
    """What a hooks-and-transcript harness has in common."""

    harness = ""
    exchanges = None

    def __init__(self, state=None):
        state = state or {}
        self.sid = state.get("sid")
        self.tails = {path: self.exchanges(path, s)
                      for path, s in state.get("tails", {}).items()}

    def state(self):
        return {"sid": self.sid,
                "tails": {p: e.state() for p, e in self.tails.items()}}

    def _follow(self, path):
        if path and path not in self.tails:
            self.tails[path] = self.exchanges(path)

    def poll(self, final=False):
        """The model calls the transcripts have now. ``final``: also the ones
        with nothing after them yet."""
        out = []
        for exchanges in self.tails.values():
            # Transcripts are no interface: a line this does not understand
            # must not cost the hook that came with it.
            try:
                events = exchanges.poll()
            except (AttributeError, KeyError, TypeError) as e:
                print(f"moirai-agent: transcript: {e!r}", file=sys.stderr,
                      flush=True)
                events = []
            if final:
                events += exchanges.flush()
            out += [dict(e, session=self.sid, harness=self.harness)
                    for e in events]
        return out

    def translate(self, hook):
        sid = self.sid = hook.get("session_id")
        self._follow(hook.get("transcript_path"))
        self._follow(hook.get("agent_transcript_path"))
        name = hook.get("hook_event_name") or ""
        base = {"session": sid, "harness": self.harness,
                "cwd": hook.get("cwd"), "model": hook.get("model")}
        call = hook.get("tool_use_id")
        tool = hook.get("tool_name")
        out = self.poll()
        if name == "SessionStart":
            out.append(dict(base, kind="session.start"))
        elif name == "UserPromptSubmit":
            out.append(dict(base, kind="turn.start", prompt=hook.get("prompt")))
        elif name == "PreToolUse":
            out.append(_tool_files(
                dict(base, kind="tool.start", call=call, name=tool,
                     input=hook.get("tool_input")),
                tool, hook.get("tool_input")))
        elif name in ("PostToolUse", "PostToolUseFailure", "PermissionDenied"):
            out.append(self._tool_end(base, call, hook))
        elif name in ("Stop", "StopFailure"):
            out += self.poll(final=True)
            out.append(dict(base, kind="turn.end",
                            reply=hook.get("last_assistant_message")))
        elif name == "SessionEnd":
            out += self.poll(final=True)
            self.tails = {}
            out.append(dict(base, kind="session.end"))
        return out

    def _tool_end(self, base, call, hook):
        response = hook.get("tool_response")
        ev = dict(base, kind="tool.end", call=call, output=response,
                  error=hook.get("error"))
        if isinstance(response, dict):
            ev["exit_code"] = response.get("exit_code", response.get("exitCode"))
        # Claude Code says it only in the error of a failure: "Exit code 2\n..".
        code = re.match(r"Exit code (\d+)", str(ev["error"] or ""))
        if code:
            ev["exit_code"] = int(code.group(1))
        elif ev.get("exit_code") is None and hook.get("hook_event_name") == \
                "PostToolUse" and hook.get("tool_name") == "Bash":
            ev["exit_code"] = 0
        return ev


class Claude(Adapter):
    harness = "claude"
    exchanges = ClaudeExchanges


class Codex(Adapter):
    harness = "codex"
    exchanges = CodexExchanges


class OpenCode:
    """OpenCode has no per-request hook either, but its plugin gets every
    message part: it gathers them, and hands over a whole exchange
    (:data:`moirai.agent.install.OPENCODE_PLUGIN`)."""

    harness = "opencode"

    def __init__(self, state=None):
        state = state or {}
        self.request = state.get("request", [])  # what the next call adds
        self.seen = state.get("seen", [])        # messages already in a request
        self.ended = state.get("ended", [])

    def state(self):
        return {"request": self.request, "seen": self.seen, "ended": self.ended}

    def poll(self, final=False):
        return []

    def _messages(self, messages):
        """The whole history comes with every call: only what is new."""
        for message in messages or ():
            info = message.get("info") or {}
            if info.get("role") == "user" or any(
                    p.get("type") == "tool" for p in message.get("parts") or ()):
                key = [info.get("id"), len(message.get("parts") or ())]
                if key not in self.seen:
                    self.seen.append(key)
                    self.request.append(message)

    def translate(self, hook):
        name = hook.get("hook_event_name")
        sid = hook.get("session_id")
        base = {"session": sid, "harness": self.harness, "cwd": hook.get("cwd")}
        if name == "chat.message":
            text = [p.get("text") for p in hook.get("parts") or ()
                    if p.get("type") == "text"]
            return [dict(base, kind="turn.start", prompt="\n".join(text))]
        if name == "chat.system":
            self.request.append({"role": "system",
                                 "content": hook.get("system")})
            return []
        if name == "chat.messages":
            self._messages(hook.get("messages"))
            return []
        if name == "tool.before":
            return [_tool_files(
                dict(base, kind="tool.start", call=hook.get("call"),
                     name=hook.get("tool"), input=hook.get("args")),
                hook.get("tool"), hook.get("args"))]
        if name == "tool.after":
            self.ended.append(hook.get("call"))
            return [dict(base, kind="tool.end", call=hook.get("call"),
                         output=hook.get("output"),
                         error=(hook.get("metadata") or {}).get("error"),
                         exit_code=(hook.get("metadata") or {}).get("exit"))]
        if name == "tool.error":
            call = hook.get("call")
            if call in self.ended:
                return []
            self.ended.append(call)
            return [dict(base, kind="tool.end", call=call,
                         error=hook.get("error"))]
        if name == "message.done":
            info, time = hook.get("info") or {}, hook.get("time") or {}
            parts = hook.get("parts") or []
            request, self.request = self.request, []
            return [dict(
                base, kind="llm.end", call=info.get("id"),
                model=info.get("modelID"), request=request, response=parts,
                usage=info.get("tokens"), stop_reason=info.get("finish"),
                started=time.get("created"), ended=time.get("completed"),
                tool_calls=[{"id": p.get("callID"), "name": p.get("tool"),
                             "input": (p.get("state") or {}).get("input")}
                            for p in parts if p.get("type") == "tool"])]
        if name == "session.idle":
            return [dict(base, kind="turn.end")]
        if name == "session.deleted":
            return [dict(base, kind="session.end")]
        return []


ADAPTERS = {a.harness: a for a in (Claude, Codex, OpenCode)}
