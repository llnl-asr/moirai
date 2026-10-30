"""moirai's Python API, over a native binding of its C++ actors.

``make_api(native)`` builds the API on one native module: ``moirai`` on
``moirai._moirai``, ``moirai.dbg`` on the debug build ``moirai._moirai_dbg``
-- as pydftracer's ``dftracer.python`` and ``dftracer.python.dbg``. A process
uses one of them: each native module brings its own dftracer.
"""
import functools

API = [
    "Activity", "Artifact", "CATEGORY", "DEFAULT_TRACE_IO", "Entity",
    "EntityType", "HAS_ARTIFACT_STORE", "HAS_HDF5", "HAS_MPI", "LAYER",
    "Lifetime", "Relation", "Role", "Store", "activity",
    "agent_configuration", "artifact_uri", "entity",
    "entity_type", "finalize", "initialize", "is_active", "read_artifact",
    "relate", "relation_name", "store_artifact", "store_artifact_file",
]


def make_api(native):
    """The API (a dict of the names in ``API``) on ``native``."""
    Store, Relation = native.Store, native.Relation

    def initialize(log_file=""):
        """Configure dftracer for provenance and start tracing; returns
        whether tracing is on. ``log_file`` overrides MOIRAI_LOG_FILE."""
        return native.initialize(log_file)

    def entity_type(name, role, description=""):
        """Describe an entity type once per process (an ET record)."""
        return native.EntityType(name, role, description)

    def entity(type, key, store=Store.MEMORY, uri=""):
        """Declare an entity once per process (an EH record)."""
        return native.Entity(type, key, store, uri)

    def as_entity(e):
        """An Entity from an Entity, an id, or a (type, key[, store, uri])
        tuple, which declares it."""
        if isinstance(e, native.Entity):
            return e
        if isinstance(e, tuple):
            return entity(*e)
        return native.Entity(int(e))

    def relate(relation, subject, object):
        """Relate two entities (an ER record), without any activity."""
        as_entity(subject).relate(relation, as_entity(object))

    class Activity:
        """One activity event, never aggregated, from ``with`` (or
        :meth:`begin`) to its end, relating the entities it touched:
        :class:`Entity` objects, ids, or ``(type, key)`` /
        ``(type, key, store, uri)`` tuples, declared on the way."""

        def __init__(self, name):
            self.name = name
            self._native = None

        def __enter__(self):
            return self.begin()

        def __exit__(self, *exc):
            self.end()
            return False

        def begin(self):
            if self._native is None:
                self._native = native.Activity(self.name)
            return self

        def end(self):
            if self._native is not None:
                self._native.end()
                self._native = None

        def relate(self, relation, e):
            self.begin()
            if isinstance(e, tuple):
                return self._native.relate_entity(relation, *e)
            e = as_entity(e)
            self._native.relate(relation, e)
            return e

        def used(self, e):
            return self.relate(Relation.USED, e)

        def generated(self, e):
            return self.relate(Relation.GENERATED, e)

        def invalidated(self, e):
            return self.relate(Relation.INVALIDATED, e)

        def updated(self, e):
            return self.relate(Relation.UPDATED, e)

        def span(self, start_us, end_us):
            """What it really spanned, when that was not this object's
            lifetime: microseconds since the epoch, in the event's args."""
            self.begin()
            self._native.span(int(start_us), int(end_us))

        def uses(self, type, key, store=Store.MEMORY, uri=""):
            return self.relate(Relation.USED, (type, key, store, uri))

        def generates(self, type, key, store=Store.MEMORY, uri=""):
            return self.relate(Relation.GENERATED, (type, key, store, uri))

    def activity(name=None, used=(), generated=(), invalidated=(),
                 updated=()):
        """Decorator: each call of the function is an activity named
        ``name`` (the function's name by default) relating the entities."""

        def wrap(fn):
            label = name or fn.__name__

            @functools.wraps(fn)
            def call(*args, **kwargs):
                with Activity(label) as act:
                    for relation, entities in (
                        (Relation.USED, used),
                        (Relation.GENERATED, generated),
                        (Relation.INVALIDATED, invalidated),
                        (Relation.UPDATED, updated),
                    ):
                        for e in entities:
                            act.relate(relation, e)
                    return fn(*args, **kwargs)

            return call

        return wrap

    def as_bytes(content):
        if isinstance(content, str):
            return content.encode("utf-8", "surrogateescape")
        return content

    def store_artifact(content):
        """Keep ``content`` (str or bytes) next to the trace, once, a transient
        artifact; give its ``uri`` to an entity."""
        return native.store_artifact(as_bytes(content))

    def artifact_uri(content):
        """The URI ``content`` has as an artifact, storing nothing."""
        return native.artifact_uri(as_bytes(content))

    def store_artifact_file(path, lifetime=native.Lifetime.PERSISTENT):
        """A file as an artifact: its content stored if transient, a link to
        it if persistent."""
        return native.store_artifact_file(str(path), lifetime)

    def read_artifact(uri, log_file=""):
        """The bytes at ``uri``, or None if they are not there or a linked
        file has changed. ``log_file`` is the run's trace prefix. A URI may
        carry the name of what it holds after an ``@``, as a file entity's
        does; only what comes before it is the key."""
        return native.read_artifact(uri.split("@", 1)[0], str(log_file))

    return {
        "Activity": Activity,
        "Artifact": native.Artifact,
        "CATEGORY": native.CATEGORY,
        "DEFAULT_TRACE_IO": native.DEFAULT_TRACE_IO,
        "Entity": native.Entity,
        "EntityType": native.EntityType,
        "HAS_ARTIFACT_STORE": native.HAS_ARTIFACT_STORE,
        "HAS_HDF5": native.HAS_HDF5,
        "HAS_MPI": native.HAS_MPI,
        "LAYER": native.LAYER,
        "Lifetime": native.Lifetime,
        "Relation": Relation,
        "Role": native.Role,
        "Store": Store,
        "activity": activity,
        "agent_configuration": native.agent_configuration,
        "artifact_uri": artifact_uri,
        "entity": entity,
        "entity_type": entity_type,
        "finalize": native.finalize,
        "initialize": initialize,
        "is_active": native.is_active,
        "read_artifact": read_artifact,
        "relate": relate,
        "relation_name": native.relation_name,
        "store_artifact": store_artifact,
        "store_artifact_file": store_artifact_file,
    }
