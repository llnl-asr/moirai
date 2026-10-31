#!/usr/bin/env python3
"""What one smoke session must have left. usage: check_agent.py <trace prefix>
<expected file content>"""
import collections
import glob
import gzip
import json
import sys

import moirai

prefix, expected = sys.argv[1], sys.argv[2].encode()
records = []
for path in glob.glob(prefix + "*.pfw.gz"):
    with gzip.open(path, "rt", errors="replace") as fh:
        for line in fh:
            line = line.strip().rstrip(",")
            if line.startswith("{"):
                records.append(json.loads(line))
activities = collections.Counter(r["name"] for r in records
                                 if r.get("cat") == "moirai")
entities = {r["args"]["id"]: r["args"] for r in records if r["name"] == "EH"}
kinds = collections.Counter(e["type"] for e in entities.values())
print("activities", dict(activities))
print("entities", dict(kinds))
failures = []
for name in ("tool.Bash",):
    if not any(a.lower() == name.lower() for a in activities):
        failures.append(f"no {name} activity")
for kind in ("agent.prompt", "tool.input", "tool.output", "tool.script", "file"):
    if not kinds[kind]:
        failures.append(f"no {kind} entity")
content = [moirai.read_artifact(e["uri"], prefix) for e in entities.values()
           if e["type"] == "file"]
if expected not in content:
    failures.append(f"the file's content is not in the store: {content}")
if not activities["llm.call"]:
    print("note: no llm.call (the harness left no transcript)")
print("FAIL: " + "; ".join(failures) if failures else "PASS")
sys.exit(1 if failures else 0)
