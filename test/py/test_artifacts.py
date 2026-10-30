#!/usr/bin/env python3
"""moirai's artifact store through its Python adapter: content is kept next to
the trace, under a key the provenance holds. Transient content is stored;
persistent content is a link, checked when read. A forked child has
its own turn at the node's store, and many producers share it. MOIRAI_TEST_DATA is the
directory of the test's files; MOIRAI_LOG_FILE the trace prefix."""
import ctypes
import os
import subprocess
import sys

import moirai

Lifetime = moirai.Lifetime
data = os.environ["MOIRAI_TEST_DATA"]
log_file = os.environ["MOIRAI_LOG_FILE"]


def expect(condition, what):
    if not condition:
        sys.exit(f"artifact test failed: {what}")


def fnv(data):
    h = 1469598103934665603
    for b in data:
        h = ((h ^ b) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h or 1


def uri_of(content):
    """The key of content of at most 64 KiB: all of it, after its size."""
    return (f"artifact://{fnv(len(content).to_bytes(8, 'little') + content):016x}")


expect(moirai.HAS_ARTIFACT_STORE, "built without the artifact store")
os.environ["MOIRAI_AGENT_REDACT"] = "hash"
moirai.initialize()

# moirai.agent's settings are moirai's own: dftracer does not see them.
getenv = ctypes.CDLL(None).getenv
getenv.restype = ctypes.c_char_p
expect(getenv(b"MOIRAI_AGENT_REDACT") == b"hash", "the setting is there")
expect(getenv(b"DFTRACER_AGENT_REDACT") is None, "passed through to dftracer")
expect(moirai.agent_configuration().redact == "hash", "the configuration")

# Transient: the content itself, also a large one, under its key.
for content in (b"", b"abc", os.urandom(1 << 16), b"prompt " * (1 << 20)):
    a = moirai.store_artifact(content)
    if len(content) <= 1 << 16:
        expect(a.uri == uri_of(content), f"address of {len(content)} bytes")
    expect(a.uri == moirai.artifact_uri(content), "the address, unstored")
    expect(a.size == len(content), "size")
    expect(a.lifetime == Lifetime.TRANSIENT, "lifetime")
    expect(moirai.read_artifact(a.uri) == content, "transient round trip")
text = moirai.store_artifact("naïve")
expect(moirai.read_artifact(text.uri).decode() == "naïve", "str is utf-8")

# Stored once: in the store it takes no more room the second time.
big = os.urandom(1 << 20)
first = moirai.store_artifact(big)
expect(moirai.store_artifact(big).uri == first.uri, "same content, same key")

# Sampling: past 64 KiB most bytes are not hashed, so two contents can share a
# key. Neither may be lost: the second gets the next key.
edited = bytearray(big)
edited[12345] ^= 0xff  # between samples
second = moirai.store_artifact(bytes(edited))
expect(moirai.artifact_uri(bytes(edited)) == first.uri, "a miss of the sample")
expect(second.uri != first.uri, "a colliding content keeps its own key")
expect(moirai.read_artifact(first.uri) == big, "the first content is intact")
expect(moirai.read_artifact(second.uri) == bytes(edited), "and so is the second")
expect(moirai.store_artifact(bytes(edited)).uri == second.uri,
       "the moved content is still found as a duplicate")

# A file, transient: copied in, so it survives the file.
scratch = os.path.join(data, "scratch.txt")
with open(scratch, "wb") as f:
    f.write(b"scratch output")
copied = moirai.store_artifact_file(scratch, Lifetime.TRANSIENT)
os.unlink(scratch)
expect(moirai.read_artifact(copied.uri) == b"scratch output",
       "a transient file outlives the file")

# A file, persistent: a link, which tells when the file is no longer it.
kept = os.path.join(data, "kept.txt")
with open(kept, "wb") as f:
    f.write(b"version 1")
linked = moirai.store_artifact_file(kept)
expect(linked.lifetime == Lifetime.PERSISTENT, "default is persistent")
expect(linked.uri == uri_of(b"version 1"), "link address")
expect(moirai.read_artifact(linked.uri) == b"version 1", "read through a link")
with open(kept, "wb") as f:
    f.write(b"version 2")
expect(moirai.read_artifact(linked.uri) is None, "a changed file is refused")

# A linked file too large to hash whole is also held to its mtime: an edit
# between the samples must not pass as the file.
large = os.path.join(data, "large.bin")
with open(large, "wb") as f:
    f.write(big)
link = moirai.store_artifact_file(large)
expect(moirai.read_artifact(link.uri) == big, "read through a large link")
with open(large, "r+b") as f:
    f.seek(12345)
    f.write(b"\x00" if big[12345] else b"\x01")
expect(moirai.read_artifact(link.uri) is None, "an edit between samples")

expect(not moirai.store_artifact_file(os.path.join(data, "none")),
       "a missing file is no artifact")
expect(moirai.read_artifact("artifact://" + "0" * 15 + "1") is None,
       "unknown key")
expect(moirai.read_artifact("file:///etc/passwd") is None, "not an address")

# The key goes in the provenance, the content does not.
marker = "SECRET-CONTENT-NOT-IN-TRACE"
out = moirai.store_artifact(marker)
moirai.entity_type("tool.output", moirai.Role.INTERMEDIATE, "what a tool wrote")
with moirai.Activity("tool") as act:
    act.generates("tool.output", "call-1", moirai.Store.DATABASE, out.uri)

# A forked child writes to a shard of its own, and the parent reads it.
child_content = b"from the child"
pid = os.fork()  # moirai is idle: its RocksDB threads hold no lock
if pid == 0:
    code = 0 if moirai.store_artifact(child_content) else 1
    moirai.finalize()
    os._exit(code)
_, status = os.waitpid(pid, 0)
expect(status == 0, "the forked child")
expect(moirai.read_artifact(uri_of(child_content)) == child_content,
       "the parent reads the child's shard")
own = moirai.store_artifact(b"parent after fork")
expect(moirai.read_artifact(own.uri) == b"parent after fork",
       "the parent's own shard still works after the fork")

moirai.finalize()

# After the run, by trace prefix alone.
expect(moirai.read_artifact(own.uri, log_file) == b"parent after fork",
       "read by trace prefix after finalize")
expect(moirai.read_artifact(uri_of(child_content), log_file) == child_content,
       "the child's shard after finalize")
shards = os.listdir(log_file + ".artifacts")
expect(shards == [os.uname().nodename], f"one store per node: {shards}")

# Many producers on a node, at once, each with its own content.
PRODUCER = """
import sys, moirai
moirai.initialize()
for i in range(20):
    moirai.store_artifact(f"producer {sys.argv[1]} item {i}" * 500)
moirai.finalize()
"""
producers = [subprocess.Popen([sys.executable, "-c", PRODUCER, str(n)])
             for n in range(12)]
expect(all(p.wait() == 0 for p in producers), "a producer failed")
for n in range(12):
    for i in range(20):
        content = (f"producer {n} item {i}" * 500).encode()
        expect(moirai.read_artifact(moirai.artifact_uri(content), log_file)
               == content, f"content of producer {n}")
shards = os.listdir(log_file + ".artifacts")
expect(shards == [os.uname().nodename], f"still one store: {shards}")
