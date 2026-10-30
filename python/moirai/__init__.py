"""moirai: data provenance for Python applications, traced by dftracer.

The Python API over moirai's C++ actors, with the same run-time configuration
(``MOIRAI_*``, see include/moirai/moirai.h). ``moirai.dbg`` is the same API on
the debug build, with moirai's and dftracer's logging compiled in::

    import moirai

    moirai.initialize()
    moirai.entity_type("dataset", moirai.Role.INPUT, "raw input")
    src = moirai.entity("dataset", "in0", moirai.Store.PARALLEL_FS, uri)
    with moirai.Activity("train") as act:        # optional: the source
        act.used(src)
        dst = act.generates("model", "m0")
    moirai.relate(moirai.Relation.DERIVED_FROM, dst, src)

    @moirai.activity(used=[("dataset", "in0")])
    def load(): ...

    moirai.finalize()
"""
from moirai.common import API as __all__  # noqa: F401

_api = None


def __getattr__(name):
    # The release binding is loaded on first use, so that importing
    # moirai.dbg never loads it too.
    global _api
    if name not in __all__:
        raise AttributeError(f"module 'moirai' has no attribute {name!r}")
    if _api is None:
        from moirai import _moirai
        from moirai.common import make_api

        _api = make_api(_moirai)
    return _api[name]


def __dir__():
    return sorted(list(globals()) + list(__all__))
