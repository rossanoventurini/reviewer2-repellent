#!/usr/bin/env python3
"""Regression test of scripts/refs_check.py (--no-refchecker) on the fixtures in evals/fixtures/refs_check/.

Run: python3 evals/tests/test_refs_check.py   (network needed: arXiv, Crossref, DataCite; skips cleanly when offline)
Each fixture's expectations are in evals/fixtures/refs_check/expectations.json. Expectations about published versions
need RefChecker's local DBLP database (~/.cache/refchecker/dblp.db); without it they are skipped.
"""
import json
import pathlib
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "evals" / "fixtures" / "refs_check"
SCRIPT = ROOT / "skills" / "reviewer2-repellent" / "scripts" / "refs_check.py"
DB = pathlib.Path.home() / ".cache" / "refchecker" / "dblp.db"
UA = {"User-Agent": "reviewer2-repellent-refs-check-test/1.0"}


def online():
    for url in ("https://api.crossref.org/works/10.1145/362384.362685",
                "https://export.arxiv.org/api/query?id_list=1706.03762"):
        try:
            urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read()
        except Exception as e:  # noqa: BLE001  (any failure means: cannot test)
            print(f"SKIP: offline or service down ({url}: {e.__class__.__name__})")
            return False
    return True


def findings(bib):
    out = subprocess.run([sys.executable, "-I", str(SCRIPT), str(bib), "--no-refchecker", "--json"],
                         capture_output=True, text=True, timeout=900)
    if out.returncode != 0:
        raise RuntimeError(out.stderr[-2000:])
    d = json.loads(out.stdout)
    return d["findings"], d["skipped"]


def match(f, sev, kind, sub):
    text = " ".join([f["quote"], " ".join(f["where"]), f["hint"]])
    return f["sev"] == sev and kind in f["kind"] and sub in text


def check(name, e):
    try:
        fs, skipped = findings(FIX / e["bib"])
    except (RuntimeError, subprocess.TimeoutExpired) as err:
        return name, [f"ERROR {err}"], []
    must = [m for m in e["must"] if DB.is_file() or "published version" not in m[1]]
    bad = [f"missing {m}" for m in must if not any(match(f, *m) for f in fs)]
    bad += [f"unexpected {m}" for m in e["must_not"] if any(match(f, *m) for f in fs)]
    return name, bad, skipped


def main():
    if not online():
        return 0
    if not DB.is_file():
        print(f"note: {DB} not found: 'published version' expectations skipped")
    exp = {k: v for k, v in json.loads((FIX / "expectations.json").read_text()).items() if not k.startswith("_")}
    failed = 0
    with ThreadPoolExecutor(4) as ex:  # few workers: arXiv and Crossref rate limits
        for name, bad, skipped in ex.map(lambda kv: check(*kv), exp.items()):
            print(("PASS " if not bad else "FAIL ") + name + ("" if not bad else ": " + "; ".join(bad)))
            for s in skipped:
                if "network" in s or "unreachable" in s:
                    print(f"     warning: incomplete run ({s})")
            failed += bool(bad)
    print(f"{failed} fixture(s) failing")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
