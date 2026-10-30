==========================
Integrating an agent
==========================

This page takes an agentic system -- a coding agent, a workflow agent, your own
program that drives a model and runs tools -- from nothing to its sessions
recorded as provenance and read back. :doc:`agents` is the reference for each
part; this is the order to do them in.

::

   agent harness --hooks--> moirai.agent --> moirai-service --> <dir>/trace_<host>.pfw.gz
        |                        |                               <dir>/trace.artifacts/  (payloads)
        +-- each command --> moirai.agent.run (I/O tracing) --> same service, or spill files

   a reader (dftracer-utils) <-- the trace         moirai.read_artifact <-- the artifact store

Three things have one job each:

* **moirai records.** Hooks turn what an agent does into entities, activities and
  relations; the service writes them to a dftracer trace; the payloads (prompts,
  replies, tool input and output, files) go to an artifact store beside it.
  moirai contains no trace reader.
* **dftracer-utils reads the trace**, including one the service is still writing.
* **Your tool draws or analyses it.** What the records mean is the same for every
  consumer; see `What is recorded`_.

------------------------------------------
Step 1: install
------------------------------------------

.. code-block:: bash

   pip install moirai          # brings the dftracer wheel it runs on

The wheel has the Python API, the hooks (``python -m moirai.agent``), the command
wrapper (``moirai.agent.run``), ``libmoirai`` and the ``moirai-service`` command.
From source, see :doc:`build`.

The artifact store needs dftracer-utils and RocksDB's headers when moirai is
**built**. Without them moirai builds with a warning and payloads are addressed but
not stored, so every prompt and reply reads back empty. Check after installing:

.. code-block:: bash

   python -c "import moirai; print(moirai.HAS_ARTIFACT_STORE)"    # must be True

If the runtimes moirai was built against are not on the default loader path (the
Cray PE is an example), put them on ``LD_LIBRARY_PATH`` in every shell that starts
the service, the agent or a reader.

------------------------------------------
Step 2: choose where it records
------------------------------------------

Two settings name the run, and the hooks and the service must agree on them:

.. code-block:: bash

   export MOIRAI_AGENT_DIR=$PWD/agent-run          # hook state, run files
   export MOIRAI_LOG_FILE=$MOIRAI_AGENT_DIR/trace  # the trace prefix

The node trace is ``$MOIRAI_LOG_FILE_<host>.pfw.gz`` and the artifact store
``$MOIRAI_LOG_FILE.artifacts``. If the service is not running, every process writes
a spill file, ``$MOIRAI_LOG_FILE-<hash>-spill.pfw.gz``, in the same format.

------------------------------------------
Step 3: install the hooks
------------------------------------------

.. code-block:: bash

   python -m moirai.agent install claude      # or codex, opencode; --user for the user config

Each harness gets its own mechanism, merged with the configuration already there:

.. list-table::
   :header-rows: 1

   * - Harness
     - Mechanism
     - Notes
   * - Claude Code
     - command hooks, ``.claude/settings.local.json``
     - model exchanges read from the transcript
   * - Codex
     - command hooks, ``.codex/hooks.json``
     - must be trusted once with ``/hooks``; reads the rollout file
   * - OpenCode
     - a plugin, ``.opencode/plugin/moirai-provenance.js``
     - cannot rewrite commands, so no command I/O

**Export your settings first, then install.** ``install`` writes the interpreter,
the hook script, the run directory and every ``MOIRAI_*`` setting in effect into
the hook command as absolute paths, because a hook does not run in your shell. To
change a setting, export it and install again.

A hook prints nothing and never fails its agent. What went wrong is in
``$MOIRAI_AGENT_DIR/hook.log``.

------------------------------------------
Step 4: start the service, run the agent
------------------------------------------

.. code-block:: bash

   moirai-service start
   claude                                   # or codex, or your agent
   moirai-service stop

Or let moirai do all of steps 2--4 in one command. ``record`` takes the settings as
options (each falls back to the environment, then to a default), installs the
hooks, starts the service, runs your command and **always** stops the service,
returning the command's exit status:

