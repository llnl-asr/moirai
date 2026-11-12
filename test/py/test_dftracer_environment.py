"""importing moirai converts MOIRAI_* to DFTRACER_* before anything imports dftracer."""
import os
import subprocess
import sys
from pathlib import Path

PY = Path(__file__).resolve().parents[2] / "python"


def run(env_extra):
    code = "import os, moirai; print(*[os.environ.get(k, '-') for k in ('DFTRACER_ENABLE','DFTRACER_INIT','DFTRACER_ENABLE_PC_MODE','DFTRACER_LOG_FILE','DFTRACER_DISABLE_IO','DFTRACER_DATA_DIR')])"
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(PY), **env_extra}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    return out.stdout.split(), out.stderr


def test_defaults_enable_dftracer_in_function_mode():
    got, err = run({})
    assert got[:3] == ["1", "FUNCTION", "1"], (got, err)


def test_moirai_settings_become_dftracer_settings():
    got, err = run({"MOIRAI_LOG_FILE": "/tmp/x/prov", "MOIRAI_TRACE_IO": "0", "MOIRAI_DATA_DIR": "/data"})
    assert got[3] == "/tmp/x/prov" and got[4] == "1" and got[5] == "/data", (got, err)


def test_disabled_moirai_disables_dftracer():
    got, err = run({"MOIRAI_ENABLE": "off"})
    assert got[0] == "0", (got, err)
