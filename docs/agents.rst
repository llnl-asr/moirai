======
Agents
======

``moirai.agent`` records what an agent does: every exchange with a model, and
everything it runs -- a tool's input, the script, its output, the files it
touched. Payloads are :ref:`artifacts <artifacts>`; the trace holds their keys.
A file an agent wrote walks back to the prompt through moirai's relations::

    agent.prompt -> llm.call -> llm.response, tool.input -> tool.<name>
                       ^                                      |
                       +------- tool.output <-----------------+-> file

------------------------------------------
Harnesses
------------------------------------------

.. code-block:: bash

   export MOIRAI_AGENT_DIR=$PWD/agent-run
   python -m moirai.agent install claude     # or codex, opencode; --user

Each writes the harness's own configuration and merges with what is there.
Start ``moirai-service`` before the harness (:doc:`running`), with the same
``MOIRAI_LOG_FILE``, or ``<dir>/trace`` if that is not set:

.. code-block:: bash

   export MOIRAI_LOG_FILE=$MOIRAI_AGENT_DIR/trace
   moirai-service start && claude && moirai-service stop

.. list-table::
   :header-rows: 1

   * - Harness
     - Hooks
     - Model exchanges
   * - Claude Code
     - command hooks (``.claude/settings.local.json``)
     - the transcript, grouped by ``requestId``
   * - Codex
     - command hooks (``.codex/hooks.json``); must be trusted with ``/hooks``
     - the rollout file; its format is not a stable interface
   * - OpenCode
     - a plugin (``.opencode/plugin/moirai-provenance.js``)
     - message events, through the plugin

No harness hooks its model calls, so what is recorded is what each one exposes:
Codex's rollout and OpenCode's plugin hooks include the system prompt, Claude
Code's transcript does not, and no harness gives the tool definitions. OpenCode's
requests also hold the system prompt of its title generator. ``started`` and
``ended`` in an ``llm.response`` are the transcript's times; the ``llm.call``
activity is when a hook read them.

A tool the harness refused still ends, with its error. In Claude Code the exit
status of a shell command is known from whether the tool failed.

``opencode run`` cannot ask anything, so it refuses what would need a question
answered. To let a build agent run shell commands, allow it in ``opencode.json``
at the level of the agent:

.. code-block:: json

   {"agent": {"build": {"permission": {"bash": "allow"}}}}

Under ``opencode run`` tools and model calls are recorded, but not yet the
``agent.turn`` and ``agent.session`` activities.

------------------------------------------
Other programs
------------------------------------------

.. code-block:: python

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

This needs no hooks and no adapter: use it when the program is yours. To
integrate a harness you do not own, see `Adding a harness`_.

------------------------------------------
The code
------------------------------------------

``python/moirai/agent/agent.py`` is the starting point: the file a harness runs
for each event, and ``AgentSession``. The rest is what it uses:

.. list-table::
   :header-rows: 1

   * - File
     - What it does
   * - ``agent.py``
     - One hook: load the session's state, take its lock, turn the payload into
       events, record them, save the state.
   * - ``adapters.py``
     - A harness's hooks and transcripts to neutral events.
   * - ``recorder.py``
     - Neutral events to moirai's entities, activities and artifacts.
   * - ``content.py``
     - Redacts a value and stores it as an artifact.
   * - ``install.py``
     - Writes the hooks into a harness's configuration.
   * - ``redact.py``
     - Secret patterns, sensitive file names, ``redact_text`` / ``redact_path``
       (`Redaction`_).
   * - ``manifest.py``
     - The per-session summary file (`Session manifests`_).
   * - ``record.py``
     - ``python -m moirai.agent record`` (`Recording a harness`_).
   * - ``artifacts.py``
     - ``read_text``: payloads out of the artifact store (`Reading payloads`_).
   * - ``shell.py``
     - The files a shell line names, and how a command is shown (`Shell
       lines`_).
   * - ``constants.py``
     - The names of the settings and the defaults.
   * - ``trace_io.py``, ``run.py``
     - ``MOIRAI_AGENT_TRACE_IO``: rewrite a shell command to run under dftracer's
       preload (``trace_io.py``, in the hook), and the wrapper that does
       (``run.py``).

A hook's path through them is::

    harness -> agent.py <harness> -> Adapter.translate(hook) -> events
            -> Recorder.handle(event) -> moirai-service, artifact store

------------------------------------------
How it runs
------------------------------------------

