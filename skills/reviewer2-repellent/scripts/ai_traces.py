#!/usr/bin/env python3
"""Gather the traces of AI use shown on the "Traces of AI use" front page of changes.pdf (step 6).

Usage: python3 ai_traces.py OUT_DIR [--root main.tex] [--json PATH]

OUT_DIR is the output folder of the run. Reads work/paper/ (the clean sources), work/facts.txt (step 2: form_check.py
and refs_check.py output under `## form_check` and `## refs_check`; `## form_check.py` is read too), report.md and
work/venue.md; writes work/ai-traces.json (or the path given with --json). Run it after the
report is final and before build_changes.py; rerun it when the report changes (--json: another output path).
Python stdlib only.

What it measures (never "who wrote the paper"; the evidence behind each check is summarised in references/ai-venue-actions.md):
  artifacts   objective defects whoever wrote them, from facts.txt: chatbot leftovers, visible Markdown, Unicode that
              prints wrongly or inconsistently, non-breaking or zero-width characters, hidden text and instructions to
              LLMs, LaTeX comments naming LLMs or prompts, references the checks could not verify; plus the LLM-use
              statement found in the sources and the venue's rule on it (venue.md). Each is linked to the report items
              that mention its location or key.
  style       perception-only densities, on the text from \\begin{document} outside math, verbatim, comments and
              tables: em dashes per 1,000 words, paragraphs with two or more 2024 excess words (delve, underscore,
              showcase, intricate, meticulous, pivotal, realm, commendable, garner, boast, groundbreaking, "a testament
              to", "aligns with"), participle tails (", highlighting ..."), bold run-in paragraphs (\\textbf, \\paragraph
              or a macro that wraps them, at the start of a paragraph), list items per page of the body, boxes
              (tcolorbox, mdframed, framed, \\fbox{\\parbox...}), tables with check marks; and the sections where they
              concentrate (a section of 300+ words at least twice the paper's own rate, with 3+ occurrences, on two or
              more signals). None of these is evidence of authorship and no calibrated baseline exists yet
              (references/ai-venue-actions.md, "Baselines").
  evidence    rule_strong is true when the sources show STRONG evidence of AI use in the writing, defined as: a
              chatbot leftover (FAIL in facts.txt); or a comment that names an LLM tool or holds a prompt; or visible
              Markdown together with two or more concentration sections. Style densities alone never count, and
              neither do Unicode, special spaces, unverified references or hidden prompts (defects to fix, not traces
              of writing).

work/ai-traces.json:
  {"version": 1, "root": "main.tex", "engine": "pdflatex",
   "paper": {"words": 15210, "paragraphs": 260, "body_pages": 32, "pages_from": "facts.txt"},
   "artifacts": [{"id": "chatbot" | "markdown" | "unicode" | "spaces" | "hidden" | "comments" | "references",
                  "label": "Chatbot leftovers", "status": "none" | "fail" | "check" | "not_checked",
                  "fail": 0, "check": 1, "count": 1,             lines of facts.txt; count = locations
                  "where": ["sections/intro.tex:12"], "examples": ["..."], "kinds": ["..."], "items": [12],
                  "note": "..."}],                                note: the agent's, optional, replaces the summary
   "style": [{"id": "em_dash", "label": "Em dashes", "count": 41, "value": 2.7, "unit": "per 1,000 words",
              "text": "41 (2.7 per 1,000 words; 30 spaced)", "examples": ["file:line"],
              "baseline": {"text": "...", "calibrated": false, "url": "..."} or null}],
   "clusters": [{"section": "2 Background and Related Work", "where": "sections/2-related.tex:1",
                 "signals": ["em_dash", "bold_runins"]}],
   "disclosure": {"statement": {"found": true, "where": "main.tex:86", "heading": "...", "text": "...",
                                "followed_by": "Acknowledgements", "before_references": false} ,
                  "venue_lines": "...", "venue_rule_found": "...", "venue_quote_found": "...", "venue_url": "...",
                  "items": [3],
                  "venue_rule": "...", "venue_quote": "...", "advice": "..."},     the agent's, optional
   "evidence": {"rule_strong": false, "reasons": ["..."], "strong": false, "why": ""},
   "assessment": "...",                                         the agent's, optional, at most 80 words
   "suggestion": {"text": "We used ...", "where": "..."}}      the agent's, ONLY when evidence.strong
Agent fields (kept when the script reruns): assessment, suggestion, artifacts[].note, disclosure.venue_rule /
venue_quote (verbatim in venue.md) / advice, and evidence.strong = false with evidence.why (the agent may lower the
rule's verdict with a reason, e.g. comments about the paper's own prompting experiments, never raise it).
front_pages.py checks these fields and renders the page; it never decides anything itself.
"""
import argparse
import json
import os
import pathlib
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import form_check as fc  # noqa: E402

