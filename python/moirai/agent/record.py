"""``python -m moirai.agent record``: run an agent harness, recorded.

::

    python -m moirai.agent record [--agent-dir D] [--log-file P] [--data-dir X]
        [--trace-io | --no-trace-io] [--command-io | --no-command-io]
        [--flush-ms N] [--service CMD] [--user] <harness> -- <command...>

In order: set the ``MOIRAI_*`` environment, install the hooks of ``<harness>``
(:mod:`moirai.agent.install`), start ``moirai-service``, run the command with
that environment, and -- whatever became of the command: failure, a signal, an
exception here -- stop the service. The exit status is the command's. The hooks
stay installed afterwards, as ``install`` leaves them; ``uninstall`` takes them
out.

The environment, each from its option, else from the environment it already has,
else the default:

=================== ======================= =================================
option              variable                default
=================== ======================= =================================
``--agent-dir``     ``MOIRAI_AGENT_DIR``    ``~/.moirai/agent``
``--log-file``      ``MOIRAI_LOG_FILE``     ``<agent dir>/trace``
``--trace-io``      ``MOIRAI_TRACE_IO``     on: the hooks' own I/O is traced
``--command-io``    ``MOIRAI_AGENT_TRACE_IO`` off: on traces the agent's commands
                                            too, and approves them (see the
                                            warning in docs/agents.rst)
``--flush-ms``      ``MOIRAI_PC_FLUSH_MS``  200
``--data-dir``      ``MOIRAI_DATA_DIR``     unset (all, for the hooks)
=================== ======================= =================================

The service is ``--service`` (a command line), else ``moirai-service`` beside
this interpreter, else the executable in the package (``moirai/bin``), else one
on ``PATH``. This module needs no native moirai: only installing the hooks does,
and that is replaceable (:func:`run`'s ``installer``).
"""
import argparse
import os
import shlex
import shutil
import signal
import subprocess
import sys

from moirai.agent.constants import (DEFAULT_AGENT_DIR, DEFAULT_FLUSH_MS,
                                    ENV_AGENT_DIR, ENV_AGENT_TRACE_IO,
                                    ENV_DATA_DIR, ENV_LOG_FILE,
                                    ENV_PC_FLUSH_MS, ENV_PREFIX, ENV_TRACE_IO)

FORWARDED = tuple(s for s in (getattr(signal, n, None)
                              for n in ("SIGTERM", "SIGHUP", "SIGQUIT"))
                  if s is not None)


class RecordError(Exception):
    """Something that stops a run before the command starts."""


def parser():
    p = argparse.ArgumentParser(
        prog="python -m moirai.agent record",
        usage="python -m moirai.agent record [options] <harness> -- "
              "<command...>",
        description="Run an agent harness with moirai recording it.")
    p.add_argument("--agent-dir", help="run directory (MOIRAI_AGENT_DIR)")
    p.add_argument("--log-file", help="trace prefix (MOIRAI_LOG_FILE; "
                                      "default <agent dir>/trace)")
    p.add_argument("--data-dir", help="':'-separated directories whose I/O is "
                                      "traced (MOIRAI_DATA_DIR)")
    p.add_argument("--trace-io", action=argparse.BooleanOptionalAction,
                   default=None, help="trace the hooks' I/O (default on)")
    p.add_argument("--command-io", action=argparse.BooleanOptionalAction,
                   default=None, help="trace the I/O of the commands the "
                                      "agent runs, which approves them "
                                      "(default off)")
    p.add_argument("--flush-ms", type=int, help=f"{ENV_PC_FLUSH_MS} "
                                                f"(default {DEFAULT_FLUSH_MS})")
    p.add_argument("--service", help="the moirai-service command line")
    p.add_argument("--user", action="store_true",
                   help="install the hooks for the user, not the project")
    p.add_argument("harness", help="claude, codex or opencode")
    return p


