#!/usr/bin/env python3
"""Measure what a paper puts in front of the checkers: deterministic counts from the LaTeX sources (and the page
count of the compiled PDF), for the "What we checked" page and the cover of changes.pdf.

Usage: python3 scope_stats.py ROOT.tex [--pdf PAPER.pdf] [--json]

Every count is a pure function of the sources: the same paper gives the same numbers. Methods (the cover and the
"What we checked" page cite them in a footnote when a count is an estimate):
  body          the document body (\\begin{document}..\\end{document}, \\input files followed), comments, \\iffalse
                blocks and verbatim removed
  prose         the body without math, tables, labels, references, citations, URLs and other non-prose arguments
                (form_check.mask_prose); an inline formula that is only a number ($1.9\\times$, $35\\%$) counts as prose
  numbers_text  numeric tokens of the prose: 12, 0.93, 1,024, 35%, 1.9x; not part of a word or identifier (BM25,
                fp16, AVX-512), not a year (1900-2099)
  table_cells   cells of tabular-like environments (split at & and \\\\) that contain a number once formatting
                commands are removed; table_cells_all counts every non-empty cell
  tables, figures   table and figure floats (table, table*, wraptable; figure, figure*, wrapfigure; subfigures are
                not counted apart); tabulars counts the tabular environments
  equations     display formulas: equation, gather, multline, \\[..\\], $$..$$ count 1 each; align-like
                environments count one per row (\\\\)
  sentences     prose split after . ! ? before a capital, a digit or a backslash; pieces of three or more words
  paragraphs    prose blocks between blank lines, headings, floats and lists with five or more words
  cited_numbers ESTIMATE: numeric tokens in sentences that refer to a table or a figure (a \\ref to a label set in
                a table or figure float, or the words Table/Figure/Fig. followed by a number)
  claims        ESTIMATE: sentences with a comparison word (faster, slower, better, worse, higher, lower, superior,
                outperform, surpass, exceed, improve, reduce, speedup, than), a superlative (best, fastest, ...,
                state of the art), a percentage, a multiplier (1.9x, 3 times, 2-fold, orders of magnitude) or
                "up to N"
  bib_entries   entries of the .bib files named by \\bibliography / \\addbibresource (not @string, @comment,
                @preamble)
  pages         pages of the compiled PDF (pdfinfo), when --pdf is given and pdfinfo is installed
Python stdlib only (plus form_check.py of this folder).
"""
import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import form_check as fc  # noqa: E402

METHOD = {
    "numbers_text": "numeric tokens of the prose (outside equations, labels and references; years excluded)",
    "table_cells": "table cells that contain a number",
    "cited_numbers": "numbers in sentences that refer to a table or a figure (estimate by pattern)",
    "claims": "sentences with a comparison word (faster, better, outperform, than, ...), a superlative (best, "
              "fastest, ...), %, \u00d7 or \"up to N\" (estimate by pattern)",
    "sentences": "prose split at sentence ends; pieces of 3+ words",
    "paragraphs": "prose blocks of 5+ words",
    "equations": "display formulas, one per row of align-like environments",
}

NUM_MATH = re.compile(r"^\s*[-+]?\s*\d[\d.,\s]*(?:\\[,;!: ]|\\(?:times|%|pm|approx|sim)|[x%~{}]|\s)*$")
NUM_RX = re.compile(r"(?<![\w.\-/\\])(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?=(?:\s?(?:%|\u00d7|x(?![A-Za-z])))?"
                    r"(?![\w]))")
YEAR_RX = re.compile(r"^(19|20)\d\d$")
TAB_ENVS = r"tabular[x*]?|tabulary|longtable|tblr|NiceTabular"
TAB_RX = re.compile(r"\\begin\{(%s)\}(.*?)\\end\{\1\}" % TAB_ENVS, re.S)
FLOAT_RX = re.compile(r"\\begin\{(table\*?|wraptable|figure\*?|wrapfigure)\}(.*?)\\end\{\1\}", re.S)
EQ_ENVS = r"equation|gather|multline|displaymath|math|dmath"
ALIGN_ENVS = r"align|alignat|flalign|eqnarray|IEEEeqnarray"
REF_RX = re.compile(r"\\(?:ref|autoref|cref|Cref|vref|subref)\*?\s*\{([^}]*)\}")
CLAIM_RX = re.compile(
    r"\b(?:faster|slower|better|worse|higher|lower|superior|inferior|outperform\w*|surpass\w*|exceed\w*|"
    r"improv(?:e|es|ed|ing|ement|ements)|reduc(?:e|es|ed|ing|tion|tions)|speed-?ups?|than|"
    r"best|fastest|slowest|highest|lowest|largest|smallest|most|least|state[- ]of[- ]the[- ]art|"
    r"orders? of magnitude|\d+(?:\.\d+)?-fold|times (?:faster|slower|smaller|larger|more|less|fewer)|"
    r"up to \d)\b|\d\s?%|\d\s?\u00d7|\d(?:\.\d+)?x(?![A-Za-z])", re.I)