ARTIFACTS = [
    ("chatbot", "Chatbot leftovers", ("chatbot leftover",)),
    ("markdown", "Visible Markdown", ("Markdown in the text",)),
    ("unicode", "Unicode that breaks typesetting", ("Unicode character in the text", "straight quotes in the text",
                                                    "mixed dash styles", "mixed quote styles")),
    ("spaces", "Non-breaking or zero-width spaces", ("invisible character in the text",
                                                     "non-breaking or special space character")),
    ("hidden", "Hidden text, instructions to LLMs", ("hidden text", "hidden-text macro used",
                                                     "near-white colour used on text", "possibly hidden text",
                                                     "instruction to LLM/reviewer")),
    ("comments", "Comments naming LLMs or prompts", ("comment mentions an LLM or a prompt",)),
    ("references", "References not verified", ("not found in the reference databases", "arXiv ID is malformed",
                                                "arXiv ID does not exist", "arXiv ID points to another paper",
                                                "DOI does not resolve", "DOI points to another work")),
]
EXCESS_RX = re.compile(r"\b(delv(?:e|es|ed|ing)|underscor(?:e|es|ed|ing)|showcas(?:e|es|ed|ing)|intricate|intricacies|"
                       r"meticulous(?:ly)?|pivotal|realms?|commendabl[ey]|garner(?:s|ed|ing)?|boast(?:s|ed|ing)?|"
                       r"groundbreaking|testament to|aligns? with)\b", re.I)
TAIL_RX = re.compile(r",\s+(highlighting|underscoring|emphasi[sz]ing|showcasing|reflecting|demonstrating|illustrating|"
                     r"signall?ing|cementing|solidifying|reinforcing|fostering|paving the way)\b", re.I)
CHECKMARK_RX = re.compile(r"[\u2713\u2714\u2717\u2718]|\\(?:cmark|xmark|checkmark|ding\{5[1256]\}|faCheck|faTimes|"
                          r"tick|cross)(?![A-Za-z])")
BOX_ENVS = {"tcolorbox", "mdframed", "framed", "shaded", "snugshade", "leftbar", "oframed"}
HEAD_RX = re.compile(r"\\(section|chapter)(\*?)\s*(?:\[[^\]]*\])?\s*\{((?:[^{}]|\{[^{}]*\})*)\}")
BREAK_RX = re.compile(r"^\s*(\\(?:sub)*section|\\chapter|\\paragraph|\\begin\{(?:figure|table|itemize|enumerate|"
                      r"description|abstract)|\\end\{(?:figure|table|itemize|enumerate|description|abstract)|\\item\b|"
                      r"\\caption|\\appendix|\\maketitle)")
DISC_HEAD_RX = re.compile(r"generative ai|ai[- ]assisted|\bllms?\b|large language model|language model|use of ai|"
                          r"\bai (use|usage|tools?|declaration|disclosure|statement)|chatgpt", re.I)
DISC_TEXT_RX = re.compile(r"during the preparation of this (work|manuscript|paper)|we used (chatgpt|gpt|claude|gemini|"
                          r"copilot|deepseek|an? (llm|large language model|ai))|\b(llm|ai) (usage|use) statement", re.I)
VENUE_AI_RX = re.compile(r"generative ai|ai[- ]assisted|\bllms?\b|large language model|\bai tools?\b|use of ai|"
                         r"\bai use\b|chatgpt|ai declaration|ai-generated", re.I)
AGENT_DISC = ("venue_rule", "venue_quote", "advice")


# ---------------------------------------------------------------- facts.txt
def facts_heading(name):
    """The script a facts.txt heading names: `## form_check`, `## form_check.py`, `## scripts/form_check.py` and
    `## form_check.out` all give form_check."""
    name = os.path.basename(name.strip("`*:"))
    return re.sub(r"\.(py|out)$", "", name)


