===
API
===

The same API in C++, C and Python. C++ is the implementation: the C API is
its connector and the Python API is bound to it, so all three write the same
records.

Strings passed to moirai are copied and sanitized to a JSON-safe character
set (letters, digits and ``_ - . : / @ + = , ~`` and space; anything else
becomes ``_``). Types are cut at 31 characters, URIs and descriptions at
255.

------------------------------------------
C++
------------------------------------------

.. code-block:: cpp

   #include <moirai/moirai.hpp>

   int main() {
     moirai::initialize();  // or initialize("<log file>")

     moirai::EntityType dataset("dataset", MOIRAI_ROLE_INPUT, "raw input");
     moirai::EntityType model("model", MOIRAI_ROLE_OUTPUT, "trained model");

     moirai::Entity in0("dataset", "in0", MOIRAI_STORE_PARALLEL_FS,
                        "file:///data/in0.h5");
     {
       moirai::Activity train("train");          // one event, never aggregated
       train.used(in0);
       moirai::Entity m0 = train.generates("model", "m0");  // declare + relate
       m0.relate(MOIRAI_REL_DERIVED_FROM, in0);  // entity -> entity
     }                                           // the event ends here
     moirai::finalize();
   }

``moirai::initialize(log_file = "")``, ``moirai::finalize()``, ``moirai::is_active()``
   Start and stop tracing. ``initialize`` returns whether tracing is on
   (``MOIRAI_ENABLE``); calling it again does nothing.

``moirai::EntityType(name, role, description = "")``
   Describes an entity type, once per process.

``moirai::Entity(type, key, store = MOIRAI_STORE_MEMORY, uri = "")``, ``moirai::Entity(id)``
   Declares an entity (once per process), or refers to one by id. ``id()``
   is its id; ``relate(relation, object)`` relates it, as subject, to
   another entity with an entity relation.

``moirai::Activity(name)``
   One activity event for the object's lifetime. ``relate(relation,
   entity)``, ``used``, ``generated``, ``invalidated``, ``updated`` relate it
   to an entity; ``relate(relation, type, key, store, uri)``, ``uses`` and
   ``generates`` declare the entity and relate it. ``name`` must outlive the
   activity (a string literal, usually).

``MOIRAI_CPP_FUNCTION()``, ``MOIRAI_CPP_ACTIVITY(name)``
   An activity for the enclosing scope: ``moirai_fn``, named after the
   function, or ``moirai_<name>``.

Relations that do not fit -- an entity relation on an activity, an activity
relation between entities -- are ignored (and logged as a warning in the
``_dbg`` build).

------------------------------------------
C
------------------------------------------

.. code-block:: c

   #include <moirai/moirai.h>

   int main(void) {
     MoiraiId in0, m0;
     moirai_initialize(NULL);
     moirai_entity_type("dataset", MOIRAI_ROLE_INPUT, "raw input");
     in0 = moirai_entity("dataset", "in0", MOIRAI_STORE_PARALLEL_FS,
                         "file:///data/in0.h5");
     {
       MOIRAI_C_ACTIVITY_START(train);
       MOIRAI_C_ACTIVITY_USED(train, in0);
       m0 = moirai_activity_relate_entity(moirai_train, MOIRAI_REL_GENERATED,
                                          "model", "m0", MOIRAI_STORE_MEMORY,
                                          NULL);
       MOIRAI_C_ACTIVITY_END(train);
     }
     moirai_relate(MOIRAI_REL_DERIVED_FROM, m0, in0);
     moirai_finalize();
     return 0;
   }

.. list-table::
   :header-rows: 1

   * - Function
     - C++ equivalent
   * - ``moirai_initialize``, ``moirai_finalize``, ``moirai_is_active``
     - ``moirai::initialize``, ``finalize``, ``is_active``
   * - ``moirai_entity_type(type, role, description)``
     - ``moirai::EntityType``
   * - ``moirai_entity(type, key, store, uri)`` → ``MoiraiId``
     - ``moirai::Entity``
   * - ``moirai_relate(relation, subject, object)``
     - ``Entity::relate``
   * - ``moirai_activity_begin(name)`` → ``struct MoiraiActivityData*``,
       ``moirai_activity_end``
     - ``moirai::Activity``
   * - ``moirai_activity_relate(data, relation, id)``,
       ``moirai_activity_relate_entity(data, relation, type, key, store, uri)``
     - ``Activity::relate``

