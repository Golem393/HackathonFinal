"""Guard against hardcoding: no value the agents found on the websites may appear in what we ship.

The package reviewer rejects copied scenario values (references, material numbers, keys, logins, TANs) in code,
prompts, config and notes. This test takes every ID-like token and e-mail address from the facts of the last local run
(dev/out/log/facts/*.json, gitignored) and checks that none of them appears in a tracked file. Without local facts it
is skipped.
"""
import glob
import json
import os
import re
import subprocess
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
FACTS = glob.glob(os.path.join(ROOT, "dev", "out", "log", "facts", "*.json"))
# ID-like: letters, a hyphen, digits (and more): e.g. a reference, a material number, a key; plus e-mail addresses.
TOKEN = re.compile(r"\b[A-Za-z]{1,6}-\d{2,}(?:-[A-Za-z0-9]+)*\b|[\w.+-]+@[\w-]+\.[\w.]+")
SKIP_FILES = ("uv.lock",)
SKIP_PREFIXES = (".entire/", ".agents/", ".codex/", ".github/", ".claude/", "agent/")


def scenario_tokens() -> set[str]:
    tokens: set[str] = set()
    for path in FACTS:
        with open(path) as file:
            tokens |= set(TOKEN.findall(json.dumps(json.load(file), ensure_ascii=False)))
    return {t for t in tokens if not t.endswith((".example",)) or "@" in t}


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    return [f for f in out if f not in SKIP_FILES and not f.startswith(SKIP_PREFIXES)]


@unittest.skipUnless(FACTS, "no local facts (dev/out/log/facts) to check against")
class NoScenarioValues(unittest.TestCase):
    def test_no_value_from_the_websites_in_tracked_files(self):
        tokens = scenario_tokens()
        hits = []
        for name in tracked_files():
            try:
                with open(os.path.join(ROOT, name), encoding="utf-8") as file:
                    text = file.read()
            except (UnicodeDecodeError, FileNotFoundError):
                continue
            hits += [f"{name}: {t}" for t in tokens if t in text]
        self.assertEqual(hits, [], "scenario values found in tracked files (the reviewer rejects these)")


if __name__ == "__main__":
    unittest.main()
