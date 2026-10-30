=======
Running
=======

moirai traces through a ``dftracer_service`` on each node, run with
``moirai-service``. Start it before the application and stop it after,
with the same ``MOIRAI_LOG_FILE``:

.. code-block:: bash

   export MOIRAI_LOG_FILE=$PWD/traces/run1
   export MOIRAI_DATA_DIR=$PWD/data        # I/O traced here
   moirai-service start
   ./my_app                                # calls moirai_initialize
   moirai-service stop

``moirai-service stop`` drains the ring and closes the node trace,
``traces/run1_<host>.pfw.gz``; the service's log and pid file are next to it.

------------------------------------------
Reading a trace while it runs
------------------------------------------

The node trace can be read while the service runs. The service seals what it
receives into whole gzip members of ``<prefix>_<host>.pfw.gz``, so what a process
wrote is there soon after, about a second here, and no other file is made.
Producers publish on their own timer, ``MOIRAI_PC_FLUSH_MS``, and at
``moirai_finalize``.

The file is a sequence of independent gzip members, and each is written at a
reserved offset, so the last may be unfinished and one can be missing for a
moment. A reader decodes member by member, keeps its position at the end of the
last whole one and tries again from there: a plain ``gzip`` reader fails at an
unfinished member.

------------------------------------------
Several jobs on one node
------------------------------------------

Give each its own ring with ``MOIRAI_SERVICE_SHM``:

.. code-block:: bash

   export MOIRAI_SERVICE_SHM=/moirai-$SLURM_JOB_ID

------------------------------------------
The ring's size
------------------------------------------

The service's ring is a file in ``/dev/shm`` of ``MOIRAI_PC_BLOCKS`` blocks of
``MOIRAI_PC_BLOCK_SIZE`` bytes: by default 1024 x 1 MiB, 1 GiB per service.
Where ``/dev/shm`` is small (containers, CI runners), or several services run
on one node, make it smaller; the application and the service must use the
same values:

.. code-block:: bash

   export MOIRAI_PC_BLOCKS=16            # 16 MiB

If the ring cannot be created the service does not start (``No space left
on device`` in its log), and the application's events go to its spill file.

------------------------------------------
Without a service
------------------------------------------

If no service runs, nothing is lost: each process writes its events to a
spill file, ``<MOIRAI_LOG_FILE>-<hash>-spill.pfw.gz``, in the same format.

------------------------------------------
Debugging
------------------------------------------

Link the ``_dbg`` build (``libmoirai_dbg``, ``moirai-service_dbg``, or
``import moirai.dbg``) and set ``MOIRAI_LOG_LEVEL``:

.. list-table::
   :header-rows: 1

   * - Level
     - What is logged
   * - ``ERROR``, ``WARN``
     - errors, and misuse moirai ignores (e.g. an entity relation on an
       activity)
   * - ``INFO``
     - what moirai does: its configuration, start and stop
   * - ``DEBUG``
     - values: the dftracer settings moirai sets, each record and relation
   * - ``TRACE``
     - the start and end of every moirai function