TF_WORD = re.compile(r"\b(?:Tables?|Figures?|Figs?\.)\s*~?\s*(?:\d|\u00a7TF\u00a7)")


def _blank(m):
    return re.sub(r"[^\n]", " ", m.group(0))


def body_text(src):
    """The document body as one string (comments, \\iffalse blocks and verbatim already out), lines kept."""
    rows = [(f, no, code) for f, no, code, _, _ in src.lines]
    k = next((i for i, r in enumerate(rows) if re.search(r"\\begin\{document\}", r[2])), None)
    if k is not None:
        rows = rows[k + 1:]
    e = next((i for i, r in enumerate(rows) if re.search(r"\\end\{document\}", r[2])), None)
    if e is not None:
        rows = rows[:e]
    text = "\n".join(c for _, _, c in rows)
    return re.sub(r"\\begin\{(%s)\}.*?\\end\{\1\}" % fc.VERBATIM_ENVS, _blank, text, flags=re.S)


def float_labels(body):
    """{label: 'table' | 'figure'} for labels set inside table and figure floats."""
    out = {}
    for m in FLOAT_RX.finditer(body):
        kind = "table" if "table" in m.group(1) else "figure"
        for lab in re.findall(r"\\label\s*\{([^}]+)\}", m.group(2)):
            out[lab.strip()] = kind
    return out


def cell_text(c):
    c = re.sub(r"\\(?:multicolumn|multirow)\s*\{[^}]*\}\s*(?:\[[^\]]*\]\s*)?\{[^}]*\}", " ", c)
    c = re.sub(r"\\(?:cellcolor|rowcolor|color|textcolor)\s*(?:\[[^\]]*\])?\s*\{[^}]*\}", " ", c)
    c = re.sub(r"\\(?:hline|toprule|midrule|bottomrule|cline\{[^}]*\}|cmidrule(?:\([^)]*\))?\{[^}]*\}|"
               r"addlinespace(?:\[[^\]]*\])?|hdashline|rule\{[^}]*\}\{[^}]*\})", " ", c)
    c = re.sub(r"\\(?:ref|cite\w*|label)\*?\s*\{[^}]*\}", " ", c)
    c = re.sub(r"\\[A-Za-z@]+\*?", " ", c)
    return re.sub(r"[{}$~^_]", " ", c).strip()


def table_cells(body):
    """(cells with a number, all non-empty cells, tabular environments)."""
    num = allc = envs = 0
    for m in TAB_RX.finditer(body):
        envs += 1
        inner = m.group(2)
        inner = re.sub(r"^\s*(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}|\[[^\]]*\])+", "", inner)   # column spec
        for row in re.split(r"\\\\(?:\[[^\]]*\])?|\\tabularnewline", inner):
            for cell in re.split(r"(?<!\\)&", row):
                t = cell_text(cell)
                if not t:
                    continue
                allc += 1
                if re.search(r"(?<![A-Za-z])\d", t):
                    num += 1
    return num, allc, envs


def equations(body):
    n = 0
    n += len(re.findall(r"\\begin\{(?:%s)\*?\}" % EQ_ENVS, body))
    n += len(re.findall(r"\\\[", body)) + len(re.findall(r"\$\$.+?\$\$", body, re.S))
    for m in re.finditer(r"\\begin\{(%s)\*?\}(.*?)\\end\{\1\*?\}" % ALIGN_ENVS, body, re.S):
        rows = [r for r in re.split(r"\\\\", m.group(2)) if r.strip()]
        n += max(1, len(rows))
    return n


def prose_of(body, flabels):
    """The prose of the body; references to table/figure floats become the marker \u00a7TF\u00a7."""
    def ref(m):
        labs = [x.strip() for x in m.group(1).split(",")]
        return " \u00a7TF\u00a7 " if any(flabels.get(x) for x in labs) else m.group(0)

    t = REF_RX.sub(ref, body)

    def inl(m):   # an inline formula that is only a number prints as one
        inner = m.group(1)
        if NUM_MATH.match(inner):
            s = re.sub(r"\\times", "\u00d7", inner)
            s = re.sub(r"\\%", "%", s)
            s = re.sub(r"\\[,;!: ]|\\(?:pm|approx|sim)|[{}~]", "", s)
            return " " + " ".join(s.split()) + " "
        return m.group(0)

    t = re.sub(r"(?<!\\)\$([^$\n]{1,40})(?<!\\)\$", inl, t)
    t = fc.mask_prose(t)
    t = fc.mask_tables(t)
    t = re.sub(r"\\begin\{(%s)\*?\}.*?\\end\{\1\*?\}" % ALIGN_ENVS, _blank, t, flags=re.S)
    return t


