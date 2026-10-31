#!/usr/bin/env python3
"""``python -m moirai.agent record`` (moirai.agent.record) with a fake service and
a fake harness command: ordering (install, start, run, stop), the environment,
the exit status, and the service stopped whatever happens. No native module and
no real service are needed."""
import io
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest

from moirai.agent import record

PY = sys.executable


class Case(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self.temp.name)
        self.log = os.path.join(self.dir, "events.log")
        self.service = self.script("service", f"""#!{PY}
import json, os, sys, time
mode = sys.argv[1] if len(sys.argv) > 1 else ""
with open({self.log!r}, "a") as fh:
    fh.write(json.dumps({{"what": "service " + mode, "t": time.time(),
        "env": {{k: v for k, v in os.environ.items() if k.startswith("MOIRAI_")}}}}) + "\\n")
sys.exit(int(os.environ.get("FAKE_SERVICE_FAIL", "0")) if mode == "start" else 0)
""")
        self.harness = self.script("harness", f"""#!{PY}
import json, os, sys, time
with open({self.log!r}, "a") as fh:
    fh.write(json.dumps({{"what": "run", "t": time.time(), "argv": sys.argv[1:],
        "env": {{k: v for k, v in os.environ.items() if k.startswith("MOIRAI_")}}}}) + "\\n")
sys.exit(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
""")
        self.agent_dir = os.path.join(self.dir, "agent")
        self.installed = []

    def tearDown(self):
        self.temp.cleanup()

    def script(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w") as fh:
            fh.write(text)
        os.chmod(path, 0o700)
        return path

    def installer(self, harness, user):
        with open(self.log, "a") as fh:
            fh.write(json.dumps({"what": "install " + harness,
                                 "env": os.environ.get("MOIRAI_AGENT_DIR")}) + "\n")
        return os.path.join(self.dir, "hooks.json")

    def events(self):
        try:
            with open(self.log) as fh:
                return [json.loads(line) for line in fh]
        except OSError:
            return []

    def run_record(self, *options, command=None, installer=True, env=None):
        args = record.parser().parse_args(
            ["--agent-dir", self.agent_dir, "--service", self.service,
             *options, "claude"])
        err = io.StringIO()
        old = dict(os.environ)
        os.environ.update(env or {})
        try:
            status = record.run(args, command or [self.harness],
                                installer=self.installer if installer else None,
                                stderr=err)
        finally:
            os.environ.clear()
            os.environ.update(old)
        return status, err.getvalue()


class OrderTests(Case):
    def test_install_start_run_stop_in_order(self):
        status, err = self.run_record()
        self.assertEqual(status, 0)
        events = self.events()
        self.assertEqual([e["what"] for e in events],
                         ["install claude", "service start", "run",
                          "service stop"])
        self.assertEqual(events[0]["env"], self.agent_dir,
                         "the hooks are installed under the run's environment")
        self.assertIn("recording claude", err)
        self.assertEqual(err.count("\n"), 1, "one status line")

    def test_the_environment_and_its_defaults(self):
        self.run_record()
        run = [e for e in self.events() if e["what"] == "run"][0]["env"]
        self.assertEqual(run["MOIRAI_AGENT_DIR"], self.agent_dir)
        self.assertEqual(run["MOIRAI_LOG_FILE"],
                         os.path.join(self.agent_dir, "trace"))
        self.assertEqual((run["MOIRAI_TRACE_IO"], run["MOIRAI_AGENT_TRACE_IO"],
                          run["MOIRAI_PC_FLUSH_MS"]), ("1", "0", "200"))
        self.assertNotIn("MOIRAI_DATA_DIR", run)
        started = [e for e in self.events() if e["what"] == "service start"][0]
        self.assertEqual(started["env"], run, "the service has the same")

    def test_command_io_is_asked_for_as_it_approves_commands(self):
        self.run_record("--command-io")
        run = [e for e in self.events() if e["what"] == "run"][0]["env"]
        self.assertEqual(run["MOIRAI_AGENT_TRACE_IO"], "1")

    def test_options_override(self):
        self.run_record("--log-file", os.path.join(self.dir, "t", "p"),
                        "--data-dir", "/a:/b", "--no-trace-io",
                        "--no-command-io", "--flush-ms", "50")
        run = [e for e in self.events() if e["what"] == "run"][0]["env"]
        self.assertEqual(
            (run["MOIRAI_LOG_FILE"], run["MOIRAI_DATA_DIR"],
             run["MOIRAI_TRACE_IO"], run["MOIRAI_AGENT_TRACE_IO"],
             run["MOIRAI_PC_FLUSH_MS"]),
            (os.path.join(self.dir, "t", "p"), "/a:/b", "0", "0", "50"))

    def test_the_environment_already_there_is_the_default(self):
        self.run_record(env={"MOIRAI_PC_FLUSH_MS": "999",
                             "MOIRAI_DATA_DIR": "/x"})
        run = [e for e in self.events() if e["what"] == "run"][0]["env"]
        self.assertEqual((run["MOIRAI_PC_FLUSH_MS"], run["MOIRAI_DATA_DIR"]),
                         ("999", "/x"))

    def test_this_process_environment_is_left_as_it_was(self):
        before = dict(os.environ)
        self.run_record()
        self.assertEqual(dict(os.environ), before)


class FailureTests(Case):
    def test_the_exit_status_is_the_commands(self):
        for code in (0, 3, 42):
            self.assertEqual(self.run_record(command=[self.harness, str(code)])[0],
                             code)

    def test_the_service_is_stopped_after_a_failing_command(self):
        self.assertEqual(self.run_record(command=[self.harness, "7"])[0], 7)
        self.assertEqual(self.events()[-1]["what"], "service stop")

    def test_the_service_is_stopped_when_the_command_cannot_run(self):
        with self.assertRaises(record.RecordError):
            self.run_record(command=[os.path.join(self.dir, "missing")])
        self.assertEqual([e["what"] for e in self.events()],
                         ["install claude", "service start", "service stop"])

    def test_a_command_killed_by_a_signal_is_128_plus(self):
        killer = self.script("killer", f"#!{PY}\nimport os, signal\n"
                             "os.kill(os.getpid(), signal.SIGKILL)\n")
        self.assertEqual(self.run_record(command=[killer])[0], 128 + 9)
        self.assertEqual(self.events()[-1]["what"], "service stop")

    def test_hooks_that_cannot_be_installed_start_nothing(self):
        def broken(harness, user):
            raise SystemExit("unknown harness 'x'")

        args = record.parser().parse_args(
            ["--agent-dir", self.agent_dir, "--service", self.service, "x"])
        with self.assertRaisesRegex(record.RecordError, "cannot install"):
            record.run(args, [self.harness], installer=broken,
                       stderr=io.StringIO())
        self.assertEqual(self.events(), [])

    def test_a_service_that_does_not_start_is_an_error_and_is_cleaned_up(self):
        with self.assertRaisesRegex(record.RecordError, "start failed"):
            self.run_record(env={"FAKE_SERVICE_FAIL": "1"})
        self.assertEqual([e["what"] for e in self.events()],
                         ["install claude", "service start", "service stop"])

    def test_no_service_binary_is_a_clear_error(self):
        with self.assertRaisesRegex(record.RecordError, "not executable"):
            record.find_service(os.path.join(self.dir, "nope"))
        old = record.shutil.which
        record.shutil.which = lambda name: None
        try:
            real = record.os.access
            record.os.access = lambda path, mode: False
            try:
                with self.assertRaisesRegex(record.RecordError,
                                            "no moirai-service"):
                    record.find_service()
            finally:
                record.os.access = real
        finally:
            record.shutil.which = old


class SignalTests(Case):
    def test_sigterm_reaches_the_command_and_the_service_still_stops(self):
        started = os.path.join(self.dir, "started")
        sleeper = self.script("sleeper", f"""#!{PY}
import time
open({started!r}, "w").close()
time.sleep(60)
""")
        driver = self.script("driver.py", f"""#!{PY}
import sys
from moirai.agent import record
args = record.parser().parse_args(["--agent-dir", {self.agent_dir!r},
    "--service", {self.service!r}, "claude"])
sys.exit(record.run(args, [{sleeper!r}], installer=lambda h, u: "hooks"))
""")
        proc = subprocess.Popen([PY, driver], stderr=subprocess.DEVNULL)
        deadline = time.time() + 30
        while not os.path.exists(started) and time.time() < deadline:
            time.sleep(0.05)
        self.assertTrue(os.path.exists(started))
        proc.send_signal(signal.SIGTERM)
        self.assertEqual(proc.wait(timeout=30), 128 + signal.SIGTERM)
        self.assertEqual([e["what"] for e in self.events()],
                         ["service start", "service stop"])


class CommandLineTests(Case):
    def cli(self, *argv):
        root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(record.__file__))))
        return subprocess.run([PY, "-m", "moirai.agent", "record", *argv],
                              capture_output=True, text=True, cwd=self.dir,
                              env=dict(os.environ, PYTHONPATH=root))

    def test_help_needs_no_command(self):
        done = self.cli("--help")
        self.assertEqual(done.returncode, 0)
        self.assertIn("--command-io", done.stdout)

    def test_the_command_must_follow_dashes(self):
        for argv in (["claude"], ["claude", "--"]):
            done = self.cli(*argv)
            self.assertEqual(done.returncode, 2, argv)
            self.assertIn("command", done.stderr)

    def test_errors_are_one_line_and_status_2(self):
        done = self.cli("--service", os.path.join(self.dir, "nope"),
                        "--agent-dir", self.agent_dir, "claude", "--", "true")
        self.assertEqual(done.returncode, 2)
        self.assertIn("moirai: --service", done.stderr)
        self.assertNotIn("Traceback", done.stderr)


if __name__ == "__main__":
    unittest.main()