.. code-block:: bash

   python -m moirai.agent record --agent-dir ./agent-run --data-dir "$PWD" \
       --flush-ms 200 claude -- claude

The word after the options is the harness the hooks are installed for; everything
after ``--`` is the command. ``--command-io`` adds Step 5, ``--no-trace-io`` stops
tracing the hooks' own I/O, ``--service`` names the service executable if it is
not next to the interpreter, and ``--user`` installs the hooks in the user
configuration. The hooks stay installed when the command ends, so this directory
keeps its ``--command-io`` choice for later sessions; see the warning in Step 5.
When you are done recording here, take them out, which keeps what was recorded:

.. code-block:: bash

   python -m moirai.agent uninstall claude

Start the service before the agent and stop it after. The service seals what it
receives into whole gzip members about once a second, so a reader can follow a
session while it runs. ``MOIRAI_PC_FLUSH_MS`` shortens how long a partial block is
held before it is sealed.

----------------------------------------------
Step 5 (optional): record what the commands do
----------------------------------------------

The hooks run in short-lived processes of their own, so by default moirai knows of
a command only what it can read from the tool call: the line, the scripts it runs
and the files it names. To record the file I/O of the command and of everything
it starts, turn on command tracing **before installing**:

.. code-block:: bash

   export MOIRAI_AGENT_TRACE_IO=1        # wrap each command in I/O tracing
   export MOIRAI_TRACE_IO=1              # also trace the hook processes themselves
   export MOIRAI_DATA_DIR=$PWD                      # whose I/O is traced
   python -m moirai.agent install claude

With it on, the ``PreToolUse`` hook rewrites each shell or command tool call to
run through ``moirai.agent.run``, which runs the command with dftracer's I/O
interception on the command and all its children, writing to the same service.
The tools wrapped are Claude Code's ``Bash`` and Codex's ``Bash``, ``shell``,
``shell_command``, ``exec_command``, ``local_shell``, ``container.exec`` and
``unified_exec``; file tools such as ``apply_patch`` are left alone.

``MOIRAI_DATA_DIR`` is a ``:``-separated list of path prefixes, matched against the
path **as the program wrote it**. moirai adds the real path of each entry that
differs from it, so a project reached through a symlink (for example
``/usr/workspace/...`` for ``/usr/WS2/...``) is traced however a program spells
it. ``all`` also traces interpreter start-up and every shared library, which is
rarely what you want.

.. warning::

   A harness applies a rewritten command only if the hook also approves it. With
   ``MOIRAI_AGENT_TRACE_IO=1`` **shell commands are auto-approved**. Use it where
   the agent already runs unattended or with pre-approved commands. Set it to
   ``0`` and install again, or ``uninstall``, to get the approval prompts back.

If the preload library is not found, the hook answers nothing and the command runs
unchanged. Set ``MOIRAI_AGENT_PRELOAD`` to ``libdftracer_preload.so`` if it is
not next to the dftracer moirai loads.

Sandboxes and the ring
----------------------

