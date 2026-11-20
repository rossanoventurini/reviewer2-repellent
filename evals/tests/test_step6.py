#!/usr/bin/env python3
"""Tests of the step-6 scripts: apply_edits.py (corrected and marked copies), mark_bbl.py (marked bibliography),
assets/r2changes.sty (margin boxes, links, check boxes), check_notes.py, front_pages.py and the driver
build_changes.py, ai_traces.py with the "Traces of AI use" page, and check_stats.py with the "What we checked" page,
on the synthetic fixtures in evals/fixtures/step6/
(invented text and references; run/ is an output folder of a whole run; ai/ holds invented facts and a paper for the
style measurements).

Run: python3 -I evals/tests/test_step6.py      (compile tests are skipped if pdflatex is missing)
"""
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "evals" / "fixtures" / "step6"
SKILL = ROOT / "skills" / "reviewer2-repellent"
APPLY = SKILL / "scripts" / "apply_edits.py"
MARK_BBL = SKILL / "scripts" / "mark_bbl.py"
CHECK_NOTES = SKILL / "scripts" / "check_notes.py"
FRONT = SKILL / "scripts" / "front_pages.py"
BUILD = SKILL / "scripts" / "build_changes.py"
# where the user finds the output folder (the tests build in temporary folders; the summary page must not name them)
FINAL = "/Users/author/paper/reviewer2-repellent/2026-11-10"
TRACES = SKILL / "scripts" / "ai_traces.py"
STATS = SKILL / "scripts" / "check_stats.py"
BIB_STYLE = SKILL / "scripts" / "bib_style.py"
STY = SKILL / "assets" / "r2changes.sty"
HAVE_TEX = shutil.which("pdflatex") is not None
HAVE_LATEXMK = HAVE_TEX and shutil.which("latexmk") is not None and shutil.which("pdfinfo") is not None


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AE = load(APPLY, "apply_edits")
MB = load(MARK_BBL, "mark_bbl")
CN = load(CHECK_NOTES, "check_notes")


def pdf_objects(path):
    """The PDF's bytes plus every Flate stream inflated (object streams hold the annotations)."""
    import zlib
    d = pathlib.Path(path).read_bytes()
    parts = [d]
    for m in re.finditer(rb"stream\r?\n", d):
        try:
            parts.append(zlib.decompressobj().decompress(d[m.end():]))
        except zlib.error:
            pass
    return b"\n".join(parts)


def split_pages(tex):
    """{page id: its LaTeX} of the front pages written by front_pages.py (one \\begin{rrfullpage}[id] each)."""
    parts = re.split(r"\\begin\{rrfullpage\}\[([\w-]+)\]", tex)
    return dict(zip(parts[1::2], parts[2::2]))


def run(*args):
    return subprocess.run([sys.executable, "-I", *map(str, args)], capture_output=True, text=True)


def pdflatex(folder, main="main.tex", runs=2):
    for _ in range(runs):
        subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", main],
                       cwd=folder, capture_output=True)
    log = (pathlib.Path(folder) / main).with_suffix(".log").read_text(encoding="latin-1")
    return [ln for ln in log.splitlines() if ln.startswith("!")], log


class ApplyEdits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="step6-"))
        cls.c, cls.m, cls.log = cls.tmp / "corrected", cls.tmp / "marked", cls.tmp / "edits.tsv"
        cls.res = run(APPLY, FIX / "spec.json", FIX / "paper", cls.c, cls.m, "--log", cls.log)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def read(self, root, f):
        return (root / f).read_text(encoding="utf-8")

    def test_runs(self):
        self.assertEqual(self.res.returncode, 0, self.res.stderr)

    def test_every_kind(self):
        ci, mi = self.read(self.c, "sections/intro.tex"), self.read(self.m, "sections/intro.tex")
        cr, mr = self.read(self.c, "sections/results.tex"), self.read(self.m, "sections/results.tex")
        cm, mm = self.read(self.c, "main.tex"), self.read(self.m, "main.tex")
        # fix, check, style, insertion, deletion, raw
        self.assertIn("is an old problem", ci)
        self.assertIn(r"\rrfix{1}{a old}{an old}", mi)
        self.assertIn(r"\rrcheck{3}{$2.3\times$}{$2.4\times$}{Is it 2.3 or 2.4? Table\_1 gives $s_1 = 2.4$.}", mi)
        self.assertIn(r"\rrstyle{4}{three encoder}{three encoders}", mi)
        self.assertIn(r"resident set size\rrstyle{15}{}{ (RSS)}", mr)
        self.assertIn("on every collection.\n", cr)
        self.assertIn("\\rrfix{13}{ and the gap grows with the\ncollection size}{}", mr)
        self.assertEqual(cr.count("}[tbp]"), 2)
        self.assertEqual(mr.count("}[tbp]"), 2)
        # plain variants
        self.assertIn(r"\rrfixplain{7}{best values in bold}", mr)
        self.assertIn(r"\rrcheckplain{8}{1.09}{", mr)
        self.assertIn(r"\title{Fast Wombat Search for Nearest \rrfixplain{10}{Neighbor}}", mm)
        self.assertIn(r"\title{Fast Wombat Search for Nearest Neighbor}", cm)
        # missing -> placeholder in the marked copy, TODO comment in the corrected copy
        self.assertIn(r"\rrmissing{5}{number of threads and core\_count}", mi)
        self.assertIn("Burrows are scanned in parallel. % TODO #5: number of threads and core_count\n", ci)
        # the corrected copy carries no mark at all
        for f in ("main.tex", "sections/intro.tex", "sections/results.tex"):
            self.assertNotIn(r"\rr", self.read(self.c, f))
        self.assertNotIn("r2changes", cm)

    def test_notes(self):
        raw = {f: self.read(self.m, f) for f in ("sections/intro.tex", "sections/results.tex", "main.tex")}
        # every note carries the location of its change in the corrected copy, which holds the changed text
        locs = re.findall(r"\\rrnote\[corrected/([^:\]]+):(\d+)\]\{(\d+)\}", "".join(raw.values()))
        self.assertEqual(len(locs), 10)
        self.assertIn(("sections/intro.tex", "4", "2"), locs)
        self.assertIn(("sections/results.tex", "20", "8"), locs)
        for f, line, it in locs:
            self.assertGreaterEqual(len(self.read(self.c, f).split("\n")), int(line))
        self.assertIn("1.09", self.read(self.c, "sections/results.tex").split("\n")[19])
        mi, mr, mm = (re.sub(r"\\rrnote\[[^\]]*\]", r"\\rrnote", raw[f])
                      for f in ("sections/intro.tex", "sections/results.tex", "main.tex"))
        allm = mi + mr + mm
        # one note per item, merged (item 2 has two edits with the same note)
        for it in (2, 3, 6, 7, 8, 9, 10, 11, 12, 14):
            self.assertEqual(allm.count(r"\rrnote{%d}{" % it), 1, it)
        for it in (1, 4, 5, 13, 15, 16):
            self.assertNotIn(r"\rrnote{%d}{" % it, allm)
        # end of the sentence; after the float / equation; outside the footnote; at note_ctx
        self.assertIn(r"we follow the same approach.\rrnote{2}{", mi)
        self.assertIn(r"less memory.\rrnote{3}{To check: Is it 2.3", mi)
        self.assertIn(r"three encoders}.\rrnote{9}{", mi)
        self.assertIn("\\end{table}\\rrnote{7}{", mr)
        self.assertIn("\\end{equation}\\rrnote{8}{To check: 1200/1100", mr)
        self.assertIn("\\end{figure}\\rrnote{14}{To check: Does the figure", mr)
        self.assertIn(r"memory in GiB.\rrnote{6}{QPS\_avg is the mean over 3 runs.}", mi)
        self.assertIn(r"a library for wombat search.\rrnote{10}{", mm)
        self.assertIn(r"every system\rrnote{11}{Floats may go on float pages: [t] $\to$ [tbp].}", mr)
        # prose escaping, not in math, not in \ref, not twice
        self.assertIn(r"Counted in results\_v2.csv: 3 \& more, 50\% of them; see \#4 and \ref{sec:results_x}.", mi)
        self.assertIn(r"$s_1 = 2.4$", mi)
        # no note inside a float, table, caption, footnote, math or verbatim
        for f in ("main.tex", "sections/intro.tex", "sections/results.tex"):
            t = self.read(self.m, f)
            frames = AE.frames_of(t)
            for mt in re.finditer(r"\\rrnote\{", t):
                bad = [fr for fr in AE.enclosing(frames, mt.start()) if AE.is_forbidden(fr)]
                self.assertEqual(bad, [], (f, t[mt.start() - 40:mt.start() + 20]))

    def test_preamble_and_sty(self):
        mm = self.read(self.m, "main.tex")
        self.assertIn("\\usepackage{r2changes}\n\\begin{document}", mm)
        self.assertEqual((self.m / "r2changes.sty").read_bytes(), STY.read_bytes())
        self.assertFalse((self.c / "r2changes.sty").exists())

    def test_log(self):
        rows = [ln.split("\t") for ln in self.log.read_text().splitlines()]
        self.assertEqual(rows[0], ["item", "kind", "file", "line", "status", "question", "what"])
        self.assertEqual(rows[4][5], "Is it 2.3 or 2.4? Table_1 gives $s_1 = 2.4$.")
        self.assertEqual(rows[6][6], "number of threads and core_count")
        rows = [r[:5] for r in rows]
        spec = json.loads((FIX / "spec.json").read_text())
        self.assertEqual(len(rows) - 1, len(spec))
        byitem = {r[0]: r for r in rows[1:]}
        self.assertEqual(byitem["1"], ["1", "fix", "sections/intro.tex", "4", "applied"])
        self.assertEqual(byitem["3"][4], "to check")
        self.assertEqual(byitem["4"][4], "not chosen (default: don't -- optional wording)")   # box pre-set off
        self.assertEqual(byitem["5"][3:], ["11", "missing facts"])
        self.assertEqual(byitem["17"], ["17", "log", "", "", "not applied (needs a new experiment)"])
        # the line numbers point at the new text in the corrected copy
        lines = self.read(self.c, "sections/results.tex").split("\n")
        self.assertIn("1.09", lines[int(byitem["8"][3]) - 1])
        self.assertIn("$0.9$", lines[int(byitem["16"][3]) - 1])

    def test_deterministic(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="step6b-"))
        try:
            r = run(APPLY, FIX / "spec.json", FIX / "paper", tmp / "c", tmp / "m", "--log", tmp / "log.tsv")
            self.assertEqual(r.returncode, 0, r.stderr)
            for root, other in ((tmp / "c", self.c), (tmp / "m", self.m)):
                for p in sorted(root.rglob("*")):
                    if p.is_file():
                        self.assertEqual(p.read_bytes(), (other / p.relative_to(root)).read_bytes(), p)
            self.assertEqual((tmp / "log.tsv").read_bytes(), self.log.read_bytes())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_refuses_existing_output(self):
        r = run(APPLY, FIX / "spec.json", FIX / "paper", self.c, self.tmp / "other")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not empty", r.stderr)

    @unittest.skipUnless(HAVE_TEX, "pdflatex not installed")
    def test_compile(self):
        for root in (self.c, self.m):
            work = pathlib.Path(tempfile.mkdtemp(prefix="step6tex-"))
            try:
                shutil.copytree(root, work / "p")
                errs, log = pdflatex(work / "p")
                self.assertEqual(errs, [], (root.name, errs))
                self.assertTrue((work / "p" / "main.pdf").is_file())
            finally:
                shutil.rmtree(work, ignore_errors=True)


class ApplyEditsErrors(unittest.TestCase):
    def test_errors_listed_nothing_written(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="step6e-"))
        try:
            r = run(APPLY, FIX / "bad-spec.json", FIX / "paper", tmp / "c", tmp / "m")
            self.assertEqual(r.returncode, 1)
            self.assertFalse((tmp / "c").exists() or (tmp / "m").exists())
            err = r.stderr
            expect = {1: "context found 4 times", 2: "context found 0 times", 3: "old not inside ctx",
                      4: "check without question", 5: "unbalanced braces in a mark",
                      7: "overlaps the text changed by edit 6", 8: "bare % (comment) in a mark",
                      9: "unbalanced braces in a mark", 10: "file not found", 11: "mark inside math"}
            for it, msg in expect.items():
                self.assertRegex(err, r"item #%d, [^\n]*%s" % (it, re.escape(msg)), it)
            self.assertNotIn("  edit 6 (", err)
            self.assertIn("ERRORS (10)", err)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_edit_inside_raw_and_todo_kept_last(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="step6f-"))
        spec = [
            {"item": 1, "file": "sections/intro.tex", "kind": "missing", "ctx": "memory in GiB.", "what": "units"},
            {"item": 2, "file": "sections/intro.tex", "kind": "fix", "old": "", "new": " (binary)",
             "ctx": "memory in GiB@@."},
            {"item": 3, "file": "sections/intro.tex", "kind": "raw", "old": "Burrows are scanned in parallel.",
             "new": "Burrows are scanned in parallel by many threads.", "mark": r"\rrfixplain{3}{Burrows are scanned in parallel by many threads.}"},
            {"item": 4, "file": "sections/intro.tex", "kind": "style", "old": "many", "new": "several",
             "ctx": "by many threads"},
        ]
        try:
            (tmp / "spec.json").write_text(json.dumps(spec))
            r = run(APPLY, tmp / "spec.json", FIX / "paper", tmp / "c", tmp / "m")
            self.assertEqual(r.returncode, 0, r.stderr)
            c = (tmp / "c" / "sections/intro.tex").read_text()
            m = (tmp / "m" / "sections/intro.tex").read_text()
            self.assertIn("memory in GiB (binary). % TODO #1: units\n", c)
            self.assertIn(r"GiB\rrfix{2}{}{ (binary)}. \rrmissing{1}{units}", m)
            self.assertIn("scanned in parallel by many threads.", c)     # #4 is optional wording: not chosen
            self.assertIn(r"\rrfixplain{3}{Burrows are scanned in parallel by \rrstyle{4}{many}{several} threads.}", m)
            r = run(APPLY, tmp / "spec.json", FIX / "paper", tmp / "c", tmp / "m", "--force", "--only", "3,4")
            self.assertEqual(r.returncode, 0, r.stderr)
            c = (tmp / "c" / "sections/intro.tex").read_text()
            self.assertIn("scanned in parallel by several threads.", c)
            self.assertNotIn("(binary)", c)                                # #2 not in --only
            self.assertIn("% TODO #1: units", c)                            # facts placeholders always kept
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_escape(self):
        self.assertEqual(AE.esc_prose(r"a_b \_ 50% \% #1 & \& $x_1$ \ref{a_b}"),
                         r"a\_b \_ 50\% \% \#1 \& \& $x_1$ \ref{a_b}")


