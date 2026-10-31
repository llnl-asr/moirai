#!/usr/bin/env python3
"""moirai.agent.manifest and the hook's use of it, without the native module."""
import json
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fake_api import FakeAPI  # noqa: E402

from moirai.agent import agent, manifest  # noqa: E402
from moirai.agent.recorder import Recorder  # noqa: E402

SECRET = "sk-" + "a" * 30


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_write_is_atomic_private_and_only_the_known_fields(self):
        target = manifest.write(self.dir, {"session_id": "s1", "name": "n",
                                           "extra": 1})
        self.assertEqual(target, os.path.join(self.dir, "manifests", "s1.json"))
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o600)
        with open(target) as fh:
            self.assertEqual(json.load(fh), {"session_id": "s1", "name": "n"})
        self.assertEqual(os.listdir(os.path.dirname(target)), ["s1.json"])

    def test_update_merges_and_stamps(self):
        manifest.update(self.dir, "s1", harness="codex", turns=1)
        got = manifest.update(self.dir, "s1", turns=2, state="ended")
        self.assertEqual((got["harness"], got["turns"], got["state"]),
                         ("codex", 2, "ended"))
        self.assertEqual(manifest.read("s1", self.dir), got)
        self.assertTrue(got["updated_at"].endswith("+00:00"))
        self.assertEqual(got["updated_at"], manifest.iso(got["updated_us"]))
        self.assertEqual(set(got), set(manifest.FIELDS))

    def test_an_id_from_a_harness_is_a_name_not_a_path(self):
        for sid in ("../../etc/x", "a/b", ".hidden", "x y"):
            target = manifest.write(self.dir, {"session_id": sid})
            self.assertEqual(os.path.dirname(target),
                             os.path.join(self.dir, "manifests"), sid)
            self.assertEqual(manifest.read(sid, self.dir)["session_id"], sid)
        self.assertNotEqual(manifest.safe_name("a/b"), manifest.safe_name("a_b"))
        self.assertEqual(manifest.safe_name("abc-1.2_x"), "abc-1.2_x")

    def test_list_is_newest_first_and_survives_junk(self):
        manifest.update(self.dir, "old", updated_us=1000)
        manifest.update(self.dir, "new", updated_us=2000)
        with open(os.path.join(self.dir, "manifests", "bad.json"), "w") as fh:
            fh.write("{")
        self.assertEqual([m["session_id"] for m in
                          manifest.list_sessions(self.dir)], ["new", "old"])
        self.assertEqual(manifest.list_sessions(os.path.join(self.dir, "no")),
                         [])
        self.assertIsNone(manifest.read("none", self.dir))

    def test_a_new_manifest_is_stamped_as_started(self):
        got = manifest.update(self.dir, "new")
        self.assertEqual(got["started_us"], got["updated_us"])
        self.assertEqual(manifest.update(self.dir, "new", turns=1)["started_us"],
                         got["started_us"])

    def test_recording_is_a_state_file(self):
        self.assertFalse(manifest.recording(self.dir))
        path, lock = agent.state_paths(self.dir, "s1")
        open(lock, "w").close()
        self.assertFalse(manifest.recording(self.dir))
        agent.save(path, {"sessions": {"s1": {}}})
        self.assertTrue(manifest.recording(self.dir))
        os.unlink(path)
        self.assertFalse(manifest.recording(self.dir))


class HookTests(unittest.TestCase):
    """What the recorder keeps, and what write_manifests makes of it."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self.temp.name)
        self.api = FakeAPI()

    def tearDown(self):
        self.temp.cleanup()

    def hook(self, sessions, events):
        # One hook: a recorder over the saved sessions, then the manifest.
        recorder = Recorder(self.api, sessions=sessions)
        for ev in events:
            recorder.handle(dict(ev, harness="codex", session="s/1"))
        agent.write_manifests(self.dir, recorder, sessions)

    def test_every_event_updates_the_manifest(self):
        sessions = {}
        self.hook(sessions, [{"kind": "session.start", "cwd": "/w",
                              "model": "m"}])
        first = manifest.read("s/1", self.dir)
        self.assertEqual((first["state"], first["turns"], first["activities"],
                          first["name"], first["harness"], first["cwd"],
                          first["model"]),
                         ("running", 0, 0, "", "codex", "/w", "m"))
        self.assertRegex(first["entity"], r"^[0-9a-f]{16}$")
        self.assertEqual(first["entity"],
                         format(sessions["s/1"]["entity"], "016x"))

        prompt = f"  sort   the\n file\t with {SECRET}  " + "x" * 300
        self.hook(sessions, [{"kind": "turn.start", "prompt": prompt}])
        second = manifest.read("s/1", self.dir)
        self.assertEqual(second["turns"], 1)
        self.assertEqual(second["entity"], first["entity"])
        self.assertTrue(second["name"].startswith(
            "sort the file with [REDACTED:api-key]"), second["name"])
        self.assertNotIn(SECRET, second["name"])
        self.assertLessEqual(len(second["name"]), 120)
        self.assertNotIn("\n", second["name"])
        self.assertGreaterEqual(second["updated_us"], first["updated_us"])

        self.hook(sessions, [{"kind": "turn.start", "prompt": "another"},
                             {"kind": "turn.end"}])
        third = manifest.read("s/1", self.dir)
        self.assertEqual(third["name"], second["name"], "the first prompt")
        self.assertEqual((third["turns"], third["activities"]), (2, 2))

        self.hook(sessions, [{"kind": "session.end"}])
        last = manifest.read("s/1", self.dir)
        self.assertEqual(last["state"], "ended")
        self.assertEqual(last["activities"], 3)
        self.assertEqual(last["started_us"], first["started_us"])
        self.assertEqual(sessions, {})
        self.assertEqual(set(last), set(manifest.FIELDS))
        self.assertEqual(stat.S_IMODE(os.stat(
            manifest.path("s/1", self.dir)).st_mode), 0o600)

    def test_a_manifest_that_cannot_be_written_does_not_fail_the_hook(self):
        blocked = os.path.join(self.dir, "file")
        open(blocked, "w").close()
        sessions = {}
        recorder = Recorder(self.api, sessions=sessions)
        recorder.handle({"kind": "session.start", "session": "x"})
        agent.write_manifests(blocked, recorder, sessions)  # no exception


if __name__ == "__main__":
    unittest.main()
