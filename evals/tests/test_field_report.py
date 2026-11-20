#!/usr/bin/env python3
"""Regression tests for five problems reported by an end-user run (2026-11-12), on invented fixtures written inline:
1. mark_bbl.py reads acmart's \\bibitem[label]%<newline>{key};
2. a mark whose text holds a line break (\\\\) compiles inside a TikZ node (apply_edits.py marks it line by line);
3. margin notes with structural LaTeX commands are rejected by apply_edits.py, naming the item;
4. ai_traces.parse_facts reads `## form_check.py` as `## form_check`, and SKILL.md names the exact headings;
5. the typos finder logs chunk_lines_max and SKILL.md reruns a finder that read blocks over 60 lines.

Run: python3 -I evals/tests/test_field_report.py      (compile tests are skipped if pdflatex is missing)
"""
import importlib.util
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "reviewer2-repellent"
SCRIPTS = SKILL / "scripts"
HAVE_TEX = shutil.which("pdflatex") is not None and shutil.which("kpsewhich") is not None
HAVE_TIKZ = HAVE_TEX and subprocess.run(["kpsewhich", "tikz.sty"], capture_output=True, text=True).stdout.strip() != ""


def load(name):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(*args):
    return subprocess.run([sys.executable, "-I", *map(str, args)], capture_output=True, text=True)


def tmpdir(test):
    d = pathlib.Path(tempfile.mkdtemp(prefix="r2field-"))
    test.addCleanup(shutil.rmtree, d, True)
    return d


def pdflatex(folder, main="main.tex", runs=3):
    for _ in range(runs):
        subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", main],
                       cwd=folder, capture_output=True)
    log = (pathlib.Path(folder) / main).with_suffix(".log").read_text(encoding="latin-1")
    return [ln for ln in log.splitlines() if ln.startswith("!")]


# ---------------------------------------------------------------- 1. acmart \bibitem
ACM_BBL = r"""\begin{thebibliography}{2}
\providecommand\bibfield[2]{#2}
\providecommand\bibinfo[2]{#2}

\bibitem[Burrow et~al\mbox{.}(2020)]%
        {burrow2020}
\bibfield{author}{\bibinfo{person}{Ada Burrow} {and} \bibinfo{person}{Ben Digger}.} \bibinfo{year}{2020}.
\newblock \bibinfo{title}{Fast Wombat Search}.

\bibitem %
  [Hopper(2019)]%
        {hopper2019}
\bibfield{author}{\bibinfo{person}{Cara Hopper}.} \bibinfo{year}{2019}.
\newblock \bibinfo{journal}{\emph{Journal of Marsupial Computing}}, \bibinfo{pages}{5--20}.

\end{thebibliography}
"""


class AcmartBibitem(unittest.TestCase):
    def test_parse(self):
        mb = load("mark_bbl")
        d = tmpdir(self)
        (d / "a.bbl").write_text(ACM_BBL)
        _, entries, _ = mb.parse(str(d / "a.bbl"))
        self.assertEqual([(k, lab) for k, lab, _ in entries],
                         [("burrow2020", r"Burrow et~al\mbox{.}(2020)"), ("hopper2019", "Hopper(2019)")])

    def test_mark(self):
        d = tmpdir(self)
        (d / "orig.bbl").write_text(ACM_BBL)
        (d / "corr.bbl").write_text(ACM_BBL.replace("{5--20}", "{5--21}"))
        (d / "map.json").write_text(json.dumps({"default_item": 7, "notes": {"7": "Pages as in the record."}}))
        r = run(SCRIPTS / "mark_bbl.py", d / "orig.bbl", d / "corr.bbl", d / "out.bbl", d / "map.json")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = (d / "out.bbl").read_text()
        self.assertIn(r"\bibitem[Hopper(2019)]{hopper2019}\rrnote{7}{Pages as in the record.}", out)
        self.assertIn(r"\bibitem[Burrow et~al\mbox{.}(2020)]{burrow2020}", out)
        self.assertRegex(out, r"\\rrfix\{7\}\{[^\n]*5--20[^\n]*\}\{[^\n]*5--21")


# ---------------------------------------------------------------- 2. and 3. apply_edits.py
PAPER = r"""\documentclass{article}
\usepackage{tikz}
\newcommand{\sys}{\textsc{Quokka}}
\begin{document}
\section{Wombats}\label{sec:w}
Ada Burrow studies wombats with \sys.

\begin{figure}\centering
\begin{tikzpicture}
\node[draw] (a) {Wombat burow};
\node[draw,align=center] at (4,0) {Quokka hops\\ quickly far};
\end{tikzpicture}
\caption{Two marsupials.}
\end{figure}
\end{document}
"""


