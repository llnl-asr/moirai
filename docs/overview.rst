========
Overview
========

moirai is a provenance library for C, C++ and Python applications. An
application tells moirai what it works with and what it does; moirai writes
it into a dftracer trace.

------------------------------------------
Concepts
------------------------------------------

Entity type
   A kind of data in the workflow (``dataset``, ``model``, ``config``), with
   a role -- input, output, intermediate, parameter, reference -- and a
   description. Written once per process as an ``ET`` record.

Entity
   One instance: a type and an application key (a path, a name, a hash).
   Its id is a 64-bit FNV-1a hash of (type, key), the same in every language
   and process, so independent processes name the same entity the same way.
   It also has a store (memory, local disk, parallel file system, object
   store, ...) and an optional URI. Written once per process as an ``EH``
   record. The key itself is never written.

Entity relation
   Between two entities: ``derived_from``, ``revision_of``, ``contains``,
   ``part_of``, ``specialization_of``, ``alternate_of``, ``depends_on``.
   Written as an ``ER`` record.

Activity
   Something the application does, from its start to its end: one dftracer
   event relating it to the entities it ``used``, ``generated``,
   ``invalidated`` or ``updated``. Activities are never aggregated, also
   when dftracer aggregation is on: every one is in the trace.

Activities are optional. An application can declare entities and relate
them directly, or run activities to record where each entity came from --
or both.

------------------------------------------
How it runs
------------------------------------------

moirai is always integrated directly: the application links ``libmoirai``
(or imports ``moirai`` in Python) and calls ``moirai_initialize``. moirai
then configures and starts dftracer for provenance:

* **Always producer/consumer mode.** The application's events go through a
  shared-memory ring to a ``dftracer_service``, started with
  ``moirai-service``, which writes one trace per node. Without a running
  service the events go to a spill file next to the trace, so nothing is
  lost.
* **I/O tracing on or off.** POSIX/STDIO calls on the data directories are
  traced with the provenance when ``MOIRAI_TRACE_IO`` is on.
* **HDF5 and MPI** are traced when moirai was built with them.
* **Configuration is moirai's.** The application sets ``MOIRAI_*`` only;
  moirai translates it into dftracer's settings (see
  :doc:`configuration`).

.. code-block:: text

   application ──moirai API──▶ libmoirai ──▶ dftracer (in the application)
                                                  │ ring (shared memory)
                                                  ▼
                       moirai-service ──▶ dftracer_service ──▶ <log>_<host>.pfw.gz