class MarkBbl(unittest.TestCase):
    def mark(self, kind, cfg=None, words=False, extra=()):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="step6bbl-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        mp = FIX / "bbl" / "map.json"
        if cfg is not None:
            mp = tmp / "map.json"
            mp.write_text(json.dumps(cfg))
        r = run(MARK_BBL, FIX / "bbl" / ("%s-orig.bbl" % kind), FIX / "bbl" / ("%s-corr.bbl" % kind),
                tmp / "main.bbl", mp, *([] if words else ["--whole-spans"]), *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return tmp, (tmp / "main.bbl").read_text(encoding="utf-8"), r

    def entry(self, text, key):
        m = re.search(r"\\bibitem(\[[^\n]*\])?\{%s\}(.*?)(?=\n\\bibitem|\n\\item|\n\\end\{thebib)" % key, text, re.S)
        return m.group(0)

    def check_common(self, t):
        w = self.entry(t, "wombat2020")
        # the change inside \emph{...} is widened to the whole balanced group, not the whole entry
        self.assertIn(r"\rrfix{31}{\emph{Proceedings of the Wombat Conference},}"
                      r"{\emph{Proceedings of the 3rd Wombat Conference ({WOMCON})},}", w)
        self.assertIn("\nAda Burrow and Ben Digger. \\newblock Fast wombat search. \\newblock In \\rrfix", w)
        self.assertIn(r"\rrfix{32}{}{\newblock \doi{10.9999/wombat_2020.1}.}", w)
        for line in t.split("\n"):                       # every entry line (and so every mark) balances
            self.assertTrue(MB.balanced([line]), line)
        # removed duplicate, struck out after the entry that replaces it
        self.assertRegex(t, r"\\item\[\\rrold\{\[3\]\}\]\\rrnote\{38\}\{Duplicate of quokka2019: merged.\}\\rrfix\{38\}\{")
        self.assertIn(r"merged} \mbox{into}~\cite{quokka2019})", t)
        # new entry
        self.assertIn("{burrow2024}\\rrnote{37}{Cited in Section 2 but missing from the bibliography.}\n\\rrfix{37}{}{Fay Tunnel.", t)
        # escaped notes
        self.assertIn(r"\rrnote{32}{DOI 10.9999/wombat\_2020.1 added (invented record\_id 42).}", t)
        self.assertIn(r"\rrnote{34}{Year 2017 $\to$ 2018 \& URL updated: 100\% of the PDF \#2 matches.}", t)
        # multi-item entry: every listed item gets its note there, the spans follow the precedence
        n = self.entry(t, "numbat2018")
        for it in (33, 34, 35, 36):
            self.assertIn(r"\rrnote{%d}{" % it, n.split("\n")[0], it)
        self.assertIn(r"\rrfix{33}{indexes for sparse vectors.}{Indexes for Sparse Vectors.}", n)
        self.assertIn(r"\rrfix{34}{2017.", n)
        # unchanged entries are untouched; one note per item
        self.assertNotIn(r"\rr", self.entry(t, "echidna2021"))
        for it in range(31, 39):
            self.assertEqual(t.count(r"\rrnote{%d}{" % it), 1, it)

    def test_plain(self):
        tmp, t, r = self.mark("plain")
        self.check_common(t)
        self.assertIn("\\bibitem{wombat2020}\\rrnote{31}", t)
        self.compile(tmp, natbib=False)

    def test_natbib(self):
        tmp, t, r = self.mark("natbib")
        self.check_common(t)
        self.assertIn("\\bibitem[Burrow and Digger(2020)]{wombat2020}\\rrnote{31}", t)
        self.assertIn("\\bibitem[{Hopper(2019{\\natexlab{a}})}]{quokka2019}\n", t)
        self.assertIn("\\bibitem[{Termite(2018)}]{numbat2018}", t)
        self.compile(tmp, natbib=True)

    def test_precedence(self):
        cfg = json.loads((FIX / "bbl" / "map.json").read_text())
        cfg["default"].pop("numbat2018")
        cfg["case_keys"] = ["numbat2018"]
        tmp, t, r = self.mark("plain", cfg)
        # without a per-entry default, a capitals-only change gets case_item; the rule still wins on its span
        self.assertIn(r"\rrfix{35}{indexes for sparse vectors.}{Indexes for Sparse Vectors.}", t)
        self.assertIn(r"\rrfix{34}{2017.", t)

    def test_unmatched_reported(self):
        cfg = json.loads((FIX / "bbl" / "map.json").read_text())
        del cfg["new"], cfg["removed"]
        tmp, t, r = self.mark("plain", cfg)
        self.assertIn("UNMATCHED corrected entries", r.stderr)
        self.assertIn("burrow2024 (item 30)", r.stderr)
        self.assertIn("UNMATCHED original entries", r.stderr)
        self.assertIn("quokka2019dup", r.stderr)
        self.assertIn(r"\rrfix{30}{}{Fay Tunnel.", t)

    def test_note_without_changed_span(self):
        cfg = json.loads((FIX / "bbl" / "map.json").read_text())
        cfg["notes"].update({"39": "Comment lines removed from the .bib.", "40": "Key tidied.", "41": "Listed."})
        cfg["rules"]["numbat2018"].append(["zzz-never", 40])
        cfg["items"]["echidna2021"] = [41]
        cfg["notes_short"] = {"39": "Comments removed."}
        tmp, t, r = self.mark("plain", cfg)
        # no entry names it: right before the first \\bibitem, inside the bibliography; short text with the pointer
        head = t[:t.index("\\bibitem")]
        self.assertIn("\\begin{thebibliography}", head)
        self.assertIn(r"\rrnotepair{39}{Comment lines removed from the .bib.}{Comments removed. See report \#39.}",
                      head)
        # named by a rule (or default) of an entry: at that entry; listed in "items": at the listed entry
        self.assertIn(r"\rrnote{40}{Key tidied.}", self.entry(t, "numbat2018"))
        self.assertIn(r"\rrnote{41}{Listed.}", self.entry(t, "echidna2021"))
        self.assertIn("item 39: no changed span and no entry names it", r.stderr)
        self.assertIn("item 40: no changed span: note placed at entry numbat2018", r.stderr)
        self.assertNotIn("notes never placed", r.stderr)
        self.compile(tmp, natbib=False)
        tmp, t, r = self.mark("natbib", cfg)
        self.compile(tmp, natbib=True)
        res = CN.check(CN.read_aux(tmp / "main.aux"))
        self.assertEqual(res["off_page"], [])
        self.assertEqual(res["notes"], 11)

    def test_widen(self):
        o = r"In \emph{Proceedings of the Wombat Conference}, 2020.".split()
        n = r"In \emph{Proceedings of the Wombat Conference (WOMCON)}, 2020.".split()
        spans = MB.widen([[5, 6, 5, 7]], o, n)
        self.assertEqual(spans, [[1, 6, 1, 7]])
        self.assertTrue(MB.balanced(o[1:6]) and MB.balanced(n[1:7]))

    def compile(self, tmp, natbib):
        if not HAVE_TEX:
            self.skipTest("pdflatex not installed")
        main = (FIX / "bbl" / "main.tex").read_text().replace("%NATBIB%", r"\usepackage{natbib}" if natbib else "")
        (tmp / "main.tex").write_text(main)
        shutil.copyfile(STY, tmp / "r2changes.sty")
        errs, log = pdflatex(tmp)
        self.assertEqual(errs, [], errs)
        self.assertNotIn("Citation `", log)


class MarkBblWords(unittest.TestCase):
    """Word-level marks (the default) and note locations from the corrected .bib."""

    def test_words_and_locations(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="step6bw-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        bib = tmp / "refs.bib"
        bib.write_text("% invented\n@inproceedings{wombat2020,\n title={x}}\n\n@techreport{numbat2018,\n title={y}}\n"
                       "@article{quokka2019,\n title={z}}\n")
        r = run(MARK_BBL, FIX / "bbl" / "plain-orig.bbl", FIX / "bbl" / "plain-corr.bbl", tmp / "main.bbl",
                FIX / "bbl" / "map.json", "--bib", bib, "--bib-name", "corrected/refs.bib")
        self.assertEqual(r.returncode, 0, r.stderr)
        t = (tmp / "main.bbl").read_text()
        # unchanged words stay plain, \emph spread over words; only the changed runs are marked
        self.assertIn(r"In \emph{Proceedings} \emph{of} \emph{the} \rrfix{31}{}{\emph{3rd}} \emph{Wombat}", t)
        # every struck-out word in its own \mbox, so the struck text can break
        self.assertIn(r"\rrfix{33}{\mbox{indexes} \mbox{for} \mbox{sparse} \mbox{vectors.}}{Indexes for Sparse "
                      r"Vectors.}", t)
        self.assertIn(r"\mbox{https:/}\allowbreak \mbox{/}\allowbreak", t)
        # notes after the \bibitem, with the .bib line
        self.assertIn(r"\bibitem{wombat2020}\rrnote[corrected/refs.bib:2]{31}{", t)
        self.assertIn(r"\bibitem{numbat2018}\rrnote[corrected/refs.bib:5]{33}{", t)
        self.assertIn(r"\rrnote[corrected/refs.bib:7]{38}{Duplicate", t)   # removed entry: the one it merged into
        for line in t.split("\n"):
            self.assertTrue(MB.balanced([line]), line)
        if HAVE_TEX:
            (tmp / "main.tex").write_text((FIX / "bbl" / "main.tex").read_text().replace("%NATBIB%", ""))
            shutil.copyfile(STY, tmp / "r2changes.sty")
            errs, log = pdflatex(tmp, runs=3)
            self.assertEqual(errs, [], errs)


class ApplyEditsExtra(unittest.TestCase):
    def apply(self, spec):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="step6x-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "spec.json").write_text(json.dumps(spec))
        paper = tmp / "paper"
        shutil.copytree(FIX / "run" / "work" / "paper", paper)
        r = run(APPLY, tmp / "spec.json", paper, tmp / "c", tmp / "m", "--log", tmp / "log.tsv")
        return tmp, r

    def test_checkmark_for_invisible_changes(self):
        tmp, r = self.apply([
            {"item": 1, "file": "main.tex", "kind": "raw", "old": r"\usepackage{xspace}",
             "new": "\\usepackage{xspace}\n\\hypersetup{pdfauthor={}}", "question": "Keep it empty?",
             "note": "Author field emptied.", "note_ctx": "a library for wombat search.@@"},
            {"item": 2, "file": "sections/results.tex", "kind": "note", "ctx": "which is modest.",
             "note": "1200/1100 = 1.0909.", "question": "Recompute 1.10?"},
            {"item": 3, "file": "sections/results.tex", "kind": "note", "ctx": "A recall of 0.9", "note": "Checked."},
            {"item": 4, "file": "sections/intro.tex", "kind": "check", "old": "a old", "new": "an old",
             "question": "Article?"}])
        self.assertEqual(r.returncode, 0, r.stderr)
        mm, mr = (tmp / "m" / "main.tex").read_text(), (tmp / "m" / "sections" / "results.tex").read_text()
        mi = (tmp / "m" / "sections" / "intro.tex").read_text()
        self.assertIn(r"wombat search.\rrcheckmark{1}\rrnote[corrected/main.tex:4]{1}{To check: Keep it empty? "
                      r"Author field emptied.}", mm)
        self.assertIn(r"which is modest.\rrcheckmark{2}\rrnote[corrected/sections/results.tex:23]{2}{", mr)
        self.assertNotIn(r"\rrcheckmark{3}", mr)          # no question: not orange
        self.assertNotIn(r"\rrcheckmark{4}", mi)          # the \rrcheck mark is visible
        self.assertIn(r"\rrcheck{4}{a old}{an old}{Article?}", mi)

    def test_bib_edits(self):
        tmp, r = self.apply([
            {"item": 7, "file": "references.bib", "kind": "fix", "old": "2017", "new": "2019",
             "ctx": "year    = {2017}"},
            {"item": 8, "file": "references.bib", "kind": "check", "old": "Wombat Conference}",
             "new": "Wombat Conference ({WOMCON})}", "question": "Acronym?"}])
        self.assertEqual(r.returncode, 0, r.stderr)
        for root in ("c", "m"):            # both copies, no marks: the marked .bbl comes from mark_bbl.py
            b = (tmp / root / "references.bib").read_text()
            self.assertIn("year    = {2019}", b)
            self.assertIn("Wombat Conference ({WOMCON})}", b)
            self.assertNotIn(r"\rr", b)
        rows = [ln.split("\t") for ln in (tmp / "log.tsv").read_text().splitlines()[1:]]
        self.assertEqual(rows[0][:5], ["7", "fix", "references.bib", "16", "applied"])
        self.assertEqual(rows[1][4:6], ["to check", "Acronym?"])
        tmp, r = self.apply([{"item": 7, "file": "references.bib", "kind": "fix", "old": "2017", "new": "2019",
                              "note": "Year fixed."}])
        self.assertEqual(r.returncode, 1)
        self.assertIn("note on a .bib edit", r.stderr)

    def test_note_short_and_lint(self):
        long = " ".join(["word"] * 65)
        tmp, r = self.apply([
            {"item": 1, "file": "sections/results.tex", "kind": "fix", "old": "modest", "new": "small",
             "note": "Ratio 1200/1100 is 1.09, which the text called modest; the word now matches.",
             "note_short": "Ratio 1.09 called modest; word changed."},
            {"item": 2, "file": "sections/results.tex", "kind": "check", "old": "every system", "new": "all systems",
             "ctx": "reached by every system", "question": "All of them?", "note": "Checked in the table.",
             "note_short": "Wording; see report #2 for the table."},
            {"item": 3, "file": "sections/results.tex", "kind": "note", "ctx": "resident set size.", "note": long},
            {"item": 4, "file": "sections/results.tex", "kind": "note", "ctx": "throughput of every system",
             "note": " ".join(["term"] * 35)}])
        self.assertEqual(r.returncode, 0, r.stderr)
        m = (tmp / "m" / "sections" / "results.tex").read_text()
        self.assertIn(r"\rrnotepair[corrected/sections/results.tex:23]{1}{Ratio 1200/1100 is 1.09, which the text "
                      r"called modest; the word now matches.}{Ratio 1.09 called modest; word changed. See report \#1.}", m)
        # a question: "To check." first; a short text that already cites the report gets no second pointer
        self.assertIn(r"{To check: All of them? Checked in the table.}{To check. Wording; see report \#2 for the "
                      r"table.}", m)
        self.assertNotIn("rrnotepair[corrected/sections/results.tex:23]{3}", m)
        self.assertIn("item #3: note of 65 words (keep it under about 60)", r.stdout)
        self.assertIn("item #3: note of 65 words without note_short", r.stdout)
        self.assertIn("item #4: note of 35 words without note_short", r.stdout)
        self.assertNotIn("item #1:", r.stdout)
        self.assertNotIn("\\rrnote{", (tmp / "c" / "sections" / "results.tex").read_text())
        tmp, r = self.apply([
            {"item": 5, "file": "references.bib", "kind": "fix", "old": "2017", "new": "2019", "note_short": "Year."},
            {"item": 6, "file": "sections/results.tex", "kind": "fix", "old": "modest", "new": "small",
             "note_short": "No long note."}])
        self.assertEqual(r.returncode, 1)
        self.assertIn("note on a .bib edit", r.stderr)
        self.assertIn("note_short without note or question", r.stderr)

    def test_raw_note_at_start_of_moved_text(self):
        # a raw edit moves the first paragraph after the second: its note goes at the start of the moved text
        # (end of its first sentence), not after the block; a note whose ctx lies inside the moved text goes at
        # that place in the mark
        p1 = "Table~\\ref{tab:main} reports the throughput of every system at $90\\%$ recall.\nQuokka is the " \
             "fastest system on every collection and the gap grows with the\ncollection size.\n\n"
        src = (FIX / "run" / "work" / "paper" / "sections" / "results.tex").read_text()
        self.assertIn(p1, src)
        block = p1 + "\\begin{table}"
        moved = "\\begin{table}"
        mark_p1 = "{\\color{rrred}" + p1.rstrip("\n") + "}\\rrtag{rrred}{8}\n\n"
        spec = [{"item": 8, "file": "sections/results.tex", "kind": "raw", "old": block, "new": moved,
                 "mark": moved},
                {"item": 8, "file": "sections/results.tex", "kind": "raw", "old": "\\begin{figure}",
                 "new": p1 + "\\begin{figure}", "mark": mark_p1 + "\\begin{figure}",
                 "note": "Paragraph moved after the equation."},
                {"item": 9, "file": "sections/results.tex", "kind": "note", "ctx": "Quokka is the fastest@@",
                 "note": "Inside the moved text."}]
        tmp, r = self.apply(spec)
        self.assertEqual(r.returncode, 0, r.stderr)
        m = (tmp / "m" / "sections" / "results.tex").read_text()
        i_mark = m.index("{\\color{rrred}Table")
        i8 = m.index("\\rrnote[corrected/sections/results.tex:21]{8}{Paragraph moved")
        i9 = m.index("\\rrnote[corrected/sections/results.tex:22]{9}{Inside")
        self.assertIn("at $90\\%$ recall.\\rrnote[corrected/sections/results.tex:21]{8}", m)
        self.assertIn("Quokka is the fastest\\rrnote[", m)
        self.assertTrue(i_mark < i8 < i9 < m.index("collection size.}\\rrtag{rrred}{8}"), m)
        c = (tmp / "c" / "sections" / "results.tex").read_text()
        self.assertNotIn("\\rr", c)
        self.assertEqual(c.count("Quokka is the fastest"), 1)
        if HAVE_TEX:
            shutil.copyfile(FIX / "run" / "work" / "paper" / "references.bib", tmp / "m" / "references.bib")
            errs, _ = pdflatex(tmp / "m")
            self.assertEqual(errs, [], errs)


@unittest.skipUnless(HAVE_TEX, "pdflatex not installed")
class Package(unittest.TestCase):
    """The marked fixture compiled with the package: boxes on the page of their note, links both ways."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="step6pkg-"))
        r = run(APPLY, FIX / "spec.json", FIX / "paper", cls.tmp / "c", cls.tmp / "m")
        assert r.returncode == 0, r.stderr
        cls.errs, cls.log = pdflatex(cls.tmp / "m", runs=3)
        cls.cerrs, _ = pdflatex(cls.tmp / "c", runs=2)
        cls.aux = CN.read_aux(cls.tmp / "m" / "main.aux")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_compiles_without_changing_pages(self):
        self.assertEqual(self.errs, [])
        pages = lambda p: len(re.findall(rb"/Type\s*/Page\b", pdf_objects(p)))
        self.assertEqual(pages(self.tmp / "m" / "main.pdf"), pages(self.tmp / "c" / "main.pdf"))

    def test_boxes_on_the_page_of_their_tags(self):
        res = CN.check(self.aux)
        self.assertEqual(res["off_page"], [])
        self.assertEqual(res["notes"], 10)
        self.assertEqual(res["boxes"], 10)
        notes, placed, marks = CN.records(self.aux)
        tagpages = {}
        for item, page in marks.values():
            tagpages.setdefault(item, set()).add(page)
        away = set()
        for k, (item, page, _) in notes.items():
            self.assertEqual(placed[k][1], page)
            if item in tagpages and page not in tagpages[item]:
                away.add(item)
        # only the note placed after a figure that floated to the next page is away from its tag
        self.assertEqual(away, {"14"})
        r = run(CHECK_NOTES, self.tmp / "m" / "main.aux")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK: every box is on the page of its note", r.stdout)

    def test_links_both_ways(self):
        objs = pdf_objects(self.tmp / "m" / "main.pdf")
        to_box = set(re.findall(rb"/D\s*\((rrbox-\d+)\)", objs))
        to_mark = set(re.findall(rb"/D\s*\((rrmark-\d+)\)", objs))
        notes, placed, marks = CN.records(self.aux)
        with_tag = {k for k, (item, page, _) in notes.items() if (item, page) in set(marks.values())}
        self.assertEqual(len(with_tag), 7)
        # every tag links to the box of its item on its page, and every such box links back to a tag
        self.assertEqual(to_box, {b"rrbox-%d" % k for k in with_tag})
        self.assertEqual(len(to_mark), len(with_tag))
        self.assertIn(b"/D (rrnote-", objs.replace(b"/D(", b"/D ("))   # boxes with no tag: back to the note
        for it in (2, 3, 5, 10):                       # one named destination per item (\rranchor)
            self.assertIn(b"(rr-%d)" % it, objs)
        self.assertRegex(self.log, r"\\rr@placed|Output written")


def run_fixture():
    """A copy of evals/fixtures/step6/run (an output folder) in a temporary folder."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="step6run-"))
    shutil.copytree(FIX / "run", tmp / "run")
    return tmp, tmp / "run"


class FrontPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp, cls.out = run_fixture()
        w = cls.out / "work"
        r = run(APPLY, w / "edits.json", w / "paper", cls.out / "corrected", w / "marked", "--log", w / "edits.tsv")
        assert r.returncode == 0, r.stderr

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def front(self, *extra):
        f = self.tmp / "front.tex"
        r = run(FRONT, "--final-dir", FINAL, self.out, self.out / "work" / "marked" / "main.tex", "--out", f, "--date", "2026-11-10", *extra)
        return r, (f.read_text() if f.exists() and r.returncode == 0 else "")

    def test_cover(self):
        r, t = self.front()
        self.assertEqual(r.returncode, 0, r.stderr)
        pages = split_pages(t)
        cover = pages["cover"]
        # the title is the corrected one, without marks
        self.assertIn(r"\bfseries\raggedright Fast Wombat Search for Nearest Neighbor\par", cover)
        self.assertIn("WOMCON 2027 (Wombat Conference), full papers", cover)
        # headline: need you and desk-reject risks dominate; problems found, numbers and claims, fixed, pre-set
        big = re.findall(r"\\rrFbig\{(\d+)\}\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", cover)
        self.assertEqual([(int(v), re.sub(r"\\hyperlink\{[^}]*\}\{([^}]*)\}", r"\1", l)) for v, l in big],
                         [(7, "need you"), (1, "desk-reject risk")])
        small = re.findall(r"\\rrFsmall\{([\d,]+)\}\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", cover)
        self.assertEqual([(int(v), l) for v, l in small][:3],
                         [(21, "problems found"), (4, "numbers and claims"), (10, "fixed in the copy")])
        self.assertIn("+5 to confirm", cover)
        self.assertIn("5 to confirm, 1 your facts, 1 to check", cover)
        self.assertIn(r"\textcolor{rrred}{\textbf{Not ready yet:}}", cover)          # the readiness verdict
        # the kind bar: every item once, the one-line legend, the item not applied by name
        kinds = [int(x) for x in re.findall(r"\\rrFchip\{[^}]*\}\\,\\textbf\{(\d+)\}", cover)]
        self.assertEqual(sum(kinds), 21)
        self.assertIn(r"\textbf{1} not applied (\rrFitem{17})", cover)
        self.assertIn(r"(placeholders} \textcolor{rrorange}{[\#n:\,\dots]}", cover)
        # most important errors: section 2, then 3, then 4; each with its box state, page and kind
        errs = [int(x) for x in re.findall(r"\\makebox\[24pt\]\[l\]\{\\rrFitem\{(\d+)\}\}", cover)]
        self.assertEqual(errs[:5], [21, 3, 8, 14, 20])
        self.assertIn(r"2.4", cover)
        self.assertNotIn(r"\rrFrowe", cover)                                   # no venue table on the summary
        self.assertIn("How to apply the changes", cover)
        # the venue page: the table, the state in the copy, the sources and the caveat
        venue = pages["venue"]
        self.assertEqual(len(re.findall(r"\\rrFrowe\{(?:rrband|white)\}\{\\rrF(?:ok|bad|conf|unk)\}", venue)), 4)
        self.assertIn(r"\rrFbad\,0 violated\quad\rrFconf\,1 to confirm\quad\rrFunk\,1 cannot tell\quad\rrFok\,2 met",
                      venue)
        self.assertIn(r"[2]\,\mbox{archived 2026-01-15}", venue)
        self.assertIn(r"\mbox{unknown}", venue)
        self.assertIn(r"The live page \url{https://womcon.example.org/template} could not be read (HTTP 403).", venue)
        self.assertIn(r"\rrFitem{21}", venue)
        self.assertIn(r"\textcolor{rrorange}{\textbf{to confirm}}", venue)       # item 21 in the copy

    def test_decisions(self):
        r, t = self.front()
        rows = re.findall(r"\\rrFdrow\{\w+\}\{(?:\\raisebox\{-1pt\}\{\\rritembox\{\d+\}\})?\}\{\\rrFitem\{(\d+)\}\}"
                          r"\{\\rrFpage\{(\d+)\}\}\{([^\n]*)", t)
        self.assertEqual([int(x[0]) for x in rows], [3, 5, 8, 12, 14, 20, 21])   # no pages yet: by item
        rows = [(x[0], x[0], x[1], x[2]) for x in rows]
        # the item's check box ("do it" / "don't") in its row, the same field as next to its change in the paper
        self.assertIn(r"\rrFdrow{rrband}{\raisebox{-1pt}{\rritembox{3}}}{\rrFitem{3}}", t)
        kinds = {int(x[0]): x[3] for x in rows}
        self.assertIn("confirm", kinds[3])
        self.assertIn("your facts}}", kinds[5])
        self.assertIn(r"major}\enspace Give: number of threads and core\_count}", kinds[5])
        self.assertIn(r"major}\enspace Recompute 1.10 from the unrounded data?}", kinds[20])    # the item's severity
        self.assertIn(r"\rrbeginform", t)
        self.assertIn(r"\rrbeginpaper", t)
        # a text field for the answer right under every question (facts too)
        self.assertEqual([int(x) for x in re.findall(r"\\rrFdans\{\w+\}\{(\d+)\}", t)], [3, 5, 8, 12, 14, 20, 21])
        self.assertIn("Is the memory saving 2.3$\\times$ or 2.4$\\times$?}\n\\rrFdans{rrband}{3}", t)
        self.assertIn("type them in the box under the question", t)

    def test_decision_pages_balanced_by_height(self):
        fp = load(FRONT, "front_pages_chunks")
        self.assertEqual(fp.decision_chunks([1] * 30), [list(range(30))])
        ch = fp.decision_chunks([1 + fp.ANSWER_UNITS] * 20)        # rows with an answer field: fewer per page
        self.assertEqual(sorted(len(c) for c in ch), [6, 7, 7])
        self.assertEqual(sum(ch, []), list(range(20)))             # in order, none lost
        ch = fp.decision_chunks([1, 6, 1, 6, 1, 6, 1, 6, 1, 6, 1, 6, 1, 6])
        self.assertTrue(all(sum([1, 6][i % 2] for i in c) <= fp.DEC_PER_PAGE for c in ch), ch)

    def test_rejects_rules_not_in_venue_md(self):
        st = json.loads((self.out / "work" / "venue-status.json").read_text())
        st["rules"][0]["quote"] = "Papers may have 20 pages"
        st["rules"][1]["status"] = "probably"
        st["rules"][2]["url"] = "https://example.org/elsewhere"
        st["rules"][3]["items"] = [99]
        bad = self.tmp / "bad-status.json"
        bad.write_text(json.dumps(st))
        r, t = self.front("--status", bad)
        self.assertEqual(r.returncode, 1)
        for msg in ("quote not found in venue.md", "status must be one of", "url not in venue.md",
                    "item 99 is not an item of report.md"):
            self.assertIn(msg, r.stderr)

    def test_markdown(self):
        fp = load(FRONT, "front_pages")
        self.assertEqual(fp.md("a `x_1` **b** *c* 50% × 2 – 3"), r"a \texttt{x\_1} \textbf{b} \emph{c} 50\% $\times$ 2 -- 3")
        self.assertEqual(fp.unmark(r"A \rrfixplain{3}{B} \rrfix{4}{x}{y}\rrnote[f:1]{4}{n}."), "A B y.")


@unittest.skipUnless(HAVE_LATEXMK, "latexmk, pdflatex or pdfinfo not installed")
class Driver(unittest.TestCase):
    """build_changes.py end to end on the fixture run."""

    @classmethod
    def setUpClass(cls):
        cls.tmp, cls.out = run_fixture()
        cls.res = run(BUILD, "--final-dir", FINAL, cls.out, "--date", "2026-11-10")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_runs(self):
        self.assertEqual(self.res.returncode, 0, self.res.stdout + self.res.stderr)
        self.assertIn("OK: every box is on the page of its note", self.res.stdout)
        self.assertIn("pages 2 -> 2", self.res.stdout)

    def test_outputs(self):
        out = self.out
        self.assertTrue((out / "changes.pdf").is_file())
        c = (out / "corrected" / "references.bib").read_text()
        self.assertIn("year    = {2019}", c)
        for p in (out / "corrected").rglob("*.tex"):
            self.assertNotIn(r"\rr", p.read_text(), p)
        self.assertFalse(list((out / "corrected").glob("*.aux")))       # corrected/ stays clean
        md = (out / "edits.md").read_text()
        self.assertIn("- **1** applied — sections/intro.tex:4", md)
        self.assertIn("- **5** missing facts — sections/intro.tex:11", md)
        self.assertIn("- **17** not applied (needs a new experiment)", md)
        self.assertIn("- **18** applied — references.bib:16", md)
        bbl = (out / "work" / "marked" / "main.bbl").read_text()
        self.assertIn(r"\rrnote[corrected/references.bib:9]{18}{Year 2017 $\to$ 2019", bbl)
        self.assertIn(r"\rrfix{18}{\mbox{2017.}}{2019.}", bbl)

    def test_pdf(self):
        objs = pdf_objects(self.out / "changes.pdf")
        self.assertIn(b"/AcroForm", objs)
        states = load(FRONT, "front_pages").read_states(self.out / "work" / "marked" / "r2states.tex")
        fields = re.findall(rb"/FT\s*/Btn\s*/T\s*\(item-(\d+)\)", objs)
        self.assertEqual(sorted(int(x) for x in fields), sorted(states))        # one field per item with a box
        kids = {int(m.group(1)): len(re.findall(rb"\d+ 0 R", m.group(2)))
                for m in re.finditer(rb"/T\s*\(item-(\d+)\).*?/Kids\s*\[([^\]]*)\]", objs, re.S)}
        self.assertGreaterEqual(max(kids.values()), 3, kids)               # one value shared by several widgets
        self.assertGreaterEqual(kids[3], 3)                                 # #3: its tag, its margin box, its decision row
        widgets = len(re.findall(rb"/Subtype\s*/Widget\s*/F 4\s*/Parent", objs))
        self.assertEqual(widgets, sum(kids.values()))
        self.assertIn(b"/D (rr-decisions)", objs.replace(b"/D(", b"/D ("))
        aux = CN.read_aux(self.out / "work" / "marked" / "main.aux")
        res = CN.check(aux)
        self.assertEqual(res["off_page"], [])
        self.assertEqual(res["notes"], 14)                # 12 in the text, 2 in the bibliography
        pages = dict(re.findall(r"\\newlabel\{rr-(\d+)\}\{\{[^{}]*\}\{(\d+)\}", aux))
        self.assertEqual(pages["21"], "1")                # the paper restarts at page 1 after the front pages

    def test_links(self):
        # every link resolves, no two links overlap, item links of the front pages land in the paper (or on the row
        # of an item with no mark), every \rrFdef anchor exists
        pl = load(SKILL / "scripts" / "pdf_links.py", "pdf_links")
        tex = (self.out / "work" / "marked" / "rrfront.tex").read_text()
        nfront = tex.count(r"\begin{rrfullpage}")
        res = pl.check(self.out / "changes.pdf", nfront)
        self.assertEqual(res["unresolved"], [])
        self.assertEqual(res["overlaps"], [])
        self.assertEqual(res["item_on_front"], [])
        defs = dict(re.findall(r"\\rrFdef\{(\d+)\}\{([^}]*)\}", tex))
        self.assertEqual(len(defs), 21)                                   # every item of report.md
        objs = pdf_objects(self.out / "changes.pdf")
        for it, anchor in defs.items():
            self.assertIn(b"(" + anchor.encode() + b")", objs, (it, anchor))
            if anchor.startswith("rrrow-"):
                self.assertIn(r"\hypertarget{%s}{}" % anchor, tex)

    def test_choices_roundtrip(self):
        # the boxes as built = the defaults; a viewer save that unticks #3 (incremental update of its field and
        # widgets) is read back; apply_edits.py --choices then leaves #3 out of corrected/
        rc = load(SKILL / "scripts" / "read_choices.py", "read_choices")
        pdf = self.out / "changes.pdf"
        states = load(FRONT, "front_pages").read_states(self.out / "work" / "marked" / "r2states.tex")
        got = rc.read_fields(pdf)
        self.assertEqual({n: t for n, (t, ro) in got.items()}, {n: st[0] and not st[1] for n, st in states.items()})
        data = pdf.read_bytes()
        objs = rc.objects(data)
        fnum = next(n for n, v in objs.items() if isinstance(v, dict) and v.get("T") in (b"item-3", "item-3"))
        kids = [k[0] for k in objs[fnum]["Kids"]]
        upd = b"\n%d 0 obj\n<</FT/Btn/T(item-3)/V/Off/Ff 0/Kids[%s]>>\nendobj\n" % (
            fnum, b" ".join(b"%d 0 R" % k for k in kids))
        for k in kids:
            upd += b"%d 0 obj\n<</Type/Annot/Subtype/Widget/Parent %d 0 R/AS/Off/Rect[0 0 6 6]>>\nendobj\n" % (k, fnum)
        saved = self.tmp / "saved.pdf"
        saved.write_bytes(data + upd + b"%%EOF\n")
        ch = rc.choices(str(saved), str(self.out / "work" / "marked" / "r2states.tex"))
        self.assertEqual(ch["items"]["3"]["choice"], "dont")
        self.assertTrue(ch["items"]["3"]["changed"])
        self.assertEqual(ch["changed"], [3])
        cj = self.tmp / "choices.json"
        cj.write_text(json.dumps(ch))
        w = self.out / "work"
        c2, m2 = self.tmp / "c2", self.tmp / "m2"
        r = run(APPLY, w / "edits.json", w / "paper", c2, m2, "--log", self.tmp / "e2.tsv", "--choices", cj)
        self.assertEqual(r.returncode, 0, r.stderr)
        intro = (c2 / "sections" / "intro.tex").read_text()
        self.assertIn(r"$2.3\times$", intro)                              # #3 not applied: the original stays
        self.assertNotIn(r"$2.4\times$", intro)
        self.assertIn(r"$2.4\times$", (self.out / "corrected" / "sections" / "intro.tex").read_text())
        self.assertIn("\\rritemstate{3}{0}{0}{your choice: don't}", (m2 / "r2states.tex").read_text())
        log = (self.tmp / "e2.tsv").read_text()
        self.assertIn("not chosen (your choice)", log)

    def answer_field(self, data, item):
        rc = load(SKILL / "scripts" / "read_choices.py", "read_choices")
        objs = rc.objects(data)
        num = next(n for n, v in objs.items() if isinstance(v, dict) and v.get("T") in (b"answer-%d" % item,))
        return rc, objs, num

    def test_answer_fields(self):
        # one empty multi-line text field per question of the decision sheet, in the one /AcroForm, with /Helv
        data = (self.out / "changes.pdf").read_bytes()
        rc, objs, num = self.answer_field(data, 3)
        f = objs[num]
        self.assertEqual((f["FT"], f["Subtype"], f["V"], f["Ff"] & 4096), ("Tx", "Widget", b"", 4096))
        self.assertIn("Helv", f["DA"].decode())
        self.assertIn("N", f["AP"])
        names = sorted(rc.text(v["T"]) for v in objs.values() if isinstance(v, dict) and v.get("FT") == "Tx")
        self.assertEqual(names, ["answer-%d" % i for i in (12, 14, 20, 21, 3, 5, 8)])
        cat = [v for v in objs.values() if isinstance(v, dict) and "AcroForm" in v]
        self.assertEqual(len(cat), 1)
        acro = rc.deref(objs, cat[0]["AcroForm"])
        self.assertIn("Helv", rc.deref(objs, acro["DR"])["Font"])
        fields = rc.deref(objs, acro["Fields"])
        self.assertIn((num, 0), fields)
        self.assertEqual(len(re.findall(rb"/AcroForm", pdf_objects(self.out / "changes.pdf"))), 1)
        self.assertEqual(rc.choices(str(self.out / "changes.pdf"))["answers"], {})

    def test_answers_roundtrip(self):
        # a viewer's incremental save (the field object redefined, a new xref section whose trailer points back with
        # /Prev) that types a non-ASCII answer into #3 and a literal one into #20 is read back into choices.json
        pdf = self.out / "changes.pdf"
        data = pdf.read_bytes()
        rc, objs, n3 = self.answer_field(data, 3)
        _, _, n20 = self.answer_field(data, 20)
        prev = int(re.findall(rb"startxref\s+(\d+)", data)[-1])
        xs = [v for v in objs.values() if isinstance(v, dict) and v.get("Type") == "XRef"]
        root = xs[-1]["Root"] if xs else re.findall(rb"/Root\s+(\d+)\s+0\s+R", data)[-1]
        size = max(objs) + 1
        quokka = "Yes: 2.4\u00d7 is right \u2014 Ada Burrow\u2019s quokka log.\nTable 3 is wrong."
        new = {n3: objs[n3], n20: objs[n20]}
        upd, offs = b"\n", {}
        for n, val in ((n3, "<FEFF%s>" % quokka.encode("utf-16-be").hex().upper()), (n20, r"(Done: 1.09\r\nwombats)")):
            d = new[n]   # the field rewritten as a viewer does: its keys and the new /V
            keys = "/Type/Annot/Subtype/Widget/FT/Tx/F 4/T(answer-%d)/Ff 4096/DA(/Helv 9 Tf 0 g)/Rect[%s]/V %s" % (
                3 if n == n3 else 20, " ".join(str(x) for x in d["Rect"]), val)
            offs[n] = len(data) + len(upd)
            upd += b"%d 0 obj\n<<%s>>\nendobj\n" % (n, keys.encode())
        x = len(data) + len(upd)
        upd += b"xref\n" + b"".join(b"%d 1\n%010d 00000 n \n" % (n, o) for n, o in sorted(offs.items()))
        upd += b"trailer\n<< /Size %d /Root %d 0 R /Prev %d >>\nstartxref\n%d\n%%%%EOF\n" % (
            size, root[0] if isinstance(root, tuple) else int(root), prev, x)
        saved = self.tmp / "answered.pdf"
        saved.write_bytes(data + upd)
        out = self.tmp / "answered.json"
        r = run(SKILL / "scripts" / "read_choices.py", saved, "--out", out, "--defaults",
                self.out / "work" / "marked" / "r2states.tex")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("2 answers", r.stdout)
        res = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(res["answers"], {"3": quokka, "20": "Done: 1.09\nwombats"})
        self.assertEqual(res["changed"], [])                       # the boxes are untouched
        for key in ("source", "items", "do", "dont", "changed", "missing"):
            self.assertIn(key, res)

    @unittest.skipUnless(sys.platform == "darwin" and shutil.which("osascript"), "macOS PDFKit (Preview) only")
    def test_answers_preview_save(self):
        # Preview's engine (PDFKit): type an answer, untick #12, save; the rewritten file is read back
        js = self.tmp / "fill.js"
        js.write_text("""ObjC.import('PDFKit');
function run(argv) {
  var doc = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0])), n = 0;
  for (var i = 0; i < doc.pageCount; i++) {
    var an = doc.pageAtIndex(i).annotations;
    for (var j = 0; j < an.count; j++) {
      var a = an.objectAtIndex(j), f = a.fieldName;
      if (f && f.js == 'answer-14') { a.widgetStringValue = $(argv[2]); n++; }
      if (f && f.js == 'item-12') { a.buttonWidgetState = 0; }
    }
  }
  return n + ' ' + doc.writeToFile(argv[1]);
}""")
        saved = self.tmp / "preview.pdf"
        text = "Both collections \u2014 wombats and quokkas (\u00fc).\nAda Burrow"
        r = subprocess.run(["osascript", "-l", "JavaScript", str(js), str(self.out / "changes.pdf"), str(saved), text],
                           capture_output=True, text=True)
        if r.returncode != 0 or not saved.is_file():
            self.skipTest("PDFKit not usable here: " + r.stderr[:200])
        self.assertTrue(r.stdout.strip().startswith("1 "), r.stdout)
        rc = load(SKILL / "scripts" / "read_choices.py", "read_choices")
        res = rc.choices(str(saved), str(self.out / "work" / "marked" / "r2states.tex"))
        self.assertEqual(res["answers"], {"14": text})
        self.assertEqual(res["changed"], [12])

    def test_one_consistent_build(self):
        # the four outputs carry one build id; verify() finds a corrected/ that is not the ticked set
        self.assertIn("9/9 consistency", self.res.stdout)
        m = re.search(r"OK: build ([0-9a-f]{12}) in all four", self.res.stdout)
        self.assertIsNotNone(m, self.res.stdout)
        bid = m.group(1)
        self.assertIn("Build: `%s`" % bid, (self.out / "report.md").read_text())
        self.assertIn("Build: `%s`" % bid, (self.out / "edits.md").read_text())
        self.assertIn(bid, (self.out / "corrected" / ".reviewer2-build").read_text())
        p1 = subprocess.run(["pdftotext", "-f", "1", "-l", "1", self.out / "changes.pdf", "-"], capture_output=True,
                            text=True).stdout
        self.assertIn("build " + bid, p1)
        md = (self.out / "edits.md").read_text()
        self.assertIn("- **fixed**: red in changes.pdf", md)
        self.assertIn("[your facts; major]", md)
        bc = load(BUILD, "build_changes")
        self.assertEqual(bc.verify(str(self.out), str(self.out / "work"), "main.tex", bid, None, []), [])
        f = self.out / "corrected" / "sections" / "intro.tex"
        keep = f.read_text()
        try:
            f.write_text(keep.replace(r"$2.4\times$", r"$2.3\times$"))
            bad = bc.verify(str(self.out), str(self.out / "work"), "main.tex", bid, None, [])
            self.assertTrue(any("corrected/ is not exactly the ticked items" in b for b in bad), bad)
        finally:
            f.write_text(keep)
        bad = bc.verify(str(self.out), str(self.out / "work"), "main.tex", "000000000000", None, [])
        self.assertTrue(any("does not carry build" in b for b in bad), bad)
        # the disabled "your facts" box of #5 is read-only in the PDF and never ticked
        rc = load(SKILL / "scripts" / "read_choices.py", "read_choices")
        self.assertEqual(rc.read_fields(self.out / "changes.pdf")[5], (False, True))

    def test_crowded_page_gets_short_notes(self):
        # six long notes on one line: the page is crowded, its notes switch to their short text, the boxes get closer
        tmp, out = run_fixture()
        self.addCleanup(shutil.rmtree, tmp, True)
        p = out / "work" / "edits.json"
        spec = json.loads(p.read_text())
        long = ("The invented measurement in this sentence was compared with the invented table of the appendix, "
                "row by row, and the two disagree in the second decimal place, so the text now follows the table.")
        for it in range(40, 46):
            spec.append({"item": it, "file": "sections/intro.tex", "kind": "note", "ctx": "memory in GiB.",
                         "note": long, "note_short": "Text disagreed with the table; now follows it."})
        p.write_text(json.dumps(spec))
        r = run(BUILD, "--final-dir", FINAL, out, "--date", "2026-11-10", "--no-png")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("round 1:", r.stdout)
        m = re.search(r"PDF page (\d+): shortened ([^;]*); max offset ([\d.]+)pt -> ([\d.]+)pt", r.stdout)
        self.assertIsNotNone(m, r.stdout)
        self.assertTrue(set("#%d" % i for i in range(40, 46)) <= set(m.group(2).split(", ")), m.group(2))
        self.assertLess(float(m.group(4)), float(m.group(3)))
        rrs = (out / "work" / "marked" / "main.rrs").read_text()
        aux = CN.read_aux(out / "work" / "marked" / "main.aux")
        has = CN.with_short(aux)
        self.assertEqual(len(has), 6)
        self.assertEqual(set(re.findall(r"\\rrshortnote\{(\d+)\}", rrs)), {str(k) for k in has})
        self.assertIn("OK: every box is on the page of its note", r.stdout)
        tex = (out / "work" / "marked" / "sections" / "intro.tex").read_text()
        self.assertIn(r"{Text disagreed with the table; now follows it. See report \#40.}", tex)

    def test_errors_are_clear(self):
        tmp, out = run_fixture()
        self.addCleanup(shutil.rmtree, tmp, True)
        (out / "work" / "venue-status.json").unlink()
        r = run(BUILD, "--final-dir", FINAL, out)
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing input(s)", r.stderr)
        self.assertIn("venue-status.json", r.stderr)
        tmp2, out2 = run_fixture()
        self.addCleanup(shutil.rmtree, tmp2, True)
        (out2 / "work" / "tmp" / "bbl-map.json").unlink()
        r = run(BUILD, "--final-dir", FINAL, out2)
        self.assertEqual(r.returncode, 1)
        self.assertIn("bbl-map.json is missing", r.stderr)


def ai_run(strong=True):
    """The run fixture with invented facts (a chatbot leftover, Markdown, a comment naming ChatGPT, an unverified
    reference) and a venue rule on LLM use; strong=False keeps only the Unicode and reference findings."""
    tmp, out = run_fixture()
    facts = (FIX / "ai" / "facts.txt").read_text()
    if not strong:
        facts = "\n".join(l for l in facts.split("\n") if not re.match(r"(FAIL \| (chatbot|Markdown)|CHECK \| comment)", l))
    (out / "work" / "facts.txt").write_text(facts)
    v = out / "work" / "venue.md"
    v.write_text(v.read_text().replace("\nFLAGS:", '- LLM use: "Any use of a large language model must be disclosed in an '
                                       'LLM usage statement." https://womcon.example.org/cfp VERIFIED\n\nFLAGS:'))
    r = run(TRACES, out)
    assert r.returncode == 0, r.stdout + r.stderr
    return tmp, out


class AITraces(unittest.TestCase):
    """ai_traces.py: style densities, artifacts linked to report items, the evidence rule, the agent's fields."""

    def test_measure(self):
        at = load(TRACES, "ai_traces")
        m = at.measure(FIX / "ai" / "paper" / "main.tex")
        self.assertEqual(m["em"], 3)                       # 2 x --- and 1 Unicode; not in math, not the table cell
        self.assertEqual(m["em_spaced"], 1)
        self.assertEqual(m["clusters_p"], ["main.tex:11 (delve, realm, underscores, pivotal)"])
        self.assertEqual(m["tails"], 1)
        self.assertEqual(m["runins"], ["main.tex:18", "main.tex:21", "main.tex:24"])   # not the coloured \todo
        self.assertEqual((len(m["items"]), m["bold_items"]), (2, 1))
        self.assertEqual(m["boxes"], ["main.tex:33"])        # \newtcolorbox{takeaway}
        self.assertEqual(m["tables"], ["main.tex:37"])       # \cmark defined by the paper
        self.assertEqual(m["sections"][0]["title"], "1 Introduction to Quokka")
        st = at.find_statement(m["src"], at.simple_macros(m["src"].code()))
        self.assertEqual((st["where"], st["heading"], st["followed_by"]), ("main.tex:42", "LLM usage statement",
                                                                           "References"))
        self.assertTrue(st["text"].startswith("We used an invented assistant"))

    def test_json(self):
        tmp, out = ai_run()
        self.addCleanup(shutil.rmtree, tmp, True)
        ai = json.loads((out / "work" / "ai-traces.json").read_text())
        arts = {a["id"]: a for a in ai["artifacts"]}
        self.assertEqual((arts["chatbot"]["status"], arts["chatbot"]["items"]), ("fail", [9]))
        self.assertEqual((arts["markdown"]["status"], arts["markdown"]["items"]), ("fail", [1, 2]))   # both at intro.tex:4
        self.assertEqual((arts["comments"]["status"], arts["comments"]["items"]), ("check", []))
        self.assertEqual((arts["references"]["where"], arts["references"]["items"]), (["quokka2019"], [18]))
        self.assertEqual(arts["unicode"]["status"], "check")
        self.assertEqual(arts["hidden"]["status"], "none")
        self.assertEqual(arts["spaces"]["status"], "none")
        self.assertTrue(ai["evidence"]["rule_strong"])
        self.assertEqual(len(ai["evidence"]["reasons"]), 2)       # the leftover and the comment, not the Markdown
        self.assertEqual(ai["paper"]["body_pages"], 1)
        d = ai["disclosure"]
        self.assertFalse(d["statement"]["found"])
        self.assertIn("LLM use", d["venue_rule_found"])
        self.assertEqual(d["venue_url"], "https://womcon.example.org/cfp")
        self.assertTrue(d["venue_quote_found"].startswith("Any use of a large language model"))
        self.assertEqual({s["id"] for s in ai["style"]}, {"em_dash", "excess_words", "participle_tails",
                                                          "bold_runins", "items", "boxes", "checkmark_tables"})
        self.assertFalse(next(s for s in ai["style"] if s["id"] == "em_dash")["baseline"]["calibrated"])
        # the agent's fields survive a rerun
        ai["assessment"] = "Two artifacts to delete."
        ai["suggestion"] = {"text": "We used ChatGPT to edit the language of Section 1.", "where": "end of paper"}
        ai["disclosure"]["advice"] = "Keep the statement."
        (out / "work" / "ai-traces.json").write_text(json.dumps(ai))
        run(TRACES, out)
        ai2 = json.loads((out / "work" / "ai-traces.json").read_text())
        self.assertEqual(ai2["assessment"], "Two artifacts to delete.")
        self.assertEqual(ai2["suggestion"]["where"], "end of paper")
        self.assertEqual(ai2["disclosure"]["advice"], "Keep the statement.")

    def test_not_strong(self):
        tmp, out = ai_run(strong=False)
        self.addCleanup(shutil.rmtree, tmp, True)
        ai = json.loads((out / "work" / "ai-traces.json").read_text())
        self.assertFalse(ai["evidence"]["rule_strong"])          # Unicode and references never count
        self.assertEqual({a["id"]: a["status"] for a in ai["artifacts"]}["chatbot"], "none")


class AIPage(unittest.TestCase):
    """front_pages.py: the "Traces of AI use" page and its checks."""

    def page(self, edit=None, strong=True):
        tmp, out = ai_run(strong)
        self.addCleanup(shutil.rmtree, tmp, True)
        w = out / "work"
        r = run(APPLY, w / "edits.json", w / "paper", out / "corrected", w / "marked", "--log", w / "edits.tsv")
        assert r.returncode == 0, r.stderr
        p = w / "ai-traces.json"
        ai = json.loads(p.read_text())
        if edit:
            edit(ai)
        p.write_text(json.dumps(ai))
        f = tmp / "front.tex"
        r = run(FRONT, "--final-dir", FINAL, out, w / "marked" / "main.tex", "--out", f, "--date", "2026-11-10")
        return r, (f.read_text() if r.returncode == 0 else "")

    def test_page(self):
        def edit(ai):
            ai["suggestion"] = {"text": "We used ChatGPT to edit the language of Section 1; the authors reviewed and "
                                        "take full responsibility for the content.", "where": "an LLM usage statement"}
            ai["assessment"] = "A chatbot leftover and a comment naming ChatGPT."
        r, t = self.page(edit)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(re.findall(r"\\begin\{rrfullpage\}\[([\w-]+)\]", t), ["cover", "venue", "decisions-1", "ai"])
        ai = split_pages(t)["ai"]
        for s in (r"Traces of AI use", r"perception only, not evidence", r"No calibrated baseline", r"\rrFitem{9}",
                  r"\rrFitem{2}", r"\rrFitem{18}", r"Your choice, and only if it matches what you actually did",
                  r"We used ChatGPT to edit the language of Section 1", r"\textbf{ICML 2026}", r"As of 2026-11-10",
                  r"\url{https://blog.icml.cc/2026/03/18/on-violations-of-llm-review-policies/}", r"\textbf{Your venue, WOMCON 2027",
                  r"``Any use of a large language model", r"\textbf{Our reading.} A chatbot leftover",
                  r"\url{https://womcon.example.org/cfp}", r"Your statement now:} none in the sources"):
            self.assertIn(s, ai, s)
        self.assertNotIn("No change needed", ai)

    def test_no_change_without_strong_evidence(self):
        r, t = self.page(lambda ai: ai["disclosure"].update(advice="Add the statement the venue requires."),
                         strong=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(r"No change needed beyond the venue\textquoteright{}s rule.", t)
        self.assertIn("Add the statement the venue requires.", t)
        self.assertNotIn("Your choice", t)

    def test_rejects(self):
        def edit(ai):
            ai["evidence"]["strong"] = False                                   # lowered without a why
            ai["suggestion"] = {"text": "Remove the disclosure statement."}    # no strong evidence; hides AI use
            ai["assessment"] = "The paper is clearly AI-generated."
            ai["disclosure"]["venue_quote"] = "LLMs are forbidden"
            ai["artifacts"][0]["items"] = [99]
        r, _ = self.page(edit)
        self.assertEqual(r.returncode, 1)
        for msg in ("lowered to false without a \"why\"", "a disclosure suggestion needs strong evidence",
                    "never suggest hiding, softening or removing", "never call the paper AI-written",
                    "venue_quote not found in venue.md", "item 99 is not an item of report.md"):
            self.assertIn(msg, r.stderr)
        r, _ = self.page(lambda ai: ai["evidence"].update(strong=True), strong=False)
        self.assertIn("never raise it", r.stderr)


@unittest.skipUnless(HAVE_LATEXMK, "latexmk, pdflatex or pdfinfo not installed")
class AIPageDriver(unittest.TestCase):
    def test_build(self):
        tmp, out = ai_run()
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run(BUILD, "--final-dir", FINAL, out, "--date", "2026-11-10", "--no-png")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"\d+ front \+ paper")
        self.assertIn("front pages filled: cover (p. i)", r.stdout)
        self.assertIn("checks.json written", r.stdout)
        self.assertIn("OK: every link resolves, none overlaps, every item link lands in the paper", r.stdout)
        log = (out / "work" / "marked" / "main.log").read_text(encoding="latin-1")
        self.assertNotIn("Front page too tall", log)
        if shutil.which("pdftotext"):
            npages = int(re.search(r"(\d+) front \+ paper", r.stdout).group(1))
            page = lambda n: " ".join(subprocess.run(["pdftotext", "-f", str(n), "-l", str(n), out / "changes.pdf", "-"],
                                                     capture_output=True, text=True).stdout.split())
            one = page(1)
            self.assertIn("How to apply the changes", one)
            self.assertIn("Applymychoicesin%s/changes.pdf" % FINAL, one.replace(" ", ""))
            self.assertIn("HOW DEEP WE LOOKED", one)
            self.assertIn("MOST IMPORTANT ERRORS", one)
            self.assertNotIn("??", one)                         # the page numbers of the front pages resolved
            titles = [next((n for n in range(2, npages + 1) if t in page(n)), None)
                      for t in ("Venue rules", "Decisions for you", "What we checked", "Traces of AI use")]
            self.assertEqual(titles, sorted(titles), titles)   # summary, venue, (bibliography), decisions, checks, AI
            self.assertIn("Avoid Desk Reject", page(titles[0]))
            self.assertIn("perception only, not evidence", page(titles[3]))
            for n in range(1, npages + 1):                      # no empty statistic on any front page
                self.assertNotIn("not counted", page(n).lower(), n)


COV_FACTS = {"form_check": "COVERAGE | pages=2 | words=640 | source_files=3 | source_lines=90 | labels=4 | "
                          "cross_references=6 | citations=5 | cited_keys=3 | figure_files=1 | tables=2 | "
                          "log_warnings=7 | log_bad_boxes=2 | fonts=9 | fonts_embedded=9 | links_found=3 | "
                          "links_tested=3",
             "refs_check": "COVERAGE | references=3 | refchecker_checked=3 | arxiv_ids=1 | arxiv_looked_up=1 | dois=2 | "
                           "dois_looked_up=2 | refs_with_identifier=3 | refs_identifier_looked_up=3 | preprints=1 | "
                           "preprints_dblp_db=0",
             "bib_style": "COVERAGE | entries_compared=3 | features=12 | venues_compared=1 | differences=1"}


def stats_run(coverage=True, blocks=True):
    """The AI run with COVERAGE lines in facts.txt (coverage) and checker files with Coverage blocks (blocks) or
    without (counted from the outputs)."""
    tmp, out = ai_run()
    w = out / "work"
    facts = (w / "facts.txt").read_text()
    if coverage:
        parts = re.split(r"(?m)^(## \S+)\n", facts)
        text = parts[0]
        for h, body in zip(parts[1::2], parts[2::2]):
            text += h + "\n" + body.rstrip("\n") + "\n" + COV_FACTS[h[3:]] + "\n\n"
        (w / "facts.txt").write_text(text)
    blk = lambda pairs: ("\n## Coverage\n" + "".join("%s: %s\n" % kv for kv in pairs)) if blocks else ""
    (w / "reader.md").write_text("# Reader report\n\n1. **PDF author** ...\n2. **Caption** ...\n" + blk(
        [("pages_viewed", 2), ("figures_viewed", 1), ("tables_checked", 2), ("crossrefs_checked", 6),
         ("bib_entries_looked_up", 3), ("venue_rules_checked", "not counted")]))
    (w / "numbers.md").write_text("1. **2.3 vs 2.4** ...\n" + blk(
        [("numbers_checked", 34), ("derived_values_recomputed", 8), ("claims_traced", 5), ("tables_checked", 2),
         ("table_cells_checked", 48)]))
    (w / "candidates.md").write_text("sections/intro.tex:4 | Many system solve it. | system | 4 | systems\n"
                                     "sections/intro.tex:4 | We use a old index. | a old | 3 | an old\n"
                                     "sections/intro.tex:10 | three encoder | encoder | 4 | encoders\n" + blk(
                                         [("chunks_read", 2), ("sentences_read", 41), ("flags", 3)]))
    (w / "typos.md").write_text("sections/intro.tex:4 | a old | an old | a/an | certain\n"
                                "sections/intro.tex:10 | three encoder | three encoders | number | likely\n" + blk(
                                    [("flags_judged", 3), ("kept_certain", 1), ("kept_likely", 1), ("dropped", 1)]))
    r = run(STATS, out)
    assert r.returncode == 0, r.stdout + r.stderr
    return tmp, out, json.loads((w / "checks.json").read_text()), r.stdout


class CheckStats(unittest.TestCase):
    """check_stats.py: every count from a file of the run or the sources, never "not counted"; rows linked to report
    items."""

    @staticmethod
    def rows(ck):
        return {ch["id"]: ch for c in ck["categories"] for ch in c["checks"]}

    def no_empty(self, ck):
        """No statistic without a value, no row without an amount, "not counted" nowhere (pdf-layout.md)."""
        for s in ck["stats"]:
            self.assertIsInstance(s["value"], int, s)
            self.assertIn(s["basis"], ("measured", "in scope", "estimate", "counted from outputs"), s)
            if s["basis"] == "estimate":
                self.assertTrue(s["method"], s)
        for c in ck["categories"]:
            for ch in c["checks"]:
                if ch["status"] != "not_checked":
                    self.assertTrue(ch["amount"].strip(), ch)
        self.assertNotIn("not counted", json.dumps({k: ck[k] for k in ("stats", "categories")}))
        self.assertEqual([s["rank"] for s in ck["stats"]], sorted(s["rank"] for s in ck["stats"]))

    def test_measured(self):
        tmp, out, ck, _ = stats_run()
        self.addCleanup(shutil.rmtree, tmp, True)
        self.no_empty(ck)
        st = {s["id"]: s for s in ck["stats"]}
        self.assertEqual((st["pages"]["value"], st["pages"]["text"], st["pages"]["basis"]),
                         (2, "640 words of PDF text; read by every checker", "measured"))
        self.assertEqual(st["refs"]["value"], 3)
        self.assertEqual(st["bib_style"]["text"], "of 2 in the .bib; 12 features")
        self.assertEqual(st["links"]["text"], "of 3 in the paper")
        # a Coverage block replaces the scope: "34 numbers checked, of 10 in the text and tables"
        self.assertEqual((st["numbers"]["value"], st["numbers"]["basis"], st["numbers"]["text"]),
                         (34, "measured", "of 10 in the text and tables; 8 values recomputed"))
        self.assertEqual((st["claims"]["label"], st["claims"]["value"]), ("claims traced", 5))
        self.assertEqual((st["sentences"]["value"], st["sentences"]["text"]), (41, "of 17 in the paper; 3 flagged, "
                                                                                   "2 kept"))
        self.assertEqual(st["crossrefs"]["text"], "6 cross-references; 5 citations of 3 keys")
        self.assertEqual(st["objects"]["text"], "1 table float, 1 figure; 1 tabular environment; 1 display equation; "
                                                "in scope of the reader")
        self.assertEqual(st["flags"]["text"], "1 certain; 1 likely; verifier")
        self.assertEqual(st["venue"]["value"], 4)                      # rules of venue-status.json
        self.assertEqual(st["fonts"]["text"], "of 9")
        self.assertEqual(st["checkers"]["text"], "3 agents + 3 scripts")   # duplicates merged: unknown, left out
        self.assertEqual([s["id"] for s in ck["stats"][:8]],
                         ["pages", "numbers", "claims", "sentences", "refs", "crossrefs", "objects", "venue"])
        self.assertEqual(ck["checkers"]["reader"]["block"]["venue_rules_checked"], None)    # "not counted" in block
        rows = self.rows(ck)
        self.assertIn("34 numbers checked", rows["numbers_agent"]["amount"])
        self.assertEqual(rows["numbers_agent"]["items"], [3, 8, 14, 20])     # section 3 of the report
        self.assertEqual(rows["verifier"]["amount"], "3 flags judged; 1 kept certain; 1 kept likely; 1 dropped")
        self.assertEqual(rows["figures_agent"]["amount"], "1 figure viewed; 2 tables checked; 2 pages viewed")
        self.assertEqual(rows["venue_rules"]["items"], [21])
        # script rows: findings of facts.txt linked to the items at their location; nothing found otherwise
        self.assertEqual(rows["notes"]["status"], "ok")
        self.assertEqual(rows["refs_db"]["status"], "problems")
        self.assertIn(18, rows["refs_db"]["items"])                    # quokka2019, the unverified reference
        linked = {i for c in ck["categories"] for ch in c["checks"] for i in ch["items"]}
        self.assertEqual(linked, set(range(1, 22)))

    def test_in_scope_without_blocks(self):
        # no COVERAGE lines, no Coverage blocks: the scope of each checker, measured on the sources, and the
        # counts of the output files; nothing unknown is shown
        tmp, out, ck, msg = stats_run(coverage=False, blocks=False)
        self.addCleanup(shutil.rmtree, tmp, True)
        self.no_empty(ck)
        st = {s["id"]: s for s in ck["stats"]}
        for sid in ("pages", "refs", "links", "cells", "reader_bib", "viewed", "fonts", "warnings", "crossrefs"):
            self.assertNotIn(sid, st, sid)                               # no file gives them: left out
        self.assertEqual((st["numbers"]["value"], st["numbers"]["basis"], st["numbers"]["text"]),
                         (10, "in scope", "6 in the text; 4 in table cells; in scope of the numbers checker"))
        self.assertEqual((st["claims"]["value"], st["claims"]["basis"]), (5, "estimate"))
        self.assertIn("comparison word", st["claims"]["method"])
        self.assertEqual((st["sentences"]["value"], st["sentences"]["basis"]), (17, "in scope"))
        self.assertEqual((st["flags"]["value"], st["flags"]["basis"]), (3, "counted from outputs"))
        self.assertEqual(ck["scope"]["table_cells"], 4)
        rows = self.rows(ck)
        self.assertEqual(rows["numbers_agent"]["amount"],
                         "6 numbers in the text; 4 table cells; 5 comparative statements* (in scope)")
        self.assertEqual(rows["numbers_agent"]["basis"], "in scope")
        self.assertEqual(rows["finder"]["amount"], "17 sentences; 9 paragraphs (in scope); 3 flags")
        self.assertEqual(rows["verifier"]["amount"], "3 flags given; 1 kept certain; 1 kept likely; 1 dropped")
        self.assertEqual(rows["verifier"]["basis"], "counted from outputs")
        self.assertEqual(ck["checkers"]["reader"]["derived"], {"problems_reported": 2})
        self.assertIn("no COVERAGE line", msg)
        self.assertIn("no Coverage block", msg)

    def test_not_checked(self):
        tmp, out = run_fixture()                        # no facts.txt, no checker files, no ai-traces.json
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run(STATS, out)
        self.assertEqual(r.returncode, 0, r.stderr)
        ck = json.loads((out / "work" / "checks.json").read_text())
        self.no_empty(ck)
        rows = self.rows(ck)
        self.assertEqual((rows["refs_db"]["status"], rows["refs_db"]["reason"]), ("not_checked",
                                                                                 "no refs_check output"))
        self.assertEqual(rows["log"]["status"], "not_checked")
        self.assertEqual(rows["ai_all"]["status"], "not_checked")
        self.assertEqual(rows["finder"]["status"], "not_checked")
        self.assertEqual(rows["verifier"]["status"], "problems")         # items of section 5 count all the same
        self.assertIn("items from report.md", rows["verifier"]["reason"])
        # only what the sources and venue-status.json give
        self.assertEqual({s["basis"] for s in ck["stats"]} - {"in scope", "estimate", "measured"}, set())
        self.assertIn("venue", {s["id"] for s in ck["stats"]})


class ScopeStats(unittest.TestCase):
    """scope_stats.py: deterministic counts of what the paper puts in front of the checkers."""

    PAPER = r"""\documentclass{article}
\begin{document}
\section{Results}\label{sec:res}
Our index is 1.9$\times$ faster than the baseline and uses 35\% less memory (Table~\ref{tab:a}).
We ran 3 seeds in 2024 on AVX-512 with BM25, see Section~\ref{sec:res} and $x_1$.

It is the best method, e.g. on MS MARCO. The recall is $0.93$ in Figure~\ref{fig:a}.
\begin{equation} y = 2x + 1 \end{equation}
\begin{align} a &= 1 \\ b &= 2 \end{align}
\begin{table}\centering
\begin{tabular}{lrr}
\toprule System & QPS & Recall \\ \midrule
Ours & \textbf{1,024} & 0.93 \\
Base & 512 & -- \\ \bottomrule
\end{tabular}
\caption{Results.}\label{tab:a}
\end{table}
\begin{figure}\centering\rule{1cm}{1cm}\caption{A plot.}\label{fig:a}\end{figure}
% 99 numbers in a comment are not counted
\bibliography{refs}
\end{document}
"""

    def test_counts(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="scope-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "main.tex").write_text(self.PAPER)
        (tmp / "refs.bib").write_text("@string{x = {y}}\n@article{a, title={A}}\n@inproceedings{b, title={B}}\n")
        sc = load(SKILL / "scripts" / "scope_stats.py", "scope_stats")
        m = sc.measure(tmp / "main.tex")
        # 1.9x, 35%, 3 (not 2024, 512 of AVX-512, 25 of BM25, x_1), 0.93
        self.assertEqual(m["numbers_text"], 4)
        self.assertEqual((m["table_cells"], m["table_cells_all"], m["tabulars"]), (3, 9, 1))
        self.assertEqual((m["tables"], m["figures"], m["equations"]), (1, 1, 3))
        self.assertEqual(m["sentences"], 5)                 # "e.g." does not end a sentence
        self.assertEqual(m["claims"], 2)                    # faster/than/%, best
        self.assertEqual(m["cited_numbers"], 3)             # 1.9x, 35% (Table) and 0.93 (Figure)
        self.assertEqual(m["bib_entries"], 2)
        self.assertEqual(sc.measure(tmp / "main.tex"), m)   # deterministic


    def test_coverage_lines(self):
        self.assertEqual(load(SKILL / "scripts" / "form_check.py", "form_check").coverage_line({"pages": 3, "words": 9}),
                         "COVERAGE | pages=3 | words=9")
        r = run(BIB_STYLE, FIX / "run" / "work" / "paper" / "references.bib")
        last = r.stdout.strip().split("\n")[-1]
        self.assertRegex(last, r"^COVERAGE \| entries_compared=\d+ \| features=\d+ \| venues_compared=\d+ \| "
                               r"differences=\d+$")
        r = run(BIB_STYLE, FIX / "run" / "work" / "paper" / "references.bib", "--json")
        self.assertIn("coverage", json.loads(r.stdout))

    def test_prompts_ask_for_coverage(self):
        for agent, key in (("reader-agent", "bib_entries_looked_up"), ("numbers-agent", "table_cells_checked"),
                           ("typos-finder", "sentences_read"), ("typos-verifier", "kept_likely"),
                           ("merge-agent", "duplicates_merged")):
            text = (SKILL / "references" / (agent + ".md")).read_text()
            self.assertIn("## Coverage", text, agent)
            self.assertIn("`%s`" % key, text, agent)


class PageOrder(unittest.TestCase):
    """front_pages.py: the summary, then Decisions for you, Venue rules, What we checked, Traces of AI use, then the
    paper (references/pdf-layout.md); the numbers of the summary reconcile with the thematic pages."""

    def front_run(self):
        tmp, out, ck, _ = stats_run()
        self.addCleanup(shutil.rmtree, tmp, True)
        w = out / "work"
        r = run(APPLY, w / "edits.json", w / "paper", out / "corrected", w / "marked", "--log", w / "edits.tsv")
        self.assertEqual(r.returncode, 0, r.stderr)
        return tmp, out, w, ck

    def test_order_and_page(self):
        tmp, out, w, ck = self.front_run()
        f = tmp / "front.tex"
        r = run(FRONT, "--final-dir", FINAL, out, w / "marked" / "main.tex", "--out", f, "--date", "2026-11-10")
        self.assertEqual(r.returncode, 0, r.stderr)
        t = f.read_text()
        self.assertEqual(re.findall(r"\\begin\{rrfullpage\}\[([\w-]+)\]", t)[:2], ["cover", "venue"])
        ids = re.findall(r"\\begin\{rrfullpage\}\[([\w-]+)\]", t)
        self.assertEqual([i for i in ids if not i.startswith("bib")], ["cover", "venue", "decisions-1", "checks", "ai"])
        self.assertLess(t.index("rrfullpage}[ai]"), t.index(r"\rrbeginpaper"))
        self.assertNotIn("not counted", t)
        pages = split_pages(t)
        # every page: the navigation to the others and to the paper, a title, its anchor and label
        npages = len([1 for k in ("cover", "venue", "bib", "decisions-1", "checks", "ai") if k in pages])
        for pid, cur in (("cover", "SUMMARY"), ("decisions-1", "DECISIONS"), ("venue", "VENUE RULES"),
                         ("checks", "WHAT WE CHECKED"), ("ai", "AI USE")):
            nav = pages[pid][:pages[pid].index(r"\vspace")]
            self.assertIn(r"\rrFnavon{%s}" % cur, nav, pid)
            self.assertEqual(nav.count(r"\hyperlink{"), npages, pid)
            self.assertIn(r"\hyperlink{page.1}{PAPER}", nav, pid)
        for anchor in ("rr-cover", "rr-decisions", "rr-venue", "rr-checks", "rr-aitraces"):
            self.assertEqual(t.count(r"\hypertarget{%s}{}\label{rrF-%s}" % (anchor, anchor)), 1, anchor)
        cover = pages["cover"]
        # the summary: one row of depth statistics chosen by id, with its link to the checks page
        self.assertIn("How deep we looked", cover)
        for s in ("pages of the original PDF read", "references checked against databases", "numbers checked",
                  "sentences read by the proofreader", "venue rules judged", "independent checkers"):
            self.assertIn(s, cover, s)
        self.assertNotIn("tables and figures", cover)                      # only on the checks page
        self.assertIn(r"\hyperlink{rr-checks}{\textbf{What we checked}}, p.~\hyperlink{rr-checks}", cover)
        # the apply box with its strip, the most important errors (desk-reject first) with their boxes
        self.assertIn("How to apply the changes", cover)
        self.assertIn(r"\rrFstrip", cover)
        self.assertIn(r"Apply my choices in {\urlstyle{tt}\path{%s/changes.pdf}}" % FINAL, cover)
        self.assertIn("corrected/ next to this PDF already holds the pre-set choices", cover)
        self.assertIn(r"\rrFheadl{Most Important Errors}", cover)
        errs = re.findall(r"\\makebox\[24pt\]\[l\]\{\\rrFitem\{(\d+)\}\}", cover)
        self.assertEqual(errs[0], "21")                                    # section 2 (desk-reject) first
        self.assertNotIn("THE FILES OF THIS CHECK", cover)
        # numbers reconcile: need you = the rows (and boxes) of the decision sheet
        need = int(re.search(r"\\rrFbig\{(\d+)\}\{\\hyperlink\{rr-decisions\}\{need you\}\}", cover).group(1))
        self.assertEqual(need, len(re.findall(r"\\rrFdrow\{(?:rrband|white)\}[^\n]*\\rrFitem", pages["decisions-1"])))
        self.assertIn(r"\textbf{%d items}, in the order of the paper" % need, pages["decisions-1"])
        line = load(FRONT, "front_pages").checks_line(ck, range(1, 22), 21)
        self.assertIn(line, pages["checks"])
        self.assertIn("together they raised all 21 items of report.md", line)
        # every category of What we checked says the reviewer pretext it prevents
        for sub in ("Avoid Desk Reject", "Avoid Easy Reject for Wrong References", "Avoid `written by ChatGPT'"):
            self.assertIn(sub, pages["checks"], sub)
        self.assertIn(r"Venue rules\,{\mdseries ---\,Avoid Desk Reject}", pages["venue"])
        page = pages["checks"]
        for s in ("Venue rules", "Language (typos and grammar)", "AI-use artifacts", "independent checkers",
                  r"\rrFitem{21}", "34 numbers checked", "nothing found", "pages of the original PDF read",
                  "tables and figures", r"\rrFpass", "3 from the other checkers"):
            self.assertIn(s, page, s)
        # split over two pages on request (build_changes.py asks when the page overflows at level 0): the second
        # page continues the first under its title
        fp = load(FRONT, "front_pages")
        nav = [(k, a, fp.NAV[k]) for k, a, _ in fp.PAGES]
        two = fp.checks_tex(ck, 21, nav, split=True)
        self.assertEqual(two.count(r"\begin{rrfullpage}"), 2)
        self.assertIn(r"\rrFcont{What we checked (continued)}{page 2 of 2}", two)
        # levels: the cover lists fewer errors at a lower level but keeps the apply box; the venue table gains quotes
        r = run(FRONT, "--final-dir", FINAL, out, w / "marked" / "main.tex", "--out", f, "--level", "cover=0", "--level", "venue=4")
        self.assertEqual(r.returncode, 0, r.stderr)
        p0 = split_pages(f.read_text())
        self.assertEqual(len(re.findall(r"\\makebox\[24pt\]\[l\]\{\\rrFitem", p0["cover"])), 3)
        self.assertIn("How to apply the changes", p0["cover"])
        self.assertIn("and its words in the guide", p0["venue"])

    def test_venue_split(self):
        tmp, out, w, ck = self.front_run()
        fp = load(FRONT, "front_pages")
        nav = [(k, a, fp.NAV[k]) for k, a, _ in fp.PAGES]
        rules = [dict(id="r%d" % i, rule="Rule %d" % i, status=("violated", "met", "unknown", "confirm")[i % 4],
                      items=[], note="note", source="UNKNOWN") for i in range(9)]
        vs = {"rules": rules, "blocked": []}
        tex = fp.venue_page(vs, "WOMCON", {}, nav, 0, split=True)
        pages = split_pages(tex)
        self.assertEqual(list(pages), ["venue", "venue-2"])
        self.assertIn(r"\rrFcont{Venue rules\,{\mdseries ---\,Avoid Desk Reject} (continued)}{page 2 of 2}", pages["venue-2"])
        rows = lambda p: len(re.findall(r"\\rrFrowe\{(?:rrband|white)\}\{\\rrF", p))
        self.assertEqual((rows(pages["venue"]), rows(pages["venue-2"])), (5, 4))
        self.assertIn("9 RULES", pages["venue"])                             # counts of all rules, on page 1
        self.assertNotRegex(pages["venue-2"], r"\d+ RULES")
        self.assertIn("Source caveat", pages["venue"])
        self.assertNotIn("Source caveat", pages["venue-2"])
        self.assertIn("meets the rule", pages["venue-2"])                    # legend once, at the end
        self.assertNotIn("meets the rule", pages["venue"])

    def test_rejects_bad_checks(self):
        tmp, out, w, ck = self.front_run()
        ck["categories"][0]["checks"][0]["items"] = [99]
        ck["categories"][0]["checks"][1]["status"] = "fine"
        ck["categories"][1]["checks"][0]["amount"] = "not counted"
        ck["categories"][1]["checks"][1]["amount"] = ""
        ck["stats"][0]["value"] = None
        ck["stats"][1]["text"] = "not counted"
        ck["stats"][2]["basis"] = "estimate"
        ck["stats"][2]["method"] = ""
        (w / "checks.json").write_text(json.dumps(ck))
        r = run(FRONT, "--final-dir", FINAL, out, w / "marked" / "main.tex", "--out", tmp / "f.tex")
        self.assertEqual(r.returncode, 1)
        for msg in ("item 99 is not an item of report.md", "status must be one of",
                    "empty statistic (value None): leave the statistic out", 'empty or "not counted" text',
                    "an estimate needs its method", "empty amount cell ('not counted')", "empty amount cell ('')"):
            self.assertIn(msg, r.stderr)

    def test_fill(self):
        fp = load(FRONT, "front_pages")
        log = ("rrfront fill: id=cover page=i natural=650.0pt full=680.0pt\n"
               "rrfront fill: id=venue page=ii natural=340.0pt full=680.0pt\n"
               "rrfront fill: id=checks page=iii natural=700.0pt full=680.0pt\n"
               "rrfront fill: id=decisions-2 page=vi natural=600.0pt full=680.0pt\n")
        fills = fp.fill_of(log)
        self.assertEqual([(f["id"], f["key"], round(f["ratio"], 2)) for f in fills],
                         [("cover", "cover", 0.96), ("venue", "venue", 0.5), ("checks", "checks", 1.03),
                          ("decisions-2", "decisions", 0.88)])
        w = fp.fill_warnings(fills)
        self.assertEqual(len(w), 2)
        self.assertIn("front page ii (venue) is only 50% full", w[0])
        self.assertIn("front page iii (checks) overflows", w[1])

    @unittest.skipUnless(HAVE_TEX, "pdflatex not installed")
    def test_fill_measured_by_latex(self):
        # r2changes.sty writes the natural height of every front page to the log; a page that fits is stretched
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="fill-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        shutil.copy(STY, tmp / "r2changes.sty")
        (tmp / "main.tex").write_text(
            "\\documentclass{article}\\usepackage[front]{r2changes}\\begin{document}\\rrbeginfront\n"
            "\\begin{rrfullpage}[half]\\rule{1pt}{300pt}\\rrFgap{0pt}x\\end{rrfullpage}\n"
            "\\begin{rrfullpage}[over]\\rule{1pt}{2000pt}\\end{rrfullpage}\n"
            "\\rrbeginpaper Paper.\\end{document}\n")
        errs, log = pdflatex(tmp, runs=1)
        self.assertEqual(errs, [])
        fills = {f["id"]: f for f in load(FRONT, "front_pages").fill_of(log)}
        self.assertEqual(set(fills), {"half", "over"})
        self.assertLess(fills["half"]["ratio"], 0.8)
        self.assertGreater(fills["over"]["ratio"], 1.0)
        self.assertIn("Front page too tall", log)

    def test_open_flag_parsed(self):
        bc = load(BUILD, "build_changes")
        self.assertTrue(bc.parse_args(["out", "--open"]).open)
        self.assertFalse(bc.parse_args(["out"]).open)



class Choices(unittest.TestCase):
    """apply_edits.py: one check box per item, pre-set from the kind and the confidence of its edits."""

    def defaults(self, spec):
        ae = load(APPLY, "apply_edits_d")
        return ae.item_defaults([ae.Edit(i, d) for i, d in enumerate(spec)])

    def test_defaults_by_kind_and_confidence(self):
        st = self.defaults([
            {"item": 1, "kind": "fix"}, {"item": 2, "kind": "raw"},
            {"item": 3, "kind": "check"}, {"item": 4, "kind": "check", "confidence": "low"},
            {"item": 5, "kind": "style"}, {"item": 6, "kind": "style", "confidence": "high"},
            {"item": 7, "kind": "missing"}, {"item": 8, "kind": "note"}, {"item": 9, "kind": "log"},
            {"item": 10, "kind": "fix"}, {"item": 10, "kind": "missing"},
            {"item": 11, "kind": "fix", "confidence": "medium"}, {"item": 11, "kind": "style"}])
        self.assertEqual({n: (t, ro) for n, (t, ro, _) in st.items()},
                         {1: (True, False), 2: (True, False), 3: (True, False), 4: (False, False),
                          5: (False, False), 6: (True, False), 7: (False, True), 10: (False, True),
                          11: (False, False)})          # 10: a fix plus missing facts waits for the facts (M3)
        self.assertEqual(st[1][2], "default: do -- certain fix")
        self.assertEqual(st[3][2], "default: do -- likely right, to confirm")
        self.assertEqual(st[5][2], "default: don't -- optional wording")
        self.assertEqual(st[4][2], "default: don't -- low confidence")
        self.assertEqual(st[7][2], "needs your facts first")
        self.assertEqual(st[10][2], "needs your facts first")

    def test_bad_confidence(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="conf-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "spec.json").write_text(json.dumps([{"item": 1, "file": "sections/intro.tex", "kind": "fix",
                                                     "old": "a old", "new": "an old", "confidence": "sure"}]))
        r = run(APPLY, tmp / "spec.json", FIX / "paper", tmp / "c", tmp / "m")
        self.assertEqual(r.returncode, 1)
        self.assertIn("confidence must be high, medium or low", r.stderr)


