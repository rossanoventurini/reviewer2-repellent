#!/usr/bin/env python3
"""Tests of scripts/bib_status.py (the data of the "Bibliography" front page) on a synthetic run (invented entries).

Run: python3 -I evals/tests/test_bib_status.py
"""
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "reviewer2-repellent" / "scripts" / "bib_status.py"

BIB = r"""@string{tbd = {IEEE Transactions on Big Data}}
@article{wombat_gpu, author = {Ann Smith and Bo Li}, title = {Wombat Search with {GPUs}}, journal = tbd,
  year = {2019}, volume = {7}}
@inproceedings{fastann, author = {Cy Doe}, title = {Fast {ANN}}, booktitle = {Proceedings of SIGIR}, year = {2020},
  doi = {10.1145/1234567.7654321}}
@misc{wombat_arxiv, author = {Di Roe}, title = {Wombats on arXiv}, journal = {CoRR}, year = {2023},
  eprint = {2301.01234}, archiveprefix = {arXiv}}
@misc{blogpost, author = {Ed Poe}, title = {A Blog Post About Wombats}, howpublished = {\url{https://example.org}},
  year = {2024}}
@inproceedings{okentry, author = {Fa Moe}, title = {Correct Entry}, booktitle = {Proc. ICDE}, year = {2021},
  doi = {10.1109/ICDE.2021.0001}}
@article{uncited, author = {Ga Zoe}, title = {Never Cited}, journal = {J}, year = {2000}}
"""

REFS = """CHECK | bib differs from the database record | wombat_gpu | "year: Year mismatch: cited: 2019 actual: 2021" | quote both
INFO | RefChecker | "5 references, 1 errors, 0 warnings, 1 unverified"
INFO | not found in the reference databases | blogpost | "unverified: Paper not found by any checker" | look the title up
CHECK | published version of a preprint in DBLP | wombat_arxiv | "published at SIGIR 2024" | cite the published version
SUMMARY | FAIL 0 | CHECK 2 | INFO 2
SKIPPED | arXiv ID check: arXiv API unreachable for 1 IDs (HTTPError): 2301.01234
COVERAGE | references=5 | refchecker_checked=5 | arxiv_ids=1 | arxiv_looked_up=0 | dois=2 | dois_looked_up=2 | preprints=1 | preprints_dblp_db=1
"""

STYLE = """INFO | bibliography style | 5 cited entries from references.bib
CHECK | style differs | @inproceedings: field 'doi' | majority present (2/2) | absent: none_here
CHECK | style differs | booktitle (inproceedings): abbreviated | majority full words (1/2) | abbreviated: okentry
CHECK | style differs | @article: field 'volume' | majority absent (3/4) | present: wombat_gpu, okentry, fastann, wombat_arx …
COVERAGE | entries_compared=5 | features=12 | venues_compared=2 | differences=3
"""

AUX = "\\relax\n\\citation{wombat_gpu,fastann}\n\\citation{wombat_arxiv}\n\\citation{blogpost}\n\\citation{okentry}\n"

REPORT = """# Report

## 1. Summary

Total 3 items.

## 6. Cosmetic

**7.** `references.bib` `wombat_gpu`: the year is 2021 (DBLP). Checkers: reader.

**8.** `references.bib` entry `wombat_arxiv` is a preprint; the published version is at SIGIR 2024. Checkers: reader.

**9.** `sections/intro.tex:3`: the `fastann` system is run twice. Checkers: numbers.
"""

BBL_ORIG = r"""\begin{thebibliography}{5}
\bibitem{wombat_gpu} A. Smith and B. Li. Wombat search with GPUs. IEEE TBD, 7, 2019.
\bibitem{fastann} C. Doe. Fast ANN. In Proceedings of SIGIR, 2020.
\bibitem{wombat_arxiv} D. Roe. Wombats on arXiv. CoRR, 2023.
\bibitem{blogpost} E. Poe. A blog post about wombats, 2024.
\bibitem{okentry} F. Moe. Correct entry. In Proc. ICDE, 2021.
\end{thebibliography}
"""
BBL_CORR = BBL_ORIG.replace("7, 2019.", "7, 2021.").replace("CoRR, 2023.", "In Proceedings of SIGIR, 2024.")

MAP = {"default": {"wombat_gpu": 7}, "rules": {"wombat_arxiv": [["SIGIR", 8]]}, "notes": {"7": "Year.", "8": "Pub."}}


def make_run(tmp, refs=True, style=True, facts_only=False):
    out = tmp / "run"
    w = out / "work"
    (w / "paper").mkdir(parents=True)
    (w / "paper" / "main.tex").write_text("\\documentclass{article}\\begin{document}x\\bibliography{references}"
                                          "\\end{document}\n")
    (w / "paper" / "references.bib").write_text(BIB)
    (w / "build").mkdir()
    (w / "build" / "main.aux").write_text(AUX)
    for b, t in (("build-original", BBL_ORIG), ("build-corrected", BBL_CORR)):
        (w / "tmp" / b).mkdir(parents=True)
        (w / "tmp" / b / "main.bbl").write_text(t)
    (w / "tmp" / "bbl-map.json").write_text(json.dumps(MAP))
    (out / "report.md").write_text(REPORT)
    if facts_only:
        (w / "facts.txt").write_text("## refs_check\n" + REFS + "\n## bib_style\n" + STYLE)
    else:
        if refs:
            (w / "refs_check.out").write_text(REFS)
        if style:
            (w / "bib_style.out").write_text(STYLE)
    return out


def run_script(out, *extra):
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(out), *map(str, extra)], capture_output=True, text=True)
    return r


class BibStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="bibstatus-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def status(self, **kw):
        out = make_run(self.tmp, **kw)
        r = run_script(out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads((out / "work" / "bib-status.json").read_text())

    def test_counts(self):
        d = self.status()
        c = d["counts"]
        self.assertEqual(c["cited"], 5)                          # from the .aux; `uncited` is left out
        self.assertEqual(c["bib_entries"], 6)
        for k, v in (("refchecker_checked", 5), ("differs", 1), ("not_found", 1), ("dois", 2), ("dois_looked_up", 2),
                     ("arxiv_ids", 1), ("arxiv_looked_up", 0), ("preprints", 1), ("preprints_checked", 1),
                     ("refchecker_errors", 1), ("refchecker_unverified", 1), ("style_entries", 5),
                     ("style_features", 12), ("style_differences", 3), ("changed_in_copy", 2)):
            self.assertEqual(c[k], v, k)
        self.assertEqual(d["skipped"], ["arXiv ID check: arXiv API unreachable for 1 IDs (HTTPError)"])
        self.assertEqual([e["key"] for e in d["entries"]], ["blogpost", "fastann", "okentry", "wombat_arxiv",
                                                           "wombat_gpu"])
        self.assertEqual(d["notes"], [])

    def test_entries(self):
        e = {x["key"]: x for x in self.status()["entries"]}
        g = e["wombat_gpu"]
        self.assertEqual((g["db"], g["db_detail"]), ("differs", "year: cited 2019; database 2021"))
        self.assertEqual((g["type"], g["year"], g["changed"], g["items"]), ("article", "2019", True, [7]))
        self.assertEqual(g["title"], "Wombat Search with GPUs")
        self.assertEqual((e["blogpost"]["db"], e["blogpost"]["db_detail"]),
                         ("not_found", "Paper not found by any checker"))
        a = e["wombat_arxiv"]
        self.assertEqual((a["db"], a["arxiv"], a["arxiv_checked"], a["preprint"], a["preprint_checked"]),
                         ("matched", ["2301.01234"], False, True, True))
        self.assertEqual(a["findings"][0]["kind"], "published version of a preprint in DBLP")
        self.assertEqual((a["changed"], a["items"]), (True, [8]))
        f = e["fastann"]
        self.assertEqual((f["db"], f["doi"], f["doi_checked"], f["changed"]),
                         ("matched", "10.1145/1234567.7654321", True, False))
        self.assertEqual(f["items"], [])                           # item 9 names it, but is not about the entry
        self.assertIsNone(e["okentry"]["arxiv_checked"])
        # style: the keys named in full; the key cut by the shortened line is not attributed
        self.assertEqual(e["okentry"]["style"], ["booktitle (inproceedings): abbreviated: abbreviated; majority full "
                                                 "words (1/2)", "@article: field 'volume': present; majority absent "
                                                 "(3/4)"])
        self.assertEqual(e["wombat_arxiv"]["style"], [])

    def test_from_facts(self):
        d = self.status(facts_only=True)
        self.assertEqual(d["inputs"]["refs_check"], "work/facts.txt (## refs_check)")
        self.assertEqual(d["counts"]["differs"], 1)

    def test_missing_inputs_are_left_out(self):
        d = self.status(refs=False, style=False)
        for k in ("differs", "not_found", "dois", "refchecker_checked", "style_entries", "style_flagged_entries"):
            self.assertNotIn(k, d["counts"], k)
        self.assertTrue(any("no refs_check output" in n for n in d["notes"]))
        self.assertTrue(any("no bib_style output" in n for n in d["notes"]))
        self.assertEqual({x["db"] for x in d["entries"]}, {"not_checked"})
        self.assertEqual({x["doi_checked"] for x in d["entries"]}, {None})

    def test_short_detail(self):
        spec = importlib.util.spec_from_file_location("bib_status", SCRIPT)
        bs = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(SCRIPT.parent))
        spec.loader.exec_module(bs)
        self.assertEqual(bs.short_detail("author: Author count mismatch: 2 cited vs 3 correct: cited: A, B actual: "
                                         "A, B, C"), "author: 2 cited vs 3 in the database: cited A, B; database A, "
                                                     "B, C")
        cut = "author: Author mismatch: cited: " + ", ".join("Name%d" % i for i in range(30))
        t = bs.short_detail(cut)
        self.assertTrue(t.endswith("(cut short in the refs_check output)"), t)
        self.assertNotIn("Name2 (", t)


class ParseArtefacts(unittest.TestCase):
    """A database "difference" that is only a parsing artefact is no flag (the bibliography page hides its row)."""

    def test_parse_artefact(self):
        spec = importlib.util.spec_from_file_location("bib_status", SCRIPT)
        sys.path.insert(0, str(SCRIPT.parent))
        bs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bs)
        yes = ["title: cited C}ol{BERT}: Efficient and Effective Passage Search; database ColBERT",
               "doi: cited 10.1007/978-3-642-41062-8\\_28; database 10.1007/978-3-642-41062-8_28",
               "title: cited {PLAID}: An Efficient Engine for Late Interaction Retrieval; database PLAID"]
        no = ["year: cited 1989; database 2009", "author: cited Wang, Zihao; database hhy3 (hhy3)",
              "title: cited {PLAID}: An Engine; database PLAID | year: cited 2020; database 2022", ""]
        for d in yes:
            self.assertTrue(bs.parse_artefact(d), d)
        for d in no:
            self.assertFalse(bs.parse_artefact(d), d)


if __name__ == "__main__":
    unittest.main(verbosity=2)
