=============
Configuration
=============

moirai is configured with ``MOIRAI_*`` environment variables only. When the
application calls ``moirai_initialize`` (and when ``moirai-service`` starts),
moirai translates them into dftracer's ``DFTRACER_*`` settings before
dftracer reads its configuration. A Python application also gets them when it
imports ``moirai`` (see `dftracer from Python`_). An application never sets
``DFTRACER_*``.

------------------------------------------
moirai's settings
------------------------------------------

.. list-table::
   :header-rows: 1

   * - Variable
     - Default
     - Meaning
   * - ``MOIRAI_ENABLE``
     - ``1``
     - ``0`` turns tracing off; the API still works and returns ids.
   * - ``MOIRAI_LOG_FILE``
     - dftracer's
     - Trace prefix. The node trace is ``<prefix>_<host>.pfw.gz``. The
       application and ``moirai-service`` must use the same one.
   * - ``MOIRAI_TRACE_IO``
     - build setting
     - ``1``/``0``: trace POSIX/STDIO I/O on the data directories.
   * - ``MOIRAI_DFTRACER_SERVICE``
     - the build's
     - The ``dftracer_service`` binary ``moirai-service`` runs.
   * - ``MOIRAI_AGENT_*``
     - 
     - ``moirai.agent``'s settings, see :doc:`agents`. Not passed to dftracer.
   * - ``MOIRAI_LOG_LEVEL``
     - ``ERROR``
     - ``ERROR``, ``WARN``, ``INFO``, ``DEBUG``, ``TRACE``: moirai's own
       logging in the ``_dbg`` build, and dftracer's.

------------------------------------------
dftracer's settings, under moirai's name
------------------------------------------

Every other ``MOIRAI_<X>`` is dftracer's ``DFTRACER_<X>``, for example:

.. list-table::
   :header-rows: 1

   * - Variable
     - dftracer setting
   * - ``MOIRAI_DATA_DIR``
     - ``DFTRACER_DATA_DIR``: ``:``-separated directories whose I/O is
       traced, each also by its real path when that differs (moirai's default:
       ``all``)
   * - ``MOIRAI_SERVICE_SHM``
     - ``DFTRACER_SERVICE_SHM``: the service's ring, to run several
       services on one node
   * - ``MOIRAI_ENABLE_AGGREGATION``
     - ``DFTRACER_ENABLE_AGGREGATION``: aggregate I/O and other events
       (activities never are)
   * - ``MOIRAI_CONFIGURATION``
     - ``DFTRACER_CONFIGURATION``: a dftracer YAML file
   * - ``MOIRAI_PC_BLOCKS``, ``MOIRAI_PC_BLOCK_SIZE``
     - ``DFTRACER_PC_BLOCKS``, ``DFTRACER_PC_BLOCK_SIZE``: the service's ring
       in ``/dev/shm`` (default 1024 x 1 MiB); see :doc:`running`
   * - ``MOIRAI_TRACE_COMPRESSION``, ...
     - the same ``DFTRACER_*`` setting

------------------------------------------
dftracer from Python
------------------------------------------

pydftracer (``dftracer.python``, the ``dft_fn`` decorators and
``dftracer.initialize_log``) reads ``DFTRACER_ENABLE`` and ``DFTRACER_INIT``
when it is imported, which is before an application starts moirai. So
``import moirai`` applies the application side of the translation above in
``os.environ`` at once, with the same names and values, and
``moirai_initialize`` applies it again:

.. list-table::
   :header-rows: 1

   * - Variable set at import
     - Value
   * - ``DFTRACER_ENABLE``
     - ``1``, or ``0`` when ``MOIRAI_ENABLE`` turns tracing off
   * - ``DFTRACER_INIT``
     - ``FUNCTION``: moirai starts dftracer itself
   * - ``DFTRACER_ENABLE_PC_MODE``
     - ``1``: events go through the service or its spill file
   * - ``DFTRACER_ATTACH``
     - ``1``: moirai owns the tracing core of the process
   * - ``DFTRACER_LOG_FILE``, ``DFTRACER_DISABLE_IO``
     - from ``MOIRAI_LOG_FILE`` and ``MOIRAI_TRACE_IO`` when they are set
   * - ``DFTRACER_<X>``
     - from every other ``MOIRAI_<X>``