A hook is a moirai process like any other: it initializes, writes through
``moirai-service`` and leaves, so start the service as for any application
(:doc:`running`); without one, each hook has a spill file. An activity is written
when it ends, and its args ``start_us`` and ``end_us`` hold what it really
spanned. What must outlive a hook is in ``<dir>/sessions``, under a lock. A hook
prints nothing and never fails its agent; what went wrong is in
``<dir>/hook.log``.

``install`` resolves the interpreter, the hook, the run directory, the trace
prefix and the ``MOIRAI_*`` settings in effect, and writes them into the hook's
command as absolute paths, because a hook does not run in this environment. To
change them, install again.

.. list-table::
   :header-rows: 1

   * - Variable
     - Default
     - Meaning
   * - ``MOIRAI_AGENT_DIR``
     - ``~/.moirai/agent``
     - The run directory: the trace prefix is ``<dir>/trace``, unless
       ``MOIRAI_LOG_FILE`` is set.
   * - ``MOIRAI_AGENT_REDACT``
     - none
     - Further secret patterns, one regular expression per line.
   * - ``MOIRAI_AGENT_SENSITIVE_PATHS``
     - none
     - Further sensitive files, one glob per line, see `Redaction`_. Baked into
       the hooks' command like the other settings.
   * - ``MOIRAI_AGENT_TRACE_IO``
     - off
     - ``1``: also trace the file I/O of a shell tool's command, see
       `Tracing what a command does`_. Read when the hooks are installed and
       baked into their command, like the other settings.
   * - ``MOIRAI_AGENT_PRELOAD``
     - found
     - The ``libdftracer_preload.so`` to use, if it is not beside the dftracer
       core library moirai runs on.

Credentials (API keys, tokens, private keys, ``password=...``) are replaced
before anything is stored (`Redaction`_). This is pattern matching, not a
guarantee: prompts and tool output are stored as they are otherwise, so treat the
run directory as sensitive.

Files are found from a tool's arguments and a shell line: what is named there.
What a script opens by itself is not seen, unless `Tracing what a command
does`_ is on.

A ``file`` or ``tool.script`` entity's URI is its artifact followed by its path,
``artifact://<key>@/path/to/file``, since an id is a hash and the trace would
otherwise not say which file it was. The artifact comes first because a URI is
cut at a fixed length, and ``read_artifact`` ignores what follows the ``@``.

------------------------------------------
Tracing what a command does
------------------------------------------

A hook is a short process of its own, so by default the I/O of the commands an
agent runs (``python``, ``grep``, ``make``...) is not traced: moirai knows the
files named on a shell line and those whose size or time changed. With

.. code-block:: bash

   export MOIRAI_AGENT_TRACE_IO=1
   python -m moirai.agent install codex      # or claude: baked into the hooks

the ``PreToolUse`` hook of every command tool (Claude Code's ``Bash``; Codex's
``Bash``, ``shell``, ``shell_command``, ``exec_command``, ``local_shell``,
``container.exec``, ``unified_exec``, whose input has a ``command`` or ``cmd``,
a line or an argv list)
answers with the command rewritten to run under dftracer's preload library, with
the same ``moirai-service`` ring and trace prefix as the hooks (``MOIRAI_*``
settings as for any moirai process, but ``DFTRACER_INIT=PRELOAD`` and I/O
always on; ``MOIRAI_DATA_DIR`` says which directories are traced, ``all`` if
unset)::

   {"hookSpecificOutput": {"hookEventName": "PreToolUse",
     "permissionDecision": "allow", "permissionDecisionReason": "...",
     "updatedInput": {"command": "<python> .../moirai/agent/run.py \
         <dir>/runs/<token>.json -- '<the original command>'", ...}}}

``run.py`` imports nothing of moirai: it writes its pid beside the run file,
puts ``libdftracer_preload.so`` (ahead of any ``LD_PRELOAD`` there is) and the
``DFTRACER_*`` settings in the environment, and ``exec``\ s the shell with the
original line, which therefore runs *as* the wrapper's pid. Every process it
starts records its POSIX and STDIO calls, as ordinary dftracer events. If the
preload library cannot be found, or the run file cannot be read, the command
runs as it was. OpenCode is not covered: its plugin cannot change a command.

