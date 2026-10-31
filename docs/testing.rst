=======
Testing
=======

.. code-block:: bash

   cmake -S moirai -B build -DMOIRAI_ENABLE_TESTS=ON \
         -DCMAKE_PREFIX_PATH=<dftracer prefix> -DMOIRAI_WARNINGS_AS_ERRORS=ON
   cmake --build build -j
   cd build && ctest -j 8

------------------------------------------
The scenario
------------------------------------------

``test/c/test_api.c``, ``test/cpp/test_api.cpp`` and ``test/py/test_api.py``
run one provenance scenario through the C, C++ and Python APIs:

* three entity types (input, output, parameter), one declared twice;
* six entities over four stores, one declared twice, two declared through
  activities;
* four activities relating every activity relation, one ended by its
  block (C), one on another thread (C++), one a decorated function
  (Python), one writing and reading a file in the data directory;
* all seven entity relations, by object and by id (Python also declares
  entities from ``(type, key)`` tuples, in the decorator);
* misuse that must be ignored: an entity relation on an activity, an
  activity relation between entities, a missing entity.

With the argument ``direct`` the same entities and entity relations are
declared without any activity.

------------------------------------------
Runs
------------------------------------------

Each scenario runs as a moirai user would run it -- ``MOIRAI_*`` settings
only -- through ``test/run_case.sh``, once with the release build and once
with the ``_dbg`` build:

.. list-table::
   :header-rows: 1

   * - Test
     - Run
   * - ``moirai_<lang>[_dbg]_service``
     - through ``moirai-service``, I/O traced
   * - ``..._service_noio``
     - ``MOIRAI_TRACE_IO=0``
   * - ``..._spill``
     - no service: everything in the spill file
   * - ``..._aggregation``
     - ``MOIRAI_ENABLE_AGGREGATION=1`` (a dftracer setting under its moirai
       name): activities still traced in full
   * - ``..._direct``
     - entities and relations only
   * - ``..._disabled``
     - ``MOIRAI_ENABLE=0``: no trace, the API still works
   * - ``..._valgrind``
     - the full scenario under valgrind's memcheck (label ``valgrind``)

------------------------------------------
The checker
------------------------------------------

``test/check_provenance.py <work dir> <service|spill|none> <io> [scenario]``
reads the run's traces and checks, exactly:

* the trace went where the mode says (node trace, spill file, or none), and
  the application wrote no trace of its own (producer/consumer mode);
* every ``ET``, ``EH`` and ``ER`` record, each once, with the ids computed
  independently in Python;
* every activity: a complete event in category ``moirai`` on layer 128,
  with exactly its relations;
* the I/O on the scenario's file traced, or not, as ``MOIRAI_TRACE_IO`` says.

------------------------------------------
Valgrind
------------------------------------------

With valgrind installed (``MOIRAI_TEST_VALGRIND``, on by default when it is
found) every test application also runs the full scenario under memcheck,
with dftracer's flags; only the application runs under valgrind, not the
service or the scripts:

.. code-block:: bash

   ctest --test-dir build -L valgrind

* C and C++ (release and ``_dbg``): any memory error, or a definite or
  possible leak, fails the run.
* Python: CPython reports thousands of objects it interns or unmarshals at
  start and never frees. As dftracer's Python valgrind runner does, only a
  context with a moirai or dftracer frame fails the run
  (``test/valgrind/check_valgrind_log.py``); the rest is counted.

Each run's log is ``<build>/test/moirai_<lang>[_dbg]_valgrind/valgrind.log``.
Known reports from outside moirai go in ``test/valgrind/moirai.supp``, each
with its reason.

------------------------------------------
Wheels
------------------------------------------

``scripts/wheel/test_wheel.py`` checks an installed wheel: both APIs import
from ``site-packages``, the libraries load, both ``moirai-service`` builds
start, and the scenario passes end to end through ``moirai-service``,
release and ``_dbg``. ``scripts/wheel/build_wheels.sh`` runs it on every
wheel it builds.

------------------------------------------
Agent smoke tests
------------------------------------------

``test/py/test_agent.py`` runs in ``ctest``: the installed hook command, with
nothing inherited, on payloads of each harness's shape. So do
``test_agent_manifest.py`` (manifests, sensitive files and ``read_text`` through
the hook and the store), ``test_datadir_native.py`` (``MOIRAI_DATA_DIR``) and,
with no service or store and ``fake_api.py`` for moirai's API, ``test_shell.py``,
``test_manifest.py``, ``test_record.py``, ``test_redact.py`` and
``test_artifact_client.py``. None can tell whether a harness really sends them.
``test/smoke/smoke_agent.sh`` can: one real session, which runs a script that writes a file, through ``moirai-service``, and
``test/smoke/check_agent.py`` on what it left. It is not in ``ctest``, as it needs
the harness, and Claude Code's run is a real model call.

.. code-block:: bash

   bash test/smoke/smoke_agent.sh <claude|codex> <build dir> <python>

It works in ``<build dir>/smoke/<harness>``; ``harness.out`` and
``run/hook.log`` there say what happened. Codex runs on
``test/smoke/fake_responses.py``, a stand-in model on ``127.0.0.1``, so no key is
needed. Codex only runs hooks that were trusted with ``/hooks``: otherwise it
works as usual and records nothing, and the check fails.
