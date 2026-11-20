#!/usr/bin/env python3
"""Tests of SKILL.md: the frontmatter parses, the name field is valid and matches the folder, the description fits
the 1024-character limit and carries its triggers, and every reference file and script SKILL.md names exists.

Run: python3 -I evals/tests/test_skill_md.py
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "reviewer2-repellent"


def frontmatter(text):
    """Parse the YAML frontmatter as one-line `key: value` pairs (what the skill loaders read)."""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ValueError("no frontmatter between --- lines at the start of SKILL.md")
    fields = {}
    for line in m.group(1).split("\n"):
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep or not re.fullmatch(r"[a-z_-]+", key):
            raise ValueError("not a one-line `key: value` field: %r" % line[:60])
        if key in fields:
            raise ValueError("repeated field: %s" % key)
        fields[key] = value.strip()
    return fields


class SkillMd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        cls.fm = frontmatter(cls.text)

    def test_name(self):
        name = self.fm.get("name", "")
        self.assertRegex(name, r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertLessEqual(len(name), 64)
        self.assertEqual(name, SKILL.name)

    def test_description_limit(self):
        d = self.fm.get("description", "")
        self.assertTrue(d, "empty description")
        self.assertLessEqual(len(d), 1024, "description has %d characters" % len(d))
        self.assertNotRegex(d, r"[<>]", "no angle brackets in the description")
        self.assertFalse(d.startswith(("'", '"', "|", ">")), "plain one-line scalar expected")
        self.assertNotIn(": ", d, "': ' would break the YAML scalar")

    def test_description_triggers(self):
        d = self.fm["description"]
        for phrase in ("check my paper before submission", "apply my choices in changes.pdf",
                       "Not for editing or polishing a draft still being written"):
            self.assertIn(phrase, d)
        self.assertNotRegex(d, r"\(use [a-z0-9-]+\)", "the description names no other skill")

    def test_referenced_files_exist(self):
        for rel in sorted(set(re.findall(r"<skill>/((?:references|scripts)/[A-Za-z0-9_.-]+\.(?:md|py))", self.text))):
            self.assertTrue((SKILL / rel).is_file(), "SKILL.md names a missing file: %s" % rel)
        for rel in sorted(set(re.findall(r"`([a-z0-9-]+\.md)`", self.text))):
            if rel not in ("SKILL.md", "SETUP.md", "README.md"):
                hits = [p for p in (SKILL / "references" / rel, SKILL / rel) if p.is_file()]
                if rel.endswith("-agent.md") or rel in ("apply-changes.md", "typos-finder.md", "typos-verifier.md",
                                                        "pdf-layout.md", "ai-venue-actions.md"):
                    self.assertTrue(hits, "SKILL.md names a missing reference: %s" % rel)


if __name__ == "__main__":
    unittest.main()
