#!/usr/bin/env python3
"""moirai.agent.artifacts.read_text with a fake reader: key handling, decoding,
the cache, errors. Pure Python (no native module)."""
import threading
import unittest

from moirai.agent import artifacts


class ReadTextTests(unittest.TestCase):
    def setUp(self):
        artifacts.forget()
        self.calls = []

    def reader(self, key, prefix):
        self.calls.append((key, prefix))
        if "missing" in key:
            return None
        if "bad" in key:
            return b"caf\xc3\xa9 \xff"
        return ("text of " + key).encode()

    def read(self, uri, prefix="p", limit=0):
        return artifacts.read_text(uri, prefix, limit, reader=self.reader)

    def test_the_name_after_at_is_stripped(self):
        self.assertEqual(self.read("artifact://k@/some/file"),
                         "text of artifact://k")
        self.assertEqual(self.calls, [("artifact://k", "p")])

    def test_not_an_artifact_is_none_without_reading(self):
        self.assertIsNone(self.read("file:///x"))
        self.assertIsNone(self.read(""))
        self.assertEqual(self.calls, [])

    def test_decoding_replaces(self):
        self.assertEqual(self.read("artifact://bad"), "café �")

    def test_hits_are_cached_per_prefix_misses_are_not(self):
        for _ in range(3):
            self.read("artifact://a")
        self.read("artifact://a", prefix="q")
        for _ in range(2):
            self.assertIsNone(self.read("artifact://missing"))
        self.assertEqual(len(self.calls), 4)

    def test_limit_clips_without_poisoning_the_cache(self):
        self.assertEqual(self.read("artifact://long", limit=4), "text")
        self.assertEqual(self.read("artifact://long"), "text of artifact://long")
        self.assertEqual(len(self.calls), 1)

    def test_the_cache_is_bounded(self):
        old, artifacts.CACHE_ENTRIES = artifacts.CACHE_ENTRIES, 2
        try:
            for key in ("a", "b", "a", "c", "a", "b"):
                self.read("artifact://" + key)
        finally:
            artifacts.CACHE_ENTRIES = old
        self.assertEqual([k[len("artifact://"):] for k, _ in self.calls],
                         ["a", "b", "c", "b"])

    def test_a_reader_that_fails_is_none_with_an_error(self):
        def boom(key, prefix):
            raise OSError("store locked")

        self.assertIsNone(artifacts.read_text("artifact://z", "p", reader=boom))
        self.assertIn("store locked", artifacts.error())
        self.read("artifact://ok")
        self.assertEqual(artifacts.error(), "")

    def test_threads(self):
        out = []

        def work():
            out.append(self.read("artifact://t"))

        threads = [threading.Thread(target=work) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(set(out), {"text of artifact://t"})


if __name__ == "__main__":
    unittest.main()
