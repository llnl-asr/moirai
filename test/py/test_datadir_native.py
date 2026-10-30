#!/usr/bin/env python3
"""The translation of MOIRAI_DATA_DIR to DFTRACER_DATA_DIR
(ConfigurationManager), as the process sees it after moirai.initialize() and as
the commands of MOIRAI_AGENT_TRACE_IO get it. Run by run_case.sh, which sets
MOIRAI_TEST_DATA to a fresh directory."""
import ctypes
import os
import sys
import types

import moirai
from moirai.agent import trace_io

work = os.path.realpath(os.environ["MOIRAI_TEST_DATA"])
real = os.path.join(work, "WS2", "proj")
os.makedirs(real)
os.symlink(os.path.join(work, "WS2"), os.path.join(work, "ws"))
link = os.path.join(work, "ws", "proj")
missing = os.path.join(work, "ws", "missing")
os.environ["MOIRAI_DATA_DIR"] = f"{missing}:{link}:{real}:{link}"
os.environ["MOIRAI_AGENT_REDACT"] = "not-dftracer's"

libc = ctypes.CDLL(None)
libc.getenv.restype = ctypes.c_char_p


def getenv(name):
    value = libc.getenv(name.encode())
    return None if value is None else value.decode()


moirai.initialize()
got = getenv("DFTRACER_DATA_DIR")
moirai.finalize()
want = f"{missing}:{link}:{real}"
if got != want:
    sys.exit(f"DFTRACER_DATA_DIR is {got!r}, want {want!r}")

conf = moirai.agent_configuration()
settings = dict(conf.dftracer_settings)
if settings.get("DFTRACER_DATA_DIR") != want or "DFTRACER_AGENT_REDACT" in settings:
    sys.exit(f"dftracer_settings: {settings}")
env = trace_io.child_environment(conf)
if env["DFTRACER_DATA_DIR"] != want or env["DFTRACER_INIT"] != "PRELOAD":
    sys.exit(f"child environment: {env}")
none = types.SimpleNamespace(dftracer_settings=[], log_file=conf.log_file)
if trace_io.child_environment(none)["DFTRACER_DATA_DIR"] != "all":
    sys.exit("a command traces everything when nothing is asked")
