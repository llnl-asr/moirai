#!/usr/bin/env python3
"""The provenance scenario through moirai's Python API; checked by
test/check_provenance.py. "cleanup" is a decorated function. With the
argument "direct", only entities and entity relations, without any activity.
MOIRAI_TEST_DEBUG=1 uses moirai.dbg. MOIRAI_TEST_DATA is the directory of the
file "load" writes and reads."""
import os
import sys

if os.environ.get("MOIRAI_TEST_DEBUG") == "1":
    import moirai.dbg as moirai
else:
    import moirai

Relation, Role, Store = moirai.Relation, moirai.Role, moirai.Store


def file_io():
    d = os.environ.get("MOIRAI_TEST_DATA")
    if not d:
        return
    path = os.path.join(d, "load.bin")
    with open(path, "wb") as f:
        f.write(b"x" * 64)
    with open(path, "rb") as f:
        f.read()


def relations(in0, in1, cfg, m0, m1):
    moirai.relate(Relation.DERIVED_FROM, m0, in0)
    moirai.relate(Relation.REVISION_OF, m1, m0)
    moirai.relate(Relation.CONTAINS, cfg, in0)
    in1.relate(Relation.PART_OF, in0)  # on the Entity itself
    moirai.relate(Relation.SPECIALIZATION_OF, m1, m0)
    moirai.relate(Relation.ALTERNATE_OF, in1, in0)
    moirai.relate(Relation.DEPENDS_ON, m0.id, cfg.id)  # by id
    moirai.relate(Relation.USED, m0, in0)  # not an entity relation
    moirai.relate(Relation.DEPENDS_ON, 0, in0)


@moirai.activity(used=[("dataset", "tmp")],
                 invalidated=[("dataset", "tmp")])
def cleanup():
    pass


moirai.initialize()

moirai.entity_type("dataset", Role.INPUT, "raw input")
moirai.entity_type("model", Role.OUTPUT, "trained model")
moirai.EntityType("config", Role.PARAMETER, "run settings")
moirai.entity_type("dataset", Role.OUTPUT, "declared again: ignored")

in0 = moirai.entity("dataset", "in0", Store.PARALLEL_FS, "file:///data/in0.h5")
in1 = moirai.entity("dataset", "in1", Store.LOCAL_DISK, "/tmp/in1")
cfg = moirai.Entity("config", "run")
assert moirai.entity("dataset", "in0", Store.PARALLEL_FS, "again") == in0

if len(sys.argv) > 1 and sys.argv[1] == "direct":
    m0 = moirai.entity("model", "m0", Store.PARALLEL_FS, "file:///data/m0.pt")
    m1 = moirai.entity("model", "m1", Store.OBJECT_STORE, "s3://bucket/m1")
    moirai.entity("dataset", "tmp")
    relations(in0, in1, cfg, m0, m1)
    moirai.finalize()
    sys.exit(0)

with moirai.Activity("load") as load:
    load.used(in0)
    load.used(in1)
    load.used(cfg.id)
    file_io()

with moirai.Activity("train") as train:
    train.used(in0)
    train.updated(cfg)
    m0 = train.generates("model", "m0", Store.PARALLEL_FS, "file:///data/m0.pt")

refine = moirai.Activity("refine").begin()
m1 = moirai.entity("model", "m1", Store.OBJECT_STORE, "s3://bucket/m1")
refine.used(m0)
refine.generated(m1)
refine.invalidated(m0)
refine.relate(Relation.DERIVED_FROM, m1)  # not an activity relation
refine.end()

cleanup()
relations(in0, in1, cfg, m0, m1)

moirai.finalize()