def parse_facts(path):
    """{section: [{'sev', 'kind', 'where': [..], 'more': n, 'quote', 'hint', 'raw'}]}"""
    out, cur = {}, None
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh.read().split("\n"):
            h = re.match(r"^##\s+(\S+)", ln)
            if h:
                cur = out.setdefault(facts_heading(h.group(1)), [])
                continue
            if cur is None or not re.match(r"^(FAIL|CHECK|INFO|SKIPPED) \| ", ln):
                continue
            parts = ln.split(" | ")
            sev, kind = parts[0], parts[1] if len(parts) > 1 else ""
            rest = " | ".join(parts[2:])
            q = re.search(r'(?:^|\| )"(.*)"(?: \| (.*))?$', rest)
            quote, hint = (q.group(1), q.group(2) or "") if q else ("", "")
            head = rest[:q.start()] if q else rest
            where, more = [], 0
            for p in [x for x in head.split(" | ") if x.strip()]:
                if p.startswith("p.") or p.startswith('"'):
                    continue
                m = re.search(r"\(\+(\d+)\)\s*$", p)
                if m:
                    more = int(m.group(1))
                    p = p[:m.start()]
                where += [w.strip() for w in p.split(", ") if w.strip()]
                break
            if not q and len(parts) > 3:
                hint = parts[-1]
            cur.append(dict(sev=sev, kind=kind, where=where, more=more, quote=quote, hint=hint, raw=ln))
    return out


# ---------------------------------------------------------------- report.md
def report_items(path):
    """{n: text of item n} for the numbered items of report.md (not summary, questions or dropped)."""
    items, cur, sec = {}, None, ""
    if not os.path.isfile(path):
        return items
    item_re = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?(\d+)\.(?:\*\*)?\s")
    with open(path, encoding="utf-8") as fh:
        for ln in fh.read().split("\n"):
            h = re.match(r"^##\s+(\d+)\.\s+(.*?)\s*$", ln)
            if h:
                sec, cur = h.group(2).lower(), None
                continue
            if not sec or sec.startswith(("summary", "question", "dropped")):
                continue
            m = item_re.match(ln)
            if m:
                cur = int(m.group(1))
                items[cur] = ln
            elif cur is not None:
                items[cur] += "\n" + ln
    return items


def items_for(items, where=(), keys=(), rx=None):
    """Report items that mention one of the locations (file:line, also within a range file:a-b), keys or rx."""
    found = []
    locs = []
    for w in where:
        m = re.match(r"(.+?):(\d+)$", w)
        if m:
            locs.append((m.group(1), int(m.group(2))))
    for n, text in sorted(items.items()):
        hit = False
        for m in re.finditer(r"([\w./-]+\.(?:tex|bib)):(\d+)(?:\s*[–-]\s*(\d+))?", text):
            f, a = m.group(1), int(m.group(2))
            b = int(m.group(3)) if m.group(3) else a
            if any((f == lf or f.endswith("/" + lf) or lf.endswith("/" + f)) and a <= ln <= b for lf, ln in locs):
                hit = True
        for k in keys:
            if k and re.search(r"(?<![\w-])" + re.escape(k) + r"(?![\w-])", text):
                hit = True
        if rx is not None and rx.search(text):
            hit = True
        if hit:
            found.append(n)
    return found[:8]


# ---------------------------------------------------------------- sources
def find_root(paper, given):
    if given:
        return given
    roots = []
    for fn in sorted(os.listdir(paper)):
        if fn.endswith(".tex"):
            with open(os.path.join(paper, fn), encoding="utf-8", errors="replace") as fh:
                t = fh.read()
            if re.search(r"^[^%\n]*\\documentclass", t, re.M) and re.search(r"^[^%\n]*\\begin\{document\}", t, re.M):
                roots.append(fn)
    if len(roots) != 1:
        raise SystemExit("cannot tell the root file in %s (%s): give --root" % (paper, ", ".join(roots) or "none"))
    return roots[0]