def environment(args, base=None):
    """The environment of the run: ``base`` (default: this process's) with the
    ``MOIRAI_*`` settings the options and defaults give."""
    env = dict(os.environ if base is None else base)
    directory = args.agent_dir or env.get(ENV_AGENT_DIR) or DEFAULT_AGENT_DIR
    directory = os.path.normpath(os.path.abspath(os.path.expanduser(directory)))
    env[ENV_AGENT_DIR] = directory
    log = args.log_file or env.get(ENV_LOG_FILE) or os.path.join(
        directory, "trace")
    env[ENV_LOG_FILE] = os.path.abspath(os.path.expanduser(log))
    for name, option, default in ((ENV_TRACE_IO, args.trace_io, "1"),
                                  (ENV_AGENT_TRACE_IO, args.command_io, "0")):
        if option is not None:
            env[name] = "1" if option else "0"
        else:
            env.setdefault(name, default)
    if args.flush_ms is not None:
        env[ENV_PC_FLUSH_MS] = str(args.flush_ms)
    else:
        env.setdefault(ENV_PC_FLUSH_MS, str(DEFAULT_FLUSH_MS))
    if args.data_dir:
        env[ENV_DATA_DIR] = args.data_dir
    return env


def find_service(explicit=None):
    """The service's command line (a list), or ``RecordError``."""
    if explicit:
        words = shlex.split(explicit)
        if not words or not (os.access(words[0], os.X_OK)
                             or shutil.which(words[0])):
            raise RecordError(f"--service {explicit!r} is not executable")
        return words
    package = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for candidate in (
            os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                         "moirai-service"),
            os.path.join(package, "bin", "moirai-service"),
            shutil.which("moirai-service")):
        if candidate and os.access(candidate, os.X_OK):
            return [candidate]
    raise RecordError("no moirai-service: install moirai from its wheel, put "
                      "moirai-service beside this interpreter or on PATH, or "
                      "give --service")


def install_hooks(harness, user=False):
    from moirai.agent import install

    return install.install(harness, "user" if user else "project")


def run(args, command, installer=None, popen=subprocess.Popen,
        stderr=sys.stderr):
    """Record ``command`` as ``args`` (from :func:`parser`) say; its exit
    status. ``installer(harness, user)`` installs the hooks (default:
    :func:`install_hooks`), and it runs with the environment set in this
    process, which is what the hooks bake in."""
    env = environment(args)
    service = find_service(args.service)
    os.makedirs(env[ENV_AGENT_DIR], mode=0o700, exist_ok=True)
    os.makedirs(os.path.dirname(env[ENV_LOG_FILE]) or ".", exist_ok=True)
    saved = {k: os.environ.get(k) for k in env if k.startswith(ENV_PREFIX)}
    os.environ.update({k: v for k, v in env.items()
                       if k.startswith(ENV_PREFIX)})
    try:
        try:
            where = (installer or install_hooks)(args.harness, args.user)
        except SystemExit as e:
            raise RecordError(f"cannot install the {args.harness} hooks: "
                              f"{e.code}")
        except Exception as e:  # noqa: BLE001
            raise RecordError(f"cannot install the {args.harness} hooks: {e}")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    print(f"moirai: recording {args.harness} to {env[ENV_LOG_FILE]} "
          f"(hooks in {where}, agent dir {env[ENV_AGENT_DIR]})",
          file=stderr)
    started = subprocess.run(service + ["start"], env=env)
    if started.returncode != 0:
        # It may have got as far as leaving something running.
        subprocess.run(service + ["stop"], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raise RecordError(f"{shlex.join(service)} start failed "
                          f"({started.returncode})")
    child = None
    previous = {}

    def forward(number, _frame):
        if child is not None and child.poll() is None:
            try:
                child.send_signal(number)
            except OSError:
                pass

    try:
        for number in FORWARDED:
            previous[number] = signal.signal(number, forward)
        # A terminal sends ^C to the whole foreground group: the command has
        # it; this process outlives it to stop the service.
        previous[signal.SIGINT] = signal.signal(signal.SIGINT,
                                                lambda *_: None)
        try:
            child = popen(command, env=env)
        except OSError as e:
            raise RecordError(f"cannot run {command[0]!r}: {e}")
        status = child.wait()
        return 128 - status if status < 0 else status
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
        if child is not None and child.poll() is None:
            child.kill()
            child.wait()
        stopped = subprocess.run(service + ["stop"], env=env)
        if stopped.returncode != 0:
            print(f"moirai: {shlex.join(service)} stop failed "
                  f"({stopped.returncode})", file=stderr)


def main(argv):
    cut = argv.index("--") if "--" in argv else len(argv)
    args = parser().parse_args(argv[:cut])
    command = argv[cut + 1:]
    if not command:
        print("moirai: give the command after --", file=sys.stderr)
        return 2
    try:
        return run(args, command)
    except RecordError as e:
        print(f"moirai: {e}", file=sys.stderr)
        return 2