class SummaryPage(unittest.TestCase):
    """The summary always carries the apply box and its strip, whatever the number of items and rules."""

    def test_apply_box_on_every_level(self):
        fp = load(FRONT, "front_pages")
        n = 400
        report = {"sections": [(2, "Desk-reject risks", list(range(1, 41))), (3, "Numbers and claims",
                                                                           list(range(41, 201))),
                               (4, "Other reviewer-visible problems", list(range(201, n + 1)))],
                  "questions": {}, "first": [], "items": set(range(1, n + 1)),
                  "texts": {i: "`a.tex:%d`: a long description of problem %d. Fix: x." % (i, i) for i in range(1, n + 1)}}
        report["all_sections"] = report["sections"]
        report["severity"] = {i: "desk-reject" if i <= 40 else "major" for i in report["items"]}
        report["order"] = sorted(report["items"])
        cls = {i: ("facts" if i <= 60 else "fixed", [], []) for i in report["items"]}
        rules = [dict(id="r%d" % i, rule="Rule %d" % i, status="violated", items=[i], note="", source="UNKNOWN")
                 for i in range(1, 61)]
        ctx = dict(title="T", authors="A", venue_name="V", total=n, counts=fp.item_counts(report["items"], cls),
                   need=0, na=[], report=report, cls=cls, vs={"rules": rules, "blocked": []}, checks=None, ai=None,
                   decide=[], bib=None, states={i: (True, False, "x") for i in range(1, n + 1)}, links={},
                   per_page={p: p % 7 for p in range(1, 300)}, paper_start=5, pdf="/x/changes.pdf")
        nav = [(k, a, fp.NAV[k]) for k, a, _ in fp.PAGES]
        for level in range(len(fp.COVER_DENS)):
            t = fp.cover_tex(ctx, level, nav)
            self.assertIn("How to apply the changes", t, level)
            self.assertIn(r"\rrFstrip", t, level)
            self.assertIn(r"Apply my choices in {\urlstyle{tt}\path{/x/changes.pdf}}", t, level)
            shown = len(re.findall(r"\\makebox\[24pt\]\[l\]\{\\rrFitem", t))
            self.assertEqual(shown, fp.COVER_DENS[level]["errors"])
            self.assertIn("%d of %d" % (shown, n), t)
        # only real desk-reject risks count: the 40 items of severity desk-reject, not the 60 rules judged violated
        self.assertIn("40 desk-reject risks open in the copy", fp.cover_tex(ctx, 0, nav))