def simple_macros(code):
    """\\newcommand{\\x}{Text} without arguments -> plain text (to print section titles written with macros)."""
    out = {}
    for m in re.finditer(r"\\(?:re)?newcommand\*?\s*\{?\\([A-Za-z]+)\}?\s*\{((?:[^{}]|\{[^{}]*\})*)\}", code):
        out[m.group(1)] = " ".join(fc.strip_tex(m.group(2)).split())
    for m in re.finditer(r"\\def\\([A-Za-z]+)\s*\{((?:[^{}]|\{[^{}]*\})*)\}", code):
        out.setdefault(m.group(1), " ".join(fc.strip_tex(m.group(2)).split()))
    return out


def plain(s, macros):
    s = re.sub(r"\\([A-Za-z]+)\b\s*(\{\})?", lambda m: " %s " % macros[m.group(1)] if m.group(1) in macros
               else m.group(0), s)
    return " ".join(fc.strip_tex(s).split())


def words_of(s):
    return re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", fc.strip_tex(s))


def measure(root_tex, body_pages=None):
    src = fc.Sources(pathlib.Path(root_tex).resolve())
    code = src.code()
    macros = simple_macros(code)
    body = fc.source_body(src)                         # masked: no math, verbatim, comments, non-prose arguments
    joined = "\n".join(c for _, _, c in body)
    prose = fc.mask_tables(joined)
    plines = prose.split("\n")
    raw_body = {}
    for f, no, c, _, _ in src.lines:
        raw_body[(f, no)] = c

    # bold run-in macros defined by the paper (\newcommand{\myparagraph}[1]{\textbf{#1}} ...)
    run_macros = [m.group(1) for m in re.finditer(   # note macros (coloured) are not run-in headings
        r"\\(?:re)?newcommand\*?\s*\{?\\([A-Za-z]+)\}?\s*(?:\[\d\])?\s*\{(?![^\n]*\\(?:textcolor|color)\b)"
        r"[^\n]*?\\(?:textbf|bfseries|paragraph)", code)]
    runin_rx = re.compile(r"^\s*(?:\\noindent\s*)?(?:\\textbf\s*\{|\{\s*\\bf(?:series)?\b|\\paragraph\*?\s*[\[{]" +
                          "".join(r"|\\%s(?![A-Za-z])" % re.escape(m) for m in run_macros) + ")")

    # paragraphs and sections
    paragraphs, cur = [], None
    sections, sec = [], None
    appendix, numbered, letter = False, 0, 0

    def close():
        nonlocal cur
        if cur and len(cur["words"]) >= 20:
            paragraphs.append(cur)
        cur = None

    for i, (f, no, _) in enumerate(body):
        line = plines[i]
        if re.search(r"\\appendix(?![A-Za-z])", line):
            appendix = True
        h = HEAD_RX.search(line)
        if h and h.group(1) in ("section", "chapter"):
            close()
            star = h.group(2) == "*"
            if not star:
                if appendix:
                    letter += 1
                    num = chr(64 + letter)
                else:
                    numbered += 1
                    num = str(numbered)
            else:
                num = ""
            sec = dict(title=(num + " " + plain(h.group(3), macros)).strip(), where="%s:%d" % (f, no),
                       words=0, em=0, excess=0, tails=0, runins=0, paras=0, items=0)
            sections.append(sec)
            if not (line[:h.start()] + line[h.end():]).strip():
                continue
        if not line.strip():
            close()
            continue
        if BREAK_RX.match(line):
            close()
        if cur is None:
            cur = dict(where="%s:%d" % (f, no), start=line, words=[], text="", sec=sec)
        cur["text"] += " " + line
        cur["words"] += words_of(line)
        if sec is not None:
            sec["words"] += len(words_of(line))
            sec["em"] += len(re.findall(r"(?<!-)---(?!-)|\u2014", line))
            sec["items"] += len(re.findall(r"\\item(?![A-Za-z])", line))
    close()

    words = sum(len(p["words"]) for p in paragraphs) or 1
    allwords = len(words_of(prose)) or 1
    em_all = re.findall(r"(?<!-)---(?!-)|\u2014", prose)
    em_spaced = len(re.findall(r"\s(?:---|\u2014)\s", prose))
    em_where = ["%s:%d" % (f, no) for i, (f, no, _) in enumerate(body) if re.search(r"(?<!-)---(?!-)|\u2014", plines[i])]

    clusters_p, excess_hits, tails, tail_ex, runins = [], 0, 0, [], []
    for p in paragraphs:
        text = " ".join(fc.strip_tex(p["text"]).split())
        hits = [m.group(0).lower() for m in EXCESS_RX.finditer(text)]
        excess_hits += len(hits)
        t = TAIL_RX.findall(text)
        tails += len(t)
        if t and len(tail_ex) < 3:
            tail_ex.append("%s (%s)" % (p["where"], t[0].lower()))
        isrun = bool(runin_rx.match(p["start"]))
        if isrun:
            runins.append(p["where"])
        if p["sec"] is not None:
            p["sec"]["excess"] += len(hits)
            p["sec"]["tails"] += len(t)
            p["sec"]["runins"] += isrun
            p["sec"]["paras"] += 1
        if len(hits) >= 2:
            clusters_p.append("%s (%s)" % (p["where"], ", ".join(dict.fromkeys(hits))))

    # list items, boxes, checkmark tables (on the unmasked body code: environments are what we count)
    body_code = [(f, no, raw_body.get((f, no), "")) for f, no, _ in body]
    items = [("%s:%d" % (f, no)) for f, no, c in body_code for _ in re.findall(r"\\item(?![A-Za-z])", c)]
    bold_items = sum(len(re.findall(r"\\item\s*(?:\[[^\]]*\]|\\textbf)", c)) for _, _, c in body_code)
    envs = set(BOX_ENVS)
    for rx in (r"\\newtcolorbox\s*(?:\[[^\]]*\])?\s*\{(\w+)\}", r"\\newtcbtheorem\s*(?:\[[^\]]*\])?\s*\{(\w+)\}",
               r"\\newmdenv\s*(?:\[[^\]]*\])?\s*\{(\w+)\}", r"\\surroundwithmdframed\s*(?:\[[^\]]*\])?\s*\{(\w+)\}",
               r"\\newenvironment\s*\{(\w+)\}(?:\[\d\])?\s*\{[^\n]{0,200}(?:tcolorbox|mdframed|framed|fbox|colorbox)"):
        envs.update(re.findall(rx, code))
    box_rx = re.compile(r"\\begin\{(%s)\*?\}|\\(?:fbox|colorbox\s*\{[^}]*\}|fcolorbox\s*\{[^}]*\}\s*\{[^}]*\})\s*\{\s*"
                        r"(?:\\parbox|\\begin\{minipage\})" % "|".join(sorted(map(re.escape, envs))))
    boxes = ["%s:%d" % (f, no) for f, no, c in body_code for _ in box_rx.findall(c)]
    tables, depth, start, mark = [], 0, None, False
    for f, no, c in body_code:
        for m in re.finditer(r"\\(begin|end)\{(tabular[x*]?|tabulary|longtable|tblr|NiceTabular)\}", c):
            if m.group(1) == "begin":
                depth += 1
                if depth == 1:
                    start, mark = "%s:%d" % (f, no), False
            elif depth:
                depth -= 1
                if depth == 0 and (mark or CHECKMARK_RX.search(c[:m.start()])):
                    tables.append(start)
                    mark = False
        if depth and CHECKMARK_RX.search(c):
            mark = True

    pages = body_pages or max(1, round(allwords / 600))
    return dict(src=src, words=allwords, paragraphs=len(paragraphs), body_pages=pages, sections=sections,
                em=len(em_all), em_spaced=em_spaced, em_where=em_where, excess_hits=excess_hits,
                clusters_p=clusters_p, tails=tails, tail_ex=tail_ex, runins=runins, items=items,
                bold_items=bold_items, boxes=boxes, tables=tables)


