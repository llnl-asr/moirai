#!/usr/bin/env python3
"""moirai.agent.install's hooks in a harness's configuration, and uninstall. The
hook commands are written here, so no native module is needed; the real ones are
in test_agent_manifest.py."""
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest

from moirai.agent import install, manifest

HANDLER = {"type": "command", "timeout": 10}
THEIRS = {"type": "command", "command": "/usr/bin/notify done", "timeout": 5}


def command(run, *settings):
    return shlex.join(["/usr/bin/env", f"MOIRAI_AGENT_DIR={run}", *settings,
                       "/usr/bin/python3",
                       "/site-packages/moirai/agent/agent.py", "claude"])


class Case(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self.temp.name)
        self.run_dir = os.path.join(self.dir, "run")
        self.config = install.config_path("claude", root=self.dir)
        self.addCleanup(self.temp.cleanup)

    def load(self):
        with open(self.config) as fh:
            return json.load(fh)

    def merge(self, *settings, events=("Stop", "PreToolUse")):
        return install.merge_hooks(self.config, events,
                                   command(self.run_dir, *settings), HANDLER)

    def with_theirs(self):
        os.makedirs(os.path.dirname(self.config))
        with open(self.config, "w") as fh:
            json.dump({"model": "m", "hooks": {"Stop": [
                {"matcher": "*", "hooks": [THEIRS]}]}}, fh)


class ReplaceTests(Case):
    def test_installing_again_replaces_a_hook_with_other_settings(self):
        # The hook with MOIRAI_AGENT_TRACE_IO=1 must not outlive the setting.
        self.merge("MOIRAI_AGENT_TRACE_IO=1")
        self.merge("MOIRAI_AGENT_TRACE_IO=0")
        hooks = self.load()["hooks"]
        for event in ("Stop", "PreToolUse"):
            self.assertEqual(len(hooks[event]), 1, event)
            self.assertIn("MOIRAI_AGENT_TRACE_IO=0",
                          hooks[event][0]["hooks"][0]["command"])

    def test_installing_again_changes_nothing(self):
        self.with_theirs()
        self.merge("MOIRAI_TRACE_IO=1")
        with open(self.config) as fh:
            first = fh.read()
        self.merge("MOIRAI_TRACE_IO=1")
        with open(self.config) as fh:
            self.assertEqual(fh.read(), first)

    def test_hooks_of_another_install_and_old_events_go(self):
        old = command(self.run_dir).replace("/site-packages/", "/old/venv/")
        install.merge_hooks(self.config, ("Stop", "Retired"), old, HANDLER)
        self.merge(events=("Stop",))
        hooks = self.load()["hooks"]
        self.assertEqual(list(hooks), ["Stop"])
        self.assertEqual(len(hooks["Stop"]), 1)
        self.assertNotIn("/old/venv/", hooks["Stop"][0]["hooks"][0]["command"])

    def test_installing_leaves_others_alone(self):
        self.with_theirs()
        self.merge()
        self.merge()
        config = self.load()
        self.assertEqual(config["model"], "m")
        self.assertEqual(config["hooks"]["Stop"][0]["hooks"], [THEIRS])
        self.assertEqual(len(config["hooks"]["Stop"]), 2)


class UninstallTests(Case):
    def test_it_leaves_nothing_of_its_own(self):
        self.merge()
        self.assertEqual(install.uninstall("claude", root=self.dir),
                         (self.config, [self.run_dir]))
        self.assertFalse(os.path.exists(self.config))

    def test_it_leaves_others_alone(self):
        self.with_theirs()
        self.merge()
        install.uninstall("claude", root=self.dir)
        self.assertEqual(self.load(), {"model": "m", "hooks": {"Stop": [
            {"matcher": "*", "hooks": [THEIRS]}]}})

    def test_a_hook_sharing_a_group_stays(self):
        os.makedirs(os.path.dirname(self.config))
        with open(self.config, "w") as fh:
            json.dump({"hooks": {"Stop": [{"hooks": [
                THEIRS, dict(HANDLER, command=command(self.run_dir))]}]}}, fh)
        install.uninstall("claude", root=self.dir)
        self.assertEqual(self.load()["hooks"]["Stop"][0]["hooks"], [THEIRS])

    def test_a_command_that_does_not_parse_is_not_ours(self):
        self.assertFalse(install.is_moirai_hook({"command": "echo 'open"}))
        self.assertFalse(install.is_moirai_hook({"command": "my/agent.py"}))

    def test_nothing_installed_is_fine(self):
        self.assertEqual(install.uninstall("claude", root=self.dir),
                         (self.config, []))

    def test_a_symbolic_link_is_refused(self):
        os.makedirs(os.path.dirname(self.config))
        target = os.path.join(self.dir, "shared.json")
        with open(target, "w") as fh:
            fh.write("{}")
        os.symlink(target, self.config)
        with self.assertRaises(SystemExit):
            install.uninstall("claude", root=self.dir)

    def test_an_unknown_harness_is_refused(self):
        with self.assertRaises(SystemExit):
            install.uninstall("nope", root=self.dir)

    def test_the_run_is_cleaned_and_the_record_kept(self):
        self.merge()
        for folder, name in (("sessions", "a.json"), ("sessions", "a.lock"),
                             ("runs", "b.json")):
            os.makedirs(os.path.join(self.run_dir, folder), exist_ok=True)
            open(os.path.join(self.run_dir, folder, name), "w").close()
        store = os.path.join(self.run_dir, "trace.artifacts", "host")
        kept = [os.path.join(self.run_dir, "trace_host.pfw.gz"),
                os.path.join(self.run_dir, "hook.log"),
                os.path.join(store, "CURRENT")]
        os.makedirs(os.path.dirname(kept[2]))
        for path in kept:
            open(path, "w").close()
        manifest.update(self.run_dir, "stuck", state="running")
        manifest.update(self.run_dir, "done", state="ended", updated_us=5)
        self.assertTrue(manifest.recording(self.run_dir))

        install.uninstall("claude", root=self.dir)

        self.assertFalse(manifest.recording(self.run_dir))
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "runs")))
        self.assertEqual(manifest.read("stuck", self.run_dir)["state"], "ended")
        self.assertEqual(manifest.read("done", self.run_dir)["updated_us"], 5)
        for path in kept:
            self.assertTrue(os.path.exists(path), path)

    def test_the_plugin_goes_and_names_its_run(self):
        path = install.config_path("opencode", root=self.dir)
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as fh:
            fh.write(install.OPENCODE_PLUGIN
                     .replace("@HOOK@", "[]")
                     .replace("@ENV@", json.dumps(
                         {"MOIRAI_AGENT_DIR": self.run_dir})))
        self.assertEqual(install.uninstall("opencode", root=self.dir),
                         (path, [self.run_dir]))
        self.assertFalse(os.path.exists(path))

    def test_the_command_line(self):
        self.merge()
        root = os.path.dirname(os.path.dirname(os.path.abspath(
            install.__file__)))
        done = subprocess.run(
            [sys.executable, "-m", "moirai.agent", "uninstall", "claude"],
            capture_output=True, text=True, cwd=self.dir,
            env=dict(os.environ, PYTHONPATH=os.path.dirname(root)))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"cleaned up {self.run_dir}", done.stdout)
        self.assertFalse(os.path.exists(self.config))


if __name__ == "__main__":
    unittest.main()
