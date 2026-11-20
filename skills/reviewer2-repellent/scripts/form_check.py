#!/usr/bin/env python3
"""Deterministic pre-submission form check of a LaTeX paper (call compliance, anonymity, hidden text,
leftovers, references, layout, numbers in tables, typography, bibliography hygiene, source hygiene: Markdown,
Unicode that prints wrongly or inconsistently, invisible characters, comments naming LLMs or prompts).

Usage (from anywhere, after compiling the paper, e.g. latexmk -pdf <root>.tex):
  python3 form_check.py <root>.tex [--authors names.txt] [--blind double|single|unknown]
        [--pages N] [--pages-include-refs] [--require "Limitations,Ethics"] [--keywords-max N]
        [--abstract-max N] [--no-widows] [--supp folder|archive.zip ...] [--json]

Every finding is one line:  SEV | kind | file:line | p.N | "quote" | hint
  FAIL  deterministic problem: fix it (or confirm it is intended)
  CHECK candidate: the agent decides (open the location, judge)
  INFO  facts for the agent (counts, lists); not problems by themselves
Venue facts (--blind, --pages, --require, limits) come from the venue profile. With --blind single, author names,
e-mails, links and acknowledgements are not anonymity problems and are not reported.
--supp scans supplementary material and code (folder or .zip, nested .zip too; stdlib only): with --blind double the
anonymity detectors plus .git folders, notebook outputs/metadata, PDF and Office metadata, LICENSE/README author lines;
with any review model credentials files and secrets (masked in the report), macOS metadata and large files.
Python stdlib + poppler (pdftotext, pdfinfo, pdffonts); pdflatex (or xelatex/lualatex, --engine or detected) for the
widow/orphan diagnostic build.
"""
import argparse
import json
import math
import pathlib
import re
import shutil
import subprocess
import tempfile
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, defaultdict

SEVS = ("FAIL", "CHECK", "INFO")


# ====================================================================== findings
class Report:
    def __init__(self):
        self.items = {}  # (sev, kind, key) -> dict
        self.skipped = []
        self.coverage = {}  # what was measured or tested (counts): the final COVERAGE line

    def add(self, sev, kind, where="", page="", quote="", hint="", key=None, maxlen=160):
        quote = " ".join(str(quote).split())[:maxlen]
        k = (sev, kind, key if key is not None else quote or where)
        it = self.items.get(k)
        if it is None:
            self.items[k] = dict(sev=sev, kind=kind, where=[where] if where else [], pages=[page] if page else [],
                                 quote=quote, hint=hint)
        else:
            if where and where not in it["where"]:
                it["where"].append(where)
            if page and page not in it["pages"]:
                it["pages"].append(page)

    def skip(self, what):
        self.skipped.append(what)

    def rows(self):
        order = {s: i for i, s in enumerate(SEVS)}
        return sorted(self.items.values(), key=lambda r: (order[r["sev"]], r["kind"]))

    def text(self):
        out = []
        for r in self.rows():
            where = ", ".join(r["where"][:6]) + (f" (+{len(r['where']) - 6})" if len(r["where"]) > 6 else "")
            pages = ",".join(r["pages"][:8]) + ("…" if len(r["pages"]) > 8 else "")
            out.append(" | ".join(x for x in (r["sev"], r["kind"], where, ("p." + pages) if pages else "",
                                              f'"{r["quote"]}"' if r["quote"] else "", r["hint"]) if x))
        c = Counter(r["sev"] for r in self.rows())
        out.append(f"SUMMARY | FAIL {c['FAIL']} | CHECK {c['CHECK']} | INFO {c['INFO']}")
        for s in self.skipped:
            out.append(f"SKIPPED | {s}")
        if self.coverage:
            out.append(coverage_line(self.coverage))
        return "\n".join(out)


def coverage_line(cov):
    """COVERAGE | key=value | ...: what a script measured or tested, for check_stats.py (counts only)."""
    return "COVERAGE | " + " | ".join(f"{k}={v}" for k, v in cov.items())