def nested_run():
    """The run fixture with its root in a subfolder (work/paper/tex/main.tex) that inputs files of the folder above
    (../sections/intro, ../references): latexmk must run in the root's folder."""
    tmp, out = run_fixture()
    paper = out / "work" / "paper"
    (paper / "tex").mkdir()
    main = (paper / "main.tex").read_text()
    main = main.replace(r"\input{sections/", r"\input{../sections/").replace(r"\bibliography{references}",
                                                                           r"\bibliography{../references}")
    (paper / "tex" / "main.tex").write_text(main)
    (paper / "main.tex").unlink()
    p = out / "work" / "edits.json"
    spec = json.loads(p.read_text())
    for e in spec:
        for k in ("file", "note_file"):
            if e.get(k) == "main.tex":
                e[k] = "tex/main.tex"
    p.write_text(json.dumps(spec))
    return tmp, out


@unittest.skipUnless(HAVE_LATEXMK, "latexmk, pdflatex or pdfinfo not installed")
class NestedRoot(unittest.TestCase):
    """--root tex/main.tex: the root in a subfolder, its \\input paths relative to that folder (latexmk -cd)."""

    def test_build(self):
        tmp, out = nested_run()
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run(BUILD, "--final-dir", FINAL, out, "--root", "tex/main.tex", "--date", "2026-11-10", "--no-png")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("pages 2 -> 2", r.stdout)
        self.assertIn("OK: build", r.stdout)
        self.assertTrue((out / "work" / "tmp" / "build-corrected" / "tex" / "main.pdf").is_file())
        self.assertTrue((out / "work" / "marked" / "tex" / "main.pdf").is_file())
        self.assertTrue((out / "work" / "marked" / "tex" / "r2states.tex").is_file())
        self.assertIn(r"\rrfix{18}", (out / "work" / "marked" / "tex" / "main.bbl").read_text())


