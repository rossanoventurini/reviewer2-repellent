#!/usr/bin/env python3
"""Regression test of scripts/form_check.py on the adversarial fixtures in evals/fixtures/form_check/.

Run: python3 evals/tests/test_form_check.py   (compiles each fixture with latexmk if its PDF is missing)
Each fixture's expectations are in evals/fixtures/form_check/expectations.json. The source-hygiene checks (Markdown,
Unicode, invisible characters, comments naming LLMs) must stay silent on every fixture not listed in HYGIENE_HITS. The
final COVERAGE line (counts of what was read) is checked on one fixture. The --supp check runs on the material that
supp/make_supp.py builds in a temporary folder (dirty/ folder, dirty.zip with a nested zip, clean/), and the --engine
detection of the widow/orphan build on engine-fontspec/ (skipped without xelatex).
"""
import json
import shutil
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "evals" / "fixtures" / "form_check"
SCRIPT = ROOT / "skills" / "reviewer2-repellent" / "scripts" / "form_check.py"


def findings(folder, args):
    if not (folder / "main.pdf").is_file():
        subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", "-no-shell-escape", "main.tex"],
                       cwd=folder, capture_output=True)
    out = subprocess.run([sys.executable, "-I", str(SCRIPT), "main.tex", "--json", *args], cwd=folder,
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr[-2000:])
    return json.loads(out.stdout)["findings"]


HYGIENE_KINDS = ("Markdown in the text", "Unicode character in the text", "straight quotes in the text",
                 "invisible character in the text", "non-breaking or special space character", "mixed dash styles",
                 "mixed quote styles", "comment mentions an LLM or a prompt")
# fixtures where a hygiene finding is a true positive: source-hygiene is made for it; num-b03 types "±" in a table
# whose other rows write $\pm$ (text font next to math font)
HYGIENE_HITS = {"source-hygiene": HYGIENE_KINDS, "num-b03": ("Unicode character in the text",)}


def match(f, sev, kind, sub):
    text = " ".join([f["quote"], " ".join(f["where"]), f["hint"]])
    return f["sev"] == sev and kind in f["kind"] and sub in text


# --supp: every finding on the dirty material (folder and zip), none on the clean folder, single-blind keeps secrets only
SUPP_MUST = [
    ("FAIL", "git repository in the supplementary material", ".git"),
    ("FAIL", "identity in a supplementary .git folder", "name = Ada Burrow"),
    ("FAIL", "identity in a supplementary .git folder", "email = ada.burrow@northwind.edu"),
    ("FAIL", "identity in a supplementary .git folder", "github.com/aburrow/fastidx"),
    ("FAIL", "identity in a supplementary .git folder", "Ada Burrow <ada.burrow@northwind.edu>"),
    ("FAIL", "home path in the supplementary material", "analysis.ipynb [cell 2 output]:1"),
    ("FAIL", "home path in the supplementary material", "src/train.py:3"),
    ("FAIL", "PDF Author metadata in the supplementary material", "Ada Burrow"),
    ("FAIL", "Office document properties in the supplementary material name a person", "dc:creator: Ada Burrow"),
    ("FAIL", "copyright line in the supplementary material names a holder", "LICENSE:3"),
    ("FAIL", "author line in the supplementary material", "README.md:3"),
    ("FAIL", "acknowledgements in the supplementary material", "README.md:7"),
    ("CHECK", "grant number in the supplementary material", "ERC-2024-StG-101077"),
    ("FAIL", "credentials file in the supplementary material", "OPENAI_API_KEY=sk-t…[32 chars]"),
    ("CHECK", "possible secret in the supplementary material", "a1b2…[20 chars]"),
    ("CHECK", "macOS metadata in the supplementary material", ".DS_Store"),
    ("INFO", "repository link in the supplementary material", "github.com/facebookresearch"),
    ("INFO", "supplementary material size", "files"),
]
SUPP_ZIP_MUST = [("FAIL", "home path in the supplementary material", "code.zip!/eval/run.sh:1"),
                 ("CHECK", "macOS metadata in the supplementary material", "__MACOSX")]
SECRET_KINDS = ("credentials file", "possible secret", "secret in the", "macOS metadata", "supplementary material size")


def run_json(folder, args):
    out = subprocess.run([sys.executable, "-I", str(SCRIPT), "main.tex", "--json", "--offline", "--no-widows", *args],
                         cwd=folder, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr[-2000:])
    return json.loads(out.stdout)