class ApplyEditsField(unittest.TestCase):
    def setup_paper(self, spec):
        d = tmpdir(self)
        (d / "paper").mkdir()
        (d / "paper" / "main.tex").write_text(PAPER)
        (d / "spec.json").write_text(json.dumps(spec))
        r = run(SCRIPTS / "apply_edits.py", d / "spec.json", d / "paper", d / "c", d / "m")
        return d, r

    def test_tikz_marks(self):
        spec = [{"item": 1, "file": "main.tex", "kind": "fix", "old": "burow", "new": "burrow",
                 "ctx": "Wombat burow", "note": "Typo in the figure."},
                {"item": 2, "file": "main.tex", "kind": "check", "old": "hops\\\\ quickly far",
                 "new": "hops\\\\ quickly afar", "question": "Is afar meant?", "note": "Word in the figure."}]
        d, r = self.setup_paper(spec)
        self.assertEqual(r.returncode, 0, r.stderr)
        m = (d / "m" / "main.tex").read_text()
        self.assertIn(r"\node[draw] (a) {Wombat \rrfix{1}{burow}{burrow}};", m)
        # line by line, one tag, no group across the \\ (the TikZ node would not compile)
        self.assertIn(r"{Quokka {\color{rrorange}hops}\\{\color{rrorange} quickly afar}\rrtag{rrorange}{2}};", m)
        self.assertIn("line by line", r.stdout)
        self.assertIn(r"{Quokka hops\\ quickly afar};", (d / "c" / "main.tex").read_text())
        if HAVE_TIKZ:
            self.assertEqual(pdflatex(d / "m"), [])

    def test_note_commands(self):
        ok = [{"item": 1, "file": "main.tex", "kind": "fix", "old": "burow", "new": "burrow", "ctx": "Wombat burow",
               "note": r"See \ref{sec:w}: \texttt{wombat_2} in $x_1 \times 2$, \emph{as} in \sys \& 50%."}]
        d, r = self.setup_paper(ok)
        self.assertEqual(r.returncode, 0, r.stderr)
        if HAVE_TIKZ:
            self.assertEqual(pdflatex(d / "m"), [])
            # a broken note gives no LaTeX error, its box is just not drawn: check that it is
            self.assertIn(r"\rr@placed{1}", (d / "m" / "main.aux").read_text(encoding="latin-1"))
        for field, text, cmd in (("note", r"Use \verb|x| here.", r"\verb"),
                                 ("note", r"As in \citet{burrow2020}.", r"\citet"),     # no natbib in the paper
                                 ("note_short", r"Typo.\footnote{burrow}", r"\footnote"),
                                 ("note", r"Fixed \todo{check}.", r"\todo"),
                                 ("note", r"Fixed. \begin{itemize}\item a\end{itemize}", r"\begin")):
            bad = [dict(ok[0], **{field: text}), {"item": 2, "file": "main.tex", "kind": "fix", "old": "Ada",
                                                 "new": "Ada", "question": "Who?"}]
            if field == "note_short":
                bad[0]["note"] = "Typo."
            d, r = self.setup_paper(bad)
            self.assertNotEqual(r.returncode, 0, text)
            self.assertIn("item #1", r.stderr)
            self.assertIn(cmd, r.stderr)
            self.assertFalse((d / "m").exists() and list((d / "m").rglob("*.tex")), "nothing written")


# ---------------------------------------------------------------- 4. facts.txt headings
class FactsHeadings(unittest.TestCase):
    def test_parse(self):
        at = load("ai_traces")
        d = tmpdir(self)
        p = d / "facts.txt"
        p.write_text("## form_check.py\nFAIL | length | p.3 | \"too long\"\n"
                     "## `refs_check`\nCHECK | preprint | burrow2020 | \"arXiv\"\n"
                     "## scripts/bib_style.out\nINFO | style | x\n")
        f = at.parse_facts(str(p))
        self.assertEqual(sorted(f), ["bib_style", "form_check", "refs_check"])
        self.assertEqual(f["form_check"][0]["kind"], "length")

    def test_skill_md_names_headings(self):
        text = (SKILL / "SKILL.md").read_text()
        cs = load("check_stats")
        for s in cs.SCRIPTS:
            self.assertIn("`## %s`" % s, text)


# ---------------------------------------------------------------- 5. typos finder chunks
class FinderChunks(unittest.TestCase):
    def test_prompt_and_skill(self):
        finder = (SKILL / "references" / "typos-finder.md").read_text()
        self.assertIn("`chunk_lines_max`", finder)
        self.assertIn("`limit` 30", finder)
        self.assertIn("largest `chunk_lines_max`", finder)       # parallel finders: max, not sum
        skill = (SKILL / "SKILL.md").read_text()
        self.assertRegex(skill, r"`chunk_lines_max` of 60 or less")


if __name__ == "__main__":
    unittest.main(verbosity=1)
