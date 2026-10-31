"""Read the payloads in moirai's artifact store, in process.

A trace holds names and keys; the prompts, replies, tool inputs and outputs and
the files a tool touched are artifacts, in a RocksDB next to the trace.
:func:`read_text` is the library interface a consumer uses::

    from moirai.agent.artifacts import read_text

    text = read_text(entity_uri, trace_prefix)   # str, or None
    text = read_text(entity_uri, trace_prefix, limit=480)

It strips the ``@name`` after the key (the file the artifact came from), calls
``moirai.read_artifact``, decodes UTF-8 with replacement, and returns ``None``
for a key that is not (yet) in the store or when moirai cannot read at all.
A key is a digest of the content, so what it names never changes: hits are kept
in a small LRU (:data:`CACHE_ENTRIES`), thread-safe. A miss is not kept, because
an artifact lands with its producer's batch, which can be after the trace names
it. Importing this module does not import the native module; :func:`read_text`
does, once.
"""
import threading
from collections import OrderedDict

CACHE_ENTRIES = 4096

_lock = threading.Lock()
_cache = OrderedDict()
_error = ""


def artifact_key(uri):
    """The ``artifact://`` URI at the start of ``uri``, or ``""``."""
    head = str(uri).split("@", 1)[0]
    return head if head.startswith("artifact://") else ""


def error():
    """Why the last read could not be done at all (moirai missing or built
    without the artifact store), or ``""``."""
    return _error


def forget():
    """Drop every cached payload."""
    with _lock:
        _cache.clear()


def read_text(uri, prefix, limit=0, reader=None):
    """The artifact ``uri`` names, in the store at trace prefix ``prefix``, as
    text (cut to ``limit`` characters if positive); ``None`` if absent.
    ``reader(key, prefix) -> bytes|None`` replaces ``moirai.read_artifact``."""
    global _error
    key = artifact_key(uri)
    if not key:
        return None
    cache_key = (str(prefix), key)
    with _lock:
        if cache_key in _cache:
            _cache.move_to_end(cache_key)
            return _clip(_cache[cache_key], limit)
    try:
        if reader is None:
            import moirai

            if not moirai.HAS_ARTIFACT_STORE:
                raise RuntimeError("moirai was built without the artifact "
                                   "store")
            reader = moirai.read_artifact
        data = reader(key, str(prefix))
        _error = ""
    except Exception as e:  # noqa: BLE001
        _error = f"cannot read artifacts: {e}"
        return None
    if data is None:
        return None
    text = bytes(data).decode("utf-8", "replace")
    with _lock:
        _cache[cache_key] = text
        while len(_cache) > CACHE_ENTRIES:
            _cache.popitem(last=False)
    return _clip(text, limit)


def _clip(text, limit):
    if not limit or limit <= 0 or len(text) <= limit:
        return text
    return text[:limit]