def supp_tests():
    failed = 0
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        subprocess.run([sys.executable, "-I", str(FIX / "supp" / "make_supp.py"), str(td)], check=True)
        for f in ("main.tex", "names.txt"):
            shutil.copy(FIX / "supp" / f, td / f)
        base = ["--authors", "names.txt"]
        for name, args, must in (("supp folder", ["--blind", "double", "--supp", "dirty"], SUPP_MUST),
                                 ("supp zip", ["--blind", "double", "--supp", "dirty.zip"], SUPP_MUST + SUPP_ZIP_MUST)):
            res = run_json(td, base + args)
            fs = [f for f in res["findings"] if "supplementary" in f["kind"]]
            bad = [f"missing {m}" for m in must if not any(match(f, *m) for f in fs)]
            known = {(m[0], m[1]) for m in must}
            bad += [f"unexpected {f['sev']} {f['kind']} {f['where']}" for f in fs if (f["sev"], f["kind"]) not in known]
            bad += [f"secret printed: {f['quote']}" for f in fs if "FAKEFAKE" in f["quote"] or "a1b2c3d4" in f["quote"]]
            if res["coverage"].get("supp_files", 0) < 11:
                bad.append(f"coverage {res['coverage']}")
            print(("PASS " if not bad else "FAIL ") + name + ("" if not bad else ": " + "; ".join(bad)))
            failed += bool(bad)
        res = run_json(td, base + ["--blind", "double", "--supp", "clean"])
        bad = [f"{f['sev']} {f['kind']} {f['where']}" for f in res["findings"]
               if "supplementary" in f["kind"] and f["sev"] != "INFO"]
        bad += [] if res["coverage"].get("supp_files") == 6 else [f"coverage {res['coverage']}"]
        print(("PASS " if not bad else "FAIL ") + "supp clean" + ("" if not bad else ": " + "; ".join(bad)))
        failed += bool(bad)
        res = run_json(td, base + ["--blind", "single", "--supp", "dirty.zip"])
        fs = [f for f in res["findings"] if "supplementary" in f["kind"]]
        bad = [f"anonymity finding with --blind single: {f['kind']}" for f in fs
               if not any(k in f["kind"] for k in SECRET_KINDS)]
        bad += [f"missing {m}" for m in SUPP_MUST if m[1].startswith(("credentials", "possible secret"))
                and not any(match(f, *m) for f in fs)]
        print(("PASS " if not bad else "FAIL ") + "supp single-blind" + ("" if not bad else ": " + "; ".join(bad)))
        failed += bool(bad)
    return failed


def engine_test():
    """fontspec paper: the widow/orphan build detects xelatex; forced pdflatex produces no pages (and says so)."""
    if not shutil.which("xelatex"):
        print("SKIP engine detection: xelatex not found")
        return 0
    folder = FIX / "engine-fontspec"
    nopages = "produced no pages"
    auto = subprocess.run([sys.executable, "-I", str(SCRIPT), "main.tex", "--json", "--offline"], cwd=folder,
                          capture_output=True, text=True)
    forced = subprocess.run([sys.executable, "-I", str(SCRIPT), "main.tex", "--json", "--offline", "--engine",
                             "pdflatex"], cwd=folder, capture_output=True, text=True)
    sa, sf = (json.loads(r.stdout)["skipped"] for r in (auto, forced))
    ok = (not any("widows" in s for s in sa)) and any(nopages in s for s in sf)
    print(("PASS " if ok else "FAIL ") + "engine detection (fontspec -> xelatex)" + ("" if ok else f": {sa} / {sf}"))
    return 0 if ok else 1


def main():
    exp = json.loads((FIX / "expectations.json").read_text())
    failed = 0
    for name, e in exp.items():
        if name.startswith("_"):
            continue
        try:
            fs = findings(FIX / e.get("dir", name), e["args"])
        except RuntimeError as err:
            print(f"ERROR {name}: {err}")
            failed += 1
            continue
        bad = [f"missing {m}" for m in e["must"] if not any(match(f, *m) for f in fs)]
        bad += [f"unexpected {m}" for m in e["must_not"] if any(match(f, *m) for f in fs)]
        allowed = HYGIENE_HITS.get(e.get("dir", name), ())
        bad += [f"hygiene false positive: {f['kind']} {f['where']}" for f in fs
                if f["kind"] in HYGIENE_KINDS and f["kind"] not in allowed]
        print(("PASS " if not bad else "FAIL ") + name + ("" if not bad else ": " + "; ".join(bad)))
        failed += bool(bad)
    # the COVERAGE counts (what was read and tested): present and measured on a compiled fixture
    folder = FIX / "source-hygiene"
    out = subprocess.run([sys.executable, "-I", str(SCRIPT), "main.tex", "--json", "--offline"], cwd=folder,
                         capture_output=True, text=True)
    cov = json.loads(out.stdout).get("coverage", {})
    text = subprocess.run([sys.executable, "-I", str(SCRIPT), "main.tex", "--facts", "--offline"], cwd=folder,
                          capture_output=True, text=True).stdout.strip().split("\n")
    ok = (cov.get("pages", 0) >= 1 and cov.get("words", 0) > 0 and cov.get("source_lines", 0) > 0
          and "links_tested" not in cov and text[-1].startswith("COVERAGE | pages="))
    print(("PASS " if ok else "FAIL ") + "coverage counts" + ("" if ok else f": {cov} / {text[-1]}"))
    failed += not ok
    failed += supp_tests()
    failed += engine_test()
    print(f"{failed} fixture(s) failing")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