class Consistency(unittest.TestCase):
    """B1-B3, M1-M4: one build, nothing invented, real paths, one severity, disabled boxes for facts."""

    def apply(self, spec, *extra):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="step6c-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "spec.json").write_text(json.dumps(spec))
        return tmp, run(APPLY, tmp / "spec.json", FIX / "paper", tmp / "c", tmp / "m", "--log", tmp / "log.tsv",
                        *extra)

    def test_invented_text_is_flagged(self):
        # a mechanism ("early-exit filter") and a causal clause added to a to-check wording
        spec = [{"item": 3, "file": "sections/intro.tex", "kind": "check", "old": "$2.3\\times$",
                 "new": "$2.4\\times$ (thanks to its early-exit filter, 7.7 times)",
                 "question": "Is it 2.3 or 2.4? Table 1 gives 2.4."}]
        tmp, r = self.apply(spec)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("'early-exit'", r.stdout)
        self.assertIn("numbers not in the paper nor computed in the note or question: 7.7", r.stdout)
        self.assertIn("a causal explanation ('thanks to')", r.stdout)
        self.assertNotIn("2.4", r.stdout.split("numbers not in the paper")[1].split(";")[0])   # 2.4 is in the question
        tmp, r = self.apply(spec, "--strict")
        self.assertEqual(r.returncode, 1)
        self.assertIn("move explanations and mechanisms to the question or the note", r.stderr)
        self.assertFalse((tmp / "c").exists())
        # restating the paper is fine
        ok = [{"item": 3, "file": "sections/intro.tex", "kind": "check", "old": "$2.3\\times$", "new": "$2.4\\times$",
               "question": "Is it 2.3 or 2.4? Table 1 gives 2.4."}]
        tmp, r = self.apply(ok, "--strict")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("new text adds", r.stdout)

    def test_submission_file_is_a_note(self):
        spec = [{"item": 1, "file": "sections/intro.tex", "kind": "missing", "ctx": "scanned in parallel@@.",
                 "what": "Highlights (3-5 bullets) as a separate file"}]
        tmp, r = self.apply(spec)
        self.assertIn("placeholder about a submission file (Highlights)", r.stdout)

    def test_facts_box_disabled_never_ticked(self):
        spec = [{"item": 4, "file": "sections/intro.tex", "kind": "fix", "old": "three encoder", "new": "three encoders"},
                {"item": 4, "file": "sections/intro.tex", "kind": "missing", "ctx": "scanned in parallel@@.",
                 "what": "number of threads"}]
        tmp, r = self.apply(spec)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(r"\rritemstate{4}{0}{1}{needs your facts first}", (tmp / "m" / "r2states.tex").read_text())
        c = (tmp / "c" / "sections" / "intro.tex").read_text()
        self.assertIn("three encoder.", c)                               # its fix waits for the facts
        self.assertIn("% TODO #4: number of threads", c)
        sty = STY.read_text()
        self.assertIn(r"\if1\csname rr@ro@#1\endcsname\rrboxsym{2}", sty)   # its own glyph
        self.assertIn(r"\rr@ibroglyph", sty)

    def test_question_repeated_at_far_marks(self):
        spec = [{"item": 3, "file": "sections/intro.tex", "kind": "check", "old": "$2.3\\times$", "new": "$2.4\\times$",
                 "question": "Is the saving 2.3 or 2.4? Table 1 gives 2.4.", "note": "Table 1 gives 2.4."},
                {"item": 3, "file": "sections/results.tex", "kind": "check", "old": "which is modest",
                 "new": "which is small", "question": "Same as in the introduction."}]
        tmp, r = self.apply(spec)
        self.assertEqual(r.returncode, 0, r.stderr)
        res = (tmp / "m" / "sections" / "results.tex").read_text()
        self.assertIn(r"\rrnote{3}{To check: Is the saving 2.3 or 2.4?}", res)
        intro = (tmp / "m" / "sections" / "intro.tex").read_text()
        self.assertEqual(intro.count(r"\rrnote"), 1)

    def test_apply_box_never_temporary(self):
        fp = load(FRONT, "front_pages")
        for p in ("/tmp/x/changes.pdf", tempfile.gettempdir() + "/r/changes.pdf",
                  "/Users/a/.claude/sessions/scratchpad/run-v10/changes.pdf"):
            self.assertTrue(fp.is_temporary(p), p)
        self.assertFalse(fp.is_temporary("/Users/a/paper/reviewer2-repellent/2026-11-09/changes.pdf"))
        tmp, out = run_fixture()
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run(BUILD, out, "--no-png")
        self.assertEqual(r.returncode, 1)
        self.assertIn("is a temporary folder", r.stderr)
        w = out / "work"
        r = run(APPLY, w / "edits.json", w / "paper", out / "corrected", w / "marked", "--log", w / "edits.tsv")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run(FRONT, out, w / "marked" / "main.tex", "--out", tmp / "f.tex")
        self.assertEqual(r.returncode, 1)
        self.assertIn("the apply box would name a temporary folder", r.stderr)

    def test_severity_ranks_and_venue(self):
        fp = load(FRONT, "front_pages")
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="step6sev-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        rp = tmp / "report.md"
        rp.write_text("# R\n\n## 1. Summary\n\nx\n\n## 2. Desk-reject risks\n\n"
                      "**1.** a. Severity: desk-reject. Checkers: reader.\n\n"
                      "**2.** cas-dc. Severity: optional. Checkers: reader.\n\n"
                      "## 3. Numbers and claims\n\n**3.** n. Severity: minor. Checkers: numbers.\n\n"
                      "**4.** m. Severity: major. Checkers: numbers.\n\n"
                      "## 4. Other reviewer-visible problems\n\n**5.** o. Severity: major. Checkers: reader.\n\n"
                      "**6.** p. Checkers: reader.\n\n## 6. Cosmetic\n\n**7.** acronyms. Severity: minor.\n\n"
                      "## 7. Appendix: possible language improvements\n\n8. `a.tex:1 | x | y`\n")
        rep = fp.parse_report(str(rp))
        self.assertEqual(rep["severity"], {1: "desk-reject", 2: "optional", 3: "minor", 4: "major", 5: "major",
                                           6: "major", 7: "minor", 8: "optional"})
        self.assertEqual(rep["severity_given"], {1, 2, 3, 4, 5, 7})
        # desk-reject, then major (numbers before other sections), then minor; optional left out; never by number
        self.assertEqual(fp.important_items(rep), [1, 4, 5, 6, 3])
        self.assertEqual(fp.desk_items(rep), [1])
        self.assertEqual(fp.effective_status({"status": "violated", "items": [2]}, rep), "confirm")
        self.assertEqual(fp.effective_status({"status": "violated", "items": [7]}, rep), "confirm")
        self.assertEqual(fp.effective_status({"status": "violated", "items": [1, 2]}, rep), "violated")
        self.assertEqual(fp.normalize_severity("reviewer-visible (minor)"), "minor")
        self.assertEqual(fp.normalize_severity("low (cas-dc is accepted)"), "minor")

    def test_within_rounding_questions_dropped(self):
        rs = load(SKILL / "scripts" / "report_sync.py", "report_sync")
        cases = json.loads((FIX / "rounding.json").read_text())
        for c in cases:
            self.assertEqual(rs.within_rounding(c["question"], c.get("item", "")), c["rounding"], c["question"])
        tmp, out = run_fixture()
        self.addCleanup(shutil.rmtree, tmp, True)
        w = out / "work"
        r = run(APPLY, w / "edits.json", w / "paper", out / "corrected", w / "marked", "--log", w / "edits.tsv")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run(SKILL / "scripts" / "report_sync.py", out, "--build-id", "abc123def456")
        self.assertIn("dropped the question of #8", r.stdout)
        t = (out / "report.md").read_text()
        self.assertNotIn("- **8**:", t)
        self.assertIn("- **20**:", t)                           # one number only: not a rounding question
        self.assertIn("Build: `abc123def456`", t)
        self.assertNotIn("work/edits.tsv", t)


