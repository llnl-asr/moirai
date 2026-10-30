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