``DFTRACER_ATTACH=1`` makes pydftracer's ``initialize_log`` attach to the core
that moirai runs instead of initializing it a second time (a second
initialization makes the process abort at exit and the decorators log
nothing), and leaves ``finalize`` to moirai. pydftracer reads only this
variable; it does not look for moirai.

``import moirai`` also imports pydftracer, after setting the variables above,
so that an application can use pydftracer's annotations without importing it:
``moirai.dft_fn`` (the function decorator), ``moirai.dftracer`` (``initialize_log``
and the regions) and ``moirai.ai``. moirai works without pydftracer; these names
are then absent. Import ``moirai`` before the first ``dftracer.python`` import:
pydftracer decides at its own import whether it is enabled.

------------------------------------------
Process metadata
------------------------------------------

While tracing, ``moirai_initialize`` records who ran the process and how it
was configured, as dftracer process metadata (``CM`` records:
``args.name``/``args.value``), once per process:

* ``user_hash``, ``group_hash``: the user and group, only as hashes
  (``moirai_hash(kind, MOIRAI_ID_SALT + name)``). The names behind them are
  ``identity`` entities (``EH``, uri ``<hash>=<name>``) related to nothing:
  dropping the ``identity`` records anonymizes the trace, and no id dangles.
* ``job``: the first of ``FLUX_JOB_ID``, ``SLURM_JOB_ID``, ``PBS_JOBID``,
  ``LSB_JOBID``, ``COBALT_JOBID``; ``pid``, ``ppid``; ``moirai.enable``,
  ``moirai.trace_io``.
* ``env.<NAME>``: the configuration environment - every ``MOIRAI_*``,
  ``DFTRACER_*`` and ``OMP_*`` variable, the launcher's job, rank and size
  (Flux, Slurm, PBS, LSF, PMI, Open MPI, PALS), threading (``MKL_NUM_THREADS``,
  ``OPENBLAS_NUM_THREADS``) and devices (``CUDA_``/``ROCR_``/``HIP_``/
  ``NVIDIA_VISIBLE_DEVICES``). The user's name in a value (a path under a home
  or a workspace) is replaced by ``@user:<user_hash>``. A name holding
  ``TOKEN``, ``SECRET``, ``PASSW``, ``CREDENTIAL``, ``API_KEY`` or ``AUTH`` is
  never recorded.

.. list-table::
   :header-rows: 1

   * - Variable
     - Default
     - Meaning
   * - ``MOIRAI_ID_SALT``
     - empty
     - Salt of the identity hashes: a site secret makes the hashes of common
       names hard to guess. Use the same one everywhere the traces are read.
   * - ``MOIRAI_METADATA_ENV``
     - empty
     - ``A,B,C``: more variable names to record as ``env.<NAME>``.
   * - ``MOIRAI_PROCESS_METADATA``
     - ``1``
     - ``0``: record no ``env.*`` (who ran it and the job are still recorded).

An application adds its own with ``moirai::metadata(key, value)``
(``moirai_metadata``, ``moirai.metadata``); see :doc:`api`.

------------------------------------------
Fixed by moirai
------------------------------------------

* ``DFTRACER_ENABLE_PC_MODE=1``: producer/consumer mode, always.
* ``DFTRACER_INIT=FUNCTION``: dftracer is started by ``moirai_initialize``.
  ``MOIRAI_INIT`` and ``MOIRAI_ENABLE_PC_MODE`` are not passed through.
* ``DFTRACER_ENABLE`` follows ``MOIRAI_ENABLE``, ``DFTRACER_DISABLE_IO``
  follows ``MOIRAI_TRACE_IO``, ``DFTRACER_LOG_FILE`` follows
  ``MOIRAI_LOG_FILE`` (or the ``log_file`` given to ``moirai_initialize``).
