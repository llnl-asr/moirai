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
import os as _os

from moirai.common import API as __all__  # noqa: F401

# MOIRAI_* settings that moirai itself reads; every other MOIRAI_<NAME> is handed to dftracer as DFTRACER_<NAME>.
_OWN_SETTINGS = ("ENABLE", "INIT", "TRACE_IO", "LOG_FILE", "DFTRACER_SERVICE", "ENABLE_PC_MODE")
_OFF = ("0", "false", "off", "no")


def _configure_dftracer_environment():
    """Convert MOIRAI_* to DFTRACER_* in os.environ, once, at import.

    pydftracer reads DFTRACER_ENABLE and DFTRACER_INIT when it is imported, which is before moirai.initialize() runs
    (an application imports its modules first, and moirai starts at its first activity): without them it silently does
    nothing. This is the application-side mapping of the C++ ConfigurationManager (the same names and values), done here
    so that everything that imports dftracer after moirai sees it; moirai.initialize() applies it again.
    """
    environ = _os.environ

    def flag(name, otherwise):
        value = environ.get(name)
        return otherwise if not value else value.lower() not in _OFF

    environ["DFTRACER_ENABLE"] = "1" if flag("MOIRAI_ENABLE", True) else "0"
    environ["DFTRACER_ENABLE_PC_MODE"] = "1"      # provenance always goes through the service or its spill file
    environ["DFTRACER_INIT"] = "FUNCTION"         # moirai starts dftracer itself
    environ["DFTRACER_ATTACH"] = "1"              # moirai owns the core: pydftracer's initialize_log attaches, never initializes it again
    if environ.get("MOIRAI_LOG_FILE"):
        environ["DFTRACER_LOG_FILE"] = environ["MOIRAI_LOG_FILE"]
    if environ.get("MOIRAI_TRACE_IO"):
        environ["DFTRACER_DISABLE_IO"] = "0" if flag("MOIRAI_TRACE_IO", True) else "1"
    for key, value in list(environ.items()):
        if key.startswith("MOIRAI_") and key[len("MOIRAI_"):] and not (
            key[len("MOIRAI_"):] in _OWN_SETTINGS or key.startswith("MOIRAI_AGENT")
        ):
            environ["DFTRACER_" + key[len("MOIRAI_"):]] = value


_configure_dftracer_environment()

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