def plain(s):
    s = re.sub(r"\\(?:begin|end)\s*\{[^}]*\}", " ", s)
    s = re.sub(r"\\(?:caption|section|subsection|subsubsection|paragraph|textbf|emph|textit|text|mbox)\*?\s*"
               r"(?:\[[^\]]*\])?", " ", s)
    s = re.sub(r"\\%", "%", s)
    s = re.sub(r"\\[A-Za-z@]+\*?", " \u039e ", s)     # a macro (a name, a symbol) may start a sentence: \u039e
    s = re.sub(r"[{}\\^_&]", " ", s).replace("~", " ")
    return s


def sentences_of(prose):
    text = " ".join(plain(prose).split())
    text = re.sub(r"\b(e\.g|i\.e|vs|et al|Fig|Figs|Eq|Eqs|Sec|cf|resp|approx|No)\.", lambda m: m.group(1).replace(".", ""),
                  text)                                # abbreviations do not end a sentence
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\u00a7\u039e(\[])", text)
    return [p for p in parts if len(re.findall(r"[A-Za-z]{2,}", p)) >= 3]


def paragraphs_of(prose):
    blocks, cur = [], []
    brk = re.compile(r"^\s*\\(?:(?:sub)*section|chapter|paragraph|caption|item|begin\{(?:figure|table|itemize|"
                     r"enumerate|description|abstract)|end\{(?:figure|table|itemize|enumerate|description|abstract))")
    for ln in prose.split("\n"):
        if not ln.strip() or brk.match(ln):
            if cur:
                blocks.append(" ".join(cur))
            cur = [] if not ln.strip() else [ln]
            continue
        cur.append(ln)
    if cur:
        blocks.append(" ".join(cur))
    return [b for b in blocks if len(re.findall(r"[A-Za-z]{2,}", plain(b))) >= 5]


def numbers_in(s):
    return [m.group(0) for m in NUM_RX.finditer(s) if not YEAR_RX.match(m.group(0))]


def bib_entries(src, root):
    code = src.code()
    names = []
    for m in re.finditer(r"\\bibliography\s*\{([^}]*)\}|\\addbibresource\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", code):
        names += [x.strip() for x in (m.group(1) or m.group(2)).split(",") if x.strip()]
    n, found = 0, 0
    for name in names:
        p = root / (name if name.endswith(".bib") else name + ".bib")
        if not p.is_file():
            continue
        found += 1
        t = p.read_text(encoding="utf-8", errors="replace")
        n += len([1 for m in re.finditer(r"^\s*@(\w+)\s*[{(]", t, re.M)
                  if m.group(1).lower() not in ("string", "comment", "preamble")])
    return n if found else None


def pdf_pages(pdf):
    if not pdf or not pathlib.Path(pdf).is_file() or not shutil.which("pdfinfo"):
        return None
    r = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, errors="replace")
    m = re.search(r"^Pages:\s+(\d+)", r.stdout, re.M)
    return int(m.group(1)) if m else None


def measure(root_tex, pdf=None):
    root_tex = pathlib.Path(root_tex).resolve()
    src = fc.Sources(root_tex)
    body = body_text(src)
    flabels = float_labels(body)
    prose = prose_of(body, flabels)
    sents = sentences_of(prose)
    paras = paragraphs_of(prose)
    nums = sum(len(numbers_in(s)) for s in sents)
    cited = sum(len(numbers_in(s)) for s in sents if "\u00a7TF\u00a7" in s or TF_WORD.search(s))
    claims = sum(1 for s in sents if CLAIM_RX.search(s))
    cells, cells_all, tabulars = table_cells(body)
    floats = [m.group(1) for m in FLOAT_RX.finditer(body)]
    out = dict(
        numbers_text=nums, table_cells=cells, table_cells_all=cells_all, tabulars=tabulars,
        tables=sum(1 for f in floats if "table" in f), figures=sum(1 for f in floats if "figure" in f),
        equations=equations(body), sentences=len(sents), paragraphs=len(paras), cited_numbers=cited,
        claims=claims, bib_entries=bib_entries(src, root_tex.parent), source_files=len(src.files),
        source_lines=len(src.lines))
    pg = pdf_pages(pdf)
    if pg is not None:
        out["pages"] = pg
    return {k: v for k, v in out.items() if v is not None}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].replace("\n", " "))
    ap.add_argument("root")
    ap.add_argument("--pdf", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    m = measure(a.root, a.pdf)
    if a.json:
        print(json.dumps(m, indent=1))
    else:
        for k, v in m.items():
            print("%-16s %s" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
