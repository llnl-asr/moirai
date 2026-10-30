#!/usr/bin/env python3
"""Validate an installed moirai wheel, as dftracer's test_wheel.py does.

Runs as cibuildwheel's CIBW_TEST_COMMAND -- the repaired wheel and the
dftracer wheel installed in a fresh virtualenv -- or by hand:

    python scripts/wheel/test_wheel.py <moirai checkout>

Checks, in order:
1. moirai (and moirai.dbg) import from site-packages, not the checkout
2. every library in moirai/lib64 dlopen()s, and finds dftracer's in the
   dftracer wheel
3. both moirai-service executables start (usage), with LD_LIBRARY_PATH
   scrubbed
4. end to end, release and _dbg: moirai-service start, the provenance
   scenario (test/py/test_api.py), moirai-service stop, then
   test/check_provenance.py on the node trace
"""
import ctypes
import glob
import os
import subprocess
import sys
import tempfile
import time


def step(name):
    print(f"=== {name} ===", flush=True)


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items()
           if k not in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONPATH")
           and not k.startswith(("MOIRAI_", "DFTRACER_"))}
    env.update(extra)
    return env


def libraries():
    """moirai's and dftracer's native files in site-packages."""
    import sysconfig
    site = sysconfig.get_paths()["purelib"]
    found = []
    for pattern in ("moirai/*.so", "moirai/lib64/*.so*", "moirai/bin/*",
                    "dftracer/lib64/libdftracer_core.so*"):
        found += sorted(glob.glob(os.path.join(site, pattern)))
    return found


def explain_loading():
    """RPATH and ldd of every native file, to see why one does not load."""
    for f in libraries():
        if os.path.islink(f):
            continue
        rpath = subprocess.run(["readelf", "-d", f], capture_output=True,
                               text=True).stdout
        rpath = [l.strip() for l in rpath.splitlines() if "PATH" in l]
        ldd = subprocess.run(["ldd", f], capture_output=True, text=True,
                             env=clean_env()).stdout
        print(f"--- {f}\n  {rpath}\n" + ldd)


def run(cmd, **kwargs):
    """subprocess.run that, on failure, prints the command's output."""
    r = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if r.returncode != 0:
        print(f"FAILED ({r.returncode}): {' '.join(map(str, cmd))}")
        print("--- stdout ---\n" + r.stdout + "--- stderr ---\n" + r.stderr)
        if "cannot open shared object" in r.stderr:
            explain_loading()
        raise SystemExit(1)
    return r


def main():
    project = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    os.chdir("/")

    step("import")
    # Each API in a process of its own, as an application uses one.
    for module in ("moirai", "moirai.dbg"):
        r = run([sys.executable, "-c",
                 f"import {module} as m, os; print(os.path.dirname(m.__file__), "
                 "m.LAYER, m.CATEGORY, m.Store.PARALLEL_FS)"],
                env=clean_env())
        print(module, r.stdout.strip())
        assert not r.stdout.startswith(project), f"{module} from the checkout"
    import moirai
    pkg = os.path.dirname(moirai.__file__)

    step("libraries")
    for lib in sorted(glob.glob(os.path.join(pkg, "lib64", "*.so*"))):
        ctypes.CDLL(lib)
        print("dlopen ok:", os.path.basename(lib))

    step("executables")
    for name in ("moirai-service", "moirai-service_dbg"):
        exe = os.path.join(pkg, "bin", name)
        r = subprocess.run([exe], env=clean_env(), capture_output=True,
                           text=True)
        assert r.returncode == 2 and "Usage" in r.stderr, (name, r)
        print(name, "starts")

    for debug in ("0", "1"):
        step(f"end to end (debug={debug})")
        work = tempfile.mkdtemp(prefix="moirai-wheel-")
        data = os.path.join(work, "data")
        os.makedirs(data)
        shm = f"/moirai-wheel-test-{os.getpid()}-{debug}"
        env = clean_env(MOIRAI_LOG_FILE=os.path.join(work, "trace"),
                        MOIRAI_SERVICE_SHM=shm, MOIRAI_DATA_DIR=data,
                        MOIRAI_TEST_DATA=data, MOIRAI_TEST_DEBUG=debug,
                        MOIRAI_SERVICE_DEBUG=debug)
        service = [sys.executable, "-m", "moirai.service"]
        run(service + ["start"], env=env)
        for _ in range(100):
            if os.path.exists("/dev/shm" + shm):
                break
            time.sleep(0.1)
        run([sys.executable,
             os.path.join(project, "test", "py", "test_api.py")], env=env)
        run(service + ["stop"], env=env)
        for _ in range(300):
            if not os.path.exists("/dev/shm" + shm):
                break
            time.sleep(0.1)
        print(run([sys.executable,
                   os.path.join(project, "test", "check_provenance.py"),
                   work, "service", "1"]).stdout.strip())
    print("PASS")


if __name__ == "__main__":
    main()