class ReportSync(unittest.TestCase):
    def test_counts_and_names(self):
        tmp, out = run_fixture()
        self.addCleanup(shutil.rmtree, tmp, True)
        w = out / "work"
        r = run(APPLY, w / "edits.json", w / "paper", out / "corrected", w / "marked", "--log", w / "edits.tsv")
        self.assertEqual(r.returncode, 0, r.stderr)
        rp = out / "report.md"
        t = rp.read_text().replace("Fix first:", "In the corrected copy: 99 fixed.\n\nOpen changes-v3.pdf.\n\nFix first:", 1)
        rp.write_text(t)
        r = run(SKILL / "scripts" / "report_sync.py", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        t2 = rp.read_text()
        self.assertNotIn("99 fixed", t2)
        self.assertIn("In the corrected copy: 10 fixed, 5 applied but to confirm", t2)
        self.assertIn("Check boxes in changes.pdf:", t2)
        self.assertNotIn("changes-v3.pdf", t2)
        self.assertIn("file names changes-v3.pdf -> changes.pdf", r.stdout)
        r = run(SKILL / "scripts" / "report_sync.py", out)                 # idempotent
        self.assertIn("counts already follow", r.stdout)


class FlagsAndCoverage(unittest.TestCase):
    def test_type3_fonts_flagged_without_items(self):
        tmp, out, ck, _ = stats_run()
        self.addCleanup(shutil.rmtree, tmp, True)
        f = out / "work" / "facts.txt"
        t = f.read_text().replace("## form_check\n", "## form_check\nINFO | Type 3 fonts in figure | imgs/arch.pdf | "
                                                       "some publishers reject Type 3 fonts\n", 1)
        f.write_text(t)
        r = run(STATS, out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ck = json.loads((out / "work" / "checks.json").read_text())
        row = {ch["id"]: ch for c in ck["categories"] for ch in c["checks"]}["fonts"]
        self.assertEqual((row["status"], row["items"], row["flags"]), ("flagged", [], 1))
        venue = {ch["id"]: ch for c in ck["categories"] for ch in c["checks"]}["venue_rules"]
        self.assertIn("cannot tell", venue["amount"])
        refs = {s["id"]: s for s in ck["stats"]}["refs"]
        self.assertEqual(refs["label"], "references checked against databases")


if __name__ == "__main__":
    unittest.main(verbosity=2)
