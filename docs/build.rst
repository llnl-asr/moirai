=====
Build
=====

moirai is a CMake project (3.24 or newer) in C++17 and C11. It needs a
dftracer with the event-type API: already installed, built by moirai with
moirai's features, or the dftracer Python wheel.

------------------------------------------
From PyPI
------------------------------------------

.. code-block:: bash

   pip install moirai          # brings the dftracer wheel it runs on

The wheel has the Python API (``moirai``, ``moirai.dbg``), ``libmoirai`` with
its headers (``site-packages/moirai/{lib64,include}``) and the
``moirai-service`` command. It runs on the ``dftracer`` wheel, so its
dftracer features are that wheel's: I/O tracing, no HDF5 or MPI. For those,
build from source.

------------------------------------------
Against an installed dftracer
------------------------------------------

.. code-block:: bash

   cmake -S moirai -B build \
         -DCMAKE_PREFIX_PATH=<dftracer prefix> \
         -DCMAKE_INSTALL_PREFIX=<prefix>
   cmake --build build -j
   cmake --install build

moirai checks the dftracer it finds: it must have the event-type API, and it
must have been built with HDF5 and MPI if moirai asks for them.

------------------------------------------
Building dftracer with moirai
------------------------------------------

With ``-DMOIRAI_DFTRACER=BUILD`` moirai first builds dftracer with exactly
moirai's features (in two passes, as dftracer's own build does: its
dependencies, then dftracer), then itself against it. Both are installed
while building, into one prefix -- ``CMAKE_INSTALL_PREFIX``, by default
``<build>/install`` -- and moirai's build tree, with its tests, is
``<build>/moirai``:

.. code-block:: bash

   cmake -S moirai -B build -DMOIRAI_DFTRACER=BUILD \
         -DMOIRAI_DFTRACER_SOURCE_DIR=<dftracer checkout>   # or:
         # -DMOIRAI_DFTRACER_GIT_REPOSITORY=... -DMOIRAI_DFTRACER_GIT_TAG=...
   cmake --build build -j
   ctest --test-dir build/moirai          # with -DMOIRAI_ENABLE_TESTS=ON

------------------------------------------
Features
------------------------------------------

Every dftracer feature moirai uses is chosen when moirai is built and passed
down to dftracer; everything else is off.

.. list-table::
   :header-rows: 1

   * - CMake option
     - Default
     - What it does
   * - ``MOIRAI_TRACE_IO``
     - ``ON``
     - Default of ``MOIRAI_TRACE_IO``: trace POSIX/STDIO I/O. (I/O
       tracing is always built in; this is the run-time default.)
   * - ``MOIRAI_ENABLE_HDF5``
     - ``OFF``
     - Trace HDF5 (``DFTRACER_ENABLE_HDF5``).
   * - ``MOIRAI_ENABLE_MPI``
     - ``OFF``
     - Trace MPI (``DFTRACER_ENABLE_MPI``).
   * - ``MOIRAI_DFTRACER_FEATURES``
     - empty
     - More dftracer features, a list of ``HIP CUDA PAPI VARIORUM
       FTRACING``. They are about performance rather than provenance and
       are off unless asked for.
   * - ``MOIRAI_DFTRACER``
     - ``FIND``
     - ``FIND`` an installed dftracer, ``BUILD`` one, or use the installed
       dftracer Python ``PACKAGE`` (``MOIRAI_DFTRACER_PACKAGE_DIR``, else
       found by importing it; what moirai's wheels use).
   * - ``MOIRAI_BUILD_PYTHON``
     - ``ON``
     - Build the Python API (needs pybind11 and Python development files).
   * - ``MOIRAI_ENABLE_TESTS``
     - ``OFF``
     - Build and register the tests (:doc:`testing`).

------------------------------------------
What is built
------------------------------------------

Every target is built twice, as dftracer's are: a release build with all
logging compiled out, and a ``_dbg`` build with moirai's logging compiled in
(through cpp-logger) on dftracer's ``_dbg`` build.

.. list-table::
   :header-rows: 1

   * - Release
     - Debug
     - What
   * - ``libmoirai.so``
     - ``libmoirai_dbg.so``
     - The C and C++ API.
   * - ``moirai-service``
     - ``moirai-service_dbg``
     - ``dftracer_service`` configured for provenance.
   * - ``moirai/_moirai*.so``
     - ``moirai/_moirai_dbg*.so``
     - The Python binding, under the ``moirai`` and ``moirai.dbg``
       packages.

Headers are installed under ``include/moirai``; the Python package under
``lib/python<X.Y>/site-packages/moirai`` (``MOIRAI_PYTHON_INSTALL_DIR``).

------------------------------------------
Artifact store
------------------------------------------

Artifacts need dftracer-utils with RocksDB's headers. They are looked for next
to dftracer and in the Python environment; otherwise give
``-DMOIRAI_DFTRACER_UTILS_PREFIX=<prefix>`` and, if the headers are elsewhere,
``-DMOIRAI_ROCKSDB_INCLUDE_DIR=<dir>``. Without them moirai builds with a
warning, and artifacts are not stored (``-DMOIRAI_ARTIFACTS=OFF`` asks for that).