Macros, as dftracer's region macros: ``MOIRAI_C_FUNCTION_START()`` /
``MOIRAI_C_FUNCTION_END()`` (``moirai_fn``), ``MOIRAI_C_ACTIVITY_START(name)``
/ ``MOIRAI_C_ACTIVITY_END(name)`` (``moirai_<name>``), and
``MOIRAI_C_ACTIVITY_RELATE``, ``_USED``, ``_GENERATED``, ``_INVALIDATED``,
``_UPDATED``. With GCC and Clang an activity started by a macro also ends
when its block is left.

------------------------------------------
Python
------------------------------------------

.. code-block:: python

   import moirai            # moirai.dbg: the same API on the _dbg build
   from moirai import Relation, Role, Store

   moirai.initialize()
   moirai.entity_type("dataset", Role.INPUT, "raw input")
   in0 = moirai.entity("dataset", "in0", Store.PARALLEL_FS, "file:///data/in0.h5")

   with moirai.Activity("train") as train:
       train.used(in0)
       m0 = train.generates("model", "m0")
   moirai.relate(Relation.DERIVED_FROM, m0, in0)

   @moirai.activity(used=[("dataset", "in0")], generated=[("model", "m1")])
   def refine():
       ...

   moirai.finalize()

Entities can be given as ``Entity`` objects, ids, or ``(type, key)`` /
``(type, key, store, uri)`` tuples, which are declared on the way.
``moirai.Entity``, ``moirai.EntityType`` and the ``Store``, ``Role`` and
``Relation`` enums are the C++ actors themselves. A process uses either
``moirai`` or ``moirai.dbg``, not both: each brings its own dftracer.

.. _artifacts:

------------------------------------------
Artifacts
------------------------------------------

An artifact is content too large for a trace, kept next to it, in a RocksDB of
dftracer-utils: a store in C++,
with C and Python adapters. An entity holds its key as its URI, so the trace
holds only ``artifact://<16 hex digits>``.

.. code-block:: python

   out = moirai.store_artifact(stdout_text)        # transient: content stored
   moirai.entity("tool.output", "call-1", moirai.Store.DATABASE, out.uri)

   data = moirai.store_artifact_file("/p/data/in.h5")  # persistent: a link
   tmp = moirai.store_artifact_file("/tmp/x", moirai.Lifetime.TRANSIENT)

   moirai.read_artifact(out.uri)                   # bytes, or None
   moirai.read_artifact(out.uri, "traces/run1")    # after the run

.. list-table::
   :header-rows: 1

   * - C++
     - C
     - Python
   * - ``store_artifact(content)``
     - ``moirai_artifact(data, size, uri)``
     - ``store_artifact(content)``
   * - ``store_artifact_file(path, lifetime)``
     - ``moirai_artifact_file(path, lifetime, uri)``
     - ``store_artifact_file(path, lifetime)``
   * - ``read_artifact(uri, &content, log_file)``
     - ``moirai_artifact_read(uri, &data, &size, log_file)``
     - ``read_artifact(uri, log_file)``
   * - ``artifact_uri(content)``
     - 
     - ``artifact_uri(content)``

Lifetime
   ``TRANSIENT`` content goes away, so it is stored. ``PERSISTENT`` content
   stays where it is, so only a link is stored: path, size and mtime. A read
   through a link returns nothing if the file is gone or has changed.

Keys
   FNV-1a, as moirai's ids, of the size and the content; past 64 KiB, of 64
   blocks of 1 KiB spread over it, so a key costs about the same at any size.
   Content is stored once. Because a key is of a sample, two large contents can
   share one: a process that finds a key it stored compares them, and other
   content takes the next key. Between two processes that is found out only at
   the second one's batch, which keeps its content under ``<key>-<pid>``, while
   a read of the key gets the first. A key is not a proof of equality between
   runs. A persistent file past 64 KiB is also held to its
   mtime, as an edit between samples would not change its key.

The store is one database per node, ``<MOIRAI_LOG_FILE>.artifacts/<host>``, for
all its producers. RocksDB has one open writer at a time, so a put waits in
memory, and a batch takes the database, writes and closes it, waiting its turn:
content is durable from that batch on, at 8 MiB and at ``finalize``. Tracing off
(``MOIRAI_ENABLE=0``), or built without dftracer-utils, artifacts get their key
and are not stored.
