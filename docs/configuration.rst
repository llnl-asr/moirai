=============
Configuration
=============

moirai is configured with ``MOIRAI_*`` environment variables only. When the
application calls ``moirai_initialize`` (and when ``moirai-service`` starts),
moirai translates them into dftracer's ``DFTRACER_*`` settings before
dftracer reads its configuration. An application never sets ``DFTRACER_*``.

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
     - ``DFTRACER_DATA_DIR``: directories whose I/O is traced (moirai's
       default: ``all``)
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
Fixed by moirai
------------------------------------------

* ``DFTRACER_ENABLE_PC_MODE=1``: producer/consumer mode, always.
* ``DFTRACER_INIT=FUNCTION``: dftracer is started by ``moirai_initialize``.
  ``MOIRAI_INIT`` and ``MOIRAI_ENABLE_PC_MODE`` are not passed through.
* ``DFTRACER_ENABLE`` follows ``MOIRAI_ENABLE``, ``DFTRACER_DISABLE_IO``
  follows ``MOIRAI_TRACE_IO``, ``DFTRACER_LOG_FILE`` follows
  ``MOIRAI_LOG_FILE`` (or the ``log_file`` given to ``moirai_initialize``).
