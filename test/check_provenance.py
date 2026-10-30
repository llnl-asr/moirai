#!/usr/bin/env python3
"""Check the provenance a test application (test/c/test_api.c,
test/cpp/test_api.cpp, test/py/test_api.py) traced through moirai.

usage: check_provenance.py <work dir> <service|spill|none> <io 1|0>
                           [activities|direct]

  service  events reached moirai-service: a node trace <work>/trace_<host>
           and no spill file
  spill    no service ran: everything is in <work>/trace-*-spill
  none     tracing was off: no trace at all

Every case checks the exact records (EH, ET, ER), once each. In the
"activities" scenario (default), also the exact activities: complete events
on moirai's layer, never aggregated, relating the declared entities. In the
"direct" scenario the same entities and relations are declared without any
activity, and there must be none. With io 1 the activity "load" wrote and read
<work>/data/load.bin, and those calls are traced; with io 0 no I/O is.
"""
import glob
import gzip
import json
import os
import sys

LAYER = 128  # MOIRAI_LAYER
CATEGORY = "moirai"

STORE = {"MEMORY": 0, "LOCAL_DISK": 2, "PARALLEL_FS": 3, "OBJECT_STORE": 5}
ROLE = {"INPUT": 1, "OUTPUT": 2, "PARAMETER": 4}
REL = {"derived_from": 16, "revision_of": 17, "contains": 18, "part_of": 19,
       "specialization_of": 20, "alternate_of": 21, "depends_on": 22}


def entity_id(type_, key):
    """moirai_hash: FNV-1a of type, 0x1f, key; 16 hex digits."""
    h = 1469598103934665603
    for b in type_.encode() + b"\x1f" + key.encode():
        h = ((h ^ b) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return f"{h or 1:016x}"


IN0, IN1, CFG = (entity_id("dataset", "in0"), entity_id("dataset", "in1"),
                 entity_id("config", "run"))
M0, M1, TMP = (entity_id("model", "m0"), entity_id("model", "m1"),
               entity_id("dataset", "tmp"))

ENTITY_TYPES = {
    "dataset": {"role": ROLE["INPUT"], "description": "raw input"},
    "model": {"role": ROLE["OUTPUT"], "description": "trained model"},
    "config": {"role": ROLE["PARAMETER"], "description": "run settings"},
}
ENTITIES = {
    IN0: {"type": "dataset", "store": STORE["PARALLEL_FS"],
          "uri": "file:///data/in0.h5"},
    IN1: {"type": "dataset", "store": STORE["LOCAL_DISK"], "uri": "/tmp/in1"},
    CFG: {"type": "config", "store": STORE["MEMORY"], "uri": ""},
    M0: {"type": "model", "store": STORE["PARALLEL_FS"],
         "uri": "file:///data/m0.pt"},
    M1: {"type": "model", "store": STORE["OBJECT_STORE"],
         "uri": "s3://bucket/m1"},
    TMP: {"type": "dataset", "store": STORE["MEMORY"], "uri": ""},
}
RELATIONS = sorted([
    (REL["derived_from"], M0, IN0), (REL["revision_of"], M1, M0),
    (REL["contains"], CFG, IN0), (REL["part_of"], IN1, IN0),
    (REL["specialization_of"], M1, M0), (REL["alternate_of"], IN1, IN0),
    (REL["depends_on"], M0, CFG),
])
ACTIVITIES = {
    "load": {"used": [IN0, IN1, CFG]},
    "train": {"used": [IN0], "updated": [CFG], "generated": [M0]},
    "refine": {"used": [M0], "generated": [M1], "invalidated": [M0]},
    "cleanup": {"used": [TMP], "invalidated": [TMP]},
}


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


def read(files):
    events = []
    for f in files:
        with gzip.open(f, "rt") as fh:
            for line in fh:
                line = line.strip().rstrip(",")
                if line.startswith("{"):
                    events.append(json.loads(line))
    return events


def main():
    work, mode, io = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
    scenario = sys.argv[4] if len(sys.argv) > 4 else "activities"
    expected_activities = ACTIVITIES if scenario == "activities" else {}
    node = glob.glob(os.path.join(work, "trace_*.pfw.gz"))
    spill = glob.glob(os.path.join(work, "trace-*-spill.pfw.gz"))
    own = [f for f in glob.glob(os.path.join(work, "trace-*.pfw.gz"))
           if f not in spill]
    if own:
        fail(f"the application wrote a trace of its own (not producer/"
             f"consumer mode): {own}")
    if mode == "none":
        if node or spill:
            fail(f"tracing was off, but there are traces: {node + spill}")
        print("OK: no trace")
        return
    if mode == "service" and (not node or spill):
        fail(f"expected a node trace and no spill file: node={node} "
             f"spill={spill}")
    if mode == "spill" and not spill:
        fail(f"expected a spill file, found node={node}")

    events = read(node + spill)
    pids = {e.get("pid") for e in events
            if e.get("name") in ("EH", "ET", "ER") or
            e.get("cat") == CATEGORY}
    if len(pids) != 1:
        fail(f"expected provenance from one process, got pids {pids}")

    # I/O events name files by hash; FH records map the hashes to paths.
    load_hashes = {(e.get("args") or {}).get("value") for e in events
                   if e.get("name") == "FH" and
                   "load.bin" in str((e.get("args") or {}).get("name"))}

    def on_load_bin(args):
        return any(v in load_hashes or "load.bin" in str(v)
                   for v in args.values())

    types, entities, relations, activities, io_events = {}, {}, [], {}, []
    for e in events:
        name, args = e.get("name"), dict(e.get("args") or {})
        args.pop("hhash", None)
        if e.get("type") == LAYER and name in ("EH", "ET", "ER"):
            if e.get("ph") != 4:
                fail(f"{name} is not a metadata record: {e}")
        if name == "ET":
            t = args.pop("type")
            if t in types:
                fail(f"entity type {t} written twice")
            types[t] = args
        elif name == "EH":
            i = args.pop("id")
            if i in entities:
                fail(f"entity {i} written twice")
            entities[i] = args
        elif name == "ER":
            relations.append((args["relation"], args["subject"],
                              args["object"]))
        elif e.get("cat") == CATEGORY:
            if e.get("ph") != 1 or e.get("type") != LAYER:
                fail(f"activity {name} is not a complete event on layer "
                     f"{LAYER}: {e}")
            if name in activities:
                fail(f"activity {name} traced twice")
            activities[name] = args.get("relations")
        elif e.get("cat") in ("POSIX", "STDIO") and on_load_bin(args):
            io_events.append(e)

    if types != ENTITY_TYPES:
        fail(f"entity types {types} != {ENTITY_TYPES}")
    if entities != ENTITIES:
        fail(f"entities {entities} != {ENTITIES}")
    if sorted(relations) != RELATIONS:
        fail(f"entity relations {sorted(relations)} != {RELATIONS}")
    if activities != expected_activities:
        fail(f"activities {activities} != {expected_activities}")
    if io and not io_events:
        fail("I/O tracing is on, but the I/O on load.bin was not traced")
    if not io and io_events:
        fail(f"I/O tracing is off, but {len(io_events)} I/O events traced")
    print(f"OK: {mode} {scenario}: {len(types)} entity types, {len(entities)} "
          f"entities, {len(relations)} relations, {len(activities)} "
          f"activities, {len(io_events)} I/O events on load.bin")


if __name__ == "__main__":
    main()