.. warning::

   Both harnesses only run an ``updatedInput`` if the hook's decision is
   ``allow``, and that decision **also skips the harness's own approval** of the
   command (what would have asked the user, does not). This is why the setting
   is off by default: turn it on only where the agent already runs unattended or
   with its commands pre-approved. With the setting off the hooks print nothing.

``MOIRAI_DATA_DIR`` is a ``:``-separated list that moirai translates to
dftracer's ``DFTRACER_DATA_DIR``, and dftracer matches a path *as the program
wrote it*, so a project reached through a symbolic link (``/usr/workspace`` ->
``/usr/WS2``) traced nothing for files opened by their real path. moirai
therefore adds, after each existing entry whose real path differs, that real
path (no entry twice, order kept; ``all`` and an empty value are left alone, and
a directory that does not exist is kept as given). ``ConfigurationManager`` does
this, for moirai's processes and, through ``agent_configuration().dftracer_settings``,
for the commands of ``MOIRAI_AGENT_TRACE_IO``.

I/O file names are **not redacted** in the trace
   dftracer's events are written by the preloaded children of the command, so
   moirai cannot rewrite the names in their ``FH`` records. ``DATA_DIR`` is a list
   of directory prefixes to *include* (dftracer's exclusions are built in), so
   sensitive locations cannot be excluded from tracing either; keeping
   ``MOIRAI_DATA_DIR`` to the project's directories is the only filter. What
   moirai does at record time is: it does not copy the content of a sensitive
   file, and names it by a placeholder in its own entities. Every consumer must
   call ``moirai.agent.redact.redact_path`` on each file name (and
   ``redact_text`` on each command) it shows.

Which I/O belongs to which call
   The ``tool.<name>`` activity of the call *generated* a ``tool.process``
   entity, whose ``EH`` record's ``uri`` is ``process://<host>/<pid>``: the pid
   the command ran as, on the node of the trace. The call's processes are that
   pid and the closure of the dftracer ``start`` events (``cat=dftracer``,
   ``name=start``, ``args.ppid``) below it. A pid can be reused, so take only
   ``start`` events inside the activity's ``args.start_us``..``args.end_us``.
   Their I/O is every ``cat`` ``POSIX`` / ``STDIO`` event with such a ``pid``;
   ``args.fhash`` is the file, named by the ``FH`` record
   (``args.value`` = ``fhash``, ``args.name`` = the path) of any process. A call
   that never ran (refused) has no ``tool.process``.

From a real trace, the call ``python3 gen.py out.txt; cat out.txt | wc -l`` (the
lines shortened)::

   {"name":"EH","cat":"dftracer","type":128,"pid":4087914,"ph":4,"args":{"uri":"process://tuolumne1001/4087894","store":6,"type":"tool.process","id":"26a9ef0652eab067"}}
   {"id":2,"name":"tool.Bash","cat":"moirai","type":128,"pid":4087914,"ts":1793391263616308,"dur":75,"ph":1,"args":{"relations":{"used":["9def37c72d49ea94"],"generated":["faaf4996d2a555c8","26a9ef0652eab067"]},"end_us":1793391263616315,"start_us":1793391263263874}}
   {"id":1,"name":"start","cat":"dftracer","type":1,"pid":4087904,"ts":1793391263420330,"ph":1,"args":{"ppid":4087894,"cmd_hash":"dc888779639771f9",...}}
   {"name":"FH","cat":"dftracer","type":1,"pid":4087904,"ph":4,"args":{"name":"/.../data/out.txt","value":"40b6481bfc599278"}}
   {"id":11,"name":"open64","cat":"POSIX","type":3,"pid":4087904,"ts":1793391263468143,"dur":556,"ph":1,"args":{"flags":524865,"mode":438,"fhash":"40b6481bfc599278"}}
   {"name":"write","cat":"POSIX","type":3,"ts":1793391263460000,"ph":3,"pid":4087904,"args":{"fhash":"40b6481bfc599278","dft_cnt":1,"dur":29,"ret":6000,"count":6000}}
   {"id":2,"name":"open","cat":"POSIX","type":3,"pid":4087912,"ts":1793391263490006,"dur":623,"ph":1,"args":{"flags":0,"fhash":"40b6481bfc599278"}}
   {"name":"read","cat":"POSIX","type":3,"ts":1793391263490000,"ph":3,"pid":4087912,"args":{"fhash":"40b6481bfc599278","dft_cnt":2,"ret_sum":6000,...}}

Root ``4087894`` is the shell, ``4087904`` ran ``python3`` (``execve`` events
name its arguments) and wrote ``out.txt``, ``4087912`` ran ``cat`` and read it.
Repeated calls are aggregated by dftracer (``ph`` 3, ``dft_cnt`` and ``*_sum``
args, time rounded) as for any traced process: sum the ``dft_cnt`` and
``*_sum`` args for totals. Processes that leave their parent (daemons) are not followed,
and a statically linked program is not intercepted.

------------------------------------------
Recording a harness
------------------------------------------

.. code-block:: bash

   python -m moirai.agent record [--agent-dir D] [--log-file P] [--data-dir X] \
       [--trace-io|--no-trace-io] [--command-io|--no-command-io] \
       [--flush-ms N] [--service CMD] [--user] <harness> -- <command...>

In order: set the ``MOIRAI_*`` environment, install the hooks of ``<harness>``
(``install``), start ``moirai-service``, run the command, and stop the service
whatever became of the command (failure, a signal, an exception). The exit
status is the command's (``128 + n`` when a signal ``n`` killed it). A
``SIGTERM`` / ``SIGHUP`` goes on to the command; ``SIGINT`` is the command's own
(a terminal sends it to both). Errors (no service binary, hooks that cannot be
installed, a service that does not start) are one line on stderr and status 2;
one status line says where the run records. The hooks stay installed afterwards,
as with ``install``: with ``--command-io`` the commands of later sessions in that
directory are approved too, until ``uninstall`` takes the hooks out (`Removing the
hooks`_) or you install them again with ``MOIRAI_AGENT_TRACE_IO=0``.

.. list-table::
   :header-rows: 1

   * - Option
     - Sets
     - Default
   * - ``--agent-dir``
     - ``MOIRAI_AGENT_DIR``
     - the environment's, else ``~/.moirai/agent``
   * - ``--log-file``
     - ``MOIRAI_LOG_FILE``
     - the environment's, else ``<agent dir>/trace``
   * - ``--trace-io``
     - ``MOIRAI_TRACE_IO``
     - on
   * - ``--command-io``
     - ``MOIRAI_AGENT_TRACE_IO``
     - off (it approves the commands, see the warning above)
   * - ``--flush-ms``
     - ``MOIRAI_PC_FLUSH_MS``
     - 200
   * - ``--data-dir``
     - ``MOIRAI_DATA_DIR``
     - the environment's, else unset

The service is ``--service`` (a command line), else ``moirai-service`` beside the
interpreter, else the executable in the package (``moirai/bin``), else one on
``PATH``. Only installing the hooks needs the native module.

------------------------------------------
Removing the hooks
------------------------------------------

.. code-block:: bash

   python -m moirai.agent uninstall claude   # or codex, opencode; --user

Stop the agent first. This takes moirai's hooks out of the harness's configuration,
however they were installed and with whatever settings, leaving everything else
there alone; a configuration file with nothing else in it is removed, as is
OpenCode's plugin. It needs no settings: each hook names its run directory. In each
such directory it removes ``sessions/`` (the hooks' state) and ``runs/`` (the files
of wrapped commands), and marks a session still ``running`` as ``ended``.

What was recorded stays: the trace, the artifact store, the manifests and
``hook.log``. Deleting those is yours to do. A harness that remembers trust keeps
its own record of it (Codex's ``/hooks``). ``moirai-service`` is not touched.

Installing replaces the hooks already there, so a harness has one set of them.

------------------------------------------
Session manifests
------------------------------------------

The hooks keep one small JSON file per session, rewritten atomically (mode 0600)
by every hook event of the session, so that a consumer lists sessions without
reading the node trace. ``<dir>/manifests/<safe session id>.json``::

   {"session_id": "6f1c...", "entity": "9def37c72d49ea94",
    "harness": "codex", "cwd": "/work/project", "model": "gpt-5.2",
    "name": "sort data.csv by the second column",
    "state": "running", "turns": 2, "activities": 14,
    "started_us": 1793391263263874, "updated_us": 1793391263616315,
    "updated_at": "2026-10-30T12:34:23.616315+00:00"}

``entity`` is the 16-hex id of the ``agent.session`` entity; ``name`` the first
prompt, whitespace-collapsed, at most 120 characters, redacted like a stored
payload; ``state`` ``running`` or ``ended``; ``activities`` how many the
recorder has written so far. ``moirai.agent.manifest``, which imports without
the native module; without a directory it is ``agent_configuration().dir``:

.. code-block:: python

   from moirai.agent import manifest

   manifest.list_sessions(directory=None)   # newest first
   manifest.read(session_id, directory=None)   # dict or None
   manifest.recording(directory=None)       # a hook has work in flight
   manifest.write(directory, m); manifest.update(directory, session_id, **fields)

``recording`` is true while ``<dir>/sessions/*.json`` (the hooks' state, removed
when no session is left) exists. A manifest that cannot be written never fails
the hook. A harness that dies before its last hook leaves its state file and a
manifest that says ``running``, until `Removing the hooks`_.

------------------------------------------
Reading payloads
------------------------------------------

.. code-block:: python

   from moirai.agent.artifacts import read_text

   text = read_text(uri, trace_prefix, limit=0)   # str, or None

In process, on ``moirai.read_artifact``: the ``@name`` after the key is dropped,
bytes are decoded as UTF-8 with replacement, and hits are kept in a small
thread-safe LRU (a key is a digest, so what it names never changes). ``None`` is
a key not in the store (yet) or a moirai that cannot read; ``artifacts.error()``
says which. moirai has no trace reader: reading traces is dftracer-utils' job.

------------------------------------------
Shell lines
------------------------------------------

``moirai.agent.shell``: ``shell_files(command, cwd)`` returns the
``(scripts, reads, writes)`` a line names (the recorder's input), and
``command_lines``,
``command_language`` and ``command_summary`` show a command as it was written:
an inline program (``python3 -c $'...'``, ``bash -c``, ``perl -e``), a heredoc,
or a chain split at its operators, with the language to highlight it in.

------------------------------------------
Redaction
------------------------------------------

``moirai.agent.redact`` holds the secret patterns (``content.py`` imports them)
and:

``redact_text(text, patterns=None) -> (text, count)``
   Replaces credentials; ``patterns`` default to the built-in ones.
``is_sensitive_path(path) -> bool``
   Whether ``path`` names a file that should not be shown by name.
``redact_path(path) -> str``
   Applies the secret patterns, and replaces a sensitive file's whole path by
   ``sensitive-file:xxxxxxxx``, eight hex digits of a hash of the normalized
   path: the same file is always the same placeholder, the name is not revealed.

Sensitive files are matched case-insensitively by glob. Without a ``/`` a glob
is matched against the name, with one against the end of the path (``*`` matches
``/``, so ``.ssh/*`` is everything under a ``.ssh`` directory), starting with
``/`` against the whole path. Built in: ``.env*``, ``.netrc``, ``_netrc``,
``.git-credentials``, ``.npmrc``, ``.pypirc``, ``.pgpass``, ``.htpasswd``,
``id_rsa*``, ``id_dsa*``, ``id_ecdsa*``, ``id_ed25519*``, ``*.pem``, ``*.key``,
``*.p12``, ``*.pfx``, ``*.jks``, ``*.keystore``, ``.aws/credentials``, ``.ssh/*``,
``.gnupg/*``, ``.config/gh/hosts.yml``, ``.docker/config.json``, ``.kube/config``
and any name containing ``secret``, ``credential`` or ``token`` (which also
matches a ``tokenizer.json``: drop it with ``!*token*``).

``MOIRAI_AGENT_SENSITIVE_PATHS`` extends the list, one glob per line (blank
lines and ``#`` comments ignored); ``!glob`` drops that built-in glob; a first
line ``@only`` makes the list just what follows. It is read by
``ConfigurationManager`` (``agent_configuration().sensitive_paths``, as written);
in a process that cannot load the native module only the built-in list applies.

At record time moirai does not copy a sensitive file a tool named: its ``file``
entity is keyed by the placeholder and has no artifact. The secret patterns are
applied to the other names. A file's *content* is otherwise stored as it is, not
pattern-redacted.

This covers the ``file`` entities only. A tool's input and output are payloads:
``cat .env`` is kept with that name in ``tool.input``, and what the tool returned
is kept in ``tool.output``, with only the secret patterns applied. See `Tracing
what a command does`_ for why the names in dftracer's own I/O events cannot be
redacted by moirai.

------------------------------------------
Adding a harness
------------------------------------------

A harness is integrated by telling moirai what its events mean. Nothing below
the adapter changes: the recorder, the store and the service know no harness.

First find out what the harness offers:

* A way to run something on each event: command hooks, or a plugin that can
  start a process. It needs at least a user prompt, and a tool's start and end.
* Where its model exchanges are, as no harness hooks them: usually a transcript
  file, whose path a hook is given, or an event a plugin receives.
* What happens when a hook fails or is slow. A hook must not be able to stop its
  agent: moirai's exits 0 and prints nothing, but a plugin must see to that
  itself (``install.OPENCODE_PLUGIN`` catches everything and never waits on a
  hook, for OpenCode awaits its plugins without a timeout).

Events
   An adapter produces these dicts, each with a ``kind`` and a ``session``, and
   also ``harness`` and ``cwd``. ``tool.start`` and ``tool.end`` are matched by
   ``call``, which should be the id the model gave the tool call: the same id in
   ``tool_calls`` and ``tool_results`` is what joins a tool to the model calls
   around it.

.. list-table::
   :header-rows: 1

   * - ``kind``
     - Fields
   * - ``session.start``
     - ``model``
   * - ``session.end``
     - 
   * - ``turn.start``
     - ``prompt``
   * - ``turn.end``
     - ``reply``
   * - ``llm.start``
     - ``call``, ``model``; optional: it only marks when the call began
   * - ``llm.end``
     - ``call``, ``model``, ``request`` (the messages new in this call),
       ``response``, ``tool_calls`` (``[{id, name, input}]``), ``tool_results``
       (ids), ``usage``, ``stop_reason``, ``started``, ``ended``
   * - ``tool.start``
     - ``call``, ``name``, ``input``; and ``command`` for a shell line, which is
       parsed for scripts and files, or ``reads`` and ``writes``, lists of paths
   * - ``tool.end``
     - ``call``, ``output``, ``error``, ``exit_code``

Step 1: the adapter
   In ``adapters.py``. A harness with Claude Code's hook names and fields needs
   only a subclass, and a class that reads its transcript:

   .. code-block:: python

      class MyExchanges(Exchanges):
          """Groups my harness's transcript lines into model calls."""

          def poll(self):
              out = []
              for record in self.tail.lines():   # new whole lines only
                  ...                            # fill self.request, self.results
                                                 # and self.response
                  out += self.flush()            # when a call is complete
              return out


      class MyHarness(Adapter):
          harness = "myharness"
          exchanges = MyExchanges

   Anything else implements the same four methods itself, as ``OpenCode`` does:

   ``__init__(self, state=None)``
      Takes what ``state()`` returned for the previous hook.
   ``state(self)``
      What must outlive this hook, as JSON. A hook is a process: nothing else
      remains. ``Exchanges`` keeps its own fields and position this way; a
      subclass sets its fields in ``setup()``.
   ``translate(self, hook)``
      The payload of one hook to a list of events. It must ignore what it does
      not know, so that a new harness version adds events without harm, and read
      the transcript on the way (``poll``), as that is the only time it runs.
   ``poll(self, final=False)``
      The model calls read so far; ``final`` also those with nothing after them
      yet, at the end of a turn.

   The payload must have a ``session_id``: the state and its lock are per
   session. Add the class to ``ADAPTERS``, whose key is the name in the hook's
   command.

Step 2: the installer
   In ``install.py``, a branch in ``install`` that writes the hooks where the
   harness reads them. ``merge_hooks`` does this for a JSON file of Claude Code's
   form. The command must be ``hook_command(harness)``, or for a plugin
   ``hook_argv(harness)`` and ``hook_environment()``: absolute paths and the
   settings in effect, as a hook does not run in this environment.

Step 3: a test
   Add payloads of its shape, and a transcript in its real order, to
   ``test/py/test_agent.py``. Take them from a real session: a parser built on
   documentation alone gets the order of lines wrong, and the fixture would
   agree with it.

Step 4: a smoke test
   Add a case to ``test/smoke/smoke_agent.sh`` (:doc:`testing`) and run a real
   session. A harness that needs a key can run on a model of your own at
   ``127.0.0.1``, as Codex does there.

Things that have gone wrong in the existing adapters, worth checking in a new
one:

* A tool that is refused gets no end event: end it from what the harness does
  say (``PermissionDenied``, a ``tool`` part with an ``error``), or from the
  transcript.
* A tool's output can come before the event that closes the model call which
  asked for it.
* Several model calls can arrive in one read: ids must not come from a position
  in the file.
* A transcript is not an interface. A line that cannot be understood must not
  cost the hook it came with.
