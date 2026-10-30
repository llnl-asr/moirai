===============
Developer Guide
===============

moirai follows dftracer's design: every part of it is an actor, a class with
its own functions and state, and every API -- C, C++ and Python -- ends in
the same C++ actors.

------------------------------------------
Layout
------------------------------------------

.. code-block:: text

   CMakeLists.txt               targets (release and _dbg), install, tests
   VERSION                      moirai's version (CMake and the docs)
   cmake/
     moirai-dftracer.cmake      the feature interface: FIND or BUILD dftracer
     moirai_config.h.in         -> <build>/include/moirai/moirai_config.h
   include/moirai/              public headers
     provenance.h               ids, stores, roles, relations, hashing (C)
     moirai.h                   the C API
     moirai.hpp                 the C++ API and moirai's event types
   src/moirai/
     core/
       common/                  Singleton, logging, enumerations
       utils/                   ConfigurationManager
       provenance/              EntityRegistry
       moirai_main.{h,cpp}      MoiraiCore
       moirai.cpp               the public actors and the C connector
     service/                   MoiraiService and moirai-service's main
     python/moirai_py.cpp       the Python binding (_moirai, _moirai_dbg)
   python/moirai/               the Python API (moirai, moirai.dbg, moirai.service,
                                moirai.agent)
   test/                        see testing
   script/formatting/           autoformat.sh, check-formatting.sh
   scripts/wheel/               build_wheels.sh, repair_wheel.sh, test_wheel.py
   pyproject.toml               the wheel (scikit-build-core)
   .github/workflows/           CI (see below)

------------------------------------------
Actors
------------------------------------------

``ConfigurationManager`` (``core/utils``)
   Reads ``MOIRAI_*`` and translates it into dftracer's settings
   (``apply``), for the application or the service side. The only place
   that knows dftracer's environment.

``EntityRegistry`` (``core/provenance``)
   The process's entities and entity types: decides what is new and writes
   the ``ET``, ``EH`` and ``ER`` records as dftracer metadata records of
   moirai's ``RecordType``.

``MoiraiCore`` (``core/moirai_main``)
   moirai in the process, through ``MOIRAI_MAIN_SINGLETON()``: owns the
   configuration and the registry; ``initialize`` applies the
   configuration, registers moirai's event types with dftracer and starts
   it; ``finalize`` stops it. Hands out the registry only while tracing.

``MoiraiService`` (``service``)
   ``dftracer_service`` for moirai: applies the service side of the
   configuration and runs the service binary.

Public actors (``moirai.hpp``)
   ``EntityType``, ``Entity`` and ``Activity``. ``Activity`` holds a dftracer
   region of moirai's ``ActivityType`` and appends relations to it with
   ``DFTracer::append_id``.

The C API (``moirai.h``) is a connector: ``moirai_entity`` makes an
``Entity``, ``moirai_activity_begin`` an ``Activity`` behind a
``MoiraiActivityData`` handle (as dftracer's ``DFTracerData``). The Python
binding binds the same classes.

------------------------------------------
Event types
------------------------------------------

moirai defines its dftracer event types at compile time, deriving from
``dftracer::EventType`` on moirai's layer, ``MOIRAI_LAYER`` (128, the first
external dftracer layer):

* ``ActivityType``: data events, ``aggregatable = false``, so dftracer
  never aggregates an activity.
* ``RecordType``: metadata records (never aggregated anyway).

``MoiraiCore::initialize`` registers ``ActivityType`` with dftracer before
any activity is logged.

------------------------------------------
Release and _dbg builds
------------------------------------------

Every target is built twice (``CMakeLists.txt``, the ``foreach(_dbg "" "_dbg")``
loop). The ``_dbg`` targets define ``MOIRAI_DEBUG``, compile with ``-g -O0``,
link cpp-logger and dftracer's ``_dbg`` libraries; the release targets
compile all logging out. Use the levels as dftracer does:

.. code-block:: cpp

   void Thing::act(int value) {
     MOIRAI_LOG_TRACE();                            // start and end
     MOIRAI_LOG_DEBUG("value %d", value);           // values
     MOIRAI_LOG_INFO("thing configured");           // information
     MOIRAI_LOG_WARN("ignored: %d", value);         // misuse moirai ignores
     MOIRAI_LOG_ERROR("cannot open %s", path);      // errors
   }

