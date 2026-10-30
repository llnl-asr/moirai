"""moirai's Python API on the debug build (``moirai._moirai_dbg``): moirai's
and dftracer's logging compiled in, its level from MOIRAI_LOG_LEVEL. The same
names as ``moirai``; a process uses one of the two."""
from moirai import _moirai_dbg
from moirai.common import API as __all__
from moirai.common import make_api

globals().update(make_api(_moirai_dbg))
