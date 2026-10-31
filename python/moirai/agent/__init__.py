"""Provenance of what agents do, on moirai's API.

The starting point is :mod:`moirai.agent.agent`: the file a harness runs for each
event, and :class:`AgentSession` for any other program. The rest is what it uses:
``adapters`` turns a harness's hooks into events, ``recorder`` events into
provenance, ``content`` values into artifacts, ``install`` registers the hooks.

Every exchange with a model and everything an agent runs: what was asked and
answered, a tool's input, script and output, the files it touched. Payloads are
moirai artifacts; a trace holds their keys. A harness is integrated by
registering hooks (``python -m moirai.agent install claude|codex|opencode``);
any other program uses a session directly::

    from moirai.agent import AgentSession

    moirai.initialize()
    with AgentSession("my-agent", "session-1", model="m") as s:
        with s.turn("sort this file"):
            with s.llm("call-1", request=messages) as call:
                call.done(response=text, tool_calls=[
                    {"id": "t1", "name": "sh", "input": {"command": line}}])
            with s.tool("t1", "sh", {"command": line}, command=line) as tool:
                tool.done(output=out, exit_code=0)
    moirai.finalize()
"""
from moirai.agent.agent import AgentSession, main

__all__ = ["AgentSession", "main"]
