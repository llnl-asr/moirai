#!/usr/bin/env python3
"""Fail on the valgrind contexts that are moirai's or dftracer's.

usage: check_valgrind_log.py <valgrind log> [project frame regex]

A Python process under valgrind reports thousands of contexts that belong
to the interpreter: objects it interns or unmarshals at start and never
frees (CPython 3.12+), allocations its import machinery keeps. They are not
moirai's to fix. As dftracer's Python valgrind runner does
(--fail-on-project-leaks-only), only an error or leak context with a frame
matching the project regex (default: moirai and dftracer) fails; the rest is
counted and reported.
"""
import re
import sys

DEFAULT_PROJECT = r"moirai|_moirai|dftracer|libdftracer"
# A context starts at a line like "==123== Invalid read of size 8" or
# "==123== 43 bytes in 1 blocks are definitely lost in loss record ..." and
# ends at the next bare "==123==" line.
PREFIX = re.compile(r"^==\d+== ?")
HEADERS = re.compile(
    r"(Invalid |Conditional jump|Use of uninitialised|Syscall param|"
    r"Mismatched free|Source and destination overlap|"
    r"are definitely lost|are possibly lost|Argument .* of function)"
)


def contexts(lines):
    current = None
    for raw in lines:
        line = PREFIX.sub("", raw.rstrip("\n"))
        if current is None:
            if HEADERS.search(line):
                current = [line]
        elif line.strip() == "":
            yield current
            current = None
        else:
            current.append(line)
    if current:
        yield current


def main():
    log = sys.argv[1]
    project = re.compile(sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PROJECT)
    with open(log, errors="replace") as f:
        found = list(contexts(f))
    ours = [c for c in found if any(project.search(l) for l in c[1:])]
    print(f"valgrind: {len(found)} error/leak contexts, {len(ours)} with a "
          f"moirai or dftracer frame ({log})")
    for c in ours[:10]:
        print("\n".join(c[:30]))
        print("--")
    sys.exit(1 if ours else 0)


if __name__ == "__main__":
    main()
