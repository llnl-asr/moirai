"""importing moirai converts MOIRAI_* to DFTRACER_* before anything imports dftracer."""
import os
import subprocess
import sys
from pathlib import Path

PY = Path(__file__).resolve().parents[2] / "python"


def run(env_extra):
    code = "import os, moirai; print(*[os.environ.get(k, '-') for k in ('DFTRACER_ENABLE','DFTRACER_INIT','DFTRACER_ENABLE_PC_MODE','DFTRACER_LOG_FILE','DFTRACER_DISABLE_IO','DFTRACER_DATA_DIR','DFTRACER_ATTACH')])"
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(PY), **env_extra}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    return out.stdout.split(), out.stderr


def test_defaults_enable_dftracer_in_function_mode():
    got, err = run({})
    assert got[:3] == ["1", "FUNCTION", "1"], (got, err)
    assert got[6] == "1", (got, err)                 # DFTRACER_ATTACH: pydftracer attaches to moirai's core


def test_moirai_settings_become_dftracer_settings():
    got, err = run({"MOIRAI_LOG_FILE": "/tmp/x/prov", "MOIRAI_TRACE_IO": "0", "MOIRAI_DATA_DIR": "/data"})
    assert got[3] == "/tmp/x/prov" and got[4] == "1" and got[5] == "/data", (got, err)


def test_disabled_moirai_disables_dftracer():
    got, err = run({"MOIRAI_ENABLE": "off"})
    assert got[0] == "0", (got, err)


def _fake_pydftracer(tmp_path):
    """A pydftracer that records the environment it was imported under."""
    pkg = tmp_path / "dftracer" / "python"
    pkg.mkdir(parents=True)
    (tmp_path / "dftracer" / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text(
        "import os\nENABLE = os.environ.get('DFTRACER_ENABLE')\nATTACH = os.environ.get('DFTRACER_ATTACH')\nINIT = os.environ.get('DFTRACER_INIT')\n"
        "dft_fn = object()\ndftracer = object()\nai = object()\n"
    )


def test_moirai_imports_pydftracer_after_setting_the_environment(tmp_path):
    _fake_pydftracer(tmp_path)
    code = (
        "import moirai, dftracer.python as P\n"
        "print(P.ENABLE, P.ATTACH, P.INIT, moirai.dft_fn is P.dft_fn, moirai.dftracer is P.dftracer, moirai.ai is P.ai)\n"
    )
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": f"{PY}:{tmp_path}"}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert out.stdout.split() == ["1", "1", "FUNCTION", "True", "True", "True"], (out.stdout, out.stderr)


def test_moirai_works_without_pydftracer():
    code = "import sys\nsys.modules['dftracer'] = None            # pydftracer is not installed\nimport moirai\ntry:\n    moirai.dft_fn\nexcept AttributeError:\n    print('absent')\n"
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(PY)}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert out.stdout.split() == ["absent"], (out.stdout, out.stderr)