def concentration(m):
    """Sections at least twice the paper's own rate (3+ occurrences, 300+ words) on two or more signals."""
    W = m["words"] or 1
    paper = {"em_dash": m["em"] / W, "excess_words": m["excess_hits"] / W, "participle_tails": m["tails"] / W,
             "bold_runins": len(m["runins"]) / max(m["paragraphs"], 1), "items": len(m["items"]) / W}
    out = []
    for s in m["sections"]:
        if s["words"] < 300:
            continue
        val = {"em_dash": (s["em"], s["em"] / s["words"]), "excess_words": (s["excess"], s["excess"] / s["words"]),
               "participle_tails": (s["tails"], s["tails"] / s["words"]),
               "bold_runins": (s["runins"], s["runins"] / max(s["paras"], 1)),
               "items": (s["items"], s["items"] / s["words"])}
        sig = [k for k, (n, r) in val.items() if n >= 3 and paper[k] > 0 and r >= 2 * paper[k]]
        if len(sig) >= 2:
            out.append(dict(section=s["title"] or "(untitled section)", where=s["where"], signals=sig))
    return out


# ---------------------------------------------------------------- disclosure
def find_statement(src, macros):
    rows = [(f, no, c) for f, no, c, _, _ in src.lines]
    k = next((i for i, r in enumerate(rows) if re.search(r"\\begin\{document\}", r[2])), 0)
    rows = rows[k:]
    start = None
    for i, (f, no, c) in enumerate(rows):
        h = re.search(r"\\(?:section|subsection|subsubsection|paragraph|chapter)\*?\s*\{((?:[^{}]|\{[^{}]*\})*)\}", c)
        if h and DISC_HEAD_RX.search(plain(h.group(1), macros)):
            start, heading = i, plain(h.group(1), macros)
            break
        if DISC_TEXT_RX.search(c):
            start, heading = i, ""
            break
    if start is None:
        return {"found": False}
    f, no, c = rows[start]
    text, j = [], start
    first = re.sub(r"^.*?\\(?:section|subsection|subsubsection|paragraph|chapter)\*?\s*\{(?:[^{}]|\{[^{}]*\})*\}", "",
                   c) if heading else c
    if first.strip():
        text.append(first)
    for j in range(start + 1, len(rows)):
        cc = rows[j][2]
        if re.search(r"\\(?:section|subsection|chapter|paragraph)\*?\s*\{|\\bibliography(?:style)?\{|\\printbibliography|"
                     r"\\begin\{thebibliography\}|\\end\{document\}|\\appendix|\\printcredits", cc):
            break
        if not cc.strip() and any(t.strip() for t in text) and not heading:
            break
        text.append(cc)
    followed = ""
    for f2, no2, cc in rows[j:]:
        m = re.search(r"\\(?:section|chapter)\*?\s*\{((?:[^{}]|\{[^{}]*\})*)\}", cc)
        if re.search(r"\\bibliography\{|\\printbibliography|\\begin\{thebibliography\}", cc):
            followed = "References"
            break
        if m:
            followed = plain(m.group(1), macros)
            break
        if re.search(r"\\appendix|\\end\{document\}", cc):
            followed = "Appendix" if "appendix" in cc else "end of the document"
            break
    body = " ".join(plain(" ".join(text), macros).split())
    return {"found": True, "where": "%s:%d" % (f, no), "heading": heading, "text": body[:700],
            "followed_by": followed, "before_references": followed == "References"}