The service is fed through a ring in the real ``/dev/shm``. A harness that
sandboxes its commands (Codex's ``workspace-write`` and ``read-only`` modes) gives
them a private ``/dev/shm``, so they cannot reach the ring. dftracer then writes
their events to spill files beside the trace. Nothing is lost, and a reader that
loads ``$MOIRAI_LOG_FILE*`` sees them with the node trace. To use the ring the
commands must run outside the sandbox, which removes its protection.

------------------------------------------
Step 6: find the sessions
------------------------------------------

Every hook keeps a small manifest for its session in
``$MOIRAI_AGENT_DIR/manifests/<session id>.json``, so a consumer can list sessions
without reading the trace:

.. code-block:: json

   {"session_id": "6f1c...", "entity": "9def37c72d49ea94", "harness": "codex",
    "cwd": "/work/project", "model": "gpt-5.2",
    "name": "sort data.csv by the second column",
    "state": "running", "turns": 2, "activities": 14,
    "started_us": 1793391263263874, "updated_us": 1793391263616315,
    "updated_at": "2026-10-30T12:34:23.616315+00:00"}

``entity`` is the session's ``agent.session`` entity id, which ties the session to
the trace. ``name`` is the first prompt, redacted and at most 120 characters.

.. code-block:: python

   from moirai.agent import manifest

   for s in manifest.list_sessions("agent-run"):    # newest first
       print(s["session_id"], s["state"], s["name"])
   manifest.recording("agent-run")                  # is a session in flight?

These modules import without moirai's native library.

------------------------------------------
Step 7: read it back
------------------------------------------

The trace is dftracer records on moirai's own layer (``"type":128``); see
:doc:`trace_format`. Read it with dftracer-utils' ``TraceViewer`` for a finished
trace, or ``LiveTraceViewer``, which reads only the verified-whole part of a trace
that is still being written (an unfinished tail is ignored, a hole is waited for,
growth shows on the next ``refresh()``):

.. code-block:: python

   from dftracer.utils import LiveTraceViewer

   view = LiveTraceViewer(["agent-run/trace_host.pfw.gz",
                           "agent-run/trace-ab12-spill.pfw.gz"])
   for batch in view.stream(batch_size=65536):
       ...                      # Arrow batches of records
   view.refresh()               # later

Ask for a record schema that declares moirai's fields. By default dftracer-utils
returns the fields its own schema knows as typed columns and drops the rest --
including the nested ``relations`` of an activity, which is the provenance itself.
Declare ``args.relations`` (as JSON) and the entity, relation, file-name and I/O
fields you need.

Payloads are read from the artifact store with a library call, in your own
process:

.. code-block:: python

   from moirai.agent.artifacts import read_text

   text = read_text(entity_uri, "agent-run/trace")        # str, or None

``read_text`` takes an entity's URI, drops the ``@name`` after the key, decodes
UTF-8, and keeps what it read in a small cache (content is immutable, so a hit never
goes stale). ``moirai.read_artifact(key, prefix)`` returns the bytes. An entity's
URI is ``artifact://<key>``; a ``file`` or ``tool.script`` entity adds its path
after an ``@`` (``artifact://<key>@/path/to/file``), which is not part of the key.

------------------------------------------
What is recorded
------------------------------------------

.. list-table::
   :header-rows: 1

   * - Event the harness reports
     - Recorded
   * - session start, end
     - an ``agent.session`` entity, and an ``agent.session`` activity at the end
   * - user prompt
     - an ``agent.prompt`` entity; an ``agent.turn`` activity when the turn **ends**
   * - model exchange
     - ``llm.request`` and ``llm.response`` entities; an ``llm.call`` activity
       that used the request, the prompt and the tool outputs it was given, and
       generated the response and the tool inputs it asked for
   * - tool start, end
     - ``tool.input``, ``tool.output``, ``tool.script`` and ``file`` entities; a
       ``tool.<name>`` activity that used the input, the scripts and files it read,
       and generated the output and files it wrote
   * - command run under I/O tracing
     - a ``tool.process`` entity on the call, ``process://<host>/<root pid>``

Everything that belongs to one event is ``part_of`` its ``agent.session`` entity.
Files and scripts are keyed by content and shared between sessions.

Shell lines can be taken apart with ``moirai.agent.shell``: ``shell_files(line, cwd)``
(the scripts, files read and files written a line names), and
``command_lines``, ``command_language`` and ``command_summary`` (the program a
``python -c`` or heredoc carries, its language for highlighting, and a one-line
title).

To tie a command's I/O to its tool call: the call's processes are the
``tool.process`` root pid plus every process dftracer saw ``start`` (with a
``ppid`` already in the set) during the call's ``start_us``..``end_us``. Their
``POSIX`` and ``STDIO`` events are the call's I/O, and ``FH`` records map a file
hash to its path. Bound by the call's time window, not by pid alone: a sandbox can
give every command the same pids. Repeated calls may arrive aggregated
(``ph`` 3, with ``dft_cnt`` and ``*_sum`` arguments).

------------------------------------------
Settings
------------------------------------------

All are environment variables; see :doc:`configuration` for the rest.

.. list-table::
   :header-rows: 1

   * - Variable
     - Default
     - Meaning
   * - ``MOIRAI_AGENT_DIR``
     - ``~/.moirai/agent``
     - the run directory
   * - ``MOIRAI_LOG_FILE``
     - ``<dir>/trace``
     - trace prefix; the hooks and the service must agree
   * - ``MOIRAI_TRACE_IO``
     - build setting
     - trace POSIX/STDIO I/O of moirai's own processes (the hooks)
   * - ``MOIRAI_AGENT_TRACE_IO``
     - off
     - wrap each shell command in I/O tracing; auto-approves commands
   * - ``MOIRAI_DATA_DIR``
     - ``all``
     - ``:``-separated prefixes whose I/O is traced
   * - ``MOIRAI_PC_FLUSH_MS``
     - dftracer's
     - how long the service holds a partial block before sealing it
   * - ``MOIRAI_SERVICE_SHM``
     - per user
     - the ring's name; give each job its own to run several services on a node
   * - ``MOIRAI_PC_BLOCKS``
     - 1024
     - the ring's size in MiB
   * - ``MOIRAI_AGENT_REDACT``
     - none
     - further secret patterns, one regular expression per line
   * - ``MOIRAI_AGENT_SENSITIVE_PATHS``
     - none
     - further sensitive-file globs, one per line (see Redaction)
   * - ``MOIRAI_AGENT_PRELOAD``
     - found
     - path to ``libdftracer_preload.so``
   * - ``MOIRAI_ENABLE``
     - ``1``
     - ``0`` turns recording off

------------------------------------------
Redaction
------------------------------------------

At record time, credentials (API keys, tokens, private keys, ``password=...``) are
replaced before any **payload** is stored, and moirai does not copy a sensitive
file a tool named (``.env*``, ``.netrc``, ``id_rsa*``, ``*.pem``,
``.aws/credentials``, ``.ssh/*``, anything whose name contains ``secret``,
``credential`` or ``token``, and more): its ``file`` entity is keyed by a stable
placeholder, ``sensitive-file:8hex``, so two accesses to the same file still
correlate. A tool's own input and output are still payloads: ``cat .env`` keeps
that command line, and what it printed, with only the secret patterns applied.
``MOIRAI_AGENT_SENSITIVE_PATHS`` (one glob per line; ``!glob`` removes a built-in;
a first line ``@only`` makes the list just what follows) and
``MOIRAI_AGENT_REDACT`` (more secret patterns) extend this. That is pattern
matching, not a guarantee.

The file **names** in command I/O events are written by dftracer inside the traced
process and are **not** redacted in the trace, and dftracer's data directories are
include-only, so a sensitive location cannot be excluded. A consumer must therefore
redact every name and command line it shows:

.. code-block:: python

   from moirai.agent.redact import redact_path, redact_text

   shown = redact_path(name)            # a sensitive file becomes its placeholder
   line, count = redact_text(command)

Treat the trace and the run directory as sensitive.

------------------------------------------
Your own program
------------------------------------------

A program of your own needs no hooks and no adapter:

.. code-block:: python

   import moirai
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

For a harness you do not own, see "Adding a harness" in :doc:`agents`: an adapter
that turns its hooks into the neutral events, an installer branch, a test from a
real session.

------------------------------------------
Troubleshooting
------------------------------------------

.. list-table::
   :header-rows: 1

   * - Symptom
     - Cause
   * - the reader finds nothing
     - the service is not running, or has not sealed its first block; hooks and
       service must use the same ``MOIRAI_LOG_FILE``
   * - no session listed
     - no manifest in ``$MOIRAI_AGENT_DIR/manifests``: the harness has not
       trusted the hooks (Codex: ``/hooks``), or ``hook.log`` says why a hook
       failed
   * - nodes but no text
     - the artifact store is off: ``moirai.HAS_ARTIFACT_STORE`` is false (see
       Step 1)
   * - no I/O for commands
     - ``MOIRAI_AGENT_TRACE_IO`` was not exported before ``install``, or
       ``MOIRAI_DATA_DIR`` does not match the paths the commands open (symlinks)
   * - command I/O is in spill files
     - the harness sandboxes commands away from ``/dev/shm``; expected
   * - ``libfi.so.1`` or ``CXXABI_1.3.13``
     - the runtimes moirai was built against are not on the loader path
