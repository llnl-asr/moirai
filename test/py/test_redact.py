#!/usr/bin/env python3
"""moirai.agent.redact: secret patterns, sensitive file names, the setting; and
what the recorder does with them. Pure Python (no native module)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fake_api import FakeAPI  # noqa: E402

from moirai.agent import content, redact  # noqa: E402
from moirai.agent.recorder import Recorder  # noqa: E402

KEY = "sk-" + "a" * 30
SENSITIVE = [
    "/w/.env", "/w/.env.production", "/home/u/.netrc", "/home/u/.git-credentials",
    "/home/u/.ssh/id_rsa", "/home/u/.ssh/id_rsa.pub", "/home/u/.ssh/config",
    "/home/u/.ssh/known_hosts", "/k/id_ed25519", "/k/server.pem", "/k/a.key",
    "/k/a.p12", "/home/u/.aws/credentials", "/home/u/.config/gh/hosts.yml",
    "/home/u/.docker/config.json", "/w/my_secret_notes.txt",
    "/w/Credentials.json", "/w/api_token", ".env", "rel/.ENV",
]
PLAIN = ["/w/data.csv", "/w/src/main.py", "/home/u/.config/other.yml",
         "/home/u/.bashrc", "/w/environment.yml", "/w/keyboard.txt",
         "/w/aws/plain.txt"]


class TextTests(unittest.TestCase):
    def test_every_pattern(self):
        cases = {
            KEY: "[REDACTED:api-key]",
            "ghp_" + "b" * 25: "[REDACTED:github-token]",
            "github_pat_" + "c" * 25: "[REDACTED:github-token]",
            "glpat-" + "d" * 22: "[REDACTED:gitlab-token]",
            "xoxb-1234567890-abc": "[REDACTED:slack-token]",
            "AKIA" + "E" * 16: "[REDACTED:aws-key]",
            "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----":
                "[REDACTED:private-key]",
            "Bearer " + "f" * 20: "Bearer [REDACTED:bearer]",
            "API_KEY=abcdefgh": "API_KEY=[REDACTED:assignment]",
            'password: "hunter22"': 'password: "[REDACTED:assignment]"',
        }
        for text, want in cases.items():
            got, n = redact.redact_text(f"x {text} y")
            self.assertEqual(got, f"x {want} y", text)
            self.assertEqual(n, 1, text)
        self.assertEqual(redact.redact_text("nothing here"), ("nothing here", 0))

    def test_site_patterns_and_explicit_patterns(self):
        patterns = redact.SECRETS + redact.site_patterns("proj-[0-9]+\n\nfoo")
        self.assertEqual(redact.redact_text("a proj-42 foo", patterns),
                         ("a [REDACTED:site] [REDACTED:site]", 2))
        self.assertEqual(redact.redact_text(KEY, [])[0], KEY)

    def test_content_keeps_working(self):
        self.assertIs(content.SECRETS, redact.SECRETS)
        self.assertEqual(content.redact_text(KEY), redact.redact_text(KEY))
        c = content.Content(FakeAPI(redact="corp-[a-z]+"))
        c.put({"k": f"{KEY} corp-xyz"})
        self.assertNotIn(KEY, c.api.artifacts[0])
        self.assertIn("[REDACTED:site]", c.api.artifacts[0])


class PathTests(unittest.TestCase):
    def test_sensitive_names(self):
        for path in SENSITIVE:
            self.assertTrue(redact.is_sensitive_path(path), path)
        for path in PLAIN:
            self.assertFalse(redact.is_sensitive_path(path), path)

    def test_the_placeholder_is_stable_and_hides_the_name(self):
        a = redact.redact_path("/home/u/.ssh/id_rsa_prod_customer")
        self.assertRegex(a, r"^sensitive-file:[0-9a-f]{8}$")
        self.assertEqual(a, redact.redact_path("/home/u/.ssh/../.ssh/id_rsa_prod_customer"))
        self.assertNotEqual(a, redact.redact_path("/home/u/.ssh/id_rsa_other"))
        self.assertNotIn("customer", a)
        self.assertEqual(redact.placeholder("/w/.env"),
                         redact.redact_path("/w/.env"))

    def test_other_paths_get_the_secret_patterns(self):
        self.assertEqual(redact.redact_path("/w/data.csv"), "/w/data.csv")
        self.assertEqual(redact.redact_path(f"/w/out-{KEY}.csv"),
                         "/w/out-[REDACTED:api-key].csv")
        self.assertEqual(redact.redact_path(None), None)

    def test_the_setting_extends_overrides_and_drops(self):
        self.assertFalse(redact.is_sensitive_path("/w/notes/private.txt"))
        globs = redact.sensitive_globs("# mine\nprivate*\n/vault/*\n")
        self.assertTrue(redact.is_sensitive_path("/w/notes/private.txt", globs))
        self.assertTrue(redact.is_sensitive_path("/vault/a/b", globs))
        self.assertTrue(redact.is_sensitive_path("/w/.env", globs),
                        "still extended")
        self.assertFalse(redact.is_sensitive_path("/w/vault/a", globs))

        globs = redact.sensitive_globs("!*token*\n!*.key")
        self.assertFalse(redact.is_sensitive_path("/w/tokenizer.json", globs))
        self.assertFalse(redact.is_sensitive_path("/w/a.key", globs))
        self.assertTrue(redact.is_sensitive_path("/w/.env", globs))

        globs = redact.sensitive_globs("@only\n*.dat")
        self.assertTrue(redact.is_sensitive_path("/w/a.dat", globs))
        self.assertFalse(redact.is_sensitive_path("/w/.env", globs))

        self.assertEqual(redact.sensitive_globs(""), redact.SENSITIVE_PATHS)
        self.assertIn("*.dat", redact.sensitive_globs("*.dat"))


class RecorderTests(unittest.TestCase):
    """A sensitive file is named by its placeholder and its content is not kept."""

    def test_a_sensitive_file_is_not_copied_or_named(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = os.path.realpath(temp)
            env = os.path.join(temp, ".env")
            plain = os.path.join(temp, "data.csv")
            for path, text in ((env, "TOKEN_X=hunter2hunter2\n"),
                               (plain, "a,b\n")):
                with open(path, "w") as fh:
                    fh.write(text)
            api = FakeAPI()
            recorder = Recorder(api, sessions={})
            base = {"harness": "claude", "session": "s"}
            recorder.handle(dict(base, kind="session.start"))
            recorder.handle(dict(base, kind="tool.start", call="c", name="Bash",
                                 input={}, command=f"cat {env} {plain}",
                                 cwd=temp))
            recorder.handle(dict(base, kind="tool.end", call="c", output="ok",
                                 exit_code=0))
            files = [v for v in api.entities.values() if v[0] == "file"]
            keys = " ".join(k for _, k, _ in files) + " ".join(u for _, _, u in files)
            self.assertNotIn(".env", keys)
            self.assertIn("sensitive-file:", keys)
            self.assertIn("data.csv", keys)
            self.assertFalse(any("hunter2" in a for a in api.artifacts))


if __name__ == "__main__":
    unittest.main()