def venue_rule(venue_text):
    lines = venue_text.split("\n")
    sec, hit = "", None
    for i, ln in enumerate(lines):
        h = re.match(r"^#+\s+(.*)", ln)
        if h:
            sec = h.group(1).lower()
            continue
        if "source" in sec or re.match(r"^\s*-\s*\[[A-Za-z]+\]\s*=", ln) or ln.startswith("FLAGS:") or i == 0:
            continue
        if VENUE_AI_RX.search(ln):
            hit = i
            break
    if hit is None:
        return {}
    ind = len(lines[hit]) - len(lines[hit].lstrip())
    block = [lines[hit]]
    for ln in lines[hit + 1:hit + 9]:
        if ln.strip() and len(ln) - len(ln.lstrip()) > ind:
            block.append(ln)
        else:
            break
    text = "\n".join(block)
    first = re.sub(r"^\s*[-*]\s*", "", lines[hit]).strip()
    first = re.sub(r"\*\*|`", "", first)
    q = [x for x in re.findall(r"\"([^\"]{20,})\"", text)]
    url = ""
    m = re.search(r"https?://[^\s)>\]]+", text)
    if m:
        url = m.group(0).rstrip(".,;")
    else:
        for tag in re.findall(r"\[([A-Za-z]+)\]", text):
            d = re.search(r"\[%s\]\s*[=:][^\n]*?(https?://[^\s)>\]]+)" % re.escape(tag), venue_text)
            if d:
                url = d.group(1).rstrip(".,;")
                break
    return {"venue_lines": text[:1500], "venue_rule_found": first[:300], "venue_quote_found": q[0] if q else "",
            "venue_url": url}