# ====================================================================== helpers
def run(cmd, cwd=None, timeout=300):
    try:
        r = subprocess.run(cmd, capture_output=True, cwd=cwd, timeout=timeout)
        return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def fold(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", s)


def name_variants(name):
    toks = [t for t in name.split() if t]
    out = {" ".join(toks)}
    plain = [t for t in toks if not re.fullmatch(r"\w\.", t)]
    if len(plain) >= 2:
        out.add(" ".join(plain))
        out.add(f"{plain[-1]}, {plain[0][0]}.")
        if len(plain[-1]) >= 5:
            out.add(plain[-1])
    return sorted(out, key=len, reverse=True)


def name_rx(v):
    body = r"\s+".join(map(re.escape, fold(v).split()))
    return re.compile(r"(?<!\w)" + body + (r"(?!\w)" if not v.endswith(".") else ""))


CMD_END = r"(?![A-Za-z@])"


def strip_tex(s):
    """Crude LaTeX → text for matching: drop commands, keep their text arguments."""
    s = re.sub(r"\\(cite[tp]?|ref|eqref|autoref|cref|Cref|label|url|href)\*?(\[[^\]]*\])*\{[^}]*\}", " ", s)
    s = re.sub(r"\\[A-Za-z@]+\*?", " ", s)
    s = re.sub(r"[{}$~\\^_&]", " ", s)
    return s


# ====================================================================== sources
INCLUDE_RX = re.compile(r"\\(input|include|subfile|InputIfFileExists)" + CMD_END + r"\s*(?:\{([^}]+)\}|([^\s{}\\%]+))")
IMPORT_RX = re.compile(r"\\(sub)?(?:import|inputfrom|includefrom)" + CMD_END + r"\*?\s*\{([^}]*)\}\s*\{([^}]+)\}")
VERBATIM_ENVS = r"verbatim\*?|Verbatim|lstlisting|minted"
IF_TOKEN = re.compile(r"\\(if[A-Za-z@]*|fi)" + CMD_END)
START_RX = re.compile(r"\\(iffalse|if0)" + CMD_END + r"|\\begin\{(comment|" + VERBATIM_ENVS + r")\}")


def split_comment(line):
    """(code, comment); honours \\%, \\url/\\href arguments and \\verb."""
    i, depth_url = 0, 0
    while i < len(line):
        if line.startswith(("\\url{", "\\href{"), i):
            depth_url = 1
            i = line.index("{", i) + 1
            continue
        m = re.match(r"\\verb\*?(.)", line[i:])
        if m and not depth_url:
            end = line.find(m.group(1), i + m.end())
            i = (end + 1) if end != -1 else len(line)
            continue
        c = line[i]
        if depth_url:
            depth_url += (c == "{") - (c == "}")
        elif c == "%":
            j, n = i - 1, 0
            while j >= 0 and line[j] == "\\":
                n += 1
                j -= 1
            if n % 2 == 0:
                return line[:i], line[i + 1:]
        i += 1
    return line, ""


def split_line(text, state):
    """(in_pdf, source_only, state); state None | ['if', depth] | ['env', name, verbatim]."""
    in_pdf, src_only, pos = [], [], 0
    while pos <= len(text):
        if state is None:
            m = START_RX.search(text, pos)
            if not m:
                in_pdf.append(text[pos:])
                break
            in_pdf.append(text[pos:m.start()])
            state = ["if", 1] if m.group(1) else ["env", m.group(2), bool(re.fullmatch(VERBATIM_ENVS, m.group(2)))]
            if state[0] == "env" and state[2]:
                in_pdf.append(m.group(0))
            pos = m.end()
        elif state[0] == "if":
            closed = False
            for t in IF_TOKEN.finditer(text, pos):
                tok = t.group(1)
                if tok == "fi":
                    state[1] -= 1
                elif tok != "ifthenelse":
                    state[1] += 1
                if state[1] == 0:
                    src_only.append(text[pos:t.end()])
                    pos, state, closed = t.end(), None, True
                    break
            if not closed:
                src_only.append(text[pos:])
                break
        else:
            end_tag = "\\end{" + state[1] + "}"
            end = text.find(end_tag, pos)
            seg = text[pos:] if end == -1 else text[pos:end]
            (in_pdf if state[2] else src_only).append(seg)
            if end == -1:
                break
            pos, state = end + len(end_tag), None
    return "".join(in_pdf), " ".join(s for s in src_only if s.strip()), state


class Sources:
    """Flattened source tree: lines = [(relpath, no, code_in_pdf, source_only, raw)]."""

    def __init__(self, root_tex):
        self.root_tex = root_tex
        self.root = root_tex.parent
        self.lines, self.files, self.unresolved, self.comment_envs = [], [], [], []
        self._visit(root_tex, self.root)
        self.code_by_file = defaultdict(list)
        for f, no, code, _, _ in self.lines:
            self.code_by_file[f].append((no, code))

    def rel(self, p):
        try:
            return str(p.relative_to(self.root))
        except ValueError:
            return str(p)

    def _resolve(self, base, name):
        for cand in (base / name.strip(), base / f"{name.strip()}.tex"):
            if cand.is_file():
                return cand
        return None

    def _visit(self, path, base):
        if path in self.files:
            return
        self.files.append(path)
        rel, state = self.rel(path), None
        for no, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if state is not None and state[0] == "env" and state[2]:
                text, comment = raw, ""
            else:
                text, comment = split_comment(raw)
            was = state
            code, hidden, state = split_line(text, state)
            if was is None and state is not None and state[0] == "env" and state[1] == "comment":
                self.comment_envs.append((rel, no, text.strip()[:100]))
            self.lines.append((rel, no, code, " ".join(x for x in (hidden, comment) if x.strip()), raw))
            for m in INCLUDE_RX.finditer(code):
                target = m.group(2) or m.group(3)
                p = self._resolve(self.root, target) or self._resolve(base, target)
                if p is None:
                    self.unresolved.append(f"{target} ({rel}:{no})")
                elif p.suffix == ".tex":
                    self._visit(p, base)
            for m in IMPORT_RX.finditer(code):
                sub, d, f = m.groups()
                nb = (base / d) if sub else (self.root / d)
                p = self._resolve(nb, f)
                if p is None:
                    self.unresolved.append(f"{d}{f} ({rel}:{no})")
                else:
                    self._visit(p, nb)

    def code(self):
        return "\n".join(c for _, _, c, _, _ in self.lines)

    def locate(self, phrase):
        """Best-effort file:line of a phrase seen in the compiled text."""
        words = re.findall(r"[a-z0-9]{2,}", fold(phrase))[:8]
        if len(words) < 2:
            return ""
        rx = re.compile(r"\W+".join(map(re.escape, words)))
        for f, items in self.code_by_file.items():
            buf, starts = "", []
            for no, code in items:
                starts.append((len(buf), no))
                buf += fold(strip_tex(code)) + " "
            m = rx.search(buf)
            if m:
                no = max((s for s in starts if s[0] <= m.start()), key=lambda s: s[0])[1]
                return f"{f}:{no}"
        return ""


# ====================================================================== compiled text
class Compiled:
    def __init__(self, pdf):
        self.pdf = pdf
        txt = run(["pdftotext", str(pdf), "-"]) if pdf.is_file() else None
        self.ok = txt is not None
        self.pages = txt.split("\f") if txt else []
        self.ref_page, self.ref_line = None, None
        for i, p in enumerate(self.pages, 1):
            for j, l in enumerate(p.split("\n")):
                if re.fullmatch(r"\s*(\d+\.?\s+)?(r\s?eferences|bibliography|literature cited)\s*", l, re.I):
                    self.ref_page, self.ref_line = i, j  # last such heading wins
        self._find_appendix()

    def iter_lines(self, with_index=False):
        for i, p in enumerate(self.pages, 1):
            for j, line in enumerate(p.split("\n")):
                yield (i, j, line) if with_index else (i, line)

    def _find_appendix(self):
        """An appendix after the reference list is body text again."""
        self.app_pos = None
        if not self.ref_page:
            return
        lines = list(self.iter_lines(with_index=True))
        for k, (i, j, l) in enumerate(lines):
            if (i, j) <= (self.ref_page, self.ref_line):
                continue
            nxt = next((x[2] for x in lines[k + 1:k + 4] if x[2].strip()), "")
            if re.match(r"\s*(Appendix|APPENDIX|Appendices|Supplementary [Mm]aterial)\b", l) or \
                    (re.match(r"\s*A(\.\d+)?\s+[A-Z][a-z]{2,}", l) and len(l.split()) <= 8) or \
                    (re.fullmatch(r"\s*A(\.\d+)?\s*", l) and re.match(r"\s*[A-Z][a-z]", nxt) and len(nxt.split()) <= 8):
                self.app_pos = (i, j)
                return

    def after_ref_heading(self, page, j):
        return self.ref_page is not None and (page, j) > (self.ref_page, self.ref_line)

    def after_refs(self, page, j):
        """True inside the reference list (after its heading and before an appendix that follows it)."""
        if self.ref_page is None or (page, j) <= (self.ref_page, self.ref_line):
            return False
        return self.app_pos is None or (page, j) < self.app_pos


# ====================================================================== checks
def check_class(src, R, a):
    for f, no, code, _, _ in src.lines:
        m = re.search(r"\\documentclass\s*(\[[^\]]*\])?\s*\{([^}]+)\}", code)
        if m:
            opts, cls = (m.group(1) or ""), m.group(2).strip()
            R.add("INFO", "class", f"{f}:{no}", quote=m.group(0))
            optlist = [o.strip() for o in opts.strip("[]").split(",")]
            if cls == "acmart" and a.blind == "double" and not any(o in ("anonymous", "anonymous=true") for o in optlist):
                R.add("FAIL", "acmart without anonymous", f"{f}:{no}", quote=m.group(0),
                      hint="authors print on page 1, headers and metadata")
            for o in ("final", "camera-ready", "accepted", "preprint"):
                if o in optlist:
                    R.add("CHECK", "camera-ready class option", f"{f}:{no}", quote=m.group(0), hint=f"option {o}")
        for pkg, opt in [(r"neurips_\d+", "final"), (r"icml\d+", "accepted"), (r"acl", "final"), (r"iclr\d+_conference", "final")]:
            m = re.search(r"\\usepackage\s*(\[[^\]]*\])?\s*\{(" + pkg + r")\}", code)
            if m and opt in (m.group(1) or ""):
                R.add("FAIL" if a.blind == "double" else "CHECK", "camera-ready style option", f"{f}:{no}",
                      quote=m.group(0), hint="prints the authors")


LAYOUT_RX = [
    (r"\\usepackage\s*(\[[^\]]*\])?\s*\{geometry\}|\\newgeometry", "geometry changes margins"),
    (r"\\(setlength|addtolength)\s*\{?\\(textheight|textwidth|topmargin|oddsidemargin|evensidemargin|columnsep|"
     r"headheight|headsep|footskip|parskip|baselineskip|abovecaptionskip|belowcaptionskip|floatsep|textfloatsep|"
     r"intextsep|dbltextfloatsep)\}?", "page/spacing dimension changed"),
    (r"\\linespread|\\(renewcommand|def)\s*\{?\\baselinestretch", "line spacing changed"),
    (r"\\enlargethispage", "\\enlargethispage"),
    (r"\\usepackage\s*(\[[^\]]*\])?\s*\{(fullpage|savetrees|a4wide|vmargin|anysize)\}", "margin-shrinking package"),
    (r"\\titlespacing|\\usepackage\s*(\[[^\]]*\])?\s*\{titlesec\}", "heading spacing changed (titlesec)"),
    (r"\\usepackage\s*(\[[^\]]*\])?\s*\{(newtxtext|newtxmath|times|mathptmx|txfonts|libertine|libertinus|"
     r"palatino|mathpazo|charter|lmodern|kpfonts|fourier)\}", "body font package"),
]
UNIT_PT = {"pt": 1, "bp": 1, "mm": 2.845, "cm": 28.45, "in": 72.27, "em": 10, "ex": 4.3}
FIXED_FONT_CLASSES = ("llncs", "acmart", "IEEEtran", "sig-alternate", "aaai", "neurips", "icml", "iclr")


def check_layout_hacks(src, R, cls):
    neg = []
    for f, no, code, _, _ in src.lines:
        for rx, what in LAYOUT_RX:
            m = re.search(rx, code)
            if m:
                if what == "body font package" and not any(c in cls for c in FIXED_FONT_CLASSES):
                    continue
                R.add("CHECK", "layout hack", f"{f}:{no}", quote=m.group(0), key=f"{f}:{no}",
                      hint=what + " (allowed only if the template/venue says so)")
        for m in re.finditer(r"\\vspace\*?\s*\{\s*-\s*([\d.]+)\s*(pt|mm|cm|em|ex|bp|in)\s*\}", code):
            if float(m.group(1)) * UNIT_PT[m.group(2)] < 150:  # >= 150pt is reported as hidden text (off page)
                neg.append(f"{f}:{no}")
    if neg:
        R.add("CHECK", "negative vertical space", ", ".join(neg[:12]) + (f" (+{len(neg) - 12})" if len(neg) > 12 else ""),
              quote=f"{len(neg)} negative \\vspace", key="negvspace",
              hint="squeezing the template; some venues reject it")


# ---- hidden text
COLOR_USE_RX = re.compile(r"\\(textcolor|color)" + CMD_END + r"\s*(?:\[(\w+)\])?\s*\{([^}]*)\}")
COLORLET_RX = re.compile(r"\\colorlet\s*\{([^}]+)\}\s*(?:\[(\w+)\])?\s*\{([^}]*)\}")
DEFCOLOR_RX = re.compile(r"\\definecolor\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}\s*\{(\w+)\}\s*\{([^}]*)\}")
BASE_W = {"white": 1.0, "black": 0.0, "gray": 0.5, "lightgray": 0.75, "darkgray": 0.25, "pink": 0.75}
HIDDEN_RX = [
    (r"\\fontsize\s*\{\s*(0?\.\d+|[0-3](\.\d+)?)\s*(pt)?\s*\}", "font under 4pt"),
    (r"\\(scalebox|resizebox)\s*\{\s*(0?\.0\d*|[0-3](\.\d+)?pt|0?\.0\d*\\\w+)\s*\}", "text scaled to almost nothing"),
    (r"\\pdfrender|\b3\s+Tr\b|TextRenderingMode", "invisible render mode"),
]
OPACITY_RX = re.compile(r"\\transparent\s*\{\s*([\d.]+)\s*\}|(?:text |fill |draw )?opacity\s*=\s*([\d.]+)")
OFFPAGE_RX = re.compile(r"\\(raisebox|vspace\*?|hspace\*?|hskip|vskip)\s*\{?\s*-\s*([\d.]+)\s*(pt|mm|cm|em|ex|bp|in)")
BACKGROUND_RX = re.compile(r"\\(rowcolor|cellcolor|columncolor|colorbox|fcolorbox|pagecolor)\b|fill\s*=|background")
INJECTION = [
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (all |any )?(the )?(previous|prior|above)",
    r"(give|write) (this paper )?(a )?(positive|favou?rable|glowing) review",
    r"recommend(s|ing)? (the )?(acceptance|accept)\b",
    r"\b(a )?(clear|strong) accept\b",
    r"do not (mention|highlight|point out) (any )?(weakness|negative)",
    r"\b(if|when) you are an? (ai|llm|language model|large language model|reviewer)\b",
    r"\b(note|instructions?|message) (to|for) (the )?(llms?|ai|language models?|automated reviewers?|reviewer models?)\b",
]
CHATBOT = [r"\bas an ai( language model)?\b", r"\bcertainly[!,] here is\b", r"\bi hope this helps\b",
           r"\bhere is (a|the) (revised|rewritten|improved) (version|paragraph|text)\b", r"\bregenerate response\b"]


def model_w(model, v):
    try:
        if model == "named":
            return BASE_W.get(v.strip())
        if model == "HTML":
            h = v.strip().lstrip("#")
            return min(int(h[i:i + 2], 16) for i in (0, 2, 4)) / 255 if len(h) == 6 else None
        n = [float(x) for x in re.split(r"[,\s]+", v.strip()) if x]
        return {"rgb": lambda: min(n), "RGB": lambda: min(n) / 255, "gray": lambda: n[0], "Gray": lambda: n[0] / 15,
                "cmyk": lambda: 1 - max(n), "cmy": lambda: 1 - max(n)}[model]()
    except (ValueError, KeyError, IndexError):
        return None


def expr_w(expr, defined):
    parts = [p.strip() for p in expr.strip().lstrip("-").split("!")]
    base = lambda n: defined.get(n, BASE_W.get(n, 0.0 if re.fullmatch(r"[a-z]+", n or "") and n in (
        "red", "green", "blue", "cyan", "magenta", "yellow", "orange", "brown", "lime", "olive", "purple", "teal", "violet") else None))
    w = base(parts[0])
    if w is None:
        return None
    i = 1
    while i < len(parts):
        try:
            p = float(parts[i]) / 100
        except ValueError:
            return None
        other = base(parts[i + 1]) if i + 1 < len(parts) else 1.0
        if other is None:
            return None
        w = p * w + (1 - p) * other
        i += 2
    return w


def check_hidden(src, R):
    defined, white_names, macros = {}, {}, {}
    depth_tab = 0
    for f, no, code, _, _ in src.lines:
        what, soft = [], []
        depth_tab += len(re.findall(r"\\begin\{(tabular\*?|tabularx|longtable|tblr)\}", code))
        in_tab = depth_tab > 0
        depth_tab -= len(re.findall(r"\\end\{(tabular\*?|tabularx|longtable|tblr)\}", code))
        depth_tab = max(depth_tab, 0)
        for m in DEFCOLOR_RX.finditer(code):
            w = model_w(m.group(2), m.group(3))
            if w is not None:
                defined[m.group(1).strip()] = w
                if w >= 0.97:
                    white_names[m.group(1).strip()] = f"{f}:{no}"
        for m in COLORLET_RX.finditer(code):
            w = model_w(m.group(2), m.group(3)) if m.group(2) else expr_w(m.group(3), defined)
            if w is not None:
                defined[m.group(1).strip()] = w
                if w >= 0.97:
                    white_names[m.group(1).strip()] = f"{f}:{no}"
        for m in COLOR_USE_RX.finditer(code):
            w = model_w(m.group(2), m.group(3)) if m.group(2) else expr_w(m.group(3), defined)
            if w is not None and w >= 0.97:
                # white text on a coloured background (table headers, boxes) is legitimate: let the agent look
                (soft if (in_tab or BACKGROUND_RX.search(code)) else what).append("white or near-white text colour")
        what += [w for rx, w in HIDDEN_RX if re.search(rx, code)]
        for m in OPACITY_RX.finditer(code):
            try:
                if float(m.group(1) or m.group(2)) < 0.02:
                    what.append("zero opacity")
            except ValueError:
                pass
        for m in OFFPAGE_RX.finditer(code):
            if float(m.group(2)) * UNIT_PT[m.group(3)] >= 150:
                what.append("content pushed off the page")
        if re.search(r"\\[hv]?phantom\s*\{[^}]*[A-Za-z]{3,}[^}]*\}", code):
            soft.append("\\phantom with words (often alignment)")
        if what:
            R.add("FAIL", "hidden text", f"{f}:{no}", quote=code.strip(), hint=", ".join(sorted(set(what))))
            m = re.search(r"\\(?:re)?newcommand\*?\s*\{?\\(\w+)\}?", code) or re.search(r"\\def\\(\w+)", code)
            if m:
                macros[m.group(1)] = f"{f}:{no}"
        elif soft:
            R.add("CHECK", "possibly hidden text", f"{f}:{no}", quote=code.strip(), hint=", ".join(sorted(set(soft))))
        elif re.search(r"\\(AddToShipoutPicture(BG|FG)?\*?|put)" + CMD_END + r"|\\begin\{(textblock\*?|picture)\}|"
                       r"\\begin\{tikzpicture\}\s*\[[^\]]*(remember picture|overlay)", code):
            R.add("CHECK", "absolute placement / overlay", f"{f}:{no}", quote=code.strip(),
                  hint="text placed over the page: read it")
    for mac, where in macros.items():
        uses = [f"{f}:{no}" for f, no, code, _, _ in src.lines if re.search(r"\\" + mac + CMD_END, code)
                and not re.search(r"(newcommand\*?\s*\{?|\\def)\\" + mac, code)]
        if uses:
            R.add("FAIL", "hidden-text macro used", ", ".join(uses[:10]), quote=f"\\{mac} (defined at {where})")
    for name, where in white_names.items():
        uses = [f"{f}:{no}" for f, no, code, _, _ in src.lines
                if re.search(r"\\(textcolor|color)\s*\{\s*" + re.escape(name) + r"\s*(!|\})", code)]
        if uses:
            R.add("FAIL", "near-white colour used on text", ", ".join(uses[:10]), quote=f"{name} (defined at {where})")


def check_injection_text(comp, src, R):
    for page, line in comp.iter_lines():
        fl = fold(line)
        for rx in INJECTION:
            m = re.search(rx, fl)
            if m:
                R.add("FAIL", "instruction to LLM/reviewer in the text", src.locate(line), str(page), line,
                      hint="desk-reject at many venues; delete it")
        for rx in CHATBOT:
            if re.search(rx, fl):
                R.add("FAIL", "chatbot leftover", src.locate(line), str(page), line)


# ---- leftovers
NOTE_PKGS = {"todonotes": "disable", "fixme": "final", "changes": "final", "easyReview": "hide"}


def check_leftovers(src, comp, R, names):
    for f, no, code, _, _ in src.lines:
        for m in re.finditer(r"\\usepackage\s*(\[[^\]]*\])?\s*\{([^}]+)\}", code):
            opts = m.group(1) or ""
            for pkg in [p.strip() for p in m.group(2).split(",")]:
                off = NOTE_PKGS.get(pkg)
                if off and off not in opts:
                    R.add("CHECK", "notes package active", f"{f}:{no}", quote=m.group(0), hint=f"load it with [{off}] or remove")
                if re.search(r"\[[^\]]*\bshow\b", opts) or (pkg.endswith("notes") and pkg not in NOTE_PKGS and "show" in opts):
                    R.add("FAIL", "notes package with [show]", f"{f}:{no}", quote=m.group(0), hint="notes print in the PDF")
        m = re.search(r"\\newcommand\*?\s*\{?\\(\w+)\}?\s*\[\d\]\s*(\[[^\]]*\])?\s*\{(.*)", code)
        if m and re.search(r"\\(textcolor|color)\s*\{(red|blue|magenta|orange|green|purple|cyan|violet|brown)|\\hl\b|\\todo\b",
                           m.group(3)):
            mac = m.group(1)
            # a later \renewcommand without colour switches the note off
            off = any(re.search(r"\\(renewcommand|def)\*?\s*\{?\\" + mac + r"\}?", c)
                      and not re.search(r"\\(textcolor|color|hl|todo)\b", c) for _, _, c, _, _ in src.lines)
            uses = [f"{g}:{n}" for g, n, c, _, _ in src.lines if re.search(r"\\" + mac + CMD_END, c)
                    and not re.search(r"(newcommand|renewcommand|def)\*?\s*\{?\\" + mac, c)]
            if off:
                R.add("INFO", "note macro (switched off)", f"{f}:{no}", quote=code.strip(), hint="remove before posting the source")
            else:
                R.add("FAIL" if uses else "INFO", "coloured note macro" + (" used in the text" if uses else " (defined, unused)"),
                      f"{f}:{no}", quote=code.strip(),
                      hint=("uses: " + ", ".join(uses[:8])) if uses else "remove before posting the source")
        if re.search(r"\\hl\s*\{", code) and not re.search(r"newcommand", code):
            R.add("CHECK", "highlighted text (\\hl)", f"{f}:{no}", quote=code.strip(), hint="highlight left from editing?")
        if re.search(r"\\date\s*\{\s*\\today\s*\}|\\today\b", code):
            R.add("INFO", "\\today in the source", f"{f}:{no}", quote=code.strip(), key="today",
                  hint="a date on a submission is unusual")
    if comp.ok:
        pats = [(r"\?\?", "FAIL", "unresolved reference ??"), (r"\[\s*\?\s*\]|, \?\]|\[\?,", "FAIL", "unresolved citation [?]"),
                (r"\b(TODO|FIXME|TBD|XXX)\b", "FAIL", "TODO marker"), (r"\bXX+(\.\d+)?\s*%|\bX\.X\b|\bXX\b", "CHECK", "placeholder"),
                (r"\[(cite|citation|ref|citation needed|reference)\]", "FAIL", "citation placeholder"),
                (r"(?i)\badd (a )?citations?\b|\bcitation needed\b|lorem ipsum", "FAIL", "placeholder text")]
        for page, line in comp.iter_lines():
            if comp.ref_page and page >= comp.ref_page and re.search(r"\?\?", line) is None:
                continue
            for rx, sev, what in pats:
                if re.search(rx, line, 0 if what != "citation placeholder" else re.I):
                    R.add(sev, what, src.locate(line), str(page), line, key=line.strip())


def check_comments(src, R, names, blind):
    per_file = Counter()
    flagged = 0
    for f, no, code, so, raw in src.lines:
        if so.strip():
            per_file[f] += 1
            t = fold(so)
            why = []
            if re.search(r"\b(todo|fixme|xxx|tbd)\b", t):
                why.append("TODO")
            if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", so):
                why.append("e-mail")
            if any(name_rx(v).search(t) for n in names for v in name_variants(n)):
                why.append("author name")
            if any(re.search(rx, t) for rx in INJECTION):
                why.append("LLM instruction")
            if why and flagged < 40:
                flagged += 1
                R.add("INFO", "comment (public if the source is posted)", f"{f}:{no}", quote="%" + so.strip(),
                      hint=", ".join(why), key=f"{f}:{no}")
    if per_file:
        R.add("INFO", "source comments", quote="; ".join(f"{k}: {v}" for k, v in per_file.most_common(10)),
              key="comments", hint=f"{sum(per_file.values())} comment lines; strip before arXiv (arxiv_latex_cleaner)")
    for f, no, first in src.comment_envs:
        R.add("INFO", "comment environment", f"{f}:{no}", quote=first, key=f"cenv{f}{no}")


# ---- source hygiene: Markdown, Unicode, invisible characters, LLM comments. Defects whoever wrote them (see
# references/ai-venue-actions.md): the findings never say "AI".
def _blank(m):
    return re.sub(r"[^\n]", " ", m.group(0))


PROSE_MASK = [  # regions that never print as running text: verbatim, math, pictures, non-prose arguments
    r"\\begin\{(verbatim\*?|Verbatim\*?|BVerbatim|lstlisting|minted|alltt)\}.*?\\end\{\1\}",
    r"\\verb\*?([^\sA-Za-z*]).*?\1", r"\\lstinline\s*(?:\[[^\]]*\])?\{[^}\n]*\}",
    r"\\lstinline\s*(?:\[[^\]]*\])?([^\s{\[]).*?\1", r"\\mintinline\s*\{[^}]*\}(?:\{[^}\n]*\}|([^\s{]).*?\1)",
    r"\\begin\{((?:equation|align|alignat|gather|multline|flalign|eqnarray|math|displaymath|IEEEeqnarray|dmath|"
    r"tikzpicture|pgfpicture|tikzcd|forest|axis)\*?)\}.*?\\end\{\1\}",
    r"\$\$.*?\$\$", r"\\\[.*?\\\]", r"\\\(.*?\\\)", r"(?<!\\)\$(?:\\\$|[^$])*?(?<!\\)\$",
    r"\\(?:url|nolinkurl|path|href|label|ref|eqref|pageref|autoref|cref|Cref|nameref|cite[a-zA-Z]*|includegraphics|"
    r"input|include|usepackage|RequirePackage|bibliography|bibliographystyle|texttt|lstinputlisting|doi|"
    r"documentclass|newcommand|renewcommand|providecommand|DeclareMathOperator|definecolor|color|textcolor|hypersetup|"
    r"setlength|addtolength|setcounter|newenvironment|renewenvironment|graphicspath|pgfplotstableread)\*?"
    r"\s*(?:\[[^\]\n]*\]\s*)*\{(?:[^{}]|\{[^{}]*\})*\}",
]
PROSE_MASK_RX = [re.compile(p, re.S) for p in PROSE_MASK]
TABLES_RX = re.compile(r"\\begin\{(tabular[x*]?|tabulary|longtable|tblr|NiceTabular|array|thebibliography)\}.*?"
                       r"\\end\{\1\}", re.S)


def mask_tables(text):
    """Blank table bodies too (cells such as --- or ✓ are not running text)."""
    return TABLES_RX.sub(_blank, text)


def mask_prose(text):
    """Blank (keeping the newlines) everything that does not print as running text."""
    for rx in PROSE_MASK_RX:
        text = rx.sub(_blank, text)
    return text


def source_body(src):
    """[(file, line, masked code)] of the document body in reading order (comments are already removed)."""
    rows, verb = [], None
    for f, no, code, _, raw in src.lines:   # Sources drops the \end{verbatim} tag: blank verbatim lines here
        if verb:
            if "\\end{%s}" % verb in raw:
                verb = None
            rows.append((f, no, ""))
            continue
        m = re.search(r"\\begin\{(%s)\}" % VERBATIM_ENVS, code)
        if m:
            if "\\end{%s}" % m.group(1) not in raw[raw.find(m.group(0)):]:
                verb = m.group(1)
            code = code[:m.start()]
        rows.append((f, no, code))
    k = next((i for i, r in enumerate(rows) if re.search(r"\\begin\{document\}", r[2])), None)
    if k is not None:
        rows = rows[k + 1:]
    e = next((i for i, r in enumerate(rows) if re.search(r"\\end\{document\}", r[2])), None)
    if e is not None:
        rows = rows[:e]
    masked = mask_prose("\n".join(c for _, _, c in rows)).split("\n")
    return [(f, no, m) for (f, no, _), m in zip(rows, masked)]


def tex_engine(src, log_path):
    head = ""
    if log_path and log_path.is_file():
        head = log_path.read_text(encoding="latin-1", errors="replace")[:300]
    if re.search(r"XeTeX|LuaTeX|LuaHBTeX", head):
        return "xelatex/lualatex"
    if "pdfTeX" in head:
        return "pdflatex"
    return "xelatex/lualatex" if re.search(r"\\usepackage\s*(\[[^\]]*\])?\s*\{[^}]*\b(fontspec|unicode-math)\b",
                                           src.code()) else "pdflatex"


MD_RX = [
    (re.compile(r"(?<![\\*\w])\*\*(?=\S)[^*\n]{1,80}?(?<=\S)\*\*(?![*\w])"), "**bold**",
     "prints with the asterisks; use \\textbf{...}"),
    (re.compile(r"(?<![`\\])`(?!`)[^`'\n]{1,60}`(?![`'])"), "`code`",
     "prints as two opening quotes; use \\texttt{...}"),
    (re.compile(r"^\s*#{1,6}\s+\S"), "# heading", "prints the # signs (or stops LaTeX); use \\section"),
    (re.compile(r"\[[^\]\n]{1,120}\]\((?:https?://|www\.)[^)\s]+\)"), "[text](url)",
     "prints literally; use \\href{url}{text}"),
]
BULLET_RX = re.compile(r"^\s*(?:[-*]|\u2022)\s+[A-Za-z\\]")
LIST_ENVS = re.compile(r"\\(begin|end)\{(itemize|enumerate|description|compactitem|compactenum|inparaenum|"
                       r"tabular[x*]?|tabulary|longtable|tblr|array|tabbing)\}")
# character -> (name, class, LaTeX equivalent, math command whose use elsewhere makes the text glyph inconsistent)
UNI_CHARS = {
    "\u2014": ("em dash —", "dash", "---", None), "\u2013": ("en dash –", "dash", "--", None),
    "\u2018": ("curly quote ‘", "quote", "`", None), "\u2019": ("curly quote ’", "quote", "'", None),
    "\u201c": ("curly quote “", "quote", "``", None), "\u201d": ("curly quote ”", "quote", "''", None),
    "\u2026": ("ellipsis …", "punct", "\\dots", None),
    "\u2264": ("≤", "math", "$\\le$", r"\\leq?(?![A-Za-z])"), "\u2265": ("≥", "math", "$\\ge$", r"\\geq?(?![A-Za-z])"),
    "\u2248": ("≈", "math", "$\\approx$", r"\\approx(?![A-Za-z])"),
    "\u00d7": ("×", "math", "$\\times$", r"\\times(?![A-Za-z])"),
    "\u2192": ("→", "math", "$\\to$", r"\\(?:to|rightarrow)(?![A-Za-z])"),
    "\u2190": ("←", "math", "$\\leftarrow$", r"\\(?:gets|leftarrow)(?![A-Za-z])"),
    "\u21d2": ("⇒", "math", "$\\Rightarrow$", r"\\(?:Rightarrow|implies)(?![A-Za-z])"),
    "\u00b1": ("±", "math", "$\\pm$", r"\\pm(?![A-Za-z])"), "\u2212": ("minus −", "math", "$-$", None),
    "\u223c": ("∼", "math", "$\\sim$", r"\\sim(?![A-Za-z])"), "\u2260": ("≠", "math", "$\\neq$", r"\\neq?(?![A-Za-z])"),
    "\u2208": ("∈", "math", "$\\in$", r"\\in(?![A-Za-z])"), "\u22c5": ("⋅", "math", "$\\cdot$", r"\\cdot(?![A-Za-z])"),
    "\u00b7": ("·", "math", "$\\cdot$", r"\\cdot(?![A-Za-z])"),
    "\u2713": ("✓", "mark", "\\checkmark", None), "\u2714": ("✔", "mark", "\\checkmark", None),
    "\u2717": ("✗", "mark", "a macro (pifont \\ding{55})", None), "\u2718": ("✘", "mark", "a macro (pifont \\ding{56})", None),
}
INVISIBLE = {"\u200b": "zero-width space U+200B", "\u200c": "zero-width non-joiner U+200C", "\u200d": "zero-width joiner U+200D",
             "\u2060": "word joiner U+2060", "\ufeff": "byte-order mark U+FEFF", "\u00ad": "soft hyphen U+00AD"}
SPACES = {"\u00a0": "non-breaking space U+00A0", "\u202f": "narrow no-break space U+202F", "\u2009": "thin space U+2009",
          "\u2007": "figure space U+2007", "\u2002": "en space U+2002", "\u2003": "em space U+2003"}
PDFLATEX_OK = set("\u2014\u2013\u2018\u2019\u201c\u201d\u2026\u00d7\u00b1\u00b7\u00a0\u00ad")  # defined by utf8 inputenc
EMOJI_RX = re.compile("[\U0001F300-\U0001FAFF\u2600-\u26FF\u2700-\u27BF]")
LLM_TOOL_RX = re.compile(r"\b(chat ?gpt|gpt-?\d(?:\.\d)?o?(?:-mini)?|gpt|openai|claude|anthropic|gemini|bard|copilot|"
                         r"deepseek|grok|perplexity\.ai|mistral ai)\b")
LLM_PROMPT_RX = re.compile(r"\b(prompts?|prompted|prompting)\b")
LLM_GENERIC_RX = re.compile(r"\b(llms?|large language models?|language models?|ai[- ]generated|generated (?:by|with) "
                            r"(?:an? )?ai)\b")


def check_source_hygiene(src, R, log_path):
    engine = tex_engine(src, log_path)
    code = src.code()
    log = log_path.read_text(encoding="latin-1", errors="replace") if log_path and log_path.is_file() else ""
    not_set = set(re.findall(r"Unicode character (\S) \(U\+[0-9A-F]+\)\s*not set up", log))
    not_set |= set(re.findall(r"Missing character: There is no (\S) ", log))
    declared = {chr(int(h, 16)) for h in re.findall(
        r"\\DeclareUnicodeCharacter\s*\{\s*([0-9A-Fa-f]{4,5})\s*\}", code)}
    declared |= set(re.findall(r"\\newunicodechar\s*\{(\S)\}", code))
    german = re.search(r"\\usepackage\s*\[[^\]]*\b(n?german|austrian|swiss)\b", code)
    body = source_body(src)
    orig = {(f, no): c.strip() for f, no, c, _, _ in src.lines}
    allcode = mask_tables("\n".join(c for _, _, c in body))
    counts = Counter()

    # Markdown
    depth, bullets = 0, []
    for f, no, line in body + [("", 0, "")]:
        for m in LIST_ENVS.finditer(line):
            depth = max(depth + (1 if m.group(1) == "begin" else -1), 0)
        for rx, what, hint in MD_RX:
            if rx.search(line):
                counts["markdown"] += 1
                R.add("FAIL", "Markdown in the text", f"{f}:{no}", quote=orig[(f, no)], key=f"md{f}:{no}",
                      hint=f"{what} {hint}")
        if depth == 0 and BULLET_RX.match(line) and "&" not in line:
            bullets.append((f, no, line))
            continue
        if len(bullets) >= 2:   # a Markdown list: two or more bullet lines in a row outside any list environment
            counts["markdown"] += len(bullets)
            R.add("FAIL", "Markdown in the text", ", ".join(f"{g}:{n}" for g, n, _ in bullets),
                  quote=orig[bullets[0][:2]], key=f"mdb{bullets[0][0]}:{bullets[0][1]}",
                  hint="'- ' or '* ' bullets outside itemize print as a run-on paragraph with dashes; use itemize")
        bullets = []

    # Unicode punctuation, symbols and spaces in the text
    occ = defaultdict(list)
    for f, no, line in body:
        for ch in sorted(set(line)):
            if ch in UNI_CHARS or ch in INVISIBLE or ch in SPACES or EMOJI_RX.match(ch):
                occ[ch].append((f, no, line))
    ascii_n = {"\u2014": len(re.findall(r"(?<!-)---(?!-)", allcode)), "\u2013": len(re.findall(r"(?<!-)--(?!-)", allcode))}
    ascii_sp = {"\u2014": len(re.findall(r"\s---\s", allcode)), "\u2013": len(re.findall(r"(?<=\s)--(?=\s)", allcode))}
    latex_q = len(re.findall(r"``|''", allcode))
    straight = [] if german else [(f, no, l) for f, no, l in body if re.search(
        r"(?<![\\\w\"])\"(?=[A-Za-z])[^\"\n]{1,80}?(?<=[\w.,!?)])\"(?![\w\"])", l)]
    straight1 = [(f, no, l) for f, no, l in body if re.search(
        r"(?:^|(?<=[\s(\[]))'(?=[A-Za-z])[^'\n]{1,60}?(?<=[\w.,!?)])'(?=[\s.,;:!?)\]]|$)", l)]

    def broken(ch):
        if ch in not_set:
            return "the log says it is not set up or missing from the font"
        if engine == "pdflatex" and ch not in PDFLATEX_OK and ch not in declared:
            return "not defined for pdfLaTeX (a LaTeX error, or missing in the PDF)"
        return ""

    for ch in sorted(occ):
        rows = occ[ch]
        locs = ", ".join(f"{f}:{no}" for f, no, _ in rows)
        quote, n = orig[rows[0][:2]], len(rows)
        why = broken(ch)
        if ch in INVISIBLE:
            counts["invisible"] += n
            R.add("FAIL", "invisible character in the text", locs, quote=quote, key="inv" + ch,
                  hint=f"{INVISIBLE[ch]} on {n} line(s): invisible in the source, breaks search and copy-paste"
                       f"{'; ' + why if why else ''}; delete it")
        elif ch in SPACES:
            counts["spaces"] += n
            R.add("FAIL" if why else "CHECK", "non-breaking or special space character", locs, quote=quote,
                  key="sp" + ch, hint=f"{SPACES[ch]} on {n} line(s), invisible in the source"
                                      f"{' and ' + why if why else ''}; write ~ or \\, instead")
        elif ch not in UNI_CHARS:
            counts["unicode"] += n
            R.add("FAIL" if why else "CHECK", "Unicode character in the text", locs, quote=quote, key="uni" + ch,
                  hint=f"emoji U+{ord(ch):04X} on {n} line(s){': ' + why if why else ''}")
        else:
            name, cls, eq, mathcmd = UNI_CHARS[ch]
            counts["unicode"] += n
            if not why and cls == "math" and mathcmd and ch not in declared and re.search(mathcmd, code):
                why = f"it prints in the text font while the paper writes {eq} (math font) elsewhere"
            if not why and cls == "dash" and ascii_n[ch]:
                spaced = sum(1 for _, _, l in rows if re.search(r"\s" + ch + r"\s", l)) * 2 > n
                if spaced != (ascii_sp[ch] * 2 > ascii_n[ch]):
                    why = f"mixed with {eq} ({ascii_n[ch]}x) and spaced differently, so the dashes look inconsistent"
                else:
                    R.add("CHECK", "mixed dash styles", locs, quote=quote, key="mix" + ch,
                          hint=f"{name} {n} line(s) and {eq} {ascii_n[ch]}x: same glyph; keep one style")
            if not why and cls == "quote" and straight:
                why = "mixed with straight \"quotes\", which print as closing quotes"
            if not why and cls == "quote" and latex_q:
                R.add("CHECK", "mixed quote styles", locs, quote=quote, key="mixq" + ch,
                      hint=f"{name} on {n} line(s) and LaTeX ``...'' {latex_q}x: same glyphs; keep one style")
            R.add("FAIL" if why else "CHECK", "Unicode character in the text", locs, quote=quote, key="uni" + ch,
                  hint=f"{name} on {n} line(s): " + (why if why else "prints, but differs from the LaTeX input") +
                       f"; LaTeX: {eq}")
    for rows, what, fix in ((straight, 'straight double quotes "..."', "``...''"),
                            (straight1, "straight single quotes '...'", "`...'")):
        if rows:
            counts["unicode"] += len(rows)
            R.add("FAIL", "straight quotes in the text", ", ".join(f"{f}:{no}" for f, no, _ in rows),
                  quote=orig[rows[0][:2]], key="sq" + fix,
                  hint=f"{what} on {len(rows)} line(s): the opening quote prints as a closing one; write {fix}")

    # comments that mention LLM tools or prompts: public if the source is posted (arXiv keeps every version)
    flagged = 0
    for f, no, _, so, _ in src.lines:
        if not so.strip() or flagged >= 40:
            continue
        t = so.lower()
        m = LLM_TOOL_RX.search(t) or LLM_PROMPT_RX.search(t) or LLM_GENERIC_RX.search(t)
        if m:
            flagged += 1
            counts["comments"] += 1
            what = ("names an LLM tool" if LLM_TOOL_RX.search(t) else
                    "mentions a prompt" if LLM_PROMPT_RX.search(t) else "mentions LLMs")
            R.add("CHECK", "comment mentions an LLM or a prompt", f"{f}:{no}", quote="%" + so.strip(),
                  key=f"llmc{f}:{no}", hint=f"{what} ({m.group(0)}): public if the source is posted; strip the "
                                            f"comments before arXiv")
    R.add("INFO", "source hygiene checks", key="hygiene",
          quote=f"engine {engine}; Markdown {counts['markdown']}, Unicode {counts['unicode']}, invisible characters "
                f"{counts['invisible']}, special spaces {counts['spaces']}, LLM/prompt comments {counts['comments']}",
          hint="text from \\begin{document}, outside math, verbatim and comments")


def check_local_support_files(src, R, names, blind):
    """Local .sty/.cls/.bst/.bib files: names and e-mails (public if the source is posted)."""
    for p in sorted(src.root.rglob("*")):
        if p.suffix not in (".sty", ".cls", ".bst", ".cfg") or not p.is_file():
            continue
        try:
            head = p.read_text(encoding="utf-8", errors="replace").splitlines()[:80]
        except OSError:
            continue
        for no, l in enumerate(head, 1):
            t = fold(l)
            em = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", l)
            nm = [n for n in names if any(name_rx(v).search(t) for v in name_variants(n))]
            if em or nm:
                sev = "CHECK" if blind == "double" else "INFO"
                R.add(sev, "name/e-mail in a local style file", f"{src.rel(p)}:{no}", quote=l.strip(),
                      hint="identifies people if the source is shared")


# ---- anonymity
ANON_VALUES = {"", "anonymous", "anon", "anon.", "anonymous author", "anonymous authors", "anonymous author(s)",
               "anonymous submission", "author", "authors"}


def check_metadata_injection(comp, R):
    if comp.ok:
        for k, v in pdf_meta(comp.pdf).items():
            if any(re.search(rx, fold(v)) for rx in INJECTION):
                R.add("FAIL", f"instruction to LLM/reviewer in PDF {k} metadata", "", "", v)


def check_anonymity(src, comp, R, names, a):
    if a.blind != "double":
        return
    for f, no, code, _, _ in src.lines:
        for m in re.finditer(r"pdfauthor\s*=\s*\{([^}]*)\}|/Author\s*\(([^)]*)\)", code):
            if fold(m.group(1) if m.group(1) is not None else m.group(2)).strip() not in ANON_VALUES:
                R.add("FAIL", "author metadata in the source", f"{f}:{no}", quote=code.strip())
        if re.search(r"pdfusetitle", code):
            R.add("CHECK", "pdfusetitle copies \\author into the PDF metadata", f"{f}:{no}", quote=code.strip())
    if not comp.ok:
        return
    meta = pdf_meta(comp.pdf)
    if fold(meta.get("Author", "")).strip() not in ANON_VALUES:
        R.add("FAIL", "PDF Author metadata", "", "", meta["Author"], hint="remove pdfauthor / \\pdfinfo; check pdfinfo")
    for k in ("Title", "Subject", "Keywords"):
        v = meta.get(k, "")
        if v and any(name_rx(x).search(fold(v)) for n in names for x in name_variants(n)):
            R.add("FAIL", f"name in PDF {k} metadata", "", "", v)
    for i, page in enumerate(comp.pages, 1):
        lines = page.split("\n")
        body = "\n".join(l for j, l in enumerate(lines) if not comp.after_refs(i, j))
        refs = "\n".join(l for j, l in enumerate(lines) if comp.after_refs(i, j))
        for n in names:
            for v in name_variants(n):
                m = name_rx(v).search(fold(body))
                if m:
                    fb = fold(body)
                    ctx = fb[max(0, m.start() - 60):m.end() + 60]
                    R.add("FAIL", "author name in the text", src.locate(ctx), str(i), ctx, key=f"name{n}{i}")
                    break
            else:
                if refs and any(name_rx(v).search(fold(refs)) for v in name_variants(n)):
                    R.add("INFO", "author name in the references", "", str(i), n, key=f"ref{n}",
                          hint="fine if cited in the third person")
        if not body.strip():
            continue
        page, fp = body, fold(body)
        if True:
            for m in re.finditer(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", fp):
                R.add("FAIL", "e-mail in the text", src.locate(fp[m.start() - 40:m.end()]), str(i), m.group(0))
            for m in re.finditer(r"(github|gitlab|bitbucket|huggingface)\.(com|co|org)/([\w.-]+)", fp):
                owner = m.group(3)
                if any(tok in owner for n in names for tok in fold(n).split() if len(tok) >= 4):
                    R.add("FAIL", "identifying repository link", src.locate(fp[m.start() - 30:m.end()]), str(i), m.group(0))
                else:
                    R.add("INFO", "repository link", "", str(i), m.group(0), key="link" + m.group(0),
                          hint="third-party is fine; an own repo must be anonymised")
            for m in re.finditer(r"/(home|users)/[\w.-]+", fp):
                R.add("FAIL", "home path", "", str(i), m.group(0))
            for rx in (r"\b(our|my) (previous|prior|earlier|own|recent) (work|paper|papers|system|library|study|implementation)s?\b",
                       r"\b(we|i) (previously|earlier|recently) (showed|proposed|introduced|presented|developed)\b",
                       r"\bmade available by our\b|\bour (\w+ )?(library|framework|toolkit|system|tool|implementation) \[",
                       r"\bin our (previous|prior|earlier) (work|paper)\b"):
                for m in re.finditer(rx, fp):
                    ctx = fp[max(0, m.start() - 50):m.end() + 60]
                    R.add("CHECK", "first-person ownership / self-citation", src.locate(ctx), str(i), ctx,
                          hint="write about your prior work in the third person")
            for m in re.finditer(r"^\s*(\d+\.?\s*)?acknowledge?ments?\b", page, re.I | re.M):
                R.add("FAIL", "acknowledgements in a double-blind submission", "", str(i), page[m.start():m.start() + 120])
            for m in re.finditer(r"\b(grants?|award|agreement)\s+(no\.?|number|n\.)?\s*[A-Z0-9][\w/-]{4,}", page):
                R.add("CHECK", "grant number", "", str(i), page[max(0, m.start() - 40):m.end() + 20])


# ---- figures
def pdf_meta(path):
    out = run(["pdfinfo", str(path)]) or ""
    meta = {}
    for line in out.splitlines():
        k, _, v = line.partition(":")
        if k.strip() in ("Author", "Title", "Subject", "Keywords", "Creator", "Producer", "Page size", "Pages") and v.strip():
            meta[k.strip()] = v.strip()
    return meta


def check_figures(src, R, names, a):
    graphics = sorted({g.strip() for _, _, code, _, _ in src.lines
                       for g in re.findall(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", code)})
    exif = shutil.which("exiftool")
    for g in graphics:
        p = next((c for c in [src.root / g] + [src.root / f"{g}{e}" for e in (".pdf", ".png", ".jpg", ".jpeg", ".eps")]
                  if c.is_file()), None)
        if p is None:
            R.add("FAIL", "figure file not found", "", "", g)
            continue
        if p.suffix == ".pdf":
            ft = fold(run(["pdftotext", str(p), "-"]) or "")
            if a.blind == "double":
                for n in names:
                    if any(name_rx(v).search(ft) for v in name_variants(n)):
                        R.add("FAIL", "author name inside a figure", g, "", n)
            for rx in INJECTION:
                if re.search(rx, ft):
                    R.add("FAIL", "instruction-like text in a figure", g, "", re.search(rx, ft).group(0))
            fonts = run(["pdffonts", str(p)]) or ""
            if re.search(r"\bType 3\b", fonts):
                R.add("INFO", "Type 3 fonts in figure", g, "", hint="some publishers reject Type 3 fonts")
        if a.blind != "double":
            continue
        fields = {}
        if exif:
            out = run([exif, "-s", "-Author", "-Artist", "-XMP-dc:Creator", "-Copyright", "-OwnerName", str(p)]) or ""
            for l in out.splitlines():
                k, _, v = l.partition(":")
                if v.strip():
                    fields[k.strip()] = v.strip()
        elif p.suffix == ".pdf":
            fields = {k: v for k, v in pdf_meta(p).items() if k == "Author"}
        else:
            raw = p.read_bytes()[:400000].decode("latin-1")
            for m in re.finditer(r'(Author|Artist|Copyright|dc:creator)[\x00\s:=>"]{1,6}([ -~]{3,60})', raw):
                fields[m.group(1)] = m.group(2)
        for k, v in fields.items():
            hit_name = any(name_rx(x).search(fold(v)) for n in names for x in name_variants(n))
            R.add("FAIL" if hit_name else "CHECK", f"figure metadata {k}", g, "", v,
                  hint="a person's name in the file metadata" if not hit_name else "author name in figure metadata")


def check_pdf(comp, R, a):
    if not comp.ok:
        return
    meta = pdf_meta(comp.pdf)
    R.add("INFO", "pdf", quote=f"{meta.get('Pages', '?')} pages, size {meta.get('Page size', '?')}", key="pdfinfo")
    fonts = run(["pdffonts", str(comp.pdf)]) or ""
    rows = [l for l in fonts.splitlines()[2:] if l.strip()]
    if fonts:
        R.coverage["fonts"] = len(rows)
        R.coverage["fonts_embedded"] = sum(1 for l in rows if re.search(r"\s(yes)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$", l))
    t3 = [l.split()[0] for l in fonts.splitlines()[2:] if " Type 3 " in l]
    noemb = [l.split()[0] for l in fonts.splitlines()[2:] if re.search(r"\s(no)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$", l)]
    if noemb:
        R.add("FAIL", "fonts not embedded", quote=", ".join(sorted(set(noemb))[:8]), key="noemb",
              hint="publishers and some submission systems reject the PDF")
    if t3:
        R.add("CHECK", "Type 3 fonts", quote=", ".join(sorted(set(t3))[:8]), key="t3",
              hint="usually from a figure; some publishers reject them")


# ---- log
def read_log(path):
    raw = path.read_bytes().decode("latin-1").split("\n")
    out, prev_full = [], False
    for l in raw:
        if prev_full and out:
            out[-1] += l
        else:
            out.append(l)
        prev_full = len(l) == 79  # pdfTeX wraps log lines at max_print_line = 79
    return "\n".join(out)


def file_at(log, pos):
    stack = []
    for m in re.finditer(r"\((?:\./|/)?([^\s()]*\.(?:tex|sty|cls|cfg|def|clo|fd|aux|bbl|toc|out|ldf))?|\)", log[:pos]):
        if m.group(0) == ")":
            if stack:
                stack.pop()
        else:
            stack.append(m.group(1))
    tex = [x for x in stack if x and x.endswith((".tex", ".bbl"))]
    return tex[-1].lstrip("./") if tex else "?"


def check_log(log_path, comp, R, a, src):
    if not log_path.is_file():
        R.skip(f"log checks: {log_path.name} not found (compile first)")
        return None
    t = read_log(log_path)
    m = re.search(r"Output written on .*?\((\d+) pages?", t, re.S)
    pages = int(m.group(1)) if m else None
    body_end = (comp.ref_page or pages) if comp.ok else pages
    R.add("INFO", "length", quote=f"{pages} pages in all; references start on page {comp.ref_page or '?'}", key="len")
    if a.pages and pages:
        last = pages if a.pages_include_refs else (comp.ref_page or pages)
        if last and last > a.pages:
            R.add("FAIL", "page limit", "", str(last),
                  f"{'total' if a.pages_include_refs else 'body'} reaches page {last}, limit {a.pages}",
                  hint="check exactly what the call counts (appendix, statements)")
    for mm in re.finditer(r"Label [`']([^']+)' multiply defined", t):
        key = mm.group(1)
        locs = [f"{f}:{no}" for f, no, c, _, _ in src.lines if re.search(r"\\label\s*\{" + re.escape(key) + r"\}", c)]
        R.add("FAIL", "label defined twice", ", ".join(locs), "", mm.group(0), key="lbl" + key,
              hint="references may point to the wrong object")
    for mm in re.finditer(r"^! (.+)$", t, re.M):
        f = file_at(t, mm.start())
        ln = re.search(r"^l\.(\d+)", t[mm.end():mm.end() + 2000], re.M)
        R.add("FAIL", "LaTeX error", f"{f}:{ln.group(1)}" if ln and f != "?" else "", "", mm.group(1), key="err" + mm.group(1),
              hint="the PDF may be incomplete or wrong where the error occurred")
    for mm in re.finditer(r"`h' float specifier changed to `ht'", t):
        R.add("INFO", "float specifier changed (h → ht)", "", "", mm.group(0), key="hfloat")
    if re.search(r"Underfull \\vbox \(badness 10000\) has occurred while \\output is active", t):
        n = len(re.findall(r"Underfull \\vbox \(badness 10000\) has occurred while \\output is active", t))
        R.add("CHECK", "underfull page (white gap / unbalanced columns)", "", "", f"{n} pages", key="uvbox",
              hint="look at pages with large white gaps")
    simple = [(r"Citation [`']([^']+)' on page (\d+) undefined", "FAIL", "undefined citation"),
              (r"Reference [`']([^']+)' on page (\d+) undefined", "FAIL", "undefined reference"),
              (r"Float too large for page by ([\d.]+pt)", "FAIL", "float too large"),
              (r"Float\(s\) lost", "FAIL", "float lost"),
              (r"File [`']([^']+)' not found", "FAIL", "file not found"),
              (r"Missing character: There is no (\S+) in font ([^!\n]+)", "CHECK", "missing glyph"),
              (r"No positions in optional float specifier", "CHECK", "float placement option ignored"),
              (r"Label\(s\) may have changed", "INFO", "rerun LaTeX"),
              (r"Token not allowed in a PDF string", "INFO", "hyperref bookmark token")]
    for rx, sev, what in simple:
        for mm in re.finditer(rx, t):
            src_file = file_at(t, mm.start())
            line = re.search(r"input line (\d+)", t[mm.start():mm.start() + 300])
            where = f"{src_file}:{line.group(1)}" if line and src_file != "?" else src_file
            R.add(sev, what, where if where != "?" else "", mm.group(2) if what in ("undefined citation", "undefined reference") else "",
                  mm.group(0), key=mm.group(1) if mm.groups() else what)
    fonts = Counter(re.findall(r"Font shape [`']([^']+)' undefined", t))
    if fonts:
        R.add("INFO", "font substitutions", quote=", ".join(f"{k}×{v}" for k, v in fonts.most_common(6)), key="fontsub")
    over = []
    for mm in re.finditer(r"Overfull \\([hv])box \(([\d.]+)pt too (wide|high)\)([^\n]*)", t):
        size = float(mm.group(2))
        if size <= 1.0:
            continue
        lines = re.search(r"lines? (\d+)(?:--(\d+))?", mm.group(4))
        f = file_at(t, mm.start())
        where = f"{f}:{lines.group(1)}" + (f"-{lines.group(2)}" if lines and lines.group(2) else "") if lines else f
        over.append((size, mm.group(1), where, "detected at line" in mm.group(4)))
    for size, hv, where, detected in sorted(over, reverse=True)[:20]:
        # boxes "detected at line" (title blocks, alignments) are often invisible: let the agent look
        sev = "FAIL" if size >= 10 and not detected else "CHECK"
        R.add(sev, f"overfull \\{hv}box {size:.1f}pt", where, "", key=f"of{where}{size}",
              hint=("text/figure sticks out of the column" if size >= 10 else "slightly into the margin")
              + ("; box built outside a paragraph: check whether it is visible" if detected else ""))
    blg = log_path.with_suffix(".blg")
    if blg.is_file():
        bl = blg.read_text(encoding="latin-1")
        for l in bl.splitlines():
            if re.search(r"I didn't find a database entry", l):
                R.add("FAIL", "bibtex: missing entry", blg.name, "", l)
            elif re.search(r"Repeated entry|I'm skipping whatever remains|I was expecting|There w(as|ere) \d+ error", l):
                R.add("FAIL", "bibtex error", blg.name, "", l, hint="entries after the error may be lost")
            elif l.startswith("Warning--"):
                R.add("CHECK", "bibtex warning", blg.name, "", l)
    if a.linenumbers and not re.search(r"lineno\.sty|\\linenumbers|Package: lineno", t):
        R.add("FAIL", "line numbers required but absent", "", "", "lineno not loaded", key="lineno",
              hint="the call requires line numbers (review option or lineno)")
    if a.paper and comp.ok:
        size = pdf_meta(comp.pdf).get("Page size", "")
        want = {"a4": "A4", "letter": "letter"}[a.paper]
        if want.lower() not in size.lower():
            R.add("FAIL", "page size", "", "", size, key="paper", hint=f"the venue wants {want}")
    return pages


def build_engine(src, root_tex, log_path, choice=None):
    """Engine for the diagnostic build: --engine, else a `% !TEX program` line, else the log of the normal build,
    else the preamble (luatexja/luacode -> lualatex; fontspec/unicode-math/polyglossia/xeCJK -> xelatex)."""
    if choice:
        return choice
    try:
        head = root_tex.read_text(encoding="utf-8", errors="replace").splitlines()[:20]
    except OSError:
        head = []
    for l in head:
        m = re.match(r"\s*%\s*!\s*T[Ee]X\s+(?:TS-)?program\s*=\s*(pdf|xe|lua)(?:la)?tex", l, re.I)
        if m:
            return m.group(1).lower() + "latex"
    if log_path and log_path.is_file():
        first = log_path.read_text(encoding="latin-1", errors="replace")[:300]
        if re.search(r"LuaTeX|LuaHBTeX", first):
            return "lualatex"
        if "XeTeX" in first:
            return "xelatex"
        if "pdfTeX" in first:
            return "pdflatex"
    pkgs = " ".join(m.group(1) for m in re.finditer(r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}",
                                                    src.code()))
    if re.search(r"\b(luatexja[\w-]*|luacode|luaotfload)\b", pkgs):
        return "lualatex"
    if re.search(r"\b(fontspec|unicode-math|polyglossia|xeCJK|xltxtra)\b", pkgs):
        return "xelatex"
    return "pdflatex"


def check_widows(src, root_tex, log_path, R, engine="pdflatex"):
    if not shutil.which(engine):
        R.skip(f"widows/orphans: {engine} not found")
        return
    with tempfile.TemporaryDirectory() as td:
        stem = root_tex.stem
        for ext in (".aux", ".bbl"):
            p = root_tex.with_suffix(ext)
            if p.is_file():
                shutil.copy(p, pathlib.Path(td) / f"wo{ext}")
        cmd = [engine, "-interaction=nonstopmode", "-no-shell-escape", f"-output-directory={td}", "-jobname=wo",
               r"\RequirePackage{widows-and-orphans}\input{" + root_tex.name + "}"]
        try:
            subprocess.run(cmd, cwd=root_tex.parent, capture_output=True, timeout=300)
        except subprocess.TimeoutExpired:
            R.skip("widows/orphans: diagnostic build timed out")
            return
        lp = pathlib.Path(td) / "wo.log"
        if not lp.is_file():
            R.skip(f"widows/orphans: diagnostic build with {engine} failed")
            return
        t = read_log(lp)
        if "widows-and-orphans" not in t:
            R.skip("widows/orphans: package widows-and-orphans not available")
            return
        if "Output written on" not in t:   # e.g. fontspec under pdflatex: the run stops before page 1
            R.skip(f"widows/orphans: diagnostic build with {engine} produced no pages (pass --engine)")
            return
        for mm in re.finditer(r"Package widows-and-orphans Warning: ([^\n]+)", t):
            msg = mm.group(1).strip()
            pg = re.search(r"page (\d+)", msg)
            R.add("CHECK", "widow/orphan/page-break hyphen", "", pg.group(1) if pg else "", msg,
                  hint="diagnostic build; page numbers as in the normal build if pagination is unchanged")


# ---- floats
CAP_RX = re.compile(r"^\s*(Figure|Fig\.|Table|TABLE)\s+([A-Z]?\.?\d+(?:\.\d+)?)\s*[.:|]")
NUM = r"[A-Z]?\.?\d+(?:\.\d+)?"
MENTION_RX = re.compile(r"\b(Figures?|Figs?\.|Tables?|Tabs?\.)\s*~?\s*(" + NUM + r"(?:\s*(?:,|and|&|–|-|to)\s*(?:" + NUM + r"))*)")


def mention_keys(kind, lst):
    kind = "Table" if kind.lower().startswith("tab") else "Figure"
    nums = re.findall(NUM, lst)
    out = set(nums)
    for a, b in re.findall(r"(\d+)\s*(?:–|-|to)\s*(\d+)", lst):  # ranges of plain numbers
        if int(a) < int(b) <= int(a) + 20:
            out.update(str(k) for k in range(int(a), int(b) + 1))
    return [(kind, n) for n in out]


def check_floats(comp, R):
    if not comp.ok:
        return
    cap_page, first, cap_after = {}, {}, {}
    for page, j, line in comp.iter_lines(with_index=True):
        c = CAP_RX.match(line)
        if c:
            key = ("Table" if c.group(1).lower().startswith("tab") else "Figure", c.group(2))
            cap_page.setdefault(key, page)
            cap_after.setdefault(key, comp.after_ref_heading(page, j))
            rest = line[c.end():]
        else:
            rest = line
        for m in MENTION_RX.finditer(rest):
            for key in mention_keys(m.group(1), m.group(2)):
                first.setdefault(key, page)
    rp = comp.ref_page
    for key, cp in cap_page.items():
        fm = first.get(key)
        if fm is None:
            R.add("CHECK", "float never referenced", "", str(cp), f"{key[0]} {key[1]}")
            continue
        if cap_after.get(key) and fm < (rp or 10 ** 6) and not re.match(r"[A-Z]", key[1]):
            R.add("FAIL", "float printed after the references", "", str(cp),
                  f"{key[0]} {key[1]}: first mentioned p.{fm}, printed p.{cp}",
                  hint="placement option ignored or too many floats; check \\begin{figure}[...] and the log")
        elif cp - fm >= 2:
            R.add("CHECK", "float far from first mention", "", str(cp), f"{key[0]} {key[1]}: mentioned p.{fm}, printed p.{cp}")
        elif fm - cp >= 2:
            R.add("CHECK", "float printed before its first mention", "", str(cp),
                  f"{key[0]} {key[1]}: printed p.{cp}, first mentioned p.{fm}")


def check_page_ends(src, comp, R):
    """A section heading printed as the last line of a page."""
    if not comp.ok:
        return
    heads = {fold(strip_tex(m.group(2))).strip() for _, _, c, _, _ in src.lines
             for m in re.finditer(r"\\(sub)*section\*?\s*\{([^}]*)\}", c) if len(strip_tex(m.group(2)).split()) <= 10}
    heads.discard("")
    for i, page in enumerate(comp.pages[:-1], 1):
        lines = [l for l in page.split("\n") if l.strip() and not re.fullmatch(r"\s*\d+\s*", l)]
        if not lines:
            continue
        last = fold(re.sub(r"^\s*[\d.]+\s+", "", lines[-1])).strip()
        if last and last in heads:
            R.add("CHECK", "heading at the bottom of a page", "", str(i), lines[-1].strip(),
                  hint="keep the heading with its text (\\needspace, or move a float)")


def check_table_captions(src, R):
    code = "\n".join(f"\x00{f}:{no}\x00" + c for f, no, c, _, _ in src.lines)
    for m in re.finditer(r"\\begin\{table\*?\}(.*?)\\end\{table\*?\}", code, re.S):
        body = m.group(1)
        cap, tab = body.find("\\caption"), body.find("\\begin{tabular")
        if cap != -1 and tab != -1 and cap > body.find("\\end{tabular"):
            k = code.rfind("\x00", 0, m.start())
            k0 = code.rfind("\x00", 0, k)
            R.add("CHECK", "table caption below the table", code[k0 + 1:k] if k0 != -1 else "", "", "",
                  key=f"tcap{m.start()}", hint="most venues want table captions above the table")


def check_mojibake(src, comp, R):
    if not comp.ok:
        return
    for page, line in comp.iter_lines():
        if re.search(r"Ã[\x80-\xbf©¨¼½¶]|â€[™œ\x9d“”˜]|\ufffd", line):
            R.add("CHECK", "garbled characters (encoding)", src.locate(line), str(page), line, key=line.strip())


# ---- front matter / required content
def tex_block(code, env):
    m = re.search(r"\\begin\{" + env + r"\}(.*?)\\end\{" + env + r"\}", code, re.S)
    return m.group(1) if m else None


def check_front(src, R, a):
    code = src.code()
    abstract = tex_block(code, "abstract")
    if abstract is None:
        m = re.search(r"\\abstract\s*\{(.*?)\}\s*\n", code, re.S)
        abstract = m.group(1) if m else None
    if abstract is not None:
        ab = re.sub(r"\\keywords\s*\{.*", "", abstract, flags=re.S)
        n = len(re.findall(r"[A-Za-z0-9][\w'-]*", strip_tex(ab)))
        R.add("INFO", "abstract", quote=f"{n} words", key="abs")
        if a.abstract_max and n > a.abstract_max:
            R.add("FAIL", "abstract too long", quote=f"{n} words, limit {a.abstract_max}", key="abslong")
    kw = tex_block(code, "keywords")
    if kw is None:
        m = re.search(r"\\keywords\s*\{([^}]*)\}", code)
        kw = m.group(1) if m else None
    if kw is not None:
        parts = [p for p in re.split(r"\\sep|\\and|[;,·]|\n\s*\n", strip_tex_keep(kw)) if p.strip()]
        R.add("INFO", "keywords", quote=f"{len(parts)}: " + "; ".join(p.strip() for p in parts)[:140], key="kw")
        if a.keywords_max and len(parts) > a.keywords_max:
            R.add("FAIL", "too many keywords", quote=f"{len(parts)} keywords, limit {a.keywords_max}", key="kwmax")
    heads = [(f, no, m.group(2)) for f, no, c, _, _ in src.lines for m in re.finditer(r"\\(section|chapter)\*?\s*\{([^}]*)\}", c)]
    R.add("INFO", "headings", quote=" / ".join(h for _, _, h in heads)[:300], key="heads")
    for req in [r.strip() for r in (a.require or "").split(",") if r.strip()]:
        if not any(fold(req) in fold(h) for _, _, h in heads) and not re.search(r"\\(paragraph|subsection|subsubsection)\*?\s*\{[^}]*" + re.escape(req), code, re.I):
            R.add("FAIL", "required section missing", quote=req, key="req" + req, hint="required by the call")


def strip_tex_keep(s):
    return re.sub(r"\\(?!sep\b|and\b)[A-Za-z@]+\*?", " ", s).replace("{", " ").replace("}", " ")


# ---- language / typography on the compiled text
def body_lines(comp):
    for page, line in comp.iter_lines():
        if comp.ref_page and page >= comp.ref_page:
            continue
        nums = len(re.findall(r"\d+(?:[.,]\d+)?", line))
        if nums >= 3 and nums * 2 > len(line.split()):
            continue  # table-like line (mostly numbers)
        yield page, line


def check_typography(src, comp, R):
    if not comp.ok:
        return
    prev = ""
    src_prose = " ".join(fold(strip_tex(c)) for _, _, c, _, _ in src.lines)
    for page, line in body_lines(comp):
        joined = prev + " " + line
        if len(line.split()) < 6:
            prev = ""
            continue
        for m in re.finditer(r"[a-z)\]](\.\.|,,|;;)(?!\.)", line):
            ctx = line[max(0, m.start() - 40):m.end() + 20]
            R.add("CHECK", "double/stray punctuation", src.locate(ctx), str(page), ctx, key=ctx)
        for m in re.finditer(r"\\[A-Za-z]{2,}\b|\\_", line):
            ctx = line[max(0, m.start() - 30):m.end() + 30]
            R.add("CHECK", "raw LaTeX in the PDF text", src.locate(ctx), str(page), ctx, key=ctx)
        prev = line


def check_doubled_words(src, R):
    """Doubled words in the source prose (linear text: pdftotext interleaves columns)."""
    prev_tail = ""
    for f, no, code, _, _ in src.lines:
        where = f"{f}:{no}"
        if re.search(r"\\begin\{|\\end\{|@\{", code):
            prev_tail = ""
            continue  # environment openings, column specifications
        # keep a placeholder where math or a command was, so that "at $2\times$ at" does not become "at at"
        line = re.sub(r"\$[^$]*\$|\\\(.*?\\\)", " \x01 ", code)
        line = re.sub(r"\\[A-Za-z@]+\*?(\[[^\]]*\])*(\{[^{}]*\})?", " \x01 ", line)
        line = re.sub(r"[{}~]", " ", line)
        if not line.strip():
            prev_tail = ""
            continue
        text = prev_tail + " " + line
        for m in re.finditer(r"\b([A-Za-z]{2,})\s+\1(?![-\w])", text, re.I):
            if m.end() > len(prev_tail) + 1 and m.group(1).lower() not in ("that", "had", "is", "can", "very"):
                R.add("CHECK", "doubled word", where, "", text[max(0, m.start() - 40):m.end() + 30].strip(),
                      key=f"dw{where}{m.start()}")
        prev_tail = " ".join(line.split()[-3:])


def check_macro_names(src, R):
    """A name that has a macro (\\newcommand{\\sysname}{\\textsc{FooBar}}) typed by hand in the text."""
    names = {}
    for f, no, code, _, _ in src.lines:
        m = re.search(r"\\(?:newcommand|renewcommand|providecommand|DeclareRobustCommand)\*?\s*\{?\\(\w+)\}?\s*\{(.*)\}\s*$", code) \
            or re.search(r"\\def\\(\w+)\s*\{(.*)\}\s*$", code)
        if not m or "#" in m.group(2):
            continue
        body = re.sub(r"\\(textsc|textrm|textsf|texttt|textbf|textit|emph|mbox|text|ensuremath|textup)\s*\{([^{}]*)\}", r"\2", m.group(2))
        body = re.sub(r"\\xspace|\\@|\{\}|\\,", "", body).strip()
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{2,}", body) and re.search(r"[A-Z]", body) and body.lower() not in (
                "the", "and", "for"):
            names.setdefault(body.lower(), (m.group(1), f"{f}:{no}"))
    if not names:
        return
    title_lines = {f"{f}:{no}" for f, no, c, _, _ in src.lines
                   if re.search(r"\\(title|shorttitle|titlerunning|shortauthors|authorrunning|hypersetup|pdfinfo|"
                                r"keywords|author|subtitle)\b", c)}
    for where, line in prose_lines(src, min_words=1):
        if where in title_lines:
            continue
        for w in re.finditer(r"(?<![\\\w-])([A-Za-z][A-Za-z0-9-]{2,})(?:'s|’s)?(?![\w-])", line):
            hit = names.get(w.group(1).lower())
            if hit:
                R.add("CHECK", "name typed without its macro", where, "", f"{w.group(1)} (macro \\{hit[0]}, {hit[1]})",
                      key=f"mn{where}{w.group(1)}", hint="the macro prints it differently (case, small caps)")


def check_citations_style(src, R):
    stats = Counter()
    where = defaultdict(list)
    for f, no, code, _, _ in src.lines:
        for rx, what in [(r"[A-Za-z] \\cite[tp]?\{", "space instead of ~ before \\cite"),
                         (r"\w\.\s*~?\\cite[tp]?\{[^}]*\}\s*([.,;:]|$)", "full stop before \\cite"),
                         (r"\\cite[tp]?\{[^}]*\}\s*~?\\cite[tp]?\{", "consecutive \\cite commands")]:
            if re.search(rx, code):
                stats[what] += 1
                where[what].append(f"{f}:{no}")
    for what, n in stats.items():
        R.add("CHECK" if what != "space instead of ~ before \\cite" else "INFO", what, ", ".join(where[what][:8]),
              quote=f"{n} lines", key=what)


# ---- names and acronyms
def check_name_variants(comp, R, src=None):
    if not comp.ok:
        return
    literal = {w for _, l in prose_lines(src, min_words=1) for w in re.findall(r"[A-Za-z][A-Za-z0-9-]*", l)} if src else None
    words = Counter()
    for page, line in body_lines(comp):
        for w in re.findall(r"\b[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*\b", line):
            if len(w) >= 3 and (re.search(r"[A-Z]", w[1:]) or (w[0].isupper() and re.search(r"[a-z]", w))):
                words[w] += 1
    groups = defaultdict(Counter)
    for w, c in words.items():
        groups[w.lower().replace("-", "")][w] += c
    for key, forms in groups.items():
        if len(forms) < 2:
            continue
        # ignore pure sentence-initial capitalisation differences (Faiss/faiss handled elsewhere)
        if literal is not None:
            forms = Counter({f: c for f, c in forms.items() if f in literal})
            if len(forms) < 2:
                continue
        distinct = {f[0].lower() + f[1:] for f in forms}
        if len(distinct) < 2:
            continue
        total = sum(forms.values())
        main = forms.most_common(1)[0]
        minority = [f"{f}×{c}" for f, c in forms.items() if f != main[0]]
        if total >= 4 and main[1] >= 2:
            R.add("CHECK", "name written in different ways", quote=f"{main[0]}×{main[1]} vs " + ", ".join(minority),
                  key="var" + key, hint="use one form (or the macro) everywhere")


COMMON_ACR = set("""AI API CPU GPU TPU RAM SSD HDD URL PDF HTML HTTP HTTPS XML JSON CSV SQL IO OS USA UK EU ID IDs
PhD NLP ML DL CV IR LLM LLMs RAG GB GiB MB MiB KB TB QPS FLOPs FLOP CUDA SIMD AVX II III IV VI VII VIII IX XI XII
ACM IEEE LNCS DOI ISBN ISSN OK ANN kNN NN CNN RNN LSTM BERT GPT ASCII UTF RGB MIT BSD GPL MRR NDCG MAP AUC ROC
BLEU ROUGE TREC BEIR MTEB BM25 SOTA SIGIR ECIR CIKM WSDM KDD WWW ICML ICLR ACL EMNLP NAACL AAAI IJCAI VLDB SIGMOD
ICDE CVPR ICCV ECCV NAACL COLING TODO FAQ PCA SVD SGD MSE MLP RL GNN""".split())
NONPROSE_ARG = (r"\\(begin|end|label|ref|cite[tp]?|eqref|cref|Cref|url|href|includegraphics|input|include|usepackage|"
                r"documentclass|newcommand|renewcommand|def|definecolor|bibliography\w*|section|subsection|subsubsection|"
                r"paragraph|caption|texttt|textsc|verb|lstinline|code|path)\*?(\[[^\]]*\])*\{[^}]*\}")


def prose_lines(src, min_words=5):
    """(file:line, text) of source prose: math, code, small caps and arguments of non-text commands removed."""
    verb = False
    for f, no, code, _, _ in src.lines:
        if re.search(r"\\begin\{(verbatim|Verbatim|lstlisting|minted|algorithmic|algorithm2e|tabular)", code):
            verb = True
        if verb:
            if re.search(r"\\end\{(verbatim|Verbatim|lstlisting|minted|algorithmic|algorithm2e|tabular)", code):
                verb = False
            continue
        c = re.sub(r"\$[^$]*\$|\\\(.*?\\\)", " ", code)
        c = re.sub(NONPROSE_ARG, " ", c)
        c = strip_tex(c)
        if len(c.split()) >= min_words:
            yield f"{f}:{no}", c


def check_acronyms(src, R):
    first, count, defined = {}, Counter(), {}
    order = 0
    for where, line in prose_lines(src):
        order += 1
        # "(ACR)", "(ACR, ...)", "(ACR; ...)" after the long form, or "ACR (long form)" before it
        for m in re.finditer(r"\(\s*([A-Z][A-Za-z0-9-]*[A-Z][A-Za-z0-9]*?)(s)?\s*[,;:)]", line):
            defined.setdefault(m.group(1), (order, where))
        for m in re.finditer(r"\b([A-Z][A-Z0-9]{2,6})s?\s+\((?:[a-z][a-z-]+ ){1,}", line):
            defined.setdefault(m.group(1), (order, where))
        if len(re.findall(r"\d+(?:\.\d+)?", line)) >= 4:
            continue  # table row
        for m in re.finditer(r"(?<![\w-])([A-Z][A-Z0-9]{2,6})(s)?(?![\w-])", line):
            acr = m.group(1)
            if acr in COMMON_ACR or re.fullmatch(r"[IVXLC]+", acr):
                continue
            before, after = line[:m.start()].rstrip(), line[m.end():].lstrip()
            if re.search(r"\b[A-Z]{2,}$", before) or re.match(r"[A-Z]{2,}\b", after):
                continue  # part of a multi-word upper-case name (MS MARCO)
            count[acr] += 1
            first.setdefault(acr, (order, where, line.strip()))
    rows = []
    for acr, c in count.items():
        if acr not in defined and c >= 2:
            rows.append(("CHECK", "acronym never expanded", acr, c))
        elif acr in defined and defined[acr][0] > first[acr][0]:
            rows.append(("CHECK", "acronym used before its definition", acr, c))
    rows.sort(key=lambda x: -x[3])
    for sev, kind, acr, c in rows[:12]:
        extra = f"; defined at {defined[acr][1]}" if acr in defined else ""
        R.add(sev, kind, first[acr][1], "", f"{acr} ×{c}: {first[acr][2][:80]}{extra}", key="acr" + acr,
              hint="expand at first use unless universally known in the venue")


# ====================================================================== numbers: tables and text
# One table model (table_index) feeds every number check: \multicolumn spans expanded to the column specification,
# header keys from the whole header stack, rows keyed by (group, method), blocks between rules, the proposed row and
# the direction of each metric.

# ---- parsing numbers (cells and prose share the same forms)
U_PREFIX = {"milli": "m", "micro": "µ", "nano": "n", "kilo": "k", "mega": "M", "giga": "G", "tera": "T", "kibi": "Ki",
            "mebi": "Mi", "gibi": "Gi", "tebi": "Ti"}
U_BASE = {"second": "s", "byte": "B", "percent": "%", "hour": "h", "minute": "min", "joule": "J", "watt": "W",
          "hertz": "Hz", "meter": "m", "metre": "m", "gram": "g", "bit": "bit"}
UNIT_CLASS = {"µs": "time", "us": "time", "ms": "time", "ns": "time", "s": "time", "sec": "time", "min": "time",
              "gib": "mem", "gb": "mem", "mib": "mem", "mb": "mem", "kib": "mem", "kb": "mem", "tb": "mem"}
UNIT_RX = r"×|%|µs|us|ms|ns|sec|min|s|GiB|GB|MiB|MB|KiB|KB|TB|QPS"
SUFFIX = {"k": 1e3, "K": 1e3, "M": 1e6, "B": 1e9, "G": 1e9, "T": 1e12}
# sign, mantissa, exponent, K/M/B suffix, unit; never inside words (GPT-4, Llama-3-8B, R@10, x_2)
NUM_TOKEN = re.compile(r"(?<![\w.\-/:@^])(-?)(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?:[eE]([-+]?\d+))?"
                       r"([kKMBGT](?![A-Za-z]))?(?:\s*(" + UNIT_RX + r"))?(?![\w.])")


class Num:
    """A printed number: value (scaled), printed form, decimals, rounding tolerance, unit."""
    __slots__ = ("v", "s", "dec", "tol", "unit", "exp", "ci")

    def __init__(self, m, ci=None):
        self.ci = ci
        sign, mant, e, suf, unit = m.groups()
        scale = (10.0 ** int(e) if e else 1.0) * SUFFIX.get(suf or "", 1.0)
        self.v = (-1 if sign else 1) * float(mant.replace(",", "")) * scale
        self.s = sign + mant + (f"e{e}" if e else "") + (suf or "")
        self.dec = len(mant.split(".")[1]) if "." in mant else 0
        self.tol = 0.5 * 10 ** (-self.dec) * scale
        self.unit = unit or ""
        self.exp = bool(e or suf)


def si_unit(u):
    u = re.sub(r"\\([A-Za-z]+)", lambda m: U_PREFIX.get(m.group(1), U_BASE.get(m.group(1), "")), u)
    u = re.sub(r"[{}\s~]", "", u)
    return "µs" if u == "us" else u


def norm_tex_numbers(code):
    """LaTeX → plain text in which every printed number is one NUM_TOKEN (signs, \\SI/\\num/\\qty, 10^{n}, ×)."""
    c = re.sub(r"\\(cite[tp]?|citeauthor|citeyear|ref|eqref|autoref|cref|Cref|label|url|href|includegraphics|input|"
               r"include)\*?(\[[^\]]*\])*\{[^}]*\}", " ", code)
    c = re.sub(r"\\(?:SI|qty)\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}\s*\{((?:[^{}]|\{[^{}]*\})*)\}",
               lambda m: f"{m.group(1)} {si_unit(m.group(2))}", c)
    c = re.sub(r"\\num\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}", r"\1", c)
    c = re.sub(r"\\si\s*(?:\[[^\]]*\])?\s*\{((?:[^{}]|\{[^{}]*\})*)\}", lambda m: si_unit(m.group(1)), c)
    c = re.sub(r"\\percent(?![A-Za-z])", "%", c)
    c = re.sub(r"(\d)\s*(\\,|\\thinspace|\{,\}|\\;|~)\s*(\d)", r"\1,\3", c)
    c = re.sub(r"\$\s*-\s*\$\s*(?=[\d.])|\\textminus\s*|−|\\minus(?![A-Za-z])\s*", "-", c)
    c = re.sub(r"(\d(?:[\d.,]*\d)?)\s*\$?\s*(?:\\times|\\cdot|×)\s*\$?\s*10\s*\^\s*\{?\s*([-+]?\d+)\s*\}?", r"\1e\2", c)
    c = re.sub(r"(?<![\d.])10\s*\^\s*(?:\{\s*([-+]?\d+)\s*\}|([-+]?\d))", lambda m: "1e" + (m.group(1) or m.group(2)), c)
    c = re.sub(r"\$?\\times\$?|\\texttimes", "×", c)
    c = re.sub(r"\$?\\mu\$?\s*\\?,?\s*s\b|\\textmu\s*s\b|\\us\b", "µs", c)
    c = c.replace("\\%", "%").replace("$", " ").replace("~", " ")
    c = re.sub(r"\\[,;:!]", " ", c)
    return c


def parse_number(s):
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def take_group(s, i):
    """s[i] == '{': (content, index after the matching '}')."""
    depth, j = 0, i
    while j < len(s):
        ch = s[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)


def cmd_apply(s, names, nargs, keep=None):
    """Rewrite each \\name[opt]{a1}...{an}: drop it, or keep its argument number `keep`."""
    rx = re.compile(r"\\(?:" + names + r")(?![A-Za-z])\*?")
    out, i = [], 0
    while True:
        m = rx.search(s, i)
        if not m:
            out.append(s[i:])
            return "".join(out)
        out.append(s[i:m.start()])
        j, args = m.end(), []
        while len(args) < nargs:
            while j < len(s) and s[j] in " \t\n":
                j += 1
            if j < len(s) and s[j] == "[":
                k = s.find("]", j)
                j = k + 1 if k != -1 else len(s)
            elif j < len(s) and s[j] == "{":
                a, j = take_group(s, j)
                args.append(a)
            else:
                break
        out.append(" " + (args[keep - 1] if keep and len(args) >= keep else "") + " ")
        i = j


def split_top(s, sep):
    """Split at `sep` ('&' or the row end) outside braces; escaped characters never split."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(s):
        ch = s[i]
        if ch == "\\":
            if sep == "\\\\" and depth == 0 and s.startswith("\\\\", i):
                parts.append(s[start:i])
                i += 2
                start = i
                continue
            if sep == "\\\\" and depth == 0 and s.startswith("\\tabularnewline", i):
                parts.append(s[start:i])
                i += len("\\tabularnewline")
                start = i
                continue
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch == sep and depth == 0:
            parts.append(s[start:i])
            start = i + 1
        i += 1
    parts.append(s[start:])
    return parts


FMT_KEEP = (r"textbf|textit|emph|textsc|textsf|texttt|textrm|textnormal|textup|text|mathbf|mathrm|mathit|mathsf|"
            r"boldsymbol|bm|underline|uline|ul|makecell|shortstack|mbox|hbox|best|thead|Centerstack")
FMT_DROP = (r"rlap|llap|hspace|vspace|phantom|hphantom|vphantom|cellcolor|rowcolor|color|footnote|tnote|"
            r"tablefootnote|label|footnotemark")
EMPTY_RX = re.compile(r"\s*(-|--|---|–|—|n/?a|oom|oot|tle|\\textemdash|\\textendash|\\xmark|✗|\\ding\{55\})\s*", re.I)
SMALL_RX = re.compile(r"\\(scriptsize|tiny|footnotesize)(?![A-Za-z])")


class Cell:
    __slots__ = ("raw", "v", "s", "dec", "tol", "unit", "times", "pct", "bold", "under", "spread", "empty", "mc", "mark",
                 "ci")

    def __init__(self, raw="", mc=False):
        self.raw, self.mc, self.ci = raw, mc, None
        self.v = self.s = None
        self.dec, self.tol, self.unit = 0, 0.0, ""
        self.times = self.pct = self.bold = self.under = self.empty = self.mark = False
        self.spread = None

    @property
    def num(self):  # a plain value (not a × ratio)
        return self.v is not None and not self.times


def parse_cell(raw, ctx=None, mc=False):
    """Value of a table cell: sign kept, 'value ± spread' split, side notes, citations and model names ignored."""
    cell = Cell(raw, mc)
    c = raw
    cell.bold = bool((ctx.bold_rx if ctx else BOLD_RX).search(c))
    cell.under = bool((ctx.under_rx if ctx else UNDER_RX).search(c))
    cell.mark = bool(re.search(r"\\(dagger|ddagger|dag|ddag)(?![A-Za-z])|[†‡]|\^\s*\{?\s*\*|\\textsuperscript\{\s*\*", c))
    c = cmd_apply(c, "multirow", 3, keep=3)
    c = cmd_apply(c, FMT_DROP, 1)
    c = cmd_apply(c, "rule", 2)
    c = cmd_apply(c, "textcolor|colorbox", 2, keep=2)
    names = FMT_KEEP + ("|" + "|".join(ctx.fmt_macros) if ctx and ctx.fmt_macros else "")
    for _ in range(2):
        c = cmd_apply(c, names, 1, keep=1)
    c = c.replace("\\\\", " ")
    c = re.sub(r"^\s*/(?!/)", "", c)  # "11\,665 & /2\,578": the second value of a column pair (two datasets)
    if EMPTY_RX.fullmatch(c.replace("{", "").replace("}", "")) or not c.strip("{} "):
        cell.empty = bool(c.strip("{} "))
        return cell
    if re.fullmatch(r"\s*-?\d+,\d{1,2}\s*", c):
        c = c.replace(",", ".")  # decimal comma
    c = norm_tex_numbers(c)
    c = re.sub(r"(\d)\s*x(?![A-Za-z])", r"\1×", c)
    spreads = []

    def spread(m):
        spreads.append(float(m.group(1)))
        return " "
    main = re.sub(r"(?:\\pm|±|\\textpm|\+/-)\s*\{?\s*(-?\d+(?:\.\d+)?)\s*\}?", spread, c)
    main = re.sub(r"_\s*\{\s*(?:\\pm|±)?\s*\(?\s*(-?\d+(?:\.\d+)?)\s*\)?\s*\}", spread, main)
    main = re.sub(r"\\textsubscript\s*\{\s*(?:\\pm|±)?\s*\(?\s*(-?\d+(?:\.\d+)?)\s*\)?\s*\}", spread, main)
    sm = SMALL_RX.search(main)
    if sm and NUM_TOKEN.search(main[:sm.start()]):  # value, then a small-font side note: (0.3) is a spread
        tail = main[sm.end():]
        tm = re.fullmatch(r"[\s{}]*\(?\s*(?:\\pm|±)?\s*(-?\d+(?:\.\d+)?)\s*\)?[\s{}]*", tail)
        if tm:
            spreads.append(float(tm.group(1)))
        main = main[:sm.start()]
    if NUM_TOKEN.search(re.sub(r"\([^()]*\)", " ", main)):
        main = re.sub(r"\([^()]*\)", " ", main)  # "85.2 (+3.1)": the parenthesis is a side note
    cell.times = "×" in main
    cell.pct = "%" in main
    main = re.sub(r"\^\s*(\{[^{}]*\}|\\?[A-Za-z]+|\S)|\\textsuperscript\s*\{[^{}]*\}", " ", main)  # footnote marks
    nums = list(NUM_TOKEN.finditer(main))
    cell.spread = spreads[0] if spreads else None
    if len(nums) != 1:
        return cell
    rest = re.sub(r"\\[A-Za-z]+", " ", main[:nums[0].start()] + " " + main[nums[0].end():])
    if re.search(r"[A-Za-z=]", rest):
        return cell  # "d=128, l2", "8 bit / m=64", "QPS 500": a label, not a value
    n = Num(nums[0])
    cell.v, cell.s, cell.dec, cell.tol, cell.unit = n.v, n.s, n.dec, n.tol, n.unit
    return cell


BOLD_RX = re.compile(r"\\(textbf|mathbf|bf|bfseries|boldmath|best)(?![A-Za-z])")
UNDER_RX = re.compile(r"\\(underline|uline|ul)(?![A-Za-z])")


def tex_plain(s):
    """Header or label text: formatting dropped, user macros kept by name, arrows and % kept."""
    s = re.sub(r"\\(cite[tp]?|citeauthor|ref|autoref|cref|Cref)\*?(\[[^\]]*\])*\{[^}]*\}", " ", s)
    s = cmd_apply(s, "multirow", 3, keep=3)
    s = cmd_apply(s, FMT_DROP, 1)
    s = cmd_apply(s, "textcolor|colorbox", 2, keep=2)
    s = s.replace("\\\\", " ")
    s = re.sub(r"\$?\\uparrow\$?|\\textuparrow", "↑", s)
    s = re.sub(r"\$?\\downarrow\$?|\\textdownarrow", "↓", s)
    s = re.sub(r"\\(dagger|ddagger|dag|ddag)(?![A-Za-z])", "†", s)
    s = re.sub(r"\$?\\mu\$?|\\textmu", "µ", s)
    s = s.replace("\\%", "%").replace("\\#", "#").replace("\\&", "&")
    s = re.sub(r"\\(" + FMT_KEEP + r"|bfseries|itshape|scshape|bf|it|small|scriptsize|footnotesize|tiny|normalsize|"
               r"large|Large|centering|raggedleft|raggedright|boldmath|arraybackslash|quad|qquad|enspace)(?![A-Za-z])\*?",
               " ", s)
    s = re.sub(r"\\[,;:! ]", " ", s)
    s = re.sub(r"\\([A-Za-z]+)", r" \1 ", s)
    s = re.sub(r"[{}$~^_]", " ", s)
    return " ".join(s.split())


def label_of(cell):
    return re.sub(r"[^a-z0-9+\-]", "", fold(tex_plain(cell)))


def htext(cell):
    return fold(tex_plain(cell))


# ---- metric semantics
LOWER_RX = re.compile(r"\b(time|latency|runtime|run-time|error|err|loss|ppl|perplexity|wer|cer|fid|bytes|memory|mem|"
                      r"size|mse|mae|rmse|footprint|energy|cost|rss|uss|ram|build)\b")
HIGHER_RX = re.compile(r"\b(acc|accuracy|recall|precision|prec|f1|map|mrr|ndcg|auc|auroc|bleu|rouge\S*|qps|throughput|"
                       r"speedup|speed-up|hits?|success|em|win rate)\b|(?<![a-z])[rp]@\d")
HIGHER_CAP = re.compile(r"higher (values? )?(is|are) better|larger (is|are) better|largest|highest")
LOWER_CAP = re.compile(r"lower (values? )?(is|are) better|smaller (is|are) better|lowest|smallest")
EFF_RX = re.compile(r"param|#|\bn\b|count|size|flops|macs|time|latency|runtime|memory|mem\b|qps|throughput|speed|"
                    r"energy|bytes|ratio|×|\bgb\b|\bmb\b|\bms\b|µs|μs")
COUNT_RX = re.compile(r"param|#|^n$|\bn\b|count|year|\bdim|bits?\b|batch|epoch|steps|layers|tokens|samples|queries|size")
TIME_RX = re.compile(r"time|latency|runtime|\bms\b|µs|μs|\(s\)|sec\b")
QPS_RX = re.compile(r"qps|throughput|queries/s|q/s|tokens/s")
METRIC_RX = re.compile(r"recall|precision|accuracy|\bacc\b|ndcg|mrr|\bmap\b|\bf1\b|bleu|rouge|latency|time|memory|"
                       r"throughput|qps|\bauc\b|error|loss|perplexity|ppl|@\d|\(%\)|\((ms|µs|μs|s|gb|mb)\)")
KNOB_RX = re.compile(r"^(k|n|m|b|bits?|steps?|budget|size|frames?|#?\s*samples?|tokens?|context|ef|nprobe|"
                     r"top-?k|batch|epochs?|budget.*|.*\(%\))$")
GAIN_RX = re.compile(r"gain|Δ|δ|delta|improv|relative|\brel\b|speedup|increase|decrease|overhead|change|diff")
BOUND_RX = re.compile(r"oracle|upper[- ]?bound|ceiling|\bexact\b|brute[- ]?force|exhaustive|\bfull\b(?! model)|"
                      r"fp16|fp32|teacher|ground[- ]?truth|\bhuman\b|uncompressed")
DENSE_RX = re.compile(r"\bdense\b")  # a bound only when the table is about sparsity, pruning or compression
DROP_RX = re.compile(r"\b(loss|drop|degradation|decrease|reduction|gap|error|overhead)\b")
ABL_RX = re.compile(r"\bw/o\b|\bwithout\b|^\s*no\s+\w|^\s*[-−–]\s*\w")
FULL_RX = re.compile(r"\bfull\b|\bours\b|proposed|complete|\ball\b")
OURS_RX = re.compile(r"\bours\b|\(ours\)|\bproposed\b|\bour (method|approach|model|system)\b", re.I)


def direction(text, caption=""):
    """+1 higher is better, -1 lower is better, 0 unknown: arrows in the header, metric name, caption arrows."""
    up, down = "↑" in text, "↓" in text
    if up != down:
        return 1 if up else -1
    if re.search(r"speed-?up", text):
        return 1
    hm = HIGHER_RX.search(text)
    if hm and DROP_RX.search(text, hm.end()):
        return -1  # "Recall loss (%)", "Accuracy drop": a quality lost, lower is better
    lm = LOWER_RX.search(text)
    if lm and not hm and re.search(r"\b(reduction|decrease|savings?|saved)\b", text[lm.end():]):
        return 1  # "Latency reduction (%)": higher is better
    lo, hi = bool(lm), bool(hm)
    if lo != hi:
        return -1 if lo else 1
    cu = "↑" in caption or bool(HIGHER_CAP.search(caption))
    cd = "↓" in caption or bool(LOWER_CAP.search(caption))
    if cu != cd:
        return 1 if cu else -1
    return 0


def better(a, b, d, tol=0.0):
    return (a - b > tol) if d > 0 else (b - a > tol)


# ---- the table model
class Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Table:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def col_text(self, c):
        return " ".join(self.htexts[c])

    def leaf(self, c):
        return self.htexts[c][-1] if self.htexts[c] else ""

    def knob_leaf(self, c):
        return bool(re.fullmatch(r"[\d.,%\s]+|[a-z]{0,6}\s*=\s*[\d.,]+%?", self.leaf(c)))

    def metric_text(self, c):
        """The column's metric: the header stack, unless the leaf is a knob value (then the stack names the knob)."""
        if not self.knob_leaf(c):
            return self.col_text(c)
        parent = " ".join(self.htexts[c][:-1])
        if "%" not in parent and (direction(parent) or METRIC_RX.search(parent) or UNIT_TOKEN_RX.search(parent)):
            return parent  # "QPS / 90%": QPS at a target
        # "Accuracy (%) / 93": the target; "MS MARCO / 95%": the dataset; the caption names the measure
        return self.caption_metric(parent) or ("" if "%" in parent else parent)

    def caption_metric(self, knob):
        """The measured quantity named by the caption, the knob's own words removed ("latency (µs) vs accuracy@10")."""
        words = {w for w in re.findall(r"[a-z]{3,}", knob)}
        text = re.sub(r"\d\s*%\s*[a-z]+(@\s*\d+)?|[a-z]+@\s*\d+\s*=?\s*[\d.]+\s*%?", " ", self.cap_text)  # "at 99% accuracy"
        for w in words:
            text = re.sub(r"\b" + re.escape(w) + r"\S*", " ", text)
        m = LOWER_RX.search(text) or HIGHER_RX.search(text)
        if not m or (LOWER_RX.search(text) and HIGHER_RX.search(text)):
            return ""
        unit = re.match(r"\s*\(([^()]{1,8})\)", text[m.end():])
        return m.group(0) + (f" ({unit.group(1)})" if unit else "")

    def direction(self, c):
        return direction(self.metric_text(c), self.cap_text)

    def eff_dir(self, c, vals=None):
        """Direction for win counts: unknown scores in [0, 100] count as higher-is-better."""
        d = self.direction(c)
        if d or COUNT_RX.search(self.metric_text(c)):
            return d
        vals = vals if vals is not None else [r.cells[c].v for r in self.rows if r.cells[c].num]
        return 1 if vals and all(0 <= v <= 100 for v in vals) else 0

    def data_cols(self):
        return range(self.nlab, self.ncols)

    def is_bound(self, r):
        """An oracle / upper bound / exact / full-precision row ('dense' only in a table about sparsity or pruning)."""
        return bool(BOUND_RX.search(r.label) or (DENSE_RX.search(r.label) and re.search(
            r"spars|prun|compress|quantiz", self.cap_text)))

    def colname(self, c, grp=None):
        """Group, parent header levels and leaf: 'ms marco/r@10'."""
        name = "/".join(x for x in (grp, *self.htexts[c]) if x) or f"col {c + 1}"
        dup = [x for x in self.data_cols() if self.htexts[x] == self.htexts[c] and not self.ratio_col(x)] \
            if self.htexts[c] else []
        return name + (f" ({dup.index(c) + 1} of {len(dup)})" if len(dup) > 1 else "")  # "11 665 / 2 578" pairs

    def ratio_col(self, c):
        vals = [r.cells[c] for r in self.rows if r.cells[c].v is not None]
        return bool(vals) and sum(x.times for x in vals) * 2 >= len(vals)

    def sets(self, c):
        """Rows of column c grouped by (block, group): the cells that compete."""
        out = defaultdict(list)
        for r in self.rows:
            if r.cells[c].num:
                out[(r.block, r.group)].append(r)
        return out

    @property
    def name(self):
        return f"table at {self.start}"


class PaperCtx:
    def __init__(self, src):
        code = src.code()
        self.defined, bold, under = {}, set(), set()
        for m in re.finditer(r"\\(?:(?:re)?newcommand|DeclareRobustCommand|providecommand)\*?\s*\{?\s*\\([A-Za-z]+)\s*\}?"
                             r"|\\def\s*\\([A-Za-z]+)", code):
            name, j = m.group(1) or m.group(2), m.end()
            while j < len(code):
                if code[j] in " \t\n":
                    j += 1
                elif code[j] == "[":
                    j = code.find("]", j) + 1 or len(code)
                elif code[j] == "#":
                    j += 2
                else:
                    break
            body = take_group(code, j)[0] if j < len(code) and code[j] == "{" else ""
            self.defined[name] = body
            if re.search(r"\\(textbf|mathbf|bfseries|boldmath|bf)(?![A-Za-z])", body) and "#1" in body:
                bold.add(name)
            if re.search(r"\\(underline|uline|ul)(?![A-Za-z])", body):
                under.add(name)
        self.fmt_macros = sorted((bold | under) - {"best"})
        self.bold_rx = re.compile(r"\\(textbf|mathbf|bf|bfseries|boldmath|best" + "".join("|" + n for n in bold) +
                                  r")(?![A-Za-z])")
        self.under_rx = re.compile(r"\\(underline|uline|ul" + "".join("|" + n for n in under) + r")(?![A-Za-z])")
        am = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", code, re.S)
        abstract = am.group(1) if am else ""
        if not am:
            m = re.search(r"\\abstract\s*\{", code)
            abstract = take_group(code, m.end() - 1)[0] if m else ""
        self.abstract_macros = {n for n in re.findall(r"\\([A-Za-z]+)", abstract)
                                if n in self.defined and n not in bold | under and re.search(r"[A-Za-z]", self.defined[n])}
        # the paper's own system: the macros of the abstract sentence that presents it ("We present \sys"), or the
        # abstract's only name macro
        intro = " ".join(x for x in re.split(r"(?<=[.!?])\s+", abstract) if re.search(
            r"\b(we|this (paper|work|article))\s+(\w+\s+)?(present|propose|introduce|develop|design|describe|"
            r"call|name)|\b(called|named|dubbed)\b", x, re.I))
        self.own_macros = {n for n in re.findall(r"\\([A-Za-z]+)", intro) if n in self.abstract_macros}
        if not self.own_macros and len(self.abstract_macros) == 1:
            self.own_macros = set(self.abstract_macros)

    def names_own(self, name):
        """A row macro that names the paper's system: the macro itself, an extension of its name (\\syshnsw for
        \\sys), or a macro whose body uses it."""
        return any(name == m or (len(m) >= 3 and name.startswith(m)) or
                   re.search(r"\\" + m + r"(?![A-Za-z])", self.defined.get(name, "")) for m in self.own_macros)


_TABLES = {}
TAB_BEGIN = re.compile(r"\\begin\{(tabular\*?|tabularx|tabulary|longtable)\}")
RULE_RX = re.compile(r"\\(toprule|midrule|bottomrule|hline|cline|cmidrule|specialrule|Xhline|hhline)(?![A-Za-z])"
                     r"(\([^)]*\))?(\[[^\]]*\])?(\{[^}]*\})*")


def expand_row(content, ctx):
    """Cells of one row with \\multicolumn spans expanded: [(Cell, raw)]; the covered columns get empty cells."""
    out = []
    for c in split_top(content, "&"):
        m = re.match(r"\s*\\multicolumn\s*\{\s*(\d+)\s*\}\s*", c)
        if m and m.end() < len(c) and c[m.end()] == "{":
            _, j = take_group(c, m.end())
            while j < len(c) and c[j] in " \t\n":
                j += 1
            if j < len(c) and c[j] == "{":
                inner, j2 = take_group(c, j)
                n = max(1, int(m.group(1)))
                out.append((parse_cell(inner + c[j2:], ctx, mc=True), inner, n))
                out += [(Cell("", True), "", 0)] * (n - 1)
                continue
        out.append((parse_cell(c.strip(), ctx), c.strip(), 1))
    return out


def table_index(src):
    """Every tabular as a Table (cached per source tree)."""
    if id(src) in _TABLES:
        return _TABLES[id(src)]
    ctx = PaperCtx(src)
    code = "\n".join(f"\x00{f}:{no}\x00" + c for f, no, c, _, _ in src.lines)
    envs = [(m.start(), m.end()) for m in re.finditer(
        r"\\begin\{(table|sidewaystable|wraptable)\*?\}.*?\\end\{\1\*?\}", code, re.S)]
    out = []
    for m in TAB_BEGIN.finditer(code):
        env = m.group(1)
        end = code.find("\\end{" + env + "}", m.end())
        if end == -1:
            continue
        j, args, nargs = m.end(), [], 2 if env in ("tabular*", "tabularx", "tabulary") else 1
        while len(args) < nargs and j < end:
            if code[j] in " \t\n":
                j += 1
            elif code[j] == "\x00":
                j = code.index("\x00", j + 1) + 1
            elif code[j] == "[":
                j = code.find("]", j) + 1
            elif code[j] == "{":
                a, j = take_group(code, j)
                args.append(a)
            else:
                break
        spec = re.sub(r"\x00[^\x00]*\x00", "", args[-1]) if args else ""
        body = re.sub(r"\x00[^\x00]*\x00", "", code[j:end])
        k = code.rfind("\x00", 0, m.start())
        k0 = code.rfind("\x00", 0, k)
        start = code[k0 + 1:k] if k0 != -1 else "?"
        env = next(((s, e) for s, e in envs if s <= m.start() < e), None)
        around = re.sub(r"\x00[^\x00]*\x00", "", code[env[0]:env[1]]) if env else ""
        if env:
            # several tabulars in one float, each with its own \caption and \label: the ones between the previous
            # tabular and this one (or, if none, between this one and the next)
            tabs = [x for x in TAB_BEGIN.finditer(code, env[0], env[1])]
            if len(tabs) >= 2 and len(re.findall(r"\\caption\s*[\[{]", around)) >= 2:
                i = next(k for k, x in enumerate(tabs) if x.start() == m.start())
                prev_end = code.find("\\end{" + tabs[i - 1].group(1) + "}", tabs[i - 1].end()) if i else env[0]
                next_start = tabs[i + 1].start() if i + 1 < len(tabs) else env[1]
                seg = code[prev_end:m.start()]
                if not re.search(r"\\caption\s*[\[{]", seg):
                    seg = code[end:next_start]
                around = re.sub(r"\x00[^\x00]*\x00", "", seg)
        caps = []
        for cm in re.finditer(r"\\caption\s*(\[[^\]]*\])?\s*\{", around):
            caps.append(take_group(around, cm.end() - 1)[0])
        caption = " ".join(caps)
        t = build_table(start, spec, body, caption, re.findall(r"\\label\{([^}]*)\}", around), ctx)
        if t:
            out.append(t)
    _TABLES[id(src)] = (out, ctx)
    return out, ctx


def build_table(start, spec, body, caption, labels, ctx):
    items = []  # (rules before the row, expanded cells)
    for ch in split_top(body, "\\\\"):
        ch = re.sub(r"^\s*\*?\s*\[[^\]]*\]", "", ch)
        rules = set(m.group(1) for m in RULE_RX.finditer(ch))
        content = RULE_RX.sub(" ", ch)
        content = re.sub(r"\\(rowcolor|rowcolors)\s*(\[[^\]]*\])?\s*\{[^}]*\}|\\addlinespace(\[[^\]]*\])?|"
                         r"\\noalign\s*\{[^}]*\}|\\(endhead|endfirsthead|endfoot|endlastfoot)(?![A-Za-z])", " ", content)
        if items and not content.strip():
            items[-1][2].update(rules)  # rules after the last row
            continue
        cells = expand_row(content, ctx) if content.strip() else []
        items.append((rules, cells, set()))
    rows_all = [(r, c) for r, c, _ in items if len(c) >= 2]
    if not rows_all:
        return None
    ncols = max(len(column_alignments(spec)), max(len(c) for _, c in rows_all))
    rows_all = [(r, c + [(Cell(), "", 1)] * (ncols - len(c))) for r, c in rows_all]
    # header: before the first \midrule (booktabs), or before the first rule that follows a row
    if any("midrule" in r for r, _ in rows_all):
        h = next((i for i, (r, _) in enumerate(rows_all) if "midrule" in r), 0)
    else:
        h = next((i for i, (r, _) in enumerate(rows_all) if i >= 1 and r & {"hline", "cline", "Xhline", "hhline"}), None)
        if h is None or h > 3:
            first = rows_all[0][1][1:]
            h = 1 if sum(1 for c, _, n in first if c.v is not None) * 2 < len(first) else 0
    header = [c for _, c in rows_all[:h]]
    levels, htexts = [[] for _ in range(ncols)], [[] for _ in range(ncols)]
    for hr in header:
        ci = 0
        for cell, raw, n in hr:
            if n == 0:
                continue
            for cj in range(ci, min(ncols, ci + n)):
                if raw.strip() and label_of(raw):
                    levels[cj].append(label_of(raw))
                    htexts[cj].append(htext(raw))
            ci += n
    # body rows, blocks, section rows
    body, block, section = [], 0, None
    for i, (rules, cells) in enumerate(rows_all[h:]):
        if i and rules:
            block += 1
        filled = [(c, raw) for c, raw, n in cells if n and raw.strip()]
        if len(filled) == 1 and filled[0][0].v is None and not filled[0][0].empty:
            section = label_of(filled[0][1]) or section  # a full-width label row names the rows below it
            continue
        body.append((block, section, cells))
    if not body:
        return None
    # label columns: leading columns that are mostly not numbers
    nlab = 0
    for c in range(min(3, ncols - 1)):
        vals = [cells[c][0] for _, _, cells in body if cells[c][1].strip()]
        if vals and sum(1 for x in vals if x.v is not None) * 2 < len(vals):
            nlab += 1
        else:
            break
    corner = htexts[0][-1] if htexts[0] else ""
    knob_rows = False
    if nlab == 0:
        col0 = [cells[0][0].v for _, _, cells in body]
        if all(v is not None for v in col0) and len(col0) >= 3 and (
                KNOB_RX.match(corner) or all(b > a for a, b in zip(col0, col0[1:]))):
            nlab, knob_rows = 1, True
    rows, group = [], None
    for ri, (blk, sec, cells) in enumerate(body):
        raws = [raw for _, raw, _ in cells]
        if nlab >= 2:
            g = " ".join(raws[:nlab - 1]).strip()
            if label_of(g) and not g.startswith("("):  # "(d=128, l2)": a second line of the group label
                group = label_of(g)  # \multirow: the group label carries down
            grp = group
        else:
            grp = sec
        lab_raw = raws[nlab - 1] if nlab else ""
        rows.append(Row(cells=[c for c, _, _ in cells], raw=raws, mc=[c.mc for c, _, _ in cells], block=blk, group=grp,
                        method=label_of(lab_raw) if nlab else str(ri), label_raw=lab_raw,
                        label=htext(lab_raw) if nlab else "", ri=ri,
                        imported=any(c.mark for c, _, _ in cells)))
    cap_text = htext(caption)
    t = Table(start=start, labels=set(labels), caption=caption, cap_text=cap_text, levels=levels, htexts=htexts,
              ncols=ncols, nlab=nlab, rows=rows, knob_rows=knob_rows, corner=corner, spec=spec, header_rows=h,
              aligns=column_alignments(spec))
    # transposed: metrics as rows, systems as columns (or rows that mix units)
    # a label names a metric as a whole: it starts with a metric word, or carries a unit, an arrow or @k
    # ("Recall-Boost" is a method that happens to contain one)
    labs = [r.label for r in rows if r.label]
    lab_metric = sum(1 for x in labs if re.match(r"\s*(" + METRIC_RX.pattern + r")(?![a-z-])", x) or re.search(
        r"\((%|ms|µs|μs|s|gb|mb|gib|mib|×)\)|[↑↓]|@\s*\d", x))
    head_metric = sum(1 for c in t.data_cols() if METRIC_RX.search(t.col_text(c)))
    units_mixed = len({u for x in labs for u in re.findall(r"\((%|ms|µs|μs|s|gb|mb)\)", x)}) >= 2
    systems = any(AVG_HEAD_RX.match(t.leaf(c)) for c in t.data_cols()) or any(
        r.label_raw and (OURS_RX.search(tex_plain(r.label_raw)) or any(
            ctx.names_own(n) for n in re.findall(r"\\([A-Za-z]+)", r.label_raw))) for r in rows)
    t.transposed = bool(nlab and not knob_rows and len(labs) >= 2 and not systems and (
        (lab_metric * 2 >= len(labs) and head_metric * 2 < max(1, len(t.data_cols()))) or units_mixed))
    t.units = {u.lower() for u in re.findall(r"(?<![A-Za-z])(µs|us|ms|ns|sec|min|GiB|GB|MiB|MB|KiB|KB|TB|QPS|(?<=\()s(?=\)))(?![A-Za-z])",
                                             norm_tex_numbers(caption + " " + " ".join(
                                                 raw for hr in header for _, raw, _ in hr)))}
    for r in rows:
        for ci, c in enumerate(r.cells):
            c.ci = ci
    t.values = [r.cells[c] for r in rows for c in t.data_cols() if r.cells[c].v is not None]
    t.header_nums = []
    for hr in header:
        ci = 0
        for _, raw, n in hr:
            if n:
                t.header_nums += [Num(m, ci) for m in NUM_TOKEN.finditer(norm_tex_numbers(raw))]
                ci += n
    t.sys_groups = system_groups(t)
    t.proposed, t.proposed_how = proposed_methods(t, ctx)
    return t


def system_groups(t):
    """Column groups that put systems side by side under one metric ("QPS: ours | faiss"): {column: siblings}."""
    groups = defaultdict(list)
    for c in t.data_cols():
        if len(t.levels[c]) >= 2:
            groups[tuple(t.levels[c][:-1])].append(c)
    out = {}
    for cols in groups.values():
        parent = " ".join(t.htexts[cols[0]][:-1])
        leaves = [t.leaf(c) for c in cols]
        if len(cols) >= 2 and (METRIC_RX.search(parent) or UNIT_TOKEN_RX.search(parent)) and not any(
                METRIC_RX.search(x) or t.knob_leaf(c) or re.search(r"\d", x) for x, c in zip(leaves, cols)):
            for c in cols:
                out[c] = cols
    return out


def proposed_methods(t, ctx):
    """(method keys of the proposed row, how): 'ours'/'proposed' labels, else the paper's own name macro (used in the
    abstract), else the row with most bold cells."""
    if not t.nlab or t.sys_groups or sum(1 for r in t.rows for c in r.cells[t.nlab:] if c.num) < 2:
        return set(), None
    ours = {r.method for r in t.rows if r.label_raw and OURS_RX.search(tex_plain(r.label_raw))
            and not ABL_RX.search(r.label)}  # "Ours (w/o pruning)": an ablation variant, not a competitor
    if ours:
        return ours, "label"
    own = {r.method for r in t.rows if not ABL_RX.search(r.label) and any(
        ctx.names_own(n) for n in re.findall(r"\\([A-Za-z]+)", r.label_raw))}
    if own and len(own) < len({r.method for r in t.rows}):
        return own, "own"
    bold = Counter()
    for r in t.rows:
        bold[r.method] += sum(1 for c in r.cells[t.nlab:] if c.bold and c.v is not None)
    by_macro = defaultdict(set)
    for r in t.rows:
        for n in re.findall(r"\\([A-Za-z]+)", r.label_raw):
            if n in ctx.abstract_macros:
                by_macro[n].add(r.method)
    if by_macro:
        score = {n: sum(bold[x] for x in ms) for n, ms in by_macro.items()}
        best = max(score.values())
        top = [n for n, s in score.items() if s == best]
        if len(top) == 1 and best > 0:
            return by_macro[top[0]], "macro+bold"
        if len(by_macro) == 1:
            return by_macro[top[0]], "macro"
    if bold:
        (m1, b1), *rest = bold.most_common(2)
        if b1 >= 2 and (not rest or rest[0][1] < b1):
            return {m1}, "bold"
    return set(), None


# ---- × ratios and bold/underlined cells
def check_tables(src, R):
    tables, _ = table_index(src)
    for t in tables:
        check_ratio_cells(t, R)
        check_bold(t, R)


def check_ratio_cells(t, R):
    """A k× cell next to a value: k must be that value over another value of the same column and block."""
    for r in t.rows:
        for ci in range(1, t.ncols):
            cell, left = r.cells[ci], r.cells[ci - 1]
            if not (cell.v is not None and cell.times) or not left.num:
                continue
            if abs(cell.v - 1.0) <= cell.tol + 1e-9:
                continue  # the reference row's own 1.0×
            cands = [o.cells[ci - 1].v for o in t.rows if o is not r and o.block == r.block and o.cells[ci - 1].num]
            ok = any(b and (abs(left.v / b - cell.v) <= cell.tol + 1e-9 or abs(b / left.v - cell.v) <= cell.tol + 1e-9)
                     for b in cands if b and left.v)
            if cands and left.v and not ok:
                best = min((b for b in cands if b), key=lambda b: min(abs(left.v / b - cell.v), abs(b / left.v - cell.v)),
                           default=None)
                if best:
                    a, b = (left.v, best) if abs(left.v / best - cell.v) <= abs(best / left.v - cell.v) else (best, left.v)
                    q, k = a / b, 10 ** cell.dec
                    trunc = math.floor(q * k + 1e-9) / k
                    hint = "recompute the ratio (rounding to the printed digits)"
                    if abs(trunc - cell.v) < 1e-9 and abs(round(q * k) / k - cell.v) > 1e-9:
                        hint = f"rounded or truncated? {q:.3f} rounds to {round(q * k) / k:.{cell.dec}f}, " \
                               f"truncates to {cell.s}"
                    R.add("CHECK", "ratio in table not reproducible", t.start, "",
                          f"{cell.s}× next to {left.s}; nearest {a:g}/{b:g} = {q:.3f}",
                          key=f"ratio{t.start}{r.ri}{ci}", hint=hint)


def check_bold(t, R):
    """Bold must be the best of its column (or row, in a transposed table) given the metric's direction; underline
    the second best."""
    highlight = {r.ri for r in t.rows
                 if sum(1 for c in r.cells[t.nlab:] if c.num) >= 2 and all(c.bold for c in r.cells[t.nlab:] if c.num)}
    groups = []  # (name, direction, [(cell, row)])
    if t.transposed:
        for r in t.rows:
            groups.append((r.label, direction(r.label), [(r.cells[c], r) for c in t.data_cols() if r.cells[c].num]))
    else:
        for c in t.data_cols():
            if t.ratio_col(c):
                continue
            d = t.direction(c)
            for rs in t.sets(c).values():
                groups.append((t.leaf(c) or f"column {c + 1}", d, [(r.cells[c], r) for r in rs]))
    def row_best(c, r, d):  # bold marks the best system of the row within its column group
        sib = [r.cells[x] for x in t.sys_groups.get(c.ci, []) if r.cells[x].num]
        if len(sib) < 2 or t.transposed:
            return False
        if d:
            return not any(better(o.v, c.v, d, max(o.tol, c.tol) + 1e-9) for o in sib)
        return c.v in (min(o.v for o in sib), max(o.v for o in sib))
    for name, d, cells in groups:
        vals = [c.v for c, _ in cells]
        bolds = [(c, r) for c, r in cells if c.bold and r.ri not in highlight and not row_best(c, r, d)]
        if d and len(cells) >= 2:
            for c, r in bolds:
                beat = [o for o, rr in cells if not o.bold and better(o.v, c.v, d, max(o.tol, c.tol) + 1e-9)]
                if beat:
                    R.add("CHECK", "bold value is not the best of its column", t.start, "",
                          f"bold {c.s} in {name}: {', '.join(o.s for o, _ in cells[:8])} "
                          f"({'higher' if d > 0 else 'lower'} is better)", key=f"bold{t.start}{name}{c.s}")
        elif not d and len(cells) >= 3 and len(bolds) == 1 and sum(1 for c, _ in cells if c.bold) == 1:
            c = bolds[0][0]
            if c.v not in (min(vals), max(vals)):
                R.add("CHECK", "bold value is not the best of its column", t.start, "", f"bold {c.v:g} in {vals}",
                      key=f"bold{t.start}{name}{c.s}")
        unders = [c for c, _ in cells if c.under]
        if d and len(unders) == 1 and len(cells) >= 3:
            u = unders[0]
            ranked = sorted({round(v, 9) for v in vals}, reverse=d > 0)
            others = [v for v in ranked if not any(c.bold and abs(c.v - v) < 1e-9 for c, _ in cells)]
            second = others[0] if any(c.bold for c, _ in cells) else (ranked[1] if len(ranked) > 1 else None)
            if second is not None and abs(u.v - second) > u.tol + 1e-9:
                R.add("CHECK", "underlined value is not the second best", t.start, "",
                      f"underlined {u.s} in {name}; second best {second:g}", key=f"under{t.start}{name}")


# ---- numbers in the text vs the tables
def text_units(src):
    """Sentences of the prose: [(section, [(file, line, normalized text)], refs, paragraph number)], tabular bodies
    skipped."""
    units, para, section, in_tab = [], [], "", False

    def flush():
        if para:
            pid = len(units)
            units.extend(x + (pid,) for x in split_sentences(list(para), section))
            para.clear()
    for f, no, code, _, _ in src.lines:
        if re.search(r"\\begin\{(tabular|tabularx|tabulary|longtable)", code):
            in_tab = True
            flush()
        if in_tab:
            if re.search(r"\\end\{(tabular|tabularx|tabulary|longtable)", code):
                in_tab = False
            continue
        sm = re.search(r"\\(section|chapter)\*?\s*\{([^}]*)\}", code)
        if sm or re.search(r"\\(sub)*section|\\paragraph|\\begin\{(abstract|figure|table)|\\end\{(abstract|figure|table)",
                           code) or not code.strip():
            flush()
        if sm:
            section = sm.group(2)
        if re.search(r"\\begin\{abstract\}|\\abstract\s*\{", code):
            section = "Abstract"
        if re.search(r"\\(affiliation|address|institute|author|email|ead|thanks|fntext|cortext|date|orcid)\b|"
                     r"addressline|postcode", code):
            continue
        txt = re.sub(r"\\(?:ref|autoref|cref|Cref|subref|vref|Vref)\*?\{([^}]*)\}",
                     lambda m: " " + " ".join(f"⟦{x.strip()}⟧" for x in m.group(1).split(",")) + " ", code)
        para.append((f, no, norm_tex_numbers(txt)))
    flush()
    return units


ABBREV = re.compile(r"(?:\b(?:Fig|Figs|Tab|Tabs|Sec|Secs|Eq|Eqs|e\.g|i\.e|al|vs|cf|resp|approx|No|Ref|Alg|App|Thm|Def|"
                    r"Ch|ca|etc))$")


def split_sentences(lines, section):
    out, cur = [], []
    for f, no, txt in lines:
        pos = 0
        for m in re.finditer(r"[.!?]\s+(?=[A-Z⟦\\(])", txt):
            if ABBREV.search(txt[:m.start()]):
                continue
            cur.append((f, no, txt[pos:m.end()]))
            out.append(cur)
            cur, pos = [], m.end()
        cur.append((f, no, txt[pos:]))
    if cur:
        out.append(cur)
    return [(section, s, set(re.findall(r"⟦([^⟧]*)⟧", " ".join(x for _, _, x in s)))) for s in out]


def matches(n, cell, scale_ok=True):
    """Same number up to the coarser printed precision; 95% matches 0.95 and 0.95 matches 95."""
    tol = max(n.tol, cell.tol) + 1e-9
    if abs(n.v - cell.v) <= tol:
        return True
    if not scale_ok:
        return False
    if n.unit == "%" and abs(cell.v) <= 1 and abs(n.v / 100 - cell.v) <= tol / 100 + max(cell.tol, 1e-12):
        return True
    return n.unit != "%" and abs(n.v) < 1 and "." in n.s and abs(n.v * 100 - cell.v) <= max(cell.tol, n.tol * 100) + 1e-9


def derived_values(t, cols=None, rows_filter=None):
    """Ratios, differences and % changes of two cells of the same column (rows of a transposed table)."""
    series = []
    if t.transposed:
        series = [[r.cells[c] for c in t.data_cols() if r.cells[c].num] for r in t.rows]
    else:
        for c in (cols if cols is not None else t.data_cols()):
            series.append([r.cells[c] for r in t.rows if r.cells[c].num and (rows_filter is None or rows_filter(r))])
    out = []
    for cells in series:
        vs = [x.v for x in cells[:60]]
        for a in vs:
            for b in vs:
                if a == b or not b:
                    continue
                out += [("x", a / b), ("d", a - b), ("%", (a / b - 1) * 100), ("%", (1 - a / b) * 100)]
    return out


def proposed_ratios(t, klass=None):
    """Ratios and changes between the proposed row and another row of the same column and block."""
    out = []
    if not t.proposed or t.transposed:
        return out
    for c in t.data_cols():
        if t.ratio_col(c):
            continue
        k = col_class(t, c)
        if klass and k and k != klass:
            continue
        for rs in t.sets(c).values():
            ps = [r.cells[c].v for r in rs if r.method in t.proposed]
            os_ = [r.cells[c].v for r in rs if r.method not in t.proposed]
            for p in ps:
                for o in os_:
                    if p and o:
                        out += [("x", p / o), ("x", o / p), ("d", p - o), ("d", o - p), ("%", (p / o - 1) * 100),
                                ("%", (1 - p / o) * 100), ("%", (o / p - 1) * 100), ("%", (1 - o / p) * 100)]
    return out


def col_class(t, c):
    text = t.metric_text(c)
    if TIME_RX.search(text) or QPS_RX.search(text):
        return "speed"
    if re.search(r"memory|\bmem\b|size|\bgb\b|\bmb\b|bytes", text):
        return "mem"
    return None


def explained(n, derived):
    """A × or % or small decimal claim that is a ratio/difference/change of two cells."""
    if n.exp:
        return False
    if n.unit == "×" or (not n.unit and abs(n.v) < 100 and "." in n.s):
        kinds = ("x", "d")
    elif n.unit == "%":
        kinds = ("%", "d")
    else:
        return False
    tol = n.tol + 1e-9
    return any(k in kinds and abs(abs(v) - abs(n.v)) <= tol for k, v in derived)


def nearest(n, cells):
    return min(cells, key=lambda x: abs(n.v - x.v) / max(abs(x.v), abs(n.v), 1e-12), default=None)


def close(n, cell):
    """A probable misquote: within 10% or the same digits in another order."""
    if cell is None:
        return False
    rel = abs(n.v - cell.v) / max(abs(cell.v), 1e-12)
    d1, d2 = re.sub(r"\D", "", n.s), re.sub(r"\D", "", cell.s or "")
    return rel <= 0.1 or (len(d1) >= 3 and sorted(d1) == sorted(d2) and d1 != d2)


def text_numbers(txt):
    """Numbers worth comparing with the tables: no years, section numbers, small counts, settings (k=10)."""
    out = []
    for m in NUM_TOKEN.finditer(txt):
        n = Num(m)
        before = txt[max(0, m.start() - 14):m.start()]
        if re.search(r"(Table|Tab\.|Figure|Fig\.|Section|Sec\.|Eq\.|Equation|Appendix|Algorithm|Theorem|Lemma|line|"
                     r"lines|version|step|Step|Phase|Stage|top-|Top-|@|k=|K=|=)\s*~?$", before, re.I):
            continue
        digits = re.sub(r"\D", "", m.group(2))
        if not n.unit and not n.exp:
            if (1900 <= n.v <= 2099 and "." not in n.s) or (abs(n.v) < 10 and "." not in n.s):
                continue
            if len(digits.lstrip("0")) < 2:
                continue
        out.append((m, n))
    return out


def check_numbers(src, R):
    """Numbers in the prose vs the tables: the cited table first, units, swapped digits; a compact list of the rest."""
    tables, ctx = table_index(src)
    if not tables:
        return
    allcells = [(x, t) for t in tables for x in t.values + t.header_nums]
    found_in = {}  # sentence id -> does one of its numbers match a cell of a cited table
    if not allcells:
        return
    by_label = {lab: t for t in tables for lab in t.labels}
    unmatched_key, unmatched_body, cache = [], [], {}
    # unit mix over a whole source line (a paragraph): one sentence alone may give a single value of the table
    for f, no, code, _, _ in src.lines:
        if re.search(r"\\(begin|end)\{(tabular|table)", code) or "&" in code:
            continue
        check_unit_mix(norm_tex_numbers(code), tables, f"{f}:{no}", R)

    def memo(k, fn):
        if k not in cache:
            cache[k] = fn()
        return cache[k]
    last_cited, last_pid = [], None
    for section, sent, refs, pid in text_units(src):
        cited = [by_label[r] for r in sorted(refs) if r in by_label]
        if pid != last_pid:
            last_cited, last_pid = [], pid
        carried = not cited and bool(last_cited)  # "Table 2 reports ... . Ours improves by 3.1 points": same table
        if cited:
            last_cited = cited
        elif carried:
            cited = last_cited
        cites_fig = any(r not in by_label and "fig" in r.lower() for r in refs)
        stext = " ".join(x for _, _, x in sent)
        klass = "speed" if re.search(r"faster|slower|speed|latency|throughput|qps|time", stext, re.I) else \
            "mem" if re.search(r"smaller|memory|compress|footprint|size", stext, re.I) else None
        quotes = bool(cited) and any(matches(n, x) for _, _, line in sent for _, n in text_numbers(line)
                                     for t in cited for x in t.values)
        lone = sum(len(text_numbers(line)) for _, _, line in sent) == 1
        # columns of a cited table the sentence names ("on T2"): differences are taken in those columns only
        named = {id(t): [c for c in t.data_cols() if re.search(r"[a-z]", t.leaf(c)) and len(t.leaf(c)) >= 2 and re.search(
            r"(?<![\w-])" + re.escape(t.leaf(c)) + r"(?![\w-])", stext.lower()) and c not in t.sys_groups] for t in cited}
        if len({tc.leaf(c) for tc in cited for c in named[id(tc)]}) != 1:  # the sentence names exactly one column
            named = {k: [] for k in named}
        for f, no, line in sent:
            where = f"{f}:{no}"
            check_unit_mix(line, tables, where, R)
            for m, n in text_numbers(line):
                hits = [(x, t) for x, t in allcells if matches(n, x)]
                hit = [t for _, t in hits]
                if cited:
                    if any(matches(n, x) for t in cited for x in t.values + t.header_nums):
                        check_unit(n, [(x, t) for x, t in hits if t in cited and matches(n, x, False)], where, R)
                        continue
                    if any(explained(n, memo(("d", id(t), tuple(named[id(t)])), lambda: derived_values(
                            t, named[id(t)] or None))) for t in cited):
                        continue
                    diff = re.match(r"\s*(points|pp|p\.p\.|percentage points)\b", line[m.end():])
                    if (diff or n.unit == "×") and any(named.values()):
                        tc = next(t for t in cited if named[id(t)])
                        R.add("CHECK", "difference not reproducible from the cited table", where, "",
                              f"{n.s}{n.unit}{' ' + diff.group(1) if diff else ''} on "
                              f"{', '.join(tc.leaf(c) for c in named[id(tc)])} ({tc.name})",
                              key=f"diff{where}{n.s}", hint="recompute it from the cells of the column the sentence names")
                        continue
                    near = nearest(n, [x for t in cited for x in t.values])
                    if not hit and check_swapped(n, allcells, where, R, cited):
                        continue  # the more specific diagnosis
                    if not carried and (quotes or lone) and close(n, near) and (
                            n.exp or "." in n.s or near.dec or n.unit):
                        tc = next(t for t in cited if near in t.values)
                        R.add("CHECK", "number not in the table the sentence cites", where, "",
                              f"{n.s}{n.unit} (cites the {tc.name}); nearest cell {near.s}", key=f"cite{where}{n.s}",
                              hint="a misquoted cell, or the number comes from another table: fix the number or the reference")
                        continue
                    if hit:
                        continue
                elif hit:
                    # no citation: compare units only with tables the sentence talks about (a row or header name)
                    hits_u = [(x, t) for x, t in hits if matches(n, x, False) and mentions(t, stext)]
                    check_unit(n, hits_u, where, R)
                    continue
                if any(explained(n, memo(("p", id(t), klass), lambda: proposed_ratios(t, klass))) for t in tables):
                    continue
                if check_swapped(n, allcells, where, R, cited):
                    continue
                if not (n.unit or "." in n.s or len(re.sub(r"\D", "", n.s)) >= 3 or n.exp):
                    continue
                near = nearest(n, [x for x, _ in allcells])
                item = (section, where, f"{n.s}{n.unit}", near.s if near else "?")
                if re.search(r"abstract|introduction|conclusion|summary", section, re.I):
                    unmatched_key.append(item)
                elif (cited or cites_fig or n.unit in ("×", "%")) and item not in unmatched_body:
                    unmatched_body.append(item)
    for sec, where, val, near in unmatched_key[:25]:
        R.add("INFO", "number in abstract/introduction/conclusions not found in any table", where, "",
              f"{val} ({sec}); nearest table value {near}", key=f"un{where}{val}",
              hint="check it against the table or figure it summarises")
    if unmatched_body:
        R.add("INFO", "numbers in the text not found in any table", quote="; ".join(
            f"{v} {w} (nearest {nr})" for _, w, v, nr in unmatched_body[:25]), maxlen=3000, key="unbody",
              hint=f"{len(unmatched_body)} numbers in sentences that cite a table/figure or claim ×/%: compare the ones "
                   f"about the paper's own experiments")


def mentions(t, stext):
    """The sentence names a row or a header of the table (its macro or its words)."""
    low = fold(stext)
    names = {m for r in t.rows for m in re.findall(r"\\([A-Za-z]+)", r.label_raw)}
    words = {w for r in t.rows for w in [r.label] if len(w) >= 4 and not re.fullmatch(r"[\d.,%\s]+", w)}
    words |= {h for c in t.data_cols() for h in t.htexts[c] if len(h) >= 4 and re.search(r"[a-z]{3}", h)}
    return any(re.search(r"\\" + n + r"(?![A-Za-z])", stext) for n in names) or any(
        re.search(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", low) for w in words)


def check_unit_mix(line, tables, where, R):
    """One sentence giving values of the same table in two units (µs and ms)."""
    mix = defaultdict(set)
    for mm in re.finditer(r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(µs|us|ms|ns|GiB|GB|MiB|MB)(?![A-Za-z])", line):
        vv = parse_number(mm.group(1))
        if vv is not None:
            mix[UNIT_CLASS[mm.group(2).lower()]].add((mm.group(2), vv, mm.group(1)))
    for cls, items in mix.items():
        if len({u.lower().replace("us", "µs") for u, _, _ in items}) < 2:
            continue
        for t in tables:
            tv = {x.v for x in t.values}
            found = [(u, s0) for u, vv, s0 in items if any(abs(vv - x) < 1e-9 for x in tv)
                     and len(re.sub(r"\D", "", s0).lstrip("0")) >= 3]  # small numbers match tables by chance
            if len({u.lower().replace("us", "µs") for u, _ in found}) >= 2:
                R.add("CHECK", "one sentence gives values of the same table in different units", where, "",
                      "; ".join(f"{s0} {u}" for u, s0 in found[:6]) + f" (table at {t.start})",
                      key=f"mix{where}", hint="the table has one unit: one of these is wrong")
                break


def col_units(t, ci):
    """Units named in a column's header stack (the table's units when the column names none); None: not a quantity
    with a unit of this kind (QPS, counts)."""
    if ci is None:
        return t.units
    text = t.col_text(ci) if not t.transposed else ""
    if QPS_RX.search(text):
        return None
    own = {u.lower() for u in re.findall(r"(?<![A-Za-z])(µs|μs|us|ms|ns|sec|min|gib|gb|mib|mb|kib|kb|tb|(?<=\()s(?=\)))"
                                         r"(?![A-Za-z])", text)}
    return {u.replace("μs", "µs") for u in own} or t.units


UNIT_LADDER = (("ns", "µs", "ms", "s"), ("kb", "mb", "gb", "tb"), ("kib", "mib", "gib", "tib"))


def adjacent_units(a, b):
    a, b = a.replace("sec", "s"), b.replace("sec", "s")
    return any(a in lad and b in lad and abs(lad.index(a) - lad.index(b)) == 1 for lad in UNIT_LADDER) or \
        {a, b} in ({"mb", "mib"}, {"gb", "gib"})


def check_unit(n, hits, where, R):
    """A number found in a table, written with a unit of the same kind but different (ms vs µs)."""
    cls = UNIT_CLASS.get(n.unit.lower())
    digits = re.sub(r"\D", "", n.s)
    if not hits or not cls or len(digits.lstrip("0")) < 3:
        return
    u0 = n.unit.lower().replace("us", "µs")
    bad = []
    for x, t in hits:
        units = col_units(t, x.ci)
        same = {u.replace("us", "µs") for u in units or () if UNIT_CLASS.get(u) == cls}
        if not same or u0 in same:
            return  # a cell with this unit, or with no unit of this kind: nothing to compare
        if not any(adjacent_units(u0, u) for u in same):
            return  # ns vs s: a coincidence, not a slip of one prefix
        bad.append((t, same))
    t, other = bad[0]
    R.add("CHECK", "unit differs from the table that has this number", where, "",
          f"{n.s} {n.unit} in the text; the table at {t.start} is in {', '.join(sorted(other))}",
          key=f"unit{where}{n.s}", hint="µs vs ms? check the unit")


def check_swapped(n, allcells, where, R, cited=()):
    digits = re.sub(r"\D", "", n.s)
    intdig = len(n.s.split(".")[0].replace(",", "").lstrip("-"))
    ucls = UNIT_CLASS.get(n.unit.lower())
    if "." in n.s or n.exp or not (intdig >= 4 or (intdig == 3 and ucls)):
        return False  # decimals collide too often
    swaps = {digits[:i] + digits[i + 1] + digits[i] + digits[i + 2:] for i in range(len(digits) - 1)
             if digits[i] != digits[i + 1]}

    def same_kind(x, t):  # the cell's column measures the same kind of quantity as the text's unit
        units = col_units(t, x.ci)
        if units is None:
            return not ucls
        return not ucls or not units or any(UNIT_CLASS.get(u) == ucls for u in units)
    near = [(x.s, t) for x, t in allcells if x.s and re.sub(r"\D", "", x.s) in swaps and abs(x.v - n.v) / max(n.v, 1) < 0.5
            and same_kind(x, t) and (intdig >= 4 or (t in cited and any(UNIT_CLASS.get(u) == ucls for u in t.units)))]
    if near:
        R.add("CHECK", "number in the text differs from a table value by two swapped digits", where, "",
              f"{n.s}{(' ' + n.unit) if n.unit else ''} in the text; {near[0][0]} in the table at {near[0][1].start}",
              key=f"swap{where}{n.s}", hint="a typo in the text or in the table")
        return True
    return False


# ---- the same cell in two tables
def implied(level, t, row=None):
    """A header level or row group of another table is implied here by the caption, the header or the row group."""
    text = " " + re.sub(r"[^a-z0-9+\-]", " ", t.cap_text + " " + " ".join(" ".join(h) for h in t.htexts)) + " "
    compact = text.replace(" ", "")
    return f" {level} " in text or (len(level) >= 4 and level in compact) or (row is not None and row.group == level)


def row_pairs(t1, t2):
    """Rows of t1 and t2 with the same method and compatible groups (never by the first duplicate)."""
    def index(t):
        d = defaultdict(list)
        for r in t.rows:
            if r.method and not r.method.isdigit():
                d[r.method].append(r)
        return d
    i1, i2 = index(t1), index(t2)
    out = []
    for m in sorted(set(i1) & set(i2)):
        a, b = i1[m], i2[m]
        if len(a) == 1 and len(b) == 1 and (a[0].group == b[0].group or (a[0].group is None and b[0].group is None)):
            out.append((a[0], b[0]))
            continue
        for x in a:
            ys = [y for y in b if y.group == x.group and x.group is not None]
            if not ys and x.group is not None:
                ys = [y for y in b if y.group is None and implied(x.group, t2)]
            if not ys and x.group is None:
                ys = [y for y in b if y.group is not None and implied(y.group, t1)]
            if len(ys) == 1 and sum(1 for z in a if z.group == x.group) == 1:
                out.append((x, ys[0]))
    return out


def col_pairs(t1, t2):
    """Columns with the same leaf key whose other header levels are equal or implied by the other table."""
    out = []
    for c2 in t2.data_cols():
        if not t2.levels[c2] or t2.ratio_col(c2):
            continue
        cands = []
        for c1 in t1.data_cols():
            if not t1.levels[c1] or t1.levels[c1][-1] != t2.levels[c2][-1] or t1.ratio_col(c1):
                continue
            up1, up2 = set(t1.levels[c1][:-1]), set(t2.levels[c2][:-1])
            if all(implied(x, t2) for x in up1 - up2) and all(implied(x, t1) for x in up2 - up1):
                cands.append(c1)
        if len(cands) == 1:
            out.append((cands[0], c2))
    return out


def same_at_precision(a, b):
    """0: different; 1: equal; 2: equal at the coarser printed precision."""
    if abs(a.v - b.v) <= 1e-9 * max(1, abs(a.v)):
        return 1
    return 2 if abs(a.v - b.v) <= max(a.tol, b.tol) + 1e-9 else 0


def check_cross_tables(src, R):
    tables, _ = table_index(src)
    for i in range(len(tables)):
        for j in range(i + 1, len(tables)):
            t1, t2 = tables[i], tables[j]
            if t1.transposed or t2.transposed:
                continue
            rows = row_pairs(t1, t2)
            reported = False
            for c1, c2 in col_pairs(t1, t2) if rows else []:
                for r1, r2 in rows:
                    a, b = r1.cells[c1], r2.cells[c2]
                    if not (a.num and b.num):
                        continue
                    lab = "/".join(x for x in (r1.group or r2.group, r1.method) if x)
                    col = " / ".join(t1.levels[c1])
                    eq = same_at_precision(a, b)
                    if eq == 0:
                        R.add("CHECK", "same row and column in two tables, different values", f"{t1.start}, {t2.start}",
                              "", f"{lab} / {col}: {a.s} vs {b.s}", key=f"x{lab}{col}{t1.start}{t2.start}",
                              hint="the same experiment must have the same number; explain or fix")
                        reported = True
                    elif eq == 2:
                        R.add("INFO", "same value at different precision in two tables", f"{t1.start}, {t2.start}", "",
                              f"{lab} / {col}: {a.s} vs {b.s}", key=f"xp{lab}{col}{t1.start}{t2.start}",
                              hint="print the same digits in both tables")
            common = sorted({r1.method for r1, _ in rows})
            if not reported and len(common) >= 2:
                R.add("INFO", "tables report the same systems", f"{t1.start}, {t2.start}", "", ", ".join(common[:8]),
                      key=f"xs{t1.start}{t2.start}", hint="where they report the same experiment, the numbers must agree")


# ---- alignment
def column_alignments(spec):
    """['l'|'c'|'r'|'S'|'D'|'p'|'X'...] per column from a tabular column specification."""
    spec = re.sub(r"\*\s*\{(\d+)\}\s*\{([^{}]*)\}", lambda m: m.group(2) * int(m.group(1)), spec)
    spec = re.sub(r"[@!>]\s*\{(?:[^{}]|\{[^{}]*\})*\}|<\s*\{(?:[^{}]|\{[^{}]*\})*\}|\|", "", spec)
    spec = re.sub(r"\[[^\]]*\]", "", spec)  # S[table-format=...]
    cols = []
    for m in re.finditer(r"([lcrSDXLCRJp mb])\s*(\{(?:[^{}]|\{[^{}]*\})*\})?", spec):
        ch = m.group(1)
        if ch == " ":
            continue
        cols.append("p" if ch in "pmb" else ch)
    return cols


def check_table_alignment(src, R):
    """Numbers centred or left-aligned in a column, and inconsistent decimal places in a column."""
    tables, _ = table_index(src)
    for t in tables:
        if len(t.aligns) != t.ncols:
            continue
        for ci in range(t.ncols):
            cells = [r.cells[ci] for r in t.rows if not r.mc[ci] and r.raw[ci].strip()]
            cells = [c for c in cells if not c.empty]
            nums = [c.s.lstrip("-") for c in cells if c.v is not None]
            if len(nums) < 3 or len(nums) < 0.8 * len(cells):
                continue
            al = t.aligns[ci]
            if al in ("c", "l", "C", "L") and len({len(n) for n in nums}) > 1:
                R.add("CHECK", f"numbers {'centred' if al in 'cC' else 'left-aligned'} in a table column", t.start, "",
                      f"column {ci + 1} ({al}): {', '.join(nums[:5])}", key=f"al{t.start}{ci}",
                      hint="right-align numbers (r), or align them on the decimal point (siunitx S)")
            decimals = [n for n in nums if "." in n and "e" not in n]
            fl = [float(n.replace(",", "").rstrip("kKMBGT")) for n in decimals]
            if len(decimals) < len(nums) or not fl or min(fl) <= 0 or max(fl) / min(fl) >= 10:
                continue  # integers and decimals mixed, or different magnitudes: rows may be different measures
            decs = Counter(len(n.split(".")[1].rstrip("kKMBGT")) for n in decimals)
            if len(decs) > 1:
                (main_dec, _), = decs.most_common(1)
                odd = [n for n in decimals if len(n.split(".")[1].rstrip("kKMBGT")) != main_dec]
                if odd and len(odd) * 3 <= len(nums):
                    R.add("CHECK", "decimal places differ within a table column", t.start, "",
                          f"column {ci + 1}: {', '.join(odd[:4])} among values with {main_dec} decimals",
                          key=f"dec{t.start}{ci}", hint="use the same number of decimals in a column")


# ---- arithmetic and ranges
AVG_RX = re.compile(r"(avg|average|mean|overall|total|sum)\w*")
AVG_HEAD_RX = re.compile(r"(avg|average|mean|overall|total|sum)\b\.?\s*")  # header text: "Avg", "Avg nDCG"
SIZE_RX = re.compile(r"^(n|#.*|size|count|samples?|queries|items|examples|instances|support|#?\s*test)$")


def means(parts, weights=None):
    out = [sum(parts) / len(parts)]
    if all(p > 0 for p in parts):
        g = 1.0
        for p in parts:
            g *= p
        out += [g ** (1 / len(parts)), len(parts) / sum(1 / p for p in parts)]
    if weights and len(weights) == len(parts) and sum(weights) > 0:
        out.append(sum(p * w for p, w in zip(parts, weights)) / sum(weights))
    return out


def off(want, cell):
    return abs(want - cell.v) > cell.tol + 1e-9 and abs(want - cell.v) > 0.005 * max(abs(want), 1e-9)


def check_table_arithmetic(src, R):
    """Avg/Mean/Total columns and rows, ranges (% > 100, fractions > 1, negative spreads), duplicated rows and
    columns, speedup columns vs times, missing units, empty cells of the proposed row, no variance, 'a factor of k'."""
    tables, _ = table_index(src)
    any_pm = False
    units_seen = defaultdict(set)
    for t in tables:
        if any(c.spread is not None for r in t.rows for c in r.cells) or re.search(
                r"\bstd\b|\bsd\b|±|\\pm", t.cap_text + " " + " ".join(" ".join(h) for h in t.htexts)):
            any_pm = True
        if t.transposed:
            check_units_missing(t, R, units_seen)
            continue
        check_avg_columns(t, R)
        check_avg_rows(t, R)
        check_ranges(t, R)
        check_duplicates(t, R)
        check_speedup_column(t, R)
        check_units_missing(t, R, units_seen)
        empty = [f"{r.label or r.method} col {ci + 1}" for r in t.rows if r.method in t.proposed
                 for ci in t.data_cols() if r.cells[ci].empty and not t.ratio_col(ci)]
        if empty:
            R.add("INFO", "the proposed method has empty cells", t.start, "", "; ".join(empty[:8]),
                  key=f"emp{t.start}", hint="explain why (out of memory, not applicable) in the caption")
    for cls, us in units_seen.items():
        if len({u for u, _ in us}) >= 2:
            R.add("INFO", "same quantity in different units across tables", quote=f"{cls}: " + ", ".join(
                f"{u} ({w})" for u, w in sorted(us)[:6]), key=f"units{cls}", hint="one unit per quantity reads easier")
    if tables and not any_pm and not re.search(r"standard deviation|\bstd\b|confidence interval|\\pm|±|random seeds?|"
                                                r"\b(\d+|three|five|ten) (random )?(seeds|runs|repetitions)|different seeds|"
                                                r"run-to-run|statistically significant|significance test|p-value", src.code(), re.I):
        R.add("INFO", "no variance reported", quote=f"{len(tables)} tables, no ±/std/seeds in the paper", key="novar",
              hint="the most frequent reviewer complaint about numbers: report variance or say why it is negligible")
    if tables and not any_pm:
        m = re.search(r"(averaged|mean|average) (over|of|across) (\d+|three|five|ten) (independent |random )?(runs|seeds|"
                      r"trials)", src.code(), re.I)
        if m and not re.search(r"standard deviation|\bstd\b|differ by at most|spread|confidence interval", src.code(), re.I):
            R.add("CHECK", "runs/seeds stated but no table shows a spread", quote=m.group(0), key="noseedspread",
                  hint="report the std (±) or the range over the runs, at least for the main table")
    for f, no, code, _, _ in src.lines:
        line = norm_tex_numbers(code)
        for m in re.finditer(r"factor of\s*(\d+(?:\.\d+)?)\s*×?.{0,80}?from\s*(\d[\d,]*(?:\.\d+)?)\s*\S*\s*to\s*(\d[\d,]*(?:\.\d+)?)", line):
            k, a, b = parse_number(m.group(1)), parse_number(m.group(2)), parse_number(m.group(3))
            if k and a and b:
                r = max(a, b) / min(a, b)
                if abs(r - k) / k > 0.1:
                    R.add("CHECK", "'a factor of k from A to B' does not add up", f"{f}:{no}", "",
                          f"factor {m.group(1)}, but {m.group(2)} → {m.group(3)} is {r:.2f}×", key=f"fac{f}{no}")


def avg_kind(t):
    if re.search(r"micro", t.cap_text) and not re.search(r"macro", t.cap_text):
        return None  # micro averages need the counts
    return "weighted" if "weighted" in t.cap_text else "any"


def check_avg_columns(t, R):
    """An Avg/Mean/Total column = mean (arithmetic, geometric, harmonic, weighted) of the metric columns of its group."""
    kind = avg_kind(t)
    if kind is None:
        return
    size_row = next((r for r in t.rows if SIZE_RX.match(r.label or "")), None)
    for ci in t.data_cols():
        lab = t.levels[ci][-1] if t.levels[ci] else ""
        if not AVG_RX.fullmatch(lab):
            continue
        total = lab.startswith(("total", "sum"))
        eff = EFF_RX.search(t.leaf(ci))
        hm = AVG_HEAD_RX.match(t.leaf(ci))
        rest = label_of(t.leaf(ci)[hm.end():]) if hm else ""
        if rest:  # "Avg nDCG": the nDCG columns of every group
            parts_cols = [c for c in t.data_cols() if c != ci and t.levels[c] and t.levels[c][-1] == rest
                          and not t.ratio_col(c)]
        else:
            parts_cols = [c for c in t.data_cols() if c < ci and t.levels[c][:-1] == t.levels[ci][:-1]
                          and not AVG_RX.fullmatch(t.levels[c][-1] if t.levels[c] else "") and not t.ratio_col(c)
                          and (bool(EFF_RX.search(t.leaf(c))) == bool(eff))]
        for r in t.rows:
            cell = r.cells[ci]
            if not cell.num:
                continue
            cols = [c for c in parts_cols if r.cells[c].num]
            parts = [r.cells[c].v for c in cols]
            if len(parts) < 2:
                continue
            w = [size_row.cells[c].v for c in cols] if size_row and all(size_row.cells[c].num for c in cols) else None
            wants = [sum(parts)] if total else means(parts, w) if kind == "any" else ([means(parts, w)[-1]] if w else [])
            if wants and all(off(x, cell) for x in wants):
                R.add("CHECK", f"{'total' if total else 'average'} column does not match its row", t.start, "",
                      f"{r.method or '?'}: printed {cell.s}, {'sum' if total else 'mean'} of the other cells "
                      f"{wants[0]:.{max(cell.dec, 1)}f}", key=f"avgc{t.start}{r.ri}",
                      hint="recompute it (weighted or geometric mean? say so in the caption)")


def check_avg_rows(t, R):
    """An Average row = mean of the rows above it in its block (or the previous block), never another Average row."""
    kind = avg_kind(t)
    if kind is None:
        return
    size_col = next((c for c in t.data_cols() if SIZE_RX.match(t.leaf(c))), None)
    for r in t.rows:
        if not AVG_RX.fullmatch(r.method or "") or UNIT_LABEL_RX.search(r.label):
            continue
        # the rows above it in its block, back to the previous Avg/Sum row; rows with their own unit are not parts
        last = max((o.ri for o in t.rows if o.ri < r.ri and o.block == r.block and o.group == r.group
                    and AVG_RX.fullmatch(o.method or "")), default=-1)
        above = [o for o in t.rows if last < o.ri < r.ri and o.block == r.block and o.group == r.group
                 and not UNIT_LABEL_RX.search(o.label)]
        if len(above) < 2 and last == -1:
            prev = [o for o in t.rows if o.ri < r.ri and o.block < r.block]
            last_avg = max((o.ri for o in prev if AVG_RX.fullmatch(o.method or "")), default=-1)
            above = [o for o in prev if o.ri > last_avg and not AVG_RX.fullmatch(o.method or "")]
        total = r.method.startswith(("total", "sum"))
        for ci in t.data_cols():
            cell = r.cells[ci]
            if not cell.num:
                continue
            rows = [o for o in above if o.cells[ci].num]
            if len(rows) < 2:
                continue
            col = [o.cells[ci].v for o in rows]
            w = [o.cells[size_col].v for o in rows] if size_col is not None and all(o.cells[size_col].num for o in rows) \
                else None
            wants = [sum(col)] if total else means(col, w) if kind == "any" else ([means(col, w)[-1]] if w else [])
            if wants and all(off(x, cell) for x in wants):
                R.add("CHECK", f"{'total' if total else 'average'} row does not match its column", t.start, "",
                      f"column {ci + 1}: printed {cell.s}, {'sum' if total else 'mean'} of the rows above "
                      f"{wants[0]:.{max(cell.dec, 1)}f}", key=f"avgr{t.start}{r.ri}{ci}",
                      hint="recompute it, or say which rows it averages")


UNIT_LABEL_RX = re.compile(r"\((%|ms|µs|μs|us|ns|s|sec|min|h|gb|mb|kb|tb|gib|mib|kib|×|x|qps)\)")


def check_ranges(t, R):
    for ci in t.data_cols():
        mt = t.metric_text(ci)
        # a row that names its own unit ("Total time (s)") measures another quantity than the column
        cells = [(r, r.cells[ci]) for r in t.rows if r.cells[ci].num and not UNIT_LABEL_RX.search(r.label)
                 and not re.match(r"(total|sum)", r.method or "")]
        # a column in percent (the unit is in its header) above 100; gains and speedups may exceed 100
        if re.search(r"[(\[]\s*%\s*[)\]]", mt) and not GAIN_RX.search(mt):
            for r, c in cells:
                if c.v > 100:
                    R.add("CHECK", "percentage above 100", t.start, "", f"{r.method or '?'}: {c.s}",
                          key=f"pct{t.start}{r.ri}{ci}", hint="a percentage of a whole cannot exceed 100")
        # a column of fractions with a value above 1
        if not EFF_RX.search(mt) and not GAIN_RX.search(mt) and "%" not in mt and not t.ratio_col(ci):
            inside = [c for _, c in cells if 0 <= c.v <= 1 and "." in c.s]
            above = [(r, c) for r, c in cells if c.v > 1]
            if len(inside) >= 3 and len(inside) + len(above) == len(cells) and 1 <= len(above) <= max(1, 0.2 * len(cells)):
                for r, c in above:
                    R.add("CHECK", "value above 1 in a column of fractions", t.start, "",
                          f"{r.method or '?'} / {t.leaf(ci) or ci + 1}: {c.s} among {', '.join(x.s for x in inside[:4])}",
                          key=f"frac{t.start}{r.ri}{ci}", hint="a fraction (recall, nDCG, accuracy) cannot exceed 1")
        for r, c in cells:
            if c.spread is not None and c.spread < 0:
                R.add("FAIL", "negative spread after ±", t.start, "", f"{r.method or '?'}: {c.raw}",
                      key=f"negsd{t.start}{r.ri}{ci}", hint="a standard deviation cannot be negative")


def check_duplicates(t, R):
    seen = {}
    for r in t.rows:
        vec = tuple(r.cells[c].s for c in t.data_cols() if r.cells[c].v is not None)
        lab = "/".join(x for x in (r.group, r.method) if x)
        if len(vec) >= 3 and r.method and not r.method.isdigit():
            if vec in seen and seen[vec] != lab:
                R.add("CHECK", "two rows with exactly the same numbers", t.start, "", f"{seen[vec]} = {lab}: {', '.join(vec[:6])}",
                      key=f"dup{t.start}{vec}", hint="copied row or a bug in the experiments?")
            seen.setdefault(vec, lab)
    cols = {}
    for c in t.data_cols():
        if t.ratio_col(c) or AVG_RX.fullmatch(t.levels[c][-1] if t.levels[c] else ""):
            continue
        vec = tuple(r.cells[c].s if r.cells[c].num else None for r in t.rows)
        nums = [x for x in vec if x is not None]
        if len(nums) >= 3 and len(set(nums)) > 1:
            if vec in cols and t.levels[cols[vec]] != t.levels[c]:
                R.add("CHECK", "two columns with exactly the same numbers", t.start, "",
                      f"{' / '.join(t.levels[cols[vec]]) or cols[vec] + 1} = {' / '.join(t.levels[c]) or c + 1}: "
                      f"{', '.join(nums[:6])}", key=f"dupc{t.start}{c}", hint="copied column or a bug in the experiments?")
            cols.setdefault(vec, c)


def check_speedup_column(t, R):
    """A Speedup/ratio column recomputed from the time (or QPS) column, with the 1.0 row as the reference."""
    for ci in t.data_cols():
        if not re.search(r"speed-?up|\bratio\b|×|^x$", t.leaf(ci)):
            continue
        cells = [r for r in t.rows if r.cells[ci].v is not None]
        if not cells or (any(r.cells[ci].times for r in cells) and ci > 0 and
                         sum(1 for r in cells if r.cells[ci - 1].num) * 2 >= len(cells)):
            continue  # k× next to its value: check_ratio_cells
        base = [c for c in t.data_cols() if c != ci and (TIME_RX.search(t.metric_text(c)) or QPS_RX.search(t.metric_text(c)))
                and t.levels[c][:-1] == t.levels[ci][:-1]]
        if not base:
            continue

        def mismatches(bc):
            lower = bool(TIME_RX.search(t.metric_text(bc)))
            out, n = [], 0
            for key, rs in t.sets(ci).items():
                ref = [r for r in rs if abs(r.cells[ci].v - 1.0) <= r.cells[ci].tol + 1e-9 and r.cells[bc].num]
                if len(ref) != 1:
                    continue
                tref = ref[0].cells[bc].v
                for r in rs:
                    if r is ref[0] or not r.cells[bc].num or not r.cells[bc].v or not tref:
                        continue
                    n += 1
                    want = tref / r.cells[bc].v if lower else r.cells[bc].v / tref
                    if off(want, r.cells[ci]) and abs(want - r.cells[ci].v) > r.cells[ci].tol + 1e-9:
                        out.append((r, want, ref[0]))
            return out, n
        # the time column the header or caption names ("Search speedup"), else the nearest one to the left; any
        # time/QPS column that reproduces every ratio is the base
        named = [c for c in base if any(w in t.leaf(ci) or re.search(r"\b" + re.escape(w) + r"\s+speed-?up", t.cap_text)
                                        for w in re.findall(r"[a-z]{4,}", t.leaf(c)) if not TIME_RX.search(w))]
        bc = named[0] if len(named) == 1 else max((c for c in base if c < ci), default=base[0])
        bad, n = mismatches(bc)
        if not n or any(mismatches(c)[1] and not mismatches(c)[0] for c in base):
            continue
        for r, want, ref in bad:
            R.add("CHECK", "speedup column does not match the times", t.start, "",
                  f"{r.method or '?'}: printed {r.cells[ci].s}, {t.leaf(bc)} gives {want:.2f} "
                  f"(reference {ref.method})", key=f"spd{t.start}{r.ri}{ci}",
                  hint="recompute the speedup from the times (rounding to the printed digits)")


UNITREQ_RX = re.compile(r"\b(time|latency|runtime|run-time|memory|energy|throughput)\b|^(index |model |file |disk |memory )?size$")
UNIT_TOKEN_RX = re.compile(r"(?<![a-z])(ms|µs|μs|us|ns|s|sec|secs|seconds?|mins?|minutes?|h|hrs?|hours?|days?|gb|mb|kb|tb|"
                           r"gib|mib|kib|tib|bytes?|bits?|j|kj|kwh|wh|w|flops|gflops|tflops|macs|qps|q/s|tokens/s|it/s|"
                           r"samples/s|req/s|%|×|x|relative|normalized)(?![a-z])")


def check_units_missing(t, R, units_seen):
    """Efficiency columns (time, memory, size, energy, throughput) need a unit in the header or the caption."""
    heads = [(r.label, r.label, [c for c in r.cells[t.nlab:] if c.v is not None]) for r in t.rows] if t.transposed \
        else [(t.metric_text(c), t.col_text(c), [r.cells[c] for r in t.rows if r.cells[c].v is not None])
              for c in t.data_cols()]
    for metric, full, cells in heads:
        m = UNITREQ_RX.search(metric)
        if not m or re.search(r"speed-?up|\bratio\b|relative|normali[sz]ed|×", metric):
            continue  # a speedup or a ratio has no unit
        units = set(UNIT_TOKEN_RX.findall(full)) | set(UNIT_TOKEN_RX.findall(t.cap_text))
        if not units and cells and sum(1 for c in cells if c.unit and c.unit not in ("×", "%")) * 2 >= len(cells):
            R.add("INFO", "unit written in every cell", t.start, "", f"'{full}' ({t.name}): "
                  + ", ".join(f"{c.s} {c.unit}" for c in cells[:3]), key=f"cellunit{t.start}{full}",
                  hint="style: give the unit once in the header")
        elif not units:
            R.add("CHECK", "unit missing in an efficiency column", t.start, "", f"'{full}' ({t.name})",
                  key=f"nounit{t.start}{full}", hint="give the unit in the header or the caption (ms, GB, ...)")
        own = [u.replace("us", "µs").replace("μs", "µs") for u in UNIT_TOKEN_RX.findall(full)]
        cls = "time" if re.search(r"time|latency|runtime", metric) else "memory" if re.search(r"memory|size", metric) else None
        for u in own:
            if cls and UNIT_CLASS.get(u) == ("time" if cls == "time" else "mem"):
                units_seen[cls].add((u, t.start))


# ---- trends and monotone series
KNOB_STEM = re.compile(r"^(|k=|n=|@|top-|[a-z]+@|[a-z]+=|bits?|steps?|frames?|x|×)$")


def ordered_runs(t):
    """Runs of ≥3 data columns whose leaf headers are increasing numbers (a knob: k, %, budget, R@k) in one group."""
    runs, cur, prev = [], [], None
    corner_knob = bool(KNOB_RX.match(t.corner))
    for c in t.data_cols():
        if t.ratio_col(c) or COUNT_RX.search(t.metric_text(c)) and not t.knob_leaf(c):
            continue
        leaf = t.leaf(c)
        nm = re.search(r"\d+(?:\.\d+)?", leaf)
        stem = re.sub(r"[\d.,%\s]", "", leaf)
        ok = nm and (KNOB_STEM.match(stem) or corner_knob)
        key = (tuple(t.levels[c][:-1]), stem)
        v = float(nm.group(0)) if nm else None
        if ok and prev and prev[0] == key and v > prev[1]:
            cur.append(c)
        else:
            if len(cur) >= 3:
                runs.append(cur)
            cur = [c] if ok else []
        prev = (key, v) if ok else None
    if len(cur) >= 3:
        runs.append(cur)
    return runs


def step_dirs(xs):
    return ["up" if b > a else "down" if b < a else "flat" for a, b in zip(xs, xs[1:])]


def check_trends(src, R):
    """A row whose values move against the trend that (almost) every other row of its table follows, over ordered
    columns; and, for a numeric knob, every series that dips or rises against its own majority (INFO)."""
    tables, _ = table_index(src)
    for t in tables:
        runs = ordered_runs(t)
        for run in runs:
            series = [(r.method or "?", r.label or r.method or "?", [r.cells[c].v for c in run if r.cells[c].num])
                      for r in t.rows]
            series = [s for s in series if len(s[2]) == len(run)]
            if not t.transposed and len(series) >= 3:
                def direction_of(xs):
                    d = set(step_dirs(xs)) - {"flat"}
                    return d.pop() if len(d) == 1 else "mixed" if d else "flat"
                dirs = [direction_of(xs) for _, _, xs in series]
                for d in ("up", "down"):
                    if dirs.count(d) >= max(3, int(0.8 * len(dirs))):
                        for (lab, _, xs), dd in zip(series, dirs):
                            if dd not in (d, "flat"):
                                R.add("CHECK", "row breaks the trend of its table", t.start, "",
                                      f"{lab}: {', '.join(f'{x:g}' for x in xs[:8])} (the other rows go {d})",
                                      key=f"trend{t.start}{lab}",
                                      hint="implausible, or an error in a cell? explain it in the text")
            knob = [t.leaf(c) for c in run]
            report_monotone(t, R, [(lab, xs) for _, lab, xs in series], knob)
        if t.knob_rows:
            for blk in sorted({r.block for r in t.rows}):
                rows = [r for r in t.rows if r.block == blk]
                ks = [r.cells[0].v for r in rows]
                if len(rows) < 3 or not all(b > a for a, b in zip(ks, ks[1:])):
                    continue
                knob = [r.cells[0].s for r in rows]
                series = [(t.leaf(c) or f"column {c + 1}", [r.cells[c].v for r in rows if r.cells[c].num])
                          for c in t.data_cols() if not t.ratio_col(c)]
                report_monotone(t, R, [(lab, xs) for lab, xs in series if len(xs) == len(rows)], knob)


def report_monotone(t, R, series, knob):
    items = []
    for lab, xs in series:
        d = step_dirs(xs)
        up, down = d.count("up"), d.count("down")
        if up and down and up != down:
            against = "down" if up > down else "up"
            at = [knob[i + 1] for i, x in enumerate(d) if x == against]
            items.append(f"{lab}: {', '.join(f'{x:g}' for x in xs[:8])} ({against} at {', '.join(at[:3])})")
    if items:
        R.add("INFO", "series over a numeric knob that dips or rises against its trend", t.start, "",
              "; ".join(items[:8]), key=f"mono{t.start}{knob}", maxlen=600,
              hint="quality should not fall as the budget grows (nor rise as it shrinks): explain or check the cell")


# ---- candidate lists for the agent (claims vs wins, bounds, ablations, margins, imported numbers, N)
QUANT_RX = re.compile(r"consistently|\bon all\b|\bevery\b|\balways\b|lossless|no (degradation|loss)|outperforms all|"
                      r"state[- ]of[- ]the[- ]art on|across the board|\bin all (cases|settings|datasets|benchmarks)", re.I)


COMPARE_RX = re.compile(r"outperform|better|faster|slower|best|beats?\b|improv|higher|lower|wins?\b|lead|ahead|superior|"
                        r"state[- ]of[- ]the[- ]art|lossless|degradation|surpass|exceed", re.I)


def wins(t, klass=None):
    """[(column name, is a proposed row best?)] per column and block where the proposed rows compete; klass 'eff'
    keeps the speed and memory columns, 'quality' the others."""
    out = []
    if t.transposed or not t.proposed:
        return out
    for c in t.data_cols():
        if t.ratio_col(c) or COUNT_RX.search(t.metric_text(c)):
            continue
        if klass and (klass == "eff") != bool(col_class(t, c)):
            continue
        d = t.eff_dir(c)
        if not d:
            continue
        for (blk, grp), rs in t.sets(c).items():
            ps = [r for r in rs if r.method in t.proposed]
            others = [r for r in rs if r.method not in t.proposed and not t.is_bound(r)
                      and not AVG_RX.fullmatch(r.method or "") and not ABL_RX.search(r.label)]
            if not ps or not others:
                continue
            p = max((r.cells[c] for r in ps), key=lambda x: x.v * d)
            best = not any(better(o.cells[c].v, p.v, d, max(p.tol, o.cells[c].tol) + 1e-9) for o in others)
            out.append((t.colname(c, grp), best))
    return out


def names_proposed(t, ctx, stext):
    """The sentence names the table's proposed rows: 'ours', or the macro of those rows (or the macro it extends)."""
    if OURS_RX.search(stext):
        return True
    row_macros = {n for r in t.rows if r.method in t.proposed for n in re.findall(r"\\([A-Za-z]+)", r.label_raw)}
    return any(n == m or (len(m) >= 3 and n.startswith(m)) or re.search(r"\\" + m + r"(?![A-Za-z])",
                                                                      ctx.defined.get(n, ""))
               for m in re.findall(r"\\([A-Za-z]+)", stext) if m in ctx.defined for n in row_macros)


def check_number_candidates(src, R):
    tables, ctx = table_index(src)
    if not tables:
        return
    by_label = {lab: t for t in tables for lab in t.labels}
    # (a) quantified claims vs the columns the proposed row wins
    key_sec = re.compile(r"abstract|introduction|conclusion|summary", re.I)
    for section, sent, refs, _ in text_units(src):
        stext = " ".join(x for _, _, x in sent)
        q = QUANT_RX.search(stext)
        if not q or not COMPARE_RX.search(stext):
            continue
        cited = [by_label[r] for r in sorted(refs) if r in by_label]
        if not cited and key_sec.search(section):  # a headline claim: every results table with a clear proposed row
            cited = [t for t in tables if t.proposed_how in ("label", "bold", "macro+bold", "own")]
        # the claim's comparative word picks the columns: "faster" is about speed (or memory), "better" about quality
        eff = re.search(r"faster|slower|\bfast|latency|throughput|speed|memory|smaller|compact|footprint|cheaper", stext,
                        re.I)
        qual = re.search(r"outperform|better|accura|quality|effective|beats?\b|superior|surpass|wins?\b|improv|"
                         r"higher|state[- ]of[- ]the[- ]art|ndcg|recall|precision", stext, re.I)
        klass = "eff" if eff and not qual else "quality" if qual and not eff else None
        for t in cited:
            clause = re.split(r"[,;:]", stext[:q.start()])[-1]  # the subject of the quantified claim
            if t.proposed_how == "own" and not names_proposed(t, ctx, clause):
                continue  # the claim is about something else than the system of the table's proposed rows
            w = wins(t, klass)
            k = sum(1 for _, b in w if b)
            if w and k < len(w):
                lost = [n for n, b in w if not b]
                R.add("CHECK", "quantified claim vs wins in the table", f"{sent[0][0]}:{sent[0][1]}", "",
                      f"claim '{q.group(0)}' vs best in {k}/{len(w)} columns of the {t.name}; not best: "
                      f"{', '.join(lost[:6])}", key=f"quant{t.start}{q.group(0).lower()}",
                      hint="qualify the claim (in k of n settings) or show where it holds")
    for t in tables:
        if t.transposed:
            continue
        check_bounds(t, R)
        check_ablation(t, tables, R)
        check_margins(t, R)
    check_imported(src, tables, R)
    check_eval_size(src, R)


def check_bounds(t, R):
    """Rows that beat an oracle / upper bound / full-precision / teacher row (quality columns only)."""
    items = []
    abl_full = ablation_full(t)
    for b in t.rows:
        if not t.is_bound(b) or b.method in t.proposed or b is abl_full:
            continue
        for c in t.data_cols():
            if not b.cells[c].num or t.ratio_col(c) or EFF_RX.search(t.metric_text(c)):
                continue
            d = t.eff_dir(c)
            if not d:
                continue
            for r in t.rows:
                if r is b or r.block != b.block or r.group != b.group or not r.cells[c].num:
                    continue
                if better(r.cells[c].v, b.cells[c].v, d, max(r.cells[c].tol, b.cells[c].tol) + 1e-9):
                    items.append(f"{r.label or r.method} > {b.label} on {t.leaf(c) or c + 1}: {r.cells[c].s} vs {b.cells[c].s}")
    if items:
        R.add("INFO", "row beats a bound row (oracle, upper bound, full precision, teacher)", t.start, "",
              "; ".join(items[:8]), key=f"bound{t.start}", maxlen=600, hint="a bound cannot be beaten: explain why")


def ablation_full(t):
    """The full model of an ablation table (the one row the w/o rows are compared with), or None."""
    abl = [r for r in t.rows if ABL_RX.search(r.label)]
    if not abl:
        return None
    full = [r for r in t.rows if r not in abl and (FULL_RX.search(r.label) or r.method in t.proposed)]
    return full[0] if len(full) == 1 else None


def check_ablation(t, tables, R):
    abl = [r for r in t.rows if ABL_RX.search(r.label)]
    f = ablation_full(t)
    if f is None:
        return
    items = []
    for r in abl:
        for c in t.data_cols():
            if not (r.cells[c].num and f.cells[c].num) or r.group != f.group:
                continue
            d = t.eff_dir(c)
            if d and better(r.cells[c].v, f.cells[c].v, d, max(r.cells[c].tol, f.cells[c].tol) + 1e-9):
                items.append(f"{r.label} > {f.label} on {t.leaf(c) or c + 1}: {r.cells[c].s} vs {f.cells[c].s}")
    if items:
        R.add("INFO", "removing a component improves the score", t.start, "", "; ".join(items[:8]),
              key=f"abl{t.start}", maxlen=600, hint="say why removing it helps, or check the run")
    # the full model of the ablation = the proposed row of a main table, on the same column
    for m in tables:
        if m is t or m.transposed or len(m.proposed) != 1:
            continue
        mine = [r for r in m.rows if r.method in m.proposed]
        # the group the ablation names ("Ablation on MS MARCO"), then any group compatible with the full row
        ours = [r for r in mine if r.group is not None and (r.group == f.group or implied(r.group, t))]
        if len(ours) != 1:
            ours = [r for r in mine if r.group is None or f.group is None or r.group == f.group or implied(r.group, t)]
        if len(ours) != 1:
            continue
        for cm, ca in col_pairs(m, t):
            a, b = ours[0].cells[cm], f.cells[ca]
            if a.num and b.num and same_at_precision(a, b) == 0:
                R.add("CHECK", "ablation full model differs from the main table", f"{t.start}, {m.start}", "",
                      f"{f.label} / {' / '.join(t.levels[ca])}: {b.s} vs {ours[0].label or ours[0].method} {a.s}",
                      key=f"ablfull{t.start}{m.start}{ca}",
                      hint="the full model of the ablation is the main result: same number, or say why it differs")


def check_margins(t, R):
    """Best minus second best per column of a comparison table, and whether any spread (±) is shown."""
    if not t.proposed:
        return
    items = []
    for c in t.data_cols():
        if t.ratio_col(c) or COUNT_RX.search(t.metric_text(c)):
            continue
        d = t.eff_dir(c)
        if not d:
            continue
        for (_, grp), rs in t.sets(c).items():
            rs = [r for r in rs if not t.is_bound(r) and not AVG_RX.fullmatch(r.method or "") and not ABL_RX.search(r.label)]
            if len(rs) < 2:
                continue
            srt = sorted(rs, key=lambda r: r.cells[c].v, reverse=d > 0)
            m = abs(srt[0].cells[c].v - srt[1].cells[c].v)
            name = t.colname(c, grp)
            items.append(f"{name}: {m:.{max(srt[0].cells[c].dec, srt[1].cells[c].dec)}f} ({srt[0].label or srt[0].method})")
    if items:
        pm = any(r.cells[c].spread is not None for r in t.rows for c in t.data_cols())
        R.add("INFO", "margins of the best row (best − second)", t.start, "",
              f"{'± shown' if pm else 'no ± in the table'}; " + "; ".join(items[:12]), key=f"margin{t.start}", maxlen=800,
              hint="a margin smaller than the run-to-run spread (or one test item) is not a result")


def check_imported(src, tables, R):
    marked = [(t, r) for t in tables for r in t.rows if (r.imported or re.search(r"†|\*$", r.label))
              and re.search(r"[a-z]", r.method)]
    if not marked:
        return
    m = re.search(r"[^.]*\b((reported|taken|copied|numbers|results|scores) (from|in) (the |their )?(original|respective|"
                  r"published|corresponding|cited)|as reported (in|by))[^.]*", src.code(), re.I)
    if m:
        R.add("INFO", "imported numbers (marked rows)", quote="; ".join(f"{r.method} ({t.start})" for t, r in marked[:8])
              + f" | {' '.join(m.group(0).split())[:120]}", key="imported", maxlen=600,
              hint="check that the copied numbers use the same data, split and metric as the paper's own runs")


def check_eval_size(src, R):
    items = []
    for f, no, code, _, _ in src.lines:
        line = norm_tex_numbers(code)
        for m in re.finditer(r"(?<![\w.,])(\d{2,5}|\d{1,2},\d{3})\s+(?:[\w-]+\s+){0,2}?(samples|questions|queries|examples|"
                             r"items|problems|prompts|instances|test cases|tasks|images|dialogues|documents)\b", line):
            n = parse_number(m.group(1))
            # an evaluation set: the sentence says test/evaluation/benchmark; the clause is not about training,
            # batches or a rate ("128 queries per step")
            b0 = max((x.end() for x in re.finditer(r"[.!?]\s", line[:m.start()])), default=0)
            e0 = next((x.start() for x in re.finditer(r"[.!?](\s|$)", line[m.end():])), len(line) - m.end()) + m.end()
            c0 = max((x.end() for x in re.finditer(r"[;,:]", line[b0:m.start()])), default=0) + b0
            c1 = next((x.start() for x in re.finditer(r"[;,:]", line[m.end():e0])), e0 - m.end()) + m.end()
            if not re.search(r"\b(test|tests|testing|eval|evaluation|evaluate[sd]?|held-out|benchmarks?)\b",
                             line[b0:e0], re.I) or re.search(r"\b(per|batch|batches|train|training|trained)\b",
                                                            line[c0:c1], re.I):
                continue
            if n and 10 <= n <= 2000:
                items.append(f"N={m.group(1)} {m.group(2)} ({f}:{no}): one item = {100 / n:.2g} points")
    if items:
        R.add("INFO", "evaluation set sizes (one item in points)", quote="; ".join(items[:8]), key="evalsize", maxlen=600,
              hint="a gain smaller than one item (100/N points) is noise")


# ---- bibliography
def parse_bib(text):
    """[(key, entry)] in file order (repeated keys kept)."""
    entries = []
    for m in re.finditer(r"(^|\n)\s*(%?)\s*@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)(?=\n\s*%?\s*@\w+\s*\{|\Z)", text, re.S):
        commented, typ, key, body = m.group(2), m.group(3).lower(), m.group(4), m.group(5)
        if typ in ("comment", "string", "preamble"):
            continue
        fields = {}
        for fm in re.finditer(r"(\w+)\s*=\s*(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}|\"[^\"]*\"|\w+)", body):
            fields[fm.group(1).lower()] = fm.group(2).strip("{}\"").strip()
        entries.append((key, dict(type=typ, commented=bool(commented), fields=fields)))
    return entries


def check_bib(src, root_tex, R):
    code = src.code()
    bibs = []
    for m in re.finditer(r"\\bibliography\s*\{([^}]+)\}|\\addbibresource\s*(?:\[[^\]]*\])?\{([^}]+)\}", code):
        for b in (m.group(1) or m.group(2)).split(","):
            p = src.root / (b.strip() if b.strip().endswith(".bib") else b.strip() + ".bib")
            if p.is_file():
                bibs.append(p)
    if not bibs:
        return
    aux = root_tex.with_suffix(".aux")
    cited = set()
    if aux.is_file():
        for m in re.finditer(r"\\citation\{([^}]+)\}|\\abx@aux@cite\{\d*\}\{([^}]+)\}", aux.read_text(errors="replace")):
            cited.update(k.strip() for k in (m.group(1) or m.group(2)).split(","))
    entries = {}
    for b in bibs:
        text = b.read_text(encoding="utf-8", errors="replace")
        for k, e in parse_bib(text):
            e["file"] = src.rel(b)
            if k in entries:
                R.add("FAIL", "bib key defined twice", e["file"], "", k, key="rep" + k,
                      hint="BibTeX keeps the first and reports an error; later entries may be skipped")
                continue
            entries[k] = e
    use = {k: e for k, e in entries.items() if (not cited or k in cited or "*" in cited)}
    for k, e in use.items():
        if e["commented"]:
            R.add("CHECK", "'%' does not comment out a .bib entry", e["file"], "", f"%@{e['type']}{{{k},",
                  hint="BibTeX still reads it, and it is cited")
    titles = defaultdict(list)
    for k, e in use.items():
        f = e["fields"]
        t = re.sub(r"[^a-z0-9]", "", fold(f.get("title", "")))
        if t:
            titles[t[:60]].append(k)
        if "year" not in f and "date" not in f:
            R.add("CHECK", "bib entry without year", e["file"], "", k)
        if e["type"] == "article" and not f.get("journal") and not f.get("journaltitle"):
            R.add("CHECK", "article without journal", e["file"], "", k)
        if e["type"] == "inproceedings" and not f.get("booktitle"):
            R.add("CHECK", "inproceedings without booktitle", e["file"], "", k)
        for fld in ("doi",):  # \_ inside url fields is usually handled by \url
            if "\\_" in f.get(fld, ""):
                R.add("CHECK", f"\\_ in {fld} (prints a backslash)", e["file"], "", f"{k}: {f[fld]}")
        if "arxiv" in fold(f.get("journal", "")) and re.search(r"\d", f.get("volume", "") + f.get("number", "")):
            R.add("CHECK", "arXiv entry with volume/number", e["file"], "", f"{k}: {f.get('journal')} {f.get('volume', '')}({f.get('number', '')})")
    for t, keys in titles.items():
        if len(keys) > 1:
            R.add("CHECK", "same title under different keys", "", "", ", ".join(keys), key="dup" + t,
                  hint="the reference list prints the work twice")
    arx = sum(1 for e in use.values() if "arxiv" in fold(" ".join(e["fields"].values())))
    if use:
        R.add("INFO", "bibliography", quote=f"{len(use)} cited entries, {arx} on arXiv only or with arXiv info",
              key="bibstats", hint="arXiv entries may have a published version (reference checker)")
    bbl = root_tex.with_suffix(".bbl")
    if bbl.is_file():
        b = bbl.read_text(encoding="utf-8", errors="replace")
        lost = set()
        for k, e in use.items():
            for w in re.findall(r"(?<![{\w])([A-Z][A-Za-z]*[A-Z][A-Za-z0-9]*)(?![\w}])", e["fields"].get("title", "")):
                low = w[0] + w[1:].lower()
                if low != w and re.search(r"\b" + re.escape(low) + r"\b", b):
                    lost.add(f"{w}→{low}")
        if lost:
            R.add("CHECK", "capitals lost in reference titles", "", "", ", ".join(sorted(lost)[:15]), key="caps",
                  hint="protect acronyms with braces in the .bib title")


# ====================================================================== round-3 checks
# Classic English misspellings (hand-written list; a typo of a word the paper never uses correctly is otherwise
# missed by the "used elsewhere" rule of check_spelling).
CLASSIC_TYPOS = dict(p.split(":") for p in """
accomodate:accommodate acheive:achieve achived:achieved accross:across adress:address agressive:aggressive
algoritm:algorithm algorith:algorithm alogrithm:algorithm apparant:apparent appearence:appearance
approch:approach aquire:acquire arbitary:arbitrary arguement:argument assesment:assessment basicly:basically
begining:beginning beleive:believe benchamrk:benchmark buisness:business calulate:calculate catagory:category
collegue:colleague comming:coming commited:committed comparision:comparison completly:completely
concious:conscious consistant:consistent convinient:convenient critisism:criticism datset:dataset
decison:decision definately:definitely desicion:decision diffrent:different effecient:efficient
efficent:efficient effcient:efficient embarass:embarrass enviroment:environment equivelant:equivalent
equivalant:equivalent evalute:evaluate excercise:exercise existance:existence experiement:experiment
experiemnt:experiment explaination:explanation familar:familiar foward:forward goverment:government
grammer:grammar guarentee:guarantee heirarchy:hierarchy heuristc:heuristic immediatly:immediately
implemention:implementation independant:independent independance:independence intial:initial
intergrate:integrate interupt:interrupt knowlege:knowledge langauge:language lenght:length liason:liaison
maintainance:maintenance managment:management millenium:millennium mutliple:multiple neccessary:necessary
neccesary:necessary neglegible:negligible nontheless:nonetheless noticable:noticeable occassion:occasion
occured:occurred occurence:occurrence occurrance:occurrence ocurred:occurred oppurtunity:opportunity
optimiation:optimization orignal:original paramter:parameter paramters:parameters parrallel:parallel
paralell:parallel perfomance:performance perfromance:performance perfrom:perform persistant:persistent
posible:possible prefered:preferred probabilty:probability proceedure:procedure propogate:propagate
 reccomend:recommend recomend:recommend recieve:receive recieved:received refered:referred
refrence:reference relevent:relevant repetion:repetition resistence:resistance retreival:retrieval
retreive:retrieve sematic:semantic seperate:separate seperately:separately signficant:significant
similiar:similar simliar:similar simultanious:simultaneous stategy:strategy stragety:strategy strenght:strength
succesful:successful succesfully:successfully sucess:success sufficent:sufficient 
suprise:surprise sytem:system tendancy:tendency  threshhold:threshold thier:their
throughtput:throughput throuhgput:throughput trainig:training tranformer:transformer transfered:transferred
truely:truly untill:until usefull:useful varient:variant visable:visible  wheter:whether
wich:which wierd:weird writting:writing accuarcy:accuracy accuray:accuracy convergance:convergence
dimentional:dimensional dimention:dimension embeding:embedding embedings:embeddings lattency:latency
""".split())



def check_typos_more(src, R):
    """Case-insensitive doubled words are in check_doubled_words; here: classic misspellings."""
    words = defaultdict(list)
    for where, line in prose_lines(src, min_words=1):
        for w in re.findall(r"(?<![\w\\-])[A-Za-z]{4,}(?![\w-])", line):
            words[w.lower()].append(where)
    for w, locs in words.items():
        if w in CLASSIC_TYPOS:
            R.add("CHECK", "probable misspelling", ", ".join(locs[:3]), "", f"{w} → {CLASSIC_TYPOS[w]}", key="ct" + w,
                  hint="common English misspelling")


def check_compound_variants(src, R):
    """The same compound written with a hyphen and as one word: multi-vector / multivector (plurals counted)."""
    text = " ".join(l for _, l in prose_lines(src, min_words=1)).lower()
    hyph = Counter((a, re.sub(r"s$", "", b)) for a, b in re.findall(r"\b([a-z]{3,})-([a-z]{3,})\b", text))
    for (a, b), n in hyph.items():
        if len(a + b) < 8:
            continue
        joined = len(re.findall(r"\b" + a + b + r"s?\b", text))
        if joined:
            R.add("CHECK", "compound written in different ways", "", "", f"{a}-{b} ×{n} vs {a}{b} ×{joined}",
                  key=f"cmp{a}{b}", hint="choose one spelling")



UNNUMBERED_OK = r"acknowledg|references|bibliography|declaration|statement|disclosure|credit|funding|appendix|" \
                r"availability|ethic|limitations|impact|contribution|abbreviation|nomenclature|conflict|competing|" \
                r"generative ai|genai|author|supplementary|reproducibility|checklist|proof|abstract|keywords|" \
                r"theorem|lemma|notation|glossary|preface|foreword|summary"


def check_label_hygiene(src, R):
    code = "\n".join(f"\x00{f}:{no}\x00" + c for f, no, c, _, _ in src.lines)

    def loc_at(pos):
        k = code.rfind("\x00", 0, pos)
        k0 = code.rfind("\x00", 0, k)
        return code[k0 + 1:k] if k0 != -1 else ""
    # \label before \caption inside a float: the label takes the number of the enclosing section
    for m in re.finditer(r"\\begin\{(figure|table|algorithm)\*?\}(.*?)\\end\{\1\*?\}", code, re.S):
        body = m.group(2)
        lab, cap = body.find("\\label{"), body.find("\\caption")
        if lab != -1 and cap != -1 and lab < cap and not re.search(r"\\subcaption|\\subfloat|subfigure", body[:cap]):
            name = re.match(r"\\label\{([^}]*)\}", body[lab:]).group(1)
            R.add("FAIL", "\\label before \\caption in a float", loc_at(m.start() + len(m.group(0)) - len(body) + lab), "",
                  name, key="lbc" + name, hint="the reference prints the section number, not the float number")
    # \ref to a label inside an unnumbered display
    starred = set()
    for m in re.finditer(r"\\begin\{(equation|align|gather|multline|eqnarray)\*\}(.*?)\\end\{\1\*\}|\\\[(.*?)\\\]", code, re.S):
        disp = m.group(2) or m.group(3) or ""
        if "\\tag" not in disp:  # \tag gives the display a number
            starred.update(re.findall(r"\\label\{([^}]*)\}", disp))
    for lab in starred:
        refs = [loc_at(r.start()) for r in re.finditer(r"\\(eq)?ref\{" + re.escape(lab) + r"\}", code)]
        if refs:
            R.add("FAIL", "\\ref to a label in an unnumbered display", ", ".join(refs[:4]), "", lab, key="st" + lab,
                  hint="the reference prints a wrong number: number the equation or drop the reference")
    # \ref to its own section
    secs = [(m.start(), len(m.group(1)), m.group(3)) for m in
            re.finditer(r"\\((?:sub)*)section(\*?)\s*\{[^}]*\}\s*(?:\\label\{([^}]*)\})?", code)]
    for i, (start, depth, lab) in enumerate(secs):
        if not lab:
            continue
        end = next((s for s, d, _ in secs[i + 1:] if d <= depth), len(code))
        for r in re.finditer(r"\\(?:auto|c|C)?ref\{" + re.escape(lab) + r"\}", code[start:end]):
            R.add("CHECK", "reference to the section it is in", loc_at(start + r.start()), "", lab, key=f"self{lab}{r.start()}",
                  hint="\"see Section 4\" inside Section 4: point elsewhere or drop it")
    # unnumbered sections mixed with numbered ones in the body
    body_secs = [(m.group(1), m.group(2), loc_at(m.start())) for m in re.finditer(r"\\section(\*?)\s*\{([^}]*)\}", code)]
    numbered = [s for s in body_secs if not s[0]]
    stray = [s for s in body_secs if s[0] and not re.search(UNNUMBERED_OK, s[1], re.I)]
    if numbered and stray:
        R.add("CHECK", "unnumbered section among numbered ones", ", ".join(s[2] for s in stray[:4]), "",
              "; ".join(s[1] for s in stray[:4]), key="secstar", hint="use \\section or explain why it is unnumbered")


def check_leftover_text(comp, src, R):
    if not comp.ok:
        return
    for page, line in comp.iter_lines():
        for rx, sev, what in [(r"(?i)under review as a (conference|workshop) paper|submitted to .{0,40}do not distribute",
                               "INFO", "submission header of the template"),
                              (r"(?i)\b(this|the) (paper|manuscript|submission|article|version) is (currently )?under review\b"
                               r"|\bdo not (distribute|circulate)\b(?!.*submitted to)|\bconfidential (draft|manuscript)\b",
                               "CHECK", "submission-status text"),
                              (r"\b(DRAFT|Draft version|draft version)\b", "CHECK", "draft marker"),
                              (r"(?i)\bpreprint submitted to\b", "INFO", "template footer 'Preprint submitted to'")]:
            if re.search(rx, line):
                R.add(sev, what, src.locate(line), str(page), line, key=what + line.strip()[:40],
                      hint="usual for this template" if sev == "INFO" else "remove before submitting")


def check_citation_usage(src, R):
    code_all = src.code()
    natbib_ay = bool((re.search(r"\\usepackage\s*(\[[^\]]*\])?\s*\{natbib\}", code_all) and not re.search(
        r"\\usepackage\s*\[[^\]]*numbers", code_all))
        or re.search(r"\\usepackage\s*\[[^\]]*style\s*=\s*(authoryear|apa|chicago|ext-authoryear)", code_all)
        or re.search(r"\\bibliographystyle\s*\{(plainnat|abbrvnat|apalike|chicago|agsm|named|iclr\w*|icml\w*|acl_natbib)\}",
                     code_all))
    for f, no, code, _, _ in src.lines:
        if natbib_ay and re.search(r"\(\s*\\citet\{|\\citet\{[^}]*\}\s*\)", code):
            R.add("CHECK", "\\citet inside parentheses", f"{f}:{no}", "", code.strip(), key=f"ct{f}{no}",
                  hint="use \\citep for a parenthetical citation")
        if natbib_ay and re.search(r"\\citep\{[^}]*\}\s+(show|propose|introduce|present|stud|demonstrat|argue|find|found)", code):
            R.add("CHECK", "\\citep used as the subject of a sentence", f"{f}:{no}", "", code.strip(), key=f"cp{f}{no}",
                  hint="use \\citet when the citation is the subject")
        if re.search(r"(^|\.\s+)~?\\cite\{[^}]*\}\s+(shows?|showed|proposes?|proposed|introduces?|introduced)\b", code):
            R.add("INFO", "numeric citation as the subject of a sentence", f"{f}:{no}", "", code.strip(), key=f"cs{f}{no}",
                  hint="\"[12] shows\": many venues prefer \"Smith et al. [12] show\"")


def bbox_words(pdf):
    """[(width, height, words)] per page, and whether the word sizes are reliable (False on a pdftocairo copy)."""
    out, reliable = run(["pdftotext", "-bbox-layout", str(pdf), "-"]), True
    if not out and shutil.which("pdftocairo"):
        reliable = False
        # poppler's -bbox-layout aborts on some hyperref PDFs; a copy rewritten by pdftocairo is read fine
        with tempfile.TemporaryDirectory() as td:
            copy = pathlib.Path(td) / "copy.pdf"
            run(["pdftocairo", "-pdf", str(pdf), str(copy)])
            out = run(["pdftotext", "-bbox-layout", str(copy), "-"]) if copy.is_file() else None
    if not out:
        return None, False
    pages = []
    for pm in re.finditer(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', out, re.S):
        w, h = float(pm.group(1)), float(pm.group(2))
        words = [(float(a), float(b), float(c), float(d), t) for a, b, c, d, t in
                 re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', pm.group(3))]
        pages.append((w, h, words))
    return pages, reliable


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(p * (len(xs) - 1))))] if xs else 0


def check_bbox(comp, R, a):
    """From word coordinates: content outside the text block, font-size drift, tiny text, page numbers."""
    if not comp.ok:
        return
    pages, reliable = bbox_words(comp.pdf)
    if not pages:
        R.skip("layout scan: pdftotext -bbox-layout failed, also on a pdftocairo copy")
        return
    size_mode = Counter((round(w), round(h)) for w, h, _ in pages).most_common(1)[0][0]
    rot = {int(m.group(1)) for m in re.finditer(r"Page\s+(\d+) rot:\s+(?:90|180|270)",
                                                 run(["pdfinfo", "-f", "1", "-l", str(len(pages)), str(comp.pdf)]) or "")}
    ys0 = [y0 for w, h, words in pages for x0, y0, x1, y1, t in words]
    ys1 = [y1 for w, h, words in pages for x0, y0, x1, y1, t in words]
    top, bottom = pct(ys0, 0.03), pct(ys1, 0.97)  # the text block; headers and footers lie outside it
    body = []  # (page, word) excluding header/footer bands, line numbers and landscape pages
    for i, (w, h, words) in enumerate(pages, 1):
        if (round(w), round(h)) != size_mode or i in rot:
            continue  # landscape (rotated) or odd-sized page: sidewaystable, pdflscape
        for x0, y0, x1, y1, t in words:
            if y0 < top - 1 or y1 > bottom + 1:
                continue
            if re.fullmatch(r"\d{1,4}", t) and (x1 < 0.12 * w or x0 > 0.88 * w):
                continue  # line numbers in the margins
            body.append((i, x0, y0, x1, y1, t))
    if len(body) < 200:
        return
    left, right = pct([b[1] for b in body], 0.02), pct([b[3] for b in body], 0.98)
    out = Counter()
    for i, x0, y0, x1, y1, t in body:
        if x1 > right + 3 or x0 < left - 3:
            out[i] += 1
    for i, n in sorted(out.items()):
        if n >= 2:
            R.add("CHECK", "content outside the text block", "", str(i), f"{n} words beyond the margins",
                  key=f"oob{i}", hint="look at the page: a table, figure or equation sticks out")
    if not reliable:
        R.skip("font-size drift and very small text: this PDF is read only through a pdftocairo copy, whose word "
               "heights are not reliable (margins are checked)")
    else:
        # font size: median word height per page
        hts = defaultdict(list)
        for i, x0, y0, x1, y1, t in body:
            if t.isalpha() and len(t) >= 4:
                hts[i].append(y1 - y0)
        med = {i: pct(v, 0.5) for i, v in hts.items() if len(v) >= 80}
        if med:
            mode = Counter(round(v, 1) for v in med.values()).most_common(1)[0][0]
            rp = comp.ref_page or len(pages) + 1
            drift = [i for i, v in med.items() if 1 < i < rp and abs(v - mode) >= 0.6]
            if drift:
                R.add("CHECK", "body font size differs on some pages", "", ",".join(map(str, drift[:10])),
                      f"usual word height {mode}pt; pages {', '.join(f'{i}:{med[i]:.1f}' for i in drift[:6])}",
                      key="fontdrift", hint="shrunk text to fit the page limit? (fine for tables, appendices)")
            # tiny text: words much smaller than the body (figure labels, table fonts)
            tiny = Counter(i for i, x0, y0, x1, y1, t in body
                           if i < rp and t.isalpha() and len(t) >= 3 and (y1 - y0) < 0.55 * mode)
            for i, n in sorted(tiny.items()):
                if n >= 8:
                    R.add("CHECK", "very small text on the page", "", str(i), f"{n} words below {0.55 * mode:.1f}pt",
                          key=f"tiny{i}", hint="figure or table text may be illegible in print")
    if a.no_page_numbers:
        for i, (w, h, words) in enumerate(pages, 1):
            if any(re.fullmatch(r"\d{1,3}", t) and y0 > bottom + 1 for x0, y0, x1, y1, t in words):
                R.add("FAIL", "page numbers printed", "", str(i), "", key="pnum", hint="the venue adds page numbers itself")
                break


def check_pdf_tech(comp, R):
    if not comp.ok:
        return
    info = run(["pdfinfo", str(comp.pdf)]) or ""
    if re.search(r"^Encrypted:\s+yes", info, re.M):
        R.add("FAIL", "PDF is encrypted", "", "", "", key="enc", hint="submission systems reject protected PDFs")
    m = re.search(r"^PDF version:\s+([\d.]+)", info, re.M)
    if m:
        R.add("INFO", "PDF version", quote=m.group(1), key="pdfver")


def check_links(comp, src, R, names, a):
    if a.offline or not comp.ok:
        return
    # complete URLs come from the source and the .bbl: pdftotext breaks long URLs at line ends
    text = "\n".join(code for _, _, code, _, _ in src.lines)  # comments and \iffalse blocks removed
    bbl = src.root_tex.with_suffix(".bbl")
    if bbl.is_file():
        text += "\n" + bbl.read_text(encoding="utf-8", errors="replace")
    urls = []
    for m in re.finditer(r"\\(?:url|href|path|nolinkurl)\s*\{([^}]+)\}|\\urlprefix\\url\{([^}]+)\}"
                         r"|(?<![{\w/])(https?://[^\s{}\\]+[^\s{}\\.,;:)])", text):
        u = (m.group(1) or m.group(2) or m.group(3)).strip().replace("\\_", "_").replace("\\#", "#").replace("\\%", "%")
        if u.startswith("http") and u not in urls and not re.search(r"doi\.org|arxiv\.org/abs", u):
            urls.append(u)
    def fetch(u):  # (url, body or None, HTTP error code or None, unreachable)
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (link check)"})
            with urllib.request.urlopen(req, timeout=10) as r:
                return u, r.read(200000).decode("utf-8", errors="replace").lower(), None, False
        except urllib.error.HTTPError as e:
            return u, None, e.code, False
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return u, None, None, True
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:  # links in parallel: the slowest site sets the time
        results = list(pool.map(fetch, urls[:20]))
    R.coverage["links_found"] = len(urls)
    R.coverage["links_tested"] = len(results)
    for u, body, code, unreachable in results:
        try:
            if body is None:
                if code is not None:
                    raise urllib.error.HTTPError(u, code, "", None, None)
                raise urllib.error.URLError("unreachable")
            if "anonymous.4open.science" in u and re.search(r"expired|not found|does not exist", body):
                R.add("FAIL", "anonymous repository expired or empty", "", "", u)
            own = "anonymous" in u or any(tok in u.lower() for n in names for tok in fold(n).split() if len(tok) >= 4)
            if a.blind == "double" and own and any(name_rx(v).search(fold(body)) for n in names for v in name_variants(n)):
                R.add("FAIL", "linked page names an author", "", "", u, hint="the linked repository de-anonymizes the paper")
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                R.add("CHECK", "broken link", src.locate(u), "", f"{u} → HTTP {e.code}", key="lnk" + u)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            R.add("INFO", "link not reachable from here", "", "", u, key="lnku" + u, hint="check it in a browser")


# ====================================================================== supplementary material (--supp)
# Folders or .zip archives of supplementary material and code. Anonymity detectors run with --blind double only;
# credentials, secrets, macOS metadata and large files are reported for every review model. Secrets are masked.
SUPP_TEXT_MAX = 2_000_000          # bytes read from a text file
SUPP_BIN_MAX = 50 * 2 ** 20        # bytes read from a PDF / Office document / nested archive
SUPP_LARGE = 10 * 2 ** 20          # a file above this size is reported
GENERIC_USERS = {"user", "username", "users", "shared", "runner", "ubuntu", "root", "anonymous", "anon", "me", "you",
                 "name", "yourname", "your_name", "<user>", "<username>", "$user", "${user}", "%username%", "jovyan",
                 "vscode", "admin", "guest", "public", "default", "work", "app", "ec2-user", "colab", "content", "x",
                 "xxx", "foo", "bar", "example", "path", "to"}
GENERIC_PEOPLE = ANON_VALUES | {"microsoft office user", "windows user", "python-docx", "openpyxl", "unknown", "admin",
                                "user", "the authors", "anonymous authors", "anonymized", "anonymised", "redacted"}
SECRET_FILE_RX = re.compile(r"(\.env(\.[\w.-]+)?|_?\.?netrc|\.pypirc|\.npmrc|\.git-credentials|\.htpasswd|"
                            r"credentials(\.(json|ya?ml|toml|ini|txt))?|secrets?\.(json|ya?ml|toml|env|txt|ini)|"
                            r"client_secrets?\.json|service[-_]?account[\w.-]*\.json|id_(rsa|dsa|ecdsa|ed25519)|"
                            r"[\w.-]+\.(pem|key|p12|pfx|jks|keystore))", re.I)
SECRET_FILE_SAFE = re.compile(r"\.(example|sample|template|dist|tmpl)$|\.pub$", re.I)
SECRET_RX = (("private key", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY(?: BLOCK)?-----"),
             ("AWS access key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
             ("GitHub token", r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
             ("API key", r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}"),
             ("Hugging Face token", r"\bhf_[A-Za-z0-9]{30,}"),
             ("Slack token", r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
             ("Google API key", r"\bAIza[0-9A-Za-z_-]{35}"),
             ("password in a URL", r"(?<=://)[^/\s:@'\"]+:[^/\s@'\"]{3,}(?=@)"))
ASSIGN_RX = re.compile(r"""(?i)\b([\w.-]*(?:api[_-]?key|secret|token|passw(?:or)?d|access[_-]?key)[\w-]*)"""
                       r"""\s*[:=]\s*["']?([^\s"',;#)]{8,})""")
HOME_RX = re.compile(r"(?:(?<![\w.])/(?:Users|home)/|\b[A-Za-z]:(?:\\\\|\\|/)(?:Users|Documents and Settings)(?:\\\\|\\|/))"
                     r"([\w.$%<>{}-]+)")
HOME_BRX = re.compile(rb"(?:/(?:Users|home)/|[A-Za-z]:\\\\?Users\\\\?)([\w.-]{2,})")
EMAIL_RX = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}\b", re.I)
EMAIL_SKIP = re.compile(r"noreply|no-reply|@example\.|@(localhost|test)\.|anonymous|^git@|@users\.noreply|"
                        r"\.(png|jpe?g|gif|svg|pdf|py|js|ts|css|html?)$", re.I)
REPO_RX = re.compile(r"(github|gitlab|bitbucket|huggingface)\.(com|co|org)/([\w.-]+)", re.I)
AUTHOR_LINE_RX = (re.compile(r"(?i)^[\s#*>|_-]*(?:authors?|maintainers?|contact|written by|created by|developed by)"
                             r"[*_]*\s*:\s*[*_]*\s*(.+)$"),   # README / CITATION / DESCRIPTION prose files only
                  re.compile(r"__author__\s*=\s*['\"](.+?)['\"]"),
                  re.compile(r"(?i)\b(?:author|maintainer)(?:_email)?\s*=\s*['\"](.+?)['\"]"),
                  re.compile(r"(?i)\{\s*name\s*=\s*['\"](.+?)['\"]"),
                  re.compile(r"(?i)\"(?:author|maintainer)\"\s*:\s*\"(.+?)\""),
                  re.compile(r"(?i)^\s*-?\s*(?:family|given)-names\s*:\s*['\"]?(.+?)['\"]?\s*$"))
AUTHOR_FILES = re.compile(r"(?i)^(readme|citation|setup\.(py|cfg)|pyproject\.toml|package\.json|description|"
                          r"[\w-]+\.cff|[\w-]+\.py)")
LICENSE_FILES = re.compile(r"(?i)^(licen[cs]e|copying|copyright|notice|authors|contributors)")
PROSE_EXT = {".md", ".txt", ".rst", ".tex", ".html", ".htm", ".org", ".ipynb", ""}
OFFICE_EXT = {".docx", ".docm", ".xlsx", ".xlsm", ".pptx", ".pptm", ".odt", ".ods", ".odp"}
ACK_RX = re.compile(r"(?i)^\s*(?:#+|\*\*|=+|\\(?:sub)*section\*?\{|\\paragraph\*?\{)?\s*acknowledge?ments?\b")
GRANT_RX = re.compile(r"\b(?i:grants?|award|agreement)\s+(?i:no\.?|number|n\.)?\s*[A-Z0-9][\w/-]{4,}")


def mask_secret(v):
    return "****" if len(v) <= 8 else f"{v[:4]}…[{len(v)} chars]"


def supp_variants(n):
    """Name variants; an institution is matched whole (its last word alone would match common words)."""
    if re.search(r"(?i)univ|institut|college|school|lab\b|laborator|department|cent(er|re)|\binc\b|ltd|gmbh|corp|"
                 r"research|academy|foundation|@", n):
        return [n]
    return name_variants(n)


def supp_entries(p, prefix="", depth=0):
    """(path inside the material, size, read(n)) for every file of a folder or .zip; nested .zip files are opened."""
    import os
    import zipfile
    if isinstance(p, pathlib.Path) and p.is_dir():
        for dp, dns, fns in os.walk(p):   # hidden folders (.git) included
            dns.sort()
            for fn in sorted(fns):
                f = pathlib.Path(dp) / fn
                if f.is_symlink() or not f.is_file():
                    continue
                def read(n, f=f):
                    with open(f, "rb") as h:
                        return h.read(n)
                yield f.relative_to(p).as_posix(), f.stat().st_size, read
        return
    try:
        z = zipfile.ZipFile(p)
    except (zipfile.BadZipFile, OSError):
        return
    with z:
        for info in z.infolist():
            if info.is_dir():
                continue
            def read(n, info=info):
                with z.open(info) as h:
                    return h.read(n)
            name = prefix + info.filename
            if info.filename.lower().endswith(".zip") and depth < 2:
                import io
                yield name, info.file_size, read
                try:
                    inner = io.BytesIO(read(SUPP_BIN_MAX))
                except (OSError, RuntimeError, ValueError):   # encrypted or broken member
                    continue
                yield from supp_entries(inner, name + "!/", depth + 1)
            else:
                yield name, info.file_size, read


def pdf_string(raw):
    if raw.startswith(b"<"):
        try:
            b = bytes.fromhex(re.sub(rb"\s", b"", raw[1:-1]).decode())
        except ValueError:
            return ""
    else:
        b = re.sub(rb"\\([nrtbf()\\]|[0-7]{1,3})", lambda m: {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"",
                   b"f": b""}.get(m.group(1), bytes([int(m.group(1), 8) & 255]) if m.group(1)[:1].isdigit()
                   else m.group(1)), raw[1:-1])
    if b.startswith(b"\xfe\xff"):
        return b[2:].decode("utf-16-be", errors="replace")
    return b.decode("latin-1")


def pdf_info_raw(data):
    """Info-dictionary and XMP metadata of a PDF from its bytes (stdlib: raw objects, then Flate streams)."""
    import zlib
    def scan(buf, out):
        for m in re.finditer(rb"/(Author|Creator|Title|Subject|Keywords)\s*(\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>)", buf):
            out.setdefault(m.group(1).decode(), pdf_string(m.group(2)).strip())
        for k, tag in (("Author", rb"dc:creator"), ("Creator", rb"xmp:CreatorTool")):
            m = re.search(rb"<" + tag + rb"[^>]*>(.*?)</" + tag + rb">", buf, re.S)
            if m:
                v = re.sub(r"<[^>]+>", " ", m.group(1).decode("utf-8", errors="replace"))
                if v.strip():
                    out.setdefault(k, " ".join(v.split()))
    out = {}
    scan(data, out)
    if "Author" not in out:   # Info dictionary inside a compressed object stream (PDF 1.5+)
        for i, m in enumerate(re.finditer(rb"stream\r?\n", data)):
            if i >= 300:
                break
            try:
                scan(zlib.decompressobj().decompress(data[m.end():m.end() + 4_000_000], 4_000_000), out)
            except zlib.error:
                continue
    return out


def office_props(data):
    """People named in an Office/ODF document's properties (docProps, meta.xml) and change/comment authors."""
    import io
    import zipfile
    found = []
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return found
    with z:
        names = set(z.namelist())
        for part, tags in (("docProps/core.xml", ("dc:creator", "cp:lastModifiedBy")),
                           ("docProps/app.xml", ("Company", "Manager")),
                           ("meta.xml", ("meta:initial-creator", "dc:creator"))):
            if part in names:
                xml = z.read(part)[:1_000_000].decode("utf-8", errors="replace")
                for t in tags:
                    for v in re.findall(r"<" + re.escape(t) + r"(?:\s[^>]*)?>([^<]*)</" + re.escape(t) + ">", xml):
                        if v.strip():
                            found.append((f"{part} {t}", v.strip()))
        for part in ("word/document.xml", "word/comments.xml", "word/people.xml"):
            if part in names:
                xml = z.read(part)[:20_000_000].decode("utf-8", errors="replace")
                for v in sorted(set(re.findall(r'w(?:15)?:author="([^"]+)"', xml))):
                    found.append((f"{part} author", v))
    return found


def notebook_segments(text):
    """(location, text) of a notebook's metadata, cell sources and cell outputs."""
    nb = json.loads(text)
    segs = [("notebook metadata", json.dumps(nb.get("metadata", {}), indent=1, ensure_ascii=False))]
    def join(x):
        return "".join(x) if isinstance(x, list) else str(x)
    for i, cell in enumerate(nb.get("cells", []), 1):
        segs.append((f"cell {i}", join(cell.get("source", ""))))
        if cell.get("metadata"):
            segs.append((f"cell {i} metadata", json.dumps(cell["metadata"], indent=1, ensure_ascii=False)))
        outs = []
        for o in cell.get("outputs", []) or []:
            if "text" in o:
                outs.append(join(o["text"]))
            for k in ("text/plain", "text/html", "text/markdown", "application/json"):
                if k in (o.get("data") or {}):
                    v = o["data"][k]
                    outs.append(join(v) if not isinstance(v, dict) else json.dumps(v))
            if o.get("traceback"):
                outs.append(re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(o["traceback"])))
        if outs:
            segs.append((f"cell {i} output", "\n".join(outs)))
    return segs


class SuppScan:
    def __init__(self, R, names, anon, label):
        self.R, self.names, self.anon, self.label = R, names, anon, label
        self.files = self.text_files = self.bytes = 0
        self.counts = {}
        self.rx = [(n, [name_rx(v) for v in supp_variants(n)]) for n in names]
        self.name_toks = {t for n in names for t in re.split(r"[\s@.,-]+", fold(n)) if len(t) >= 4}

    def named(self, s):
        t = fold(s)
        return [n for n, rxs in self.rx if any(r.search(t) for r in rxs)]

    def hit(self, sev, kind, where, quote, tag, hint="", seen=""):
        """First occurrence per (file, kind, tag) only."""
        k = (seen, kind, tag)
        self.counts[k] = self.counts.get(k, 0) + 1
        if self.counts[k] == 1:
            self.R.add(sev, kind, where, quote=quote, hint=hint, key="supp" + "|".join(map(str, k)))

    def file(self, rel, size, read):
        R, anon = self.R, self.anon
        self.files += 1
        self.bytes += size
        parts = rel.replace("!/", "/").split("/")
        base, low = parts[-1], parts[-1].lower()
        where = f"{self.label}:{rel}"
        ext = pathlib.PurePosixPath(low).suffix
        if "__MACOSX" in parts or low == ".ds_store":
            R.add("CHECK", "macOS metadata in the supplementary material", where, key="supp-mac" + self.label,
                  hint="__MACOSX/.DS_Store list folder names; zip with `zip -r -X` or delete them")
            return
        if anon:
            for n in self.named(re.sub(r"[_./-]+", " ", rel)):
                self.hit("FAIL", "author name in a supplementary file name", where, rel, n, seen=where)
        if ".git" in parts:
            gi = parts.index(".git")
            root = f"{self.label}:" + "/".join(parts[:gi + 1])
            if anon:
                R.add("FAIL", "git repository in the supplementary material", root, key="supp-git" + root,
                      hint="its config, logs and objects carry names, e-mails and remotes: export with `git archive`")
            inner = parts[gi + 1:]
            if inner[:1] in (["config"], ["logs"], ["packed-refs"], ["FETCH_HEAD"]):
                self.git_file(where, read(SUPP_TEXT_MAX).decode("utf-8", errors="replace"), inner[0])
            return
        if SECRET_FILE_RX.fullmatch(base) and not SECRET_FILE_SAFE.search(base):
            data = read(SUPP_TEXT_MAX)
            keys = []
            if b"\0" not in data[:8192]:
                for l in data.decode("utf-8", errors="replace").splitlines():
                    m = re.match(r"\s*(?:export\s+)?([\w.-]+)\s*[=:]\s*['\"]?([^'\"\s#]+)", l)
                    if m:
                        keys.append(f"{m.group(1)}={mask_secret(m.group(2))}")
            R.add("FAIL", "credentials file in the supplementary material", where, quote="; ".join(keys[:4]),
                  hint="remove it and revoke the keys it holds" + (f" ({len(keys)} values)" if keys else ""))
            return
        if size > SUPP_LARGE:
            R.add("CHECK", "large file in the supplementary material", where, quote=f"{size / 2 ** 20:.1f} MB",
                  hint="venues cap the upload size; data belongs in an anonymous repository")
        if low.endswith(".zip"):
            return   # its members are scanned as entries
        if ext == ".pdf":
            if anon:
                self.pdf(where, read(SUPP_BIN_MAX))
            return
        if ext in OFFICE_EXT:
            if anon:
                for part, v in office_props(read(SUPP_BIN_MAX)):
                    if fold(v).strip() not in GENERIC_PEOPLE:
                        self.hit("FAIL", "Office document properties in the supplementary material name a person", where, f"{part}: {v}", part,
                                 hint="File > Info > Inspect Document / remove personal information", seen=where)
            return
        data = read(SUPP_TEXT_MAX)
        if b"\0" in data[:8192]:   # binary: compiled files (.pyc, executables) embed absolute paths
            if anon:
                for m in HOME_BRX.finditer(data):
                    u = m.group(1).decode("latin-1")
                    if u.lower() not in GENERIC_USERS:   # one finding per user, every file listed (.pyc caches)
                        R.add("FAIL", "home path in a supplementary binary file", where, quote=m.group(0).decode("latin-1"),
                              key=f"supp-binhome|{self.label}|{u}",
                              hint="compiled files (.pyc, __pycache__) and binaries embed build paths: delete them")
                        break
            return
        self.text_files += 1
        text = data.decode("utf-8", errors="replace")
        segs = [("", text)]
        if ext == ".ipynb":
            try:
                segs = notebook_segments(text)
            except (ValueError, AttributeError, TypeError):
                pass
        for loc, seg in segs:
            for no, line in enumerate(seg.splitlines(), 1):
                w = f"{where}:{no}" if not loc else f"{where} [{loc}]:{no}"
                self.secrets(w, where, line)
                if anon:
                    self.anon_line(w, where, line, base, ext, loc)

    def secrets(self, w, where, line):
        for kind, rx in SECRET_RX:
            m = re.search(rx, line)
            if m:
                q = line[:m.start()] + mask_secret(m.group(0)) + line[m.end():]
                self.hit("FAIL", "secret in the supplementary material", w, q.strip(), kind, seen=where,
                         hint=f"{kind}: remove it and revoke it")
                return
        m = ASSIGN_RX.search(line)
        if m:
            v = m.group(2)
            if (re.search(r"[A-Za-z]", v) and re.search(r"\d", v) and not re.search(r"[(<$%{.\[]", v)
                    and not re.search(r"(?i)your|xxx|example|changeme|dummy|placeholder|environ|getenv", v)):
                q = line[:m.start(2)] + mask_secret(v) + line[m.end(2):]
                self.hit("CHECK", "possible secret in the supplementary material", w, q.strip(), m.group(1),
                         seen=where)

    def anon_line(self, w, where, line, base, ext, loc):
        if not self.authorship(w, where, line, base):   # a named holder/author is reported once, there
            for n in self.named(HOME_RX.sub(" ", line)):   # a name inside a home path is the home-path finding
                self.hit("FAIL", "author name in the supplementary material", w, line.strip(), n, seen=where)
        for m in EMAIL_RX.finditer(line):
            e = m.group(0)
            if EMAIL_SKIP.search(e):
                continue
            own = any(t in fold(e) for t in self.name_toks) or not self.names
            self.hit("FAIL" if own else "CHECK", "e-mail in the supplementary material", w, e, e.lower(), seen=where,
                     hint="" if own else "third-party code keeps its authors; an own address must go")
        for m in HOME_RX.finditer(line):
            u = m.group(1)
            if u.lower() not in GENERIC_USERS:
                self.hit("FAIL", "home path in the supplementary material", w, m.group(0), u, seen=where,
                         hint=("notebook outputs and metadata keep paths: clear them (Kernel > Restart & Clear Output)"
                               if loc else "use relative paths"))
        for m in REPO_RX.finditer(line):
            owner = m.group(3)
            if any(t in fold(owner) for t in self.name_toks):
                self.hit("FAIL", "identifying repository link in the supplementary material", w, m.group(0), owner,
                         seen=where)
            else:
                self.R.add("INFO", "repository link in the supplementary material", w, quote=m.group(0).lower(),
                           key="supp-repo" + owner.lower(), hint="third-party is fine; an own repo must be anonymised")
        if ext in PROSE_EXT and (not loc or not loc.endswith("output")):
            if ACK_RX.match(line):
                self.hit("FAIL", "acknowledgements in the supplementary material", w, line.strip(), "ack", seen=where)
            m = GRANT_RX.search(line)
            if m:
                self.hit("CHECK", "grant number in the supplementary material", w, line.strip(), m.group(0), seen=where)

    def authorship(self, w, where, line, base):
        """Copyright lines of LICENSE-like files and author lines of README/metadata files; True if one names an
        author."""
        named = False
        if LICENSE_FILES.match(base):
            m = re.search(r"(?i)\bcopyright\b\s*(?:\(c\)|©)?\s*(.*)$", line)
            if m:
                holder = re.sub(r"(?i)\(c\)|©|\b(19|20)\d\d\b|[-–,]|all rights reserved\.?|\bby\b", " ", m.group(1))
                holder = " ".join(holder.split()).strip(" .")
                if re.search(r"[A-Za-z]{2}", holder) and fold(holder) not in GENERIC_PEOPLE \
                        and not re.search(r"(?i)anonym|the authors?\b|^holders?$|notice|owner", holder):
                    own = bool(self.named(holder))
                    named |= own
                    self.hit("FAIL" if own else "CHECK", "copyright line in the supplementary material names a holder",
                             w, line.strip(), holder, seen=where, hint="write 'Anonymous Authors' for the review copy" if own
                             else "fine for third-party code; anonymise your own")
        if AUTHOR_FILES.match(base):
            for rx in AUTHOR_LINE_RX:
                m = rx.search(line)
                code = base.lower().endswith((".py", ".toml", ".cfg", ".json"))
                if m and (rx is not AUTHOR_LINE_RX[0] or not code) \
                        and (rx is not AUTHOR_LINE_RX[3] or base.lower() == "pyproject.toml") \
                        and (rx is not AUTHOR_LINE_RX[2] or base.lower() in ("setup.py", "setup.cfg")):
                    v = m.group(1).strip(" *_`'\"")
                    if v and fold(v) not in GENERIC_PEOPLE and not re.search(r"(?i)anonym|redacted|^\W*$", v):
                        own = bool(self.named(v)) or not self.names
                        named |= own
                        self.hit("FAIL" if own else "CHECK", "author line in the supplementary material", w,
                                 line.strip(), v, seen=where)
                    break
        return named

    def git_file(self, where, text, part):
        for no, line in enumerate(text.splitlines(), 1):
            w = f"{where}:{no}"
            self.secrets(w, where, line)
            if not self.anon:
                continue
            ids = []
            if part == "config":
                m = re.match(r"\s*(name|email|url)\s*=\s*(.+)$", line)
                if m:
                    ids.append(f"{m.group(1)} = {m.group(2).strip()}")
            else:
                ids += [f"{n.strip()} <{e}>" for n, e in
                        re.findall(r"[0-9a-f]{40} [0-9a-f]{40} ([^<>\t\n]*?)\s*<([^>]*)>\s+\d{9,}\s+[+-]\d{4}", line)]
            for i in ids:
                self.hit("FAIL", "identity in a supplementary .git folder", w, i, i, seen=where,
                         hint="names, e-mails and remotes of the authors")

    def pdf(self, where, data):
        info = pdf_info_raw(data)
        author = info.get("Author", "")
        if author and fold(author).strip() not in GENERIC_PEOPLE and not re.search(r"https?://|www\.", author):
            self.hit("FAIL", "PDF Author metadata in the supplementary material", where, author, "Author", seen=where,
                     hint="rebuild with \\hypersetup{pdfauthor={}} or strip it (exiftool -all= / qpdf)")
        for k in ("Creator", "Title", "Subject", "Keywords"):
            v = info.get(k, "")
            if v and (self.named(v) or any(u.lower() not in GENERIC_USERS for u in HOME_RX.findall(v))):
                self.hit("FAIL", f"name in PDF {k} metadata in the supplementary material", where, v, k, seen=where)


def check_supplementary(paths, R, names, a):
    anon = a.blind == "double"
    tot = dict(files=0, text=0, bytes=0)
    for s in paths:
        p = pathlib.Path(s).expanduser().resolve()
        if not p.exists():
            R.skip(f"supplementary material not found: {s}")
            continue
        if not p.is_dir():
            import zipfile
            if not zipfile.is_zipfile(p):
                R.skip(f"supplementary material is neither a folder nor a .zip, not scanned: {s}")
                continue
        sc = SuppScan(R, names, anon, p.name)
        for rel, size, read in supp_entries(p):
            try:
                sc.file(rel, size, read)
            except (OSError, RuntimeError, ValueError, EOFError) as e:   # encrypted or broken member
                R.skip(f"supplementary file not read: {p.name}:{rel} ({type(e).__name__})")
        tot["files"] += sc.files
        tot["text"] += sc.text_files
        tot["bytes"] += sc.bytes
        R.add("INFO", "supplementary material size", p.name, quote=f"{sc.files} files, {sc.bytes / 2 ** 20:.1f} MB "
              f"uncompressed" + (f", {p.stat().st_size / 2 ** 20:.1f} MB archive" if p.is_file() else ""),
              key="supp-size" + p.name, hint="compare with the venue's upload limit")
    if paths and a.blind != "double":
        R.skip("supplementary anonymity: not checked (review model is not double-blind); secrets still checked")
    R.coverage["supp_files"] = tot["files"]
    R.coverage["supp_text_files"] = tot["text"]


# ====================================================================== main
# Heuristics whose precision on real papers (6 ICLR 2026 dev papers, 2026-11-07) was near zero, or that the agent does
# better by reading: dropped from --facts output. The agent is the detector; the facts block only gives what it cannot
# see or measure itself.
FACTS_DROP = (
    "same row and column in two tables", "numbers centred", "numbers left-aligned", "total column does not match",
    "average column does not match", "acronym", "float far from first mention", "probable misspelling",
    "name typed without its macro", "name written in different ways", "bold value is not the best",
    "underlined value is not the second best", "compound written in different ways", "garbled characters",
    "ablation full model differs", "placeholder", "float printed before its first mention", "underfull page",
    "heading at the bottom of a page", "float placement option ignored", "used as the subject of a sentence",
    "decimal places differ", "tables report the same systems", "not found in any table", "not found in the cited",
    "words unknown to the dictionaries", "margins of the best row", "removing a component", "row beats a bound",
    "space instead of ~", "coloured note macro (defined, unused)", "two swapped digits", "different units",
    "claim", "trend", "monotone", "speedup", "eval", "unit missing", "difference not reproducible",
)
FACTS_DEMOTE = {"page limit": "INFO", "Type 3 fonts": "INFO", "coloured note macro used in the text": "CHECK"}


def facts_only(R):
    for k in list(R.items):
        it = R.items[k]
        if any(d in it["kind"] for d in FACTS_DROP):
            del R.items[k]
        elif it["kind"] in FACTS_DEMOTE:
            it["sev"] = FACTS_DEMOTE[it["kind"]]
            if it["kind"] == "page limit":
                it["hint"] = ("the page where the body (everything before the references) ends; apply the venue's "
                              "rule and its exemptions (statements, appendix) by looking at what is on the extra pages")


def measure_coverage(src, comp, log_path, root_tex, R):
    """Counts of what the checks read (COVERAGE line): measured, never estimated; absent when not measurable."""
    cov = {}
    if comp.ok:
        cov["pages"] = sum(1 for p in comp.pages if p.strip())
        cov["words"] = sum(len(p.split()) for p in comp.pages)
    cov["source_files"] = len(src.files)
    cov["source_lines"] = len(src.lines)
    code = src.code()
    cov["labels"] = len(set(re.findall(r"\\label\s*\{([^}]+)\}", code)))
    cov["cross_references"] = len(re.findall(r"\\(?:ref|eqref|autoref|cref|Cref|pageref|nameref|vref)\*?\s*\{", code))
    cov["citations"] = len(re.findall(r"\\(?:[a-zA-Z]*cite[a-zA-Z]*|nocite)\*?\s*(?:\[[^\]]*\]\s*)*\{", code))
    aux = root_tex.with_suffix(".aux")
    if aux.is_file():
        keys = set()
        for m in re.finditer(r"\\citation\{([^}]+)\}|\\abx@aux@cite\{\d*\}\{([^}]+)\}", aux.read_text(errors="replace")):
            keys.update(k.strip() for k in (m.group(1) or m.group(2)).split(",") if k.strip() != "*")
        cov["cited_keys"] = len(keys)
    cov["figure_files"] = len(re.findall(r"\\includegraphics\*?\s*(?:\[[^\]]*\]\s*)?\{", code))
    cov["tables"] = len(re.findall(r"\\begin\{(?:tabular|tabularx|tabular\*|longtable|tblr)\}", code))
    if log_path.is_file():
        t = read_log(log_path)
        cov["log_warnings"] = len(re.findall(r"^(?:LaTeX|Package|Class|pdfTeX)\b[^\n]*?[Ww]arning", t, re.M))
        cov["log_bad_boxes"] = len(re.findall(r"^(?:Overfull|Underfull) \\[hv]box", t, re.M))
    cov.update(R.coverage)   # fonts, links: set by their checks
    R.coverage = cov


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tex")
    ap.add_argument("--authors", help="names.txt: one author name, affiliation, e-mail or handle per line")
    ap.add_argument("--pdf")
    ap.add_argument("--log")
    ap.add_argument("--blind", choices=("double", "single", "unknown"), default="unknown")
    ap.add_argument("--pages", type=int, help="page limit")
    ap.add_argument("--pages-include-refs", action="store_true", help="the limit counts the references too")
    ap.add_argument("--require", help="comma-separated section titles the call requires")
    ap.add_argument("--keywords-max", type=int)
    ap.add_argument("--abstract-max", type=int, help="abstract word limit")
    ap.add_argument("--linenumbers", action="store_true", help="the call requires line numbers")
    ap.add_argument("--paper", choices=("a4", "letter"), help="page size the call requires")
    ap.add_argument("--no-page-numbers", action="store_true", help="the call forbids page numbers")
    ap.add_argument("--offline", action="store_true", help="do not check the links printed in the paper")
    ap.add_argument("--no-widows", action="store_true", help="skip the widow/orphan diagnostic build")
    ap.add_argument("--engine", choices=("pdflatex", "xelatex", "lualatex"),
                    help="engine of the widow/orphan diagnostic build (default: %% !TEX program line, the log, "
                         "or the preamble: fontspec/unicode-math -> xelatex, luatexja/luacode -> lualatex)")
    ap.add_argument("--supp", action="append", default=[], metavar="PATH",
                    help="supplementary material or code (folder or .zip; repeatable): anonymity (double-blind), "
                         "credentials and secrets, macOS metadata, large files")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--facts", action="store_true",
                    help="print only deterministic facts for the agent (drops heuristic candidate lists)")
    a = ap.parse_args()

    root_tex = pathlib.Path(a.tex).resolve()
    if not root_tex.is_file():
        raise SystemExit(f"{a.tex} not found")
    names = []
    if a.authors:
        names = [l.strip() for l in open(a.authors, encoding="utf-8") if l.strip() and not l.startswith("#")]
    R = Report()
    src = Sources(root_tex)
    for u in src.unresolved:
        R.skip(f"include not resolved, not scanned: {u}")
    pdf = pathlib.Path(a.pdf).resolve() if a.pdf else root_tex.with_suffix(".pdf")
    comp = Compiled(pdf)
    if not comp.ok:
        R.skip(f"compiled-text checks: {pdf.name} not found (compile first)")
    log_path = pathlib.Path(a.log) if a.log else root_tex.with_suffix(".log")
    if log_path.is_dir():
        log_path = log_path / f"{root_tex.stem}.log"
    if a.blind == "unknown":
        R.skip("anonymity: review model unknown (pass --blind double|single from the venue profile)")
    if a.blind == "double" and not names:
        R.skip("author names: no --authors file")
    cls = " ".join(m.group(1) for _, _, c, _, _ in src.lines for m in re.finditer(r"\\documentclass\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", c))

    check_class(src, R, a)
    check_layout_hacks(src, R, cls)
    check_hidden(src, R)
    check_leftovers(src, comp, R, names)
    check_comments(src, R, names, a.blind)
    check_source_hygiene(src, R, log_path)
    check_local_support_files(src, R, names, a.blind)
    check_anonymity(src, comp, R, names, a)
    check_metadata_injection(comp, R)
    check_figures(src, R, names, a)
    check_pdf(comp, R, a)
    check_log(log_path, comp, R, a, src)
    if not a.no_widows:
        check_widows(src, root_tex, log_path, R, build_engine(src, root_tex, log_path, a.engine))
    check_floats(comp, R)
    check_page_ends(src, comp, R)
    check_table_captions(src, R)
    check_mojibake(src, comp, R)
    check_front(src, R, a)
    if comp.ok:
        check_injection_text(comp, src, R)
    check_typography(src, comp, R)
    check_citations_style(src, R)
    check_doubled_words(src, R)
    check_macro_names(src, R)
    check_typos_more(src, R)
    check_compound_variants(src, R)
    check_label_hygiene(src, R)
    check_leftover_text(comp, src, R)
    check_citation_usage(src, R)
    check_bbox(comp, R, a)
    check_pdf_tech(comp, R)
    check_links(comp, src, R, names, a)
    check_name_variants(comp, R, src)
    check_acronyms(src, R)
    check_tables(src, R)
    check_numbers(src, R)
    check_cross_tables(src, R)
    check_number_candidates(src, R)
    check_trends(src, R)
    check_table_alignment(src, R)
    check_table_arithmetic(src, R)
    check_bib(src, root_tex, R)
    if a.supp:
        check_supplementary(a.supp, R, names, a)

    measure_coverage(src, comp, log_path, root_tex, R)
    if a.facts:
        facts_only(R)
    if a.json:
        print(json.dumps(dict(findings=R.rows(), skipped=R.skipped, coverage=R.coverage), indent=1, ensure_ascii=False))
    else:
        print(R.text())


if __name__ == "__main__":
    main()