Logging formats with libc's own ``snprintf`` and a re-entry guard, because
it runs inside a process whose stdio dftracer intercepts.

------------------------------------------
Adding a dftracer feature
------------------------------------------

``cmake/moirai-dftracer.cmake`` maps moirai's feature names to dftracer's
CMake options (``_moirai_feature_<NAME>``). To add one, add its mapping and
its name to ``_moirai_all_features``; it is then accepted in
``MOIRAI_DFTRACER_FEATURES``, passed to dftracer in ``BUILD`` mode, and
forced off when not asked for. If dftracer's package records the feature
(as ``DFTRACER_INCLUDE_<NAME>``), check it in ``FIND`` mode as HDF5 and MPI
are.

------------------------------------------
Adding a provenance record
------------------------------------------

A new record kind is a method of ``EntityRegistry`` writing a
``DFTracer record(<name>, RecordType{})`` with its fields; strings passed
to ``update`` are kept by pointer until the record is written at the end of
the scope, so keep them in local buffers declared before the record. Then
give it a public actor in ``moirai.hpp``, its C connector in ``moirai.h``
and ``moirai.cpp``, its Python binding, and a case in the test scenario.

------------------------------------------
Style
------------------------------------------

C and C++ follow dftracer's ``.clang-format`` (clang-format 19.1.7):

.. code-block:: bash

   script/formatting/autoformat.sh [clang-format]          # format src, include, test
   script/formatting/check-formatting.sh [clang-format]    # what CI runs

------------------------------------------
Continuous integration
------------------------------------------

.. list-table::
   :header-rows: 1

   * - Workflow
     - What it does
   * - ``ci.yml``
     - dftracer built from git (``dftracer_ref``, default ``develop``) with
       moirai's features (``MOIRAI_DFTRACER=BUILD``), moirai on it with
       ``-Werror``, every test but the valgrind ones, on GCC 12, 13 and 14;
       and the documentation, with warnings as errors.
   * - ``valgrind-ci.yml``
     - the valgrind runs (``ctest -L valgrind``), and a gate that every
       test application ran under valgrind.
   * - ``format-check.yml``
     - ``script/formatting/check-formatting.sh`` with clang-format 19.
   * - ``wheels.yml``
     - manylinux wheels for Python 3.9 to 3.14, built and tested by
       ``scripts/wheel/build_wheels.sh``.
   * - ``python-publish.yml``
     - on a release: the wheels and an sdist to PyPI.

------------------------------------------
Wheels
------------------------------------------

moirai's wheel runs on the ``dftracer`` wheel and does not carry dftracer:

* it is built against the installed dftracer package
  (``MOIRAI_DFTRACER=PACKAGE``, set in ``pyproject.toml`` with
  ``MOIRAI_WHEEL=ON``), which is a build requirement and a dependency;
* everything is installed under ``site-packages/moirai`` with RPATHs to
  ``$ORIGIN/../dftracer/lib64``, and ``moirai-service`` runs the dftracer
  wheel's ``dftracer_service`` relative to itself;
* ``scripts/wheel/repair_wheel.sh`` runs ``auditwheel repair`` with every
  library of the dftracer wheel excluded, and keeps it away from the
  executables, which dftracer found it can leave unloadable.

.. code-block:: bash

   scripts/wheel/build_wheels.sh --list                       # the plan
   scripts/wheel/build_wheels.sh --python 3.12                # one interpreter
   MOIRAI_DFTRACER_SPEC="dftracer @ git+https://github.com/llnl-asr/dftracer@develop" \
       scripts/wheel/build_wheels.sh                          # against dftracer from git

``MOIRAI_DFTRACER_SPEC`` is the dftracer to build against. No dftracer
release has the event-type API yet, so the default is dftracer's
``develop`` branch from git, which builds as
``2.2.0.post17.dev0``; ``pyproject.toml`` requires
``dftracer>=2.2.0.post17.dev0`` to match. Once a release has the API, set
both to it.