# ---------------------------------------------------------------- main
def baselines():
    path = os.path.join(os.path.dirname(HERE), "references", "ai-venue-actions.md")
    out, sec = {}, ""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for ln in fh.read().split("\n"):
                h = re.match(r"^##\s+(.*)", ln)
                if h:
                    sec = h.group(1).lower()
                    continue
                if sec.startswith("baseline") and ln.startswith("- ") and ln.count(" | ") >= 3:
                    sid, text, cal, url = [x.strip() for x in ln[2:].split(" | ", 3)]
                    out[sid] = {"text": text, "calibrated": cal.lower().endswith("yes"), "url": url}
    return out


def build(out_dir, root=None, old=None):
    out_dir = os.path.abspath(out_dir)
    work = os.path.join(out_dir, "work")
    paper = os.path.join(work, "paper")
    if not os.path.isdir(paper):
        raise SystemExit("no work/paper in %s" % out_dir)
    root = find_root(paper, root)
    facts = parse_facts(os.path.join(work, "facts.txt"))
    items = report_items(os.path.join(out_dir, "report.md"))
    venue_text = ""
    if os.path.isfile(os.path.join(work, "venue.md")):
        with open(os.path.join(work, "venue.md"), encoding="utf-8") as fh:
            venue_text = fh.read()
    fcl = facts.get("form_check", [])
    rcl = facts.get("refs_check", [])
    body_pages, pages_from = None, "estimate (600 words per page)"
    for r in fcl:
        m = re.search(r"references start on page (\d+)", r["quote"])
        if r["kind"] == "length" and m:
            body_pages, pages_from = max(int(m.group(1)) - 1, 1), "facts.txt (body before the references)"
    m = measure(os.path.join(paper, root), body_pages)
    hygiene = next((r for r in fcl if r["kind"] == "source hygiene checks"), None)
    engine = re.search(r"engine (\S+);", hygiene["quote"]).group(1) if hygiene else ""
    compiled_skip = any(r["sev"] == "SKIPPED" and "compiled-text" in r["raw"] for r in fcl)

    arts = []
    oldnotes = {a.get("id"): a.get("note") for a in (old or {}).get("artifacts", []) if a.get("note")}
    for aid, label, kinds in ARTIFACTS:
        pool = rcl if aid == "references" else fcl
        rows = [r for r in pool if r["sev"] in ("FAIL", "CHECK", "INFO") and any(k in r["kind"] for k in kinds)]
        if aid == "references":
            checked = any(r["kind"] == "references checked" for r in rcl)
        elif aid in ("chatbot", "hidden"):
            checked = bool(fcl) and not (aid == "chatbot" and compiled_skip)
        else:
            checked = hygiene is not None
        where, keys = [], []
        count = 0
        for r in rows:
            where += r["where"]
            count += len(r["where"]) + r["more"] if r["where"] else 1
            if aid == "references":
                keys += r["where"]
        nf = sum(1 for r in rows if r["sev"] == "FAIL")
        nc = len(rows) - nf
        status = "not_checked" if not checked else ("fail" if nf else "check" if rows else "none")
        a = dict(id=aid, label=label, status=status, fail=nf, check=nc, count=count,
                 where=list(dict.fromkeys(where))[:8], examples=[r["quote"][:120] for r in rows[:2]],
                 kinds=sorted({r["kind"] for r in rows}), hints=[r["hint"][:160] for r in rows[:3]],
                 items=items_for(items, where, keys if aid == "references" else ()) if rows else [])
        if aid in oldnotes:
            a["note"] = oldnotes[aid]
        arts.append(a)

    base = baselines()
    W = m["words"] or 1
    P = m["paragraphs"] or 1

    def row(sid, label, count, value, unit, text, examples):
        return dict(id=sid, label=label, count=count, value=round(value, 2), unit=unit, text=text,
                    examples=examples[:3], baseline=base.get(sid))

    style = [
        row("em_dash", "Em dashes", m["em"], 1000 * m["em"] / W, "per 1,000 words",
            "%d (%.1f per 1,000 words; %d spaced)" % (m["em"], 1000 * m["em"] / W, m["em_spaced"]), m["em_where"]),
        row("excess_words", "Excess-word clusters", len(m["clusters_p"]), len(m["clusters_p"]) / P,
            "paragraphs with 2+ of the 2024 excess words",
            "%d of %d paragraphs (%d excess words in all)" % (len(m["clusters_p"]), P, m["excess_hits"]),
            m["clusters_p"]),
        row("participle_tails", "Participle tails", m["tails"], 1000 * m["tails"] / W, "per 1,000 words",
            "%d (%.2f per 1,000 words)" % (m["tails"], 1000 * m["tails"] / W), m["tail_ex"]),
        row("bold_runins", "Bold run-in paragraphs", len(m["runins"]), len(m["runins"]) / P, "share of paragraphs",
            "%d of %d paragraphs (%.0f%%)" % (len(m["runins"]), P, 100 * len(m["runins"]) / P), m["runins"]),
        row("items", "List items", len(m["items"]), len(m["items"]) / m["body_pages"], "per page of the body",
            "%d (%.1f per page over %d body pages; %d open in bold)" % (
                len(m["items"]), len(m["items"]) / m["body_pages"], m["body_pages"], m["bold_items"]), m["items"]),
        row("boxes", "Takeaway boxes", len(m["boxes"]), len(m["boxes"]), "boxes", "%d" % len(m["boxes"]), m["boxes"]),
        row("checkmark_tables", "Check-mark tables", len(m["tables"]), len(m["tables"]), "tables",
            "%d" % len(m["tables"]), m["tables"]),
    ]
    clusters = concentration(m)

    st = find_statement(m["src"], simple_macros(m["src"].code()))
    disc = dict(statement=st, **venue_rule(venue_text))
    disc["items"] = items_for(items, [st["where"]] if st.get("found") else [], (),
                              re.compile(r"AI declaration|generative AI|AI[- ]assisted|\bLLM|large language model|"
                                         r"AI use|AI usage|use of AI", re.I))
    for k in AGENT_DISC:
        v = ((old or {}).get("disclosure") or {}).get(k)
        if v:
            disc[k] = v

    by = {a["id"]: a for a in arts}
    reasons = []
    if by["chatbot"]["fail"]:
        reasons.append("chatbot leftover in the text")
    named = [r for r in fcl if r["kind"] == "comment mentions an LLM or a prompt"
             and re.search(r"names an LLM tool|mentions a prompt", r["hint"])]
    if named:
        reasons.append("%d comment(s) naming an LLM tool or holding a prompt" % len(named))
    if by["markdown"]["fail"] and len(clusters) >= 2:
        reasons.append("visible Markdown together with %d concentration sections" % len(clusters))
    ev = {"rule_strong": bool(reasons), "reasons": reasons, "strong": bool(reasons), "why": ""}
    oev = (old or {}).get("evidence") or {}
    if reasons and oev.get("strong") is False and oev.get("why"):
        ev["strong"], ev["why"] = False, oev["why"]

    res = {"version": 1, "root": root, "engine": engine,
           "paper": {"words": m["words"], "paragraphs": m["paragraphs"], "body_pages": m["body_pages"],
                     "pages_from": pages_from},
           "artifacts": arts, "style": style, "clusters": clusters, "disclosure": disc, "evidence": ev,
           "facts": bool(fcl), "refs": bool(rcl)}
    for k in ("assessment", "suggestion"):
        if (old or {}).get(k):
            res[k] = old[k]
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out")
    ap.add_argument("--root", default=None)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    path = a.json or os.path.join(os.path.abspath(a.out), "work", "ai-traces.json")
    old = None
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            try:
                old = json.load(fh)
            except ValueError:
                old = None
    res = build(a.out, a.root, old)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    if not res["facts"]:
        print("warning: no form_check section in work/facts.txt: artifacts marked not checked")
    print("written: %s" % path)
    for x in res["artifacts"]:
        print("  %-11s %-12s %s" % (x["id"], x["status"], ", ".join(x["where"][:3])))
    for s in res["style"]:
        print("  %-17s %s" % (s["id"], s["text"]))
    print("  clusters: %s" % ("; ".join("%s (%s)" % (c["section"], ", ".join(c["signals"])) for c in res["clusters"])
                              or "none"))
    st = res["disclosure"]["statement"]
    print("  statement: %s" % (("%s, followed by %s" % (st["where"], st["followed_by"] or "?")) if st["found"]
                               else "none found"))
    print("  strong evidence (rule): %s %s" % (res["evidence"]["rule_strong"], "; ".join(res["evidence"]["reasons"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
