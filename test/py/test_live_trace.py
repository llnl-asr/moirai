#!/usr/bin/env python3
"""A node trace can be read while moirai-service runs: the service seals what it
receives into whole gzip members, so what a process wrote is readable soon after
it left, with no stop and no other file. Run by run_case.sh in service mode."""
import glob
import json
import os
import socket
import subprocess
import sys
import time
import zlib

prefix = os.environ["MOIRAI_LOG_FILE"]
trace = f"{prefix}_{socket.gethostname()}.pfw.gz"
PRODUCER = """
import sys, moirai
moirai.initialize()
with moirai.Activity(sys.argv[1]):
    pass
moirai.finalize()
"""


def activities():
    """The activities in the whole members written so far."""
    with open(trace, "rb") as fh:
        data = fh.read()
    names, used = [], 0
    while used < len(data):
        d = zlib.decompressobj(zlib.MAX_WBITS | 16)
        try:
            text = d.decompress(data[used:])
        except zlib.error:
            break
        if not d.eof:
            break
        used = len(data) - len(d.unused_data)
        for line in text.splitlines():
            line = line.strip().rstrip(b",")
            if line.startswith(b"{"):
                record = json.loads(line)
                if record.get("cat") == "moirai":
                    names.append(record["name"])
    return names


for n in range(3):
    name = f"live{n}"
    subprocess.run([sys.executable, "-c", PRODUCER, name], check=True,
                   capture_output=True)
    deadline = time.monotonic() + 30
    while name not in activities():
        if time.monotonic() > deadline:
            sys.exit(f"{name} was not readable while the service ran")
        time.sleep(0.1)
if glob.glob(prefix + "*spill*"):
    sys.exit("events went to a spill file")
if len(glob.glob(prefix + "*.pfw.gz")) != 1:
    sys.exit("more than the node trace")
print("PASS")
