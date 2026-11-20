#!/usr/bin/env python3
"""Collect what every check of a run looked at and found into work/checks.json (the "What we checked" page).

Usage: python3 check_stats.py OUT_DIR [--out PATH]

OUT_DIR is the output folder of the run. Run it after the report is final (step 6, with ai_traces.py) and before
build_changes.py, which renders page 2 of changes.pdf from the file (front_pages.py). Python stdlib only.

Every number comes from a file of the run or from the sources, never from a guess:
  scripts   the final "COVERAGE | key=value | ..." line of form_check.py, refs_check.py and bib_style.py, read from
            the script's section of work/facts.txt, else from work/<script>.out; their FAIL and CHECK lines (from
            facts.txt, else the .out file) are the findings of each check row
  agents    the "## Coverage" block (one "key: N" line per key) at the end of work/reader.md, work/numbers.md,
            work/candidates.md, work/typos.md and report.md (or work/merged.md); keys in references/*.md
  scope     scope_stats.py on work/paper/ (and the PDF in work/build/): what the paper puts in front of each
            checker (numbers in the text and table cells, comparative statements, sentences, paragraphs, tables,
            figures, equations, .bib entries). A checker reads its whole scope by design, so without a Coverage
            block its row and statistic show the scope, labelled "in scope"; pattern counts are labelled
            "estimate" and carry their method (references/pdf-layout.md)
  outputs   what can be counted in the checkers' files themselves: flag lines of candidates.md, certain/likely
            lines of typos.md, numbered items of reader.md and numbers.md, items of report.md ("counted from
            outputs")
  others    work/venue-status.json (rules judged), work/ai-traces.json (artifacts), report.md (items)
A count that no file gives is left out: no statistic has an empty value, and no text says "not counted". A check
whose input is missing is "not_checked" with the reason.

Report items are tied to check rows in two ways: a script finding links to the items that mention its location or
key (as in ai_traces.py); an agent row takes the items of its report section (2 desk-reject -> venue, 3 numbers,
5 and 7 language) and, for sections 4 and 6, the first matching rule of ITEM_RULES on the item's first 200
characters (and its "Checkers:" list).

work/checks.json:
  {"version": 2,
   "stats": [{"id": "pages", "label": "pages read", "value": 41, "text": "36,819 words of PDF text; every checker",
              "basis": "measured" | "in scope" | "estimate" | "counted from outputs", "source": "form_check.py",
              "rank": 1, "method": "how an in-scope or estimated count is made"}],       sorted by rank
   "scope": {"numbers_text": 890, ...},                      scope_stats.py
   "methods": {"claims": "...", ...},                         scope_stats.METHOD
   "categories": [{"id": "venue", "label": "Venue rules",
                   "checks": [{"id": "venue_rules", "what": "Rules of the call ...", "by": "venue agent + you",
                               "amount": "26 rules judged: ...", "basis": "measured" | "in scope" | ...,
                               "status": "ok" | "problems" | "flagged" | "not_checked",
                               "problems": 3, "flags": 0, "items": [1, 2, 3], "reason": ""}]}],
   "checkers": {"reader": {"file": "work/reader.md", "present": true, "block": {...} | null,
                           "derived": {"problems_reported": 81}}, ...},
   "notes": ["..."]}
status: ok = nothing found (with flags: the flags went to the next stage, as for the typos finder); problems =
report items (items, problems = their number); flagged = the script flagged something (flags) and no report item
links to it; not_checked = no output for it (reason; amount empty). Every other row has a non-empty amount. Amount
texts are plain text with Markdown `code`.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ai_traces import facts_heading, find_root, parse_facts  # noqa: E402
import scope_stats  # noqa: E402

SCRIPTS = ("form_check", "refs_check", "bib_style")
AGENT_KEYS = {
    "reader": ("pages_viewed", "figures_viewed", "tables_checked", "crossrefs_checked", "bib_entries_looked_up",
               "venue_rules_checked"),
    "numbers": ("numbers_checked", "derived_values_recomputed", "claims_traced", "tables_checked",
                "table_cells_checked"),
    "finder": ("chunks_read", "sentences_read", "flags", "chunk_lines_max"),
    "verifier": ("flags_judged", "kept_certain", "kept_likely", "dropped"),
    "merge": ("items_in", "duplicates_merged", "quotes_checked", "quotes_not_found", "items_out"),
}

# rules for items of report sections 4 and 6 (first match wins), on the first 200 characters of the item
ITEM_RULES = [
    ("leftovers", re.compile(r"leftover|comment lines|TODO|placeholder|Markdown|hidden text|PDF metadata", re.I)),
    ("bib", re.compile(r"references\.bib|\.bib\b|\bbib\b|DBLP|bibliograph|reference entr|persistent identifier|"
                       r"citation keys?|journal is written|appears in \w+ forms|venues are written|"
                       r"\bentries\b|\bfields?\b|article numbers", re.I)),
    ("build", re.compile(r"overfull|underfull|float|footer|\bfonts?\b|margin|hbox|layout|printed after|Page \d+ of",
                         re.I)),
    ("numbers", re.compile(r"\\times|×|\d\s*\\?%|\d+(?:\.\d+)?\s*QPS|(?<!version )\d\.\d+\$?\s*(?:vs\.?|but)\s*\$?\d",
                           re.I)),
    ("figures", re.compile(r"\bFig(?:ure)?s?\b|\bFig\.|\bTables?\b|caption|panel|legend|marker|y-label|x-label|"
                           r"\bbold\b|column label", re.I)),
    ("refs", re.compile(r"\\(?:ref|cite)|cross-?ref|citation|\bSection~", re.I)),
]

# script finding kinds -> check rows (category, id, what, kind regex); first match wins
FACT_ROWS = [
    ("venue", "venue_form", "Page limit, page size, line numbers, required sections, length limits",
     r"page limit|page size|line numbers|required section|abstract too long|too many keywords|page numbers printed|"
     r"camera-ready|acmart without anonymous"),
    ("venue", "anonymity", "Anonymity: names, e-mails, acknowledgements, links, PDF metadata",
     r"author name|e-mail in the text|identifying repository|home path|ownership|acknowledgements in|"
     r"grant number|author metadata|PDF Author|pdfusetitle|linked page names|anonymous repository|"
     r"name/e-mail in a local"),
    ("build", "log", "LaTeX log: errors, missing files and glyphs, bad boxes",
     r"LaTeX error|overfull|underfull|file not found|missing glyph|float too large|float lost|rerun"),
    ("build", "floats", "Float placement and floats never referenced",
     r"float"),
    ("build", "layout", "Layout: text outside the text block, layout hacks, widows, page ends",
     r"outside the text block|layout hack|negative vertical|widow|heading at the bottom|font size|"
     r"small text|table caption below|absolute placement|unnumbered section"),
    ("build", "fonts", "Fonts embedded, Type 3 fonts, PDF encryption",
     r"fonts not embedded|Type 3 fonts$|PDF is encrypted"),
    ("refs", "labels", "Labels and \\ref: undefined, defined twice, misplaced",
     r"undefined reference|label defined twice|\\label before|\\ref to a label|reference to the section"),
    ("refs", "citations", "Citations: undefined, BibTeX errors and warnings",
     r"undefined citation|bibtex|\\cite"),
    ("refs", "links", "Links printed in the paper (HTTP status)", r"broken link|link not reachable"),
    ("bib", "bib_tex", ".bib hygiene: repeated keys, missing fields, escapes, lost capitals",
     r"bib key|bib entry|without journal|without booktitle|arXiv entry with|same title under|capitals lost|"
     r"in doi|does not comment out"),
    ("figures", "figure_files", "Figure files: present, names or text inside, metadata",
     r"figure|empty cells"),
    ("language", "doubled", "Doubled words, stray punctuation, raw LaTeX in the PDF",
     r"doubled word|punctuation|raw LaTeX|garbled|misspelling"),
    ("leftovers", "notes", "TODOs, notes packages, highlighted or coloured notes",
     r"TODO|notes package|highlighted|coloured note|leftover text|placeholder"),
    ("leftovers", "hidden", "Hidden text, instructions to LLMs or reviewers",
     r"hidden|near-white|instruction|chatbot leftover"),
    ("leftovers", "hygiene", "Markdown, wrong Unicode, invisible characters, LLM comments",
     r"Markdown|Unicode|straight quotes|invisible character|"
     r"special space|mixed dash|mixed quote|comment mentions an LLM"),
    ("leftovers", "comments", "Comments that name people or carry notes", r"comment"),
]

INFO_FLAGS = r"^Type 3 fonts"   # INFO kinds of form_check.py shown as flags (orange) on the "What we checked" page


# internals that the front pages must not show (pdf-layout.md: plain statements): tool names, work/ paths
PLAIN = [(re.compile(r"this PDF is read only through a pdftocairo copy, whose word heights are not reliable", re.I),
          "the PDF's text layer gives no reliable word heights"),
         (re.compile(r"\bpdftocairo copy\b", re.I), "a re-rendered copy of the PDF"),
         (re.compile(r"\bno work/[\w./-]+"), "its output is missing"),
         (re.compile(r"\bwork/[\w./-]+"), "the run's files"),
         (re.compile(r"\bno output for it in facts\.txt"), "no output for it in this run"),
         (re.compile(r"\bfacts\.txt\b"), "the measurements of this run")]


def plain_reason(text):
    for rx, rep_ in PLAIN:
        text = rx.sub(rep_, text or "")
    return text


def refs_summary(rows):
    """{not_found, differs} from the refs_check findings (None when refs_check did not run)."""
    if not rows:
        return {"not_found": None, "differs": 0}
    nf = {k for r in rows if "not found" in r["kind"] for k in r["where"]}
    df = {k for r in rows if "differs" in r["kind"] for k in r["where"]}
    return {"not_found": len(nf), "differs": len(df)}


CATEGORIES = [
    ("venue", "Venue rules"), ("build", "Build and layout"), ("refs", "References and citations"),
    ("bib", "Bibliography metadata and style"), ("numbers", "Numbers and claims"), ("figures", "Figures and tables"),
    ("language", "Language (typos and grammar)"), ("notation", "Notation, terms and wording"),
    ("leftovers", "Leftovers and source hygiene"), ("ai", "AI-use artifacts"),
]


def fmt(n):
    return "{:,}".format(n) if isinstance(n, int) else "?"


PLURALS = {"entries": "entry", "boxes": "box"}


def qty(n, phrase):
    """'1 table', '2 tables': the first plural noun of the phrase agrees with n."""
    if n != 1:
        return "%s %s" % (fmt(n), phrase)
    words = phrase.split(" ")
    for i, w in enumerate(words):
        if w in PLURALS:
            words[i] = PLURALS[w]
            break
        if re.fullmatch(r"[a-zA-Z-]+[^s]s", w) and w not in ("this", "has", "was", "its", "is"):
            words[i] = w[:-1]
            break
    return "1 " + " ".join(words)


def join(*parts):
    """The parts that are known, joined with "; " (a part that is None is left out, never shown as unknown)."""
    return "; ".join(p for p in parts if p)


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


# ---------------------------------------------------------------- inputs
def coverage_of(text):
    """{key: int} from the last COVERAGE line of a script's output, or None."""
    if not text:
        return None
    lines = [ln for ln in text.split("\n") if ln.startswith("COVERAGE | ")]
    if not lines:
        return None
    out = {}
    for part in lines[-1].split(" | ")[1:]:
        k, _, v = part.partition("=")
        if re.fullmatch(r"\d+", v.strip()):
            out[k.strip()] = int(v)
    return out


def facts_sections(path):
    """{script: raw text of its section} of facts.txt."""
    text = read(path) or ""
    out, cur = {}, None
    for ln in text.split("\n"):
        h = re.match(r"^##\s+(\S+)", ln)
        if h:
            cur = facts_heading(h.group(1))
            out[cur] = []
            continue
        if cur:
            out[cur].append(ln)
    return {k: "\n".join(v) for k, v in out.items()}


def block_of(text, keys):
    """{key: int | None} from a '## Coverage' block, or None when the text has no block."""
    if not text:
        return None
    m = None
    for m in re.finditer(r"^#+\s*Coverage\s*$", text, re.M | re.I):
        pass
    if m is None:
        return None
    out = {}
    for ln in text[m.end():].split("\n"):
        mm = re.match(r"^\s*[-*]?\s*`?([a-z_]+)`?\s*[:=]\s*(.+?)\s*$", ln)
        if mm and mm.group(1) in keys:
            v = mm.group(2).replace(",", "")
            out[mm.group(1)] = int(v) if re.fullmatch(r"\d+", v) else None
        elif ln.startswith("#"):
            break
    return out


def report_items(path):
    """[(n, section title, text)] of report.md, and the item numbers of section 'Dropped'."""
    text = read(path) or ""
    items, sec, dropped = [], "", 0
    item_re = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?(\d+)\.(?:\*\*)?\s")
    for ln in text.split("\n"):
        h = re.match(r"^##\s+(\d+)\.\s+(.*?)\s*$", ln)
        if h:
            sec = h.group(2)
            continue
        if re.match(r"^##\s", ln):
            sec = ""
            continue
        low = sec.lower()
        if not sec or low.startswith(("summary", "question")):
            continue
        m = item_re.match(ln)
        if low.startswith("dropped"):
            dropped += bool(m)
            continue
        if m:
            items.append([int(m.group(1)), sec, ln])
        elif items and items[-1][1] == sec:
            items[-1][2] += "\n" + ln
    return [tuple(x) for x in items], dropped


def numbered(text):
    """Problems in a checker report: numbered items ('1. ', '**1.**', '### 1')."""
    if not text:
        return None
    return len(re.findall(r"^(?:\*\*)?\d+\.(?:\*\*)?\s|^#{2,4}\s+\d+[.)]?\s", text, re.M))


def checkers_of(text):
    m = re.search(r"Checkers?:\s*([^.\n]*)", text)
    if m:
        return set(re.findall(r"[a-z]+", m.group(1).lower()))
    m = re.search(r"\(((?:reader|numbers|typos|facts)(?:,\s*(?:reader|numbers|typos|facts))*)\)", text)
    return set(re.findall(r"[a-z]+", m.group(1))) if m else set()


def category_of(sec, text):
    s = sec.lower()
    if s.startswith("desk"):
        return "venue"
    if s.startswith("numbers"):
        return "numbers"
    if s.startswith(("typos", "appendix")) or "language" in s:
        return "language"
    head = text[:200]
    for cat, rx in ITEM_RULES:
        if cat == "numbers" and "numbers" in checkers_of(text):
            return "numbers"
        if rx.search(head):
            return cat
    return "notation"


def items_for(items, where=(), keys=()):
    """Report items that mention one of the locations (file:line, also in a range) or keys (no cap)."""
    locs = []
    for w in where:
        m = re.match(r"(.+?):(\d+)$", w)
        if m:
            locs.append((m.group(1), int(m.group(2))))
    found = []
    for n, _, text in items:
        hit = False
        for m in re.finditer(r"([\w./-]+\.(?:tex|bib)):(\d+)(?:\s*[–-]\s*(\d+))?", text):
            f, a = m.group(1), int(m.group(2))
            b = int(m.group(3)) if m.group(3) else a
            if any((f == lf or f.endswith("/" + lf) or lf.endswith("/" + f)) and a <= ln <= b for lf, ln in locs):
                hit = True
        for k in keys:
            if k and re.search(r"(?<![\w-])" + re.escape(k) + r"(?![\w-])", text):
                hit = True
        if hit:
            found.append(n)
    return found


# ---------------------------------------------------------------- build
def build(out_dir):
    out_dir = os.path.abspath(out_dir)
    work = os.path.join(out_dir, "work")
    notes = []
    sections = facts_sections(os.path.join(work, "facts.txt"))
    parsed = parse_facts(os.path.join(work, "facts.txt"))
    cov, findings, ran = {}, {}, {}
    for s in SCRIPTS:
        out_text = read(os.path.join(work, s + ".out"))
        sec_text = sections.get(s)
        cov[s] = coverage_of(sec_text) or coverage_of(out_text)
        if s in parsed:
            findings[s] = parsed[s]
        elif out_text is not None:
            tmp = os.path.join(work, "tmp")
            os.makedirs(tmp, exist_ok=True)
            p = os.path.join(tmp, "checks-%s.txt" % s)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("## %s\n%s\n" % (s, out_text))
            findings[s] = parse_facts(p).get(s, [])
        ran[s] = s in findings
        if ran[s] and cov[s] is None:
            notes.append("%s: no COVERAGE line (output older than the line): its counts are left out" % s)
    report_p = os.path.join(out_dir, "report.md")
    items, dropped = report_items(report_p)
    item_cat = {n: category_of(sec, text) for n, sec, text in items}
    sec_no = {}
    for ln in (read(report_p) or "").split("\n"):
        h = re.match(r"^##\s+(\d+)\.\s+(.*?)\s*$", ln)
        if h:
            for n, sec, _ in items:
                if sec == h.group(2):
                    sec_no[n] = int(h.group(1))

    # agent reports
    files = {"reader": "work/reader.md", "numbers": "work/numbers.md", "finder": "work/candidates.md",
             "verifier": "work/typos.md", "merge": "report.md"}
    if not os.path.isfile(os.path.join(out_dir, "report.md")) and os.path.isfile(os.path.join(work, "merged.md")):
        files["merge"] = "work/merged.md"
    checkers = {}
    texts = {}
    for k, rel in files.items():
        t = read(os.path.join(out_dir, rel))
        if k == "merge":
            m = read(os.path.join(work, "merged.md"))
            if m and block_of(m, AGENT_KEYS[k]) is not None and block_of(t, AGENT_KEYS[k]) is None:
                t, rel = m, "work/merged.md"
        texts[k] = t
        checkers[k] = {"file": rel, "present": t is not None, "block": block_of(t, AGENT_KEYS[k]), "derived": {}}
    cand = texts["finder"] or ""
    cand_body = re.split(r"^#+\s*Coverage\s*$", cand, flags=re.M | re.I)[0]
    flag_lines = len(re.findall(r"^[^\s|][^|\n]*:\d+\s*\|", cand_body, re.M)) if texts["finder"] is not None else None
    typ = texts["verifier"] or ""
    typ_body = re.split(r"^#+\s*Coverage\s*$", typ, flags=re.M | re.I)[0]
    kept_c = len(re.findall(r"\|\s*certain\s*$", typ_body, re.M)) if texts["verifier"] is not None else None
    kept_l = len(re.findall(r"\|\s*likely\s*$", typ_body, re.M)) if texts["verifier"] is not None else None
    checkers["finder"]["derived"] = {"flags": flag_lines} if flag_lines is not None else {}
    if kept_c is not None:
        checkers["verifier"]["derived"] = {"flags_given": flag_lines, "kept_certain": kept_c, "kept_likely": kept_l}
    for k in ("reader", "numbers"):
        n = numbered(texts[k])
        if n is not None:
            checkers[k]["derived"] = {"problems_reported": n}
    if items:
        checkers["merge"]["derived"] = {"items_out": len(items), "quotes_not_found": dropped}
    for k, c in checkers.items():
        if c["present"] and c["block"] is None:
            notes.append("%s (%s): no Coverage block; counts derived from the file where possible" % (k, c["file"]))

    def agent(k, key):
        """(value, basis) of an agent's count: its block, else a value counted from its outputs."""
        c = checkers[k]
        if c["block"] is not None and c["block"].get(key) is not None:
            return c["block"][key], "measured"
        d = c["derived"].get(key)
        if d is not None:
            return d, "counted from outputs"
        return None, ""

    # ------------------------------------------------ scope: what the paper puts in front of the checkers
    scope = {}
    paper = os.path.join(work, "paper")
    if os.path.isdir(paper):
        try:
            root = find_root(paper, None)
            stem = os.path.splitext(root)[0]
            pdf = next((p for p in (os.path.join(work, "build", stem + ".pdf"),
                                    os.path.join(work, "tmp", "build-original", stem + ".pdf"))
                        if os.path.isfile(p)), None)
            scope = scope_stats.measure(os.path.join(paper, root), pdf)
        except (SystemExit, OSError, ValueError) as ex:
            notes.append("scope_stats.py: %s" % ex)
    else:
        notes.append("no work/paper: no counts of the paper's numbers, sentences, tables")

    # ------------------------------------------------ stats (headline)
    stats = []

    def stat(sid, label, value, text, basis, source, rank=99, method=""):
        """A statistic exists only with a value: an unknown count is left out, never shown as unknown."""
        if value is None:
            return
        stats.append(dict(id=sid, label=label, value=value, text=text, basis=basis, source=source, rank=rank,
                          method=method))

    fc, rc, bs = cov["form_check"] or {}, cov["refs_check"] or {}, cov["bib_style"] or {}
    sc = scope
    pages = fc.get("pages", sc.get("pages"))
    stat("pages", "pages of the original PDF read", pages,
         join(("%s words of PDF text" % fmt(fc["words"])) if fc.get("words") is not None else None,
              "read by every checker"), "measured", "form_check.py" if fc.get("pages") is not None else "scope_stats.py", 1)
    nt, ncells = sc.get("numbers_text"), sc.get("table_cells")
    n_in = (nt or 0) + (ncells or 0) if nt is not None or ncells is not None else None
    nck, _ = agent("numbers", "numbers_checked")
    rec, _ = agent("numbers", "derived_values_recomputed")
    if nck is not None and checkers["numbers"]["block"] is not None:
        stat("numbers", "numbers checked", nck,
             join(("of %s in the text and tables" % fmt(n_in)) if n_in is not None else None,
                  ("%s values recomputed" % fmt(rec)) if rec is not None else None),
             "measured", files["numbers"], 2)
    else:
        stat("numbers", "numbers in the text and tables", n_in,
             join(("%s in the text" % fmt(nt)) if nt is not None else None,
                  ("%s in table cells" % fmt(ncells)) if ncells is not None else None,
                  "in scope of the numbers checker"),
             "in scope", "scope_stats.py", 2, scope_stats.METHOD["numbers_text"] + "; " +
             scope_stats.METHOD["table_cells"])
    ct, _ = agent("numbers", "claims_traced")
    if ct is not None and checkers["numbers"]["block"] is not None:
        stat("claims", "claims traced", ct, join(("of %s comparative statements*" % fmt(sc["claims"]))
                                                 if sc.get("claims") is not None else None, "numbers checker"),
             "measured", files["numbers"], 3, scope_stats.METHOD["claims"])
    else:
        stat("claims", "comparative or quantified statements*", sc.get("claims"),
             "found by pattern; in scope of the numbers checker", "estimate", "scope_stats.py", 3,
             scope_stats.METHOD["claims"])
    sr, _ = agent("finder", "sentences_read")
    j, bj = agent("verifier", "flags_judged")
    if j is None and flag_lines is not None:
        j, bj = flag_lines, "counted from outputs"
    kc, _ = agent("verifier", "kept_certain")
    kl, _ = agent("verifier", "kept_likely")
    flags_txt = None
    if j is not None:
        flags_txt = "%s flagged%s" % (fmt(j), (", %s kept" % fmt((kc or 0) + (kl or 0))) if kc is not None else "")
    if sr is not None and checkers["finder"]["block"] is not None:
        stat("sentences", "sentences read by the proofreader", sr,
             join(("of %s in the paper" % fmt(sc["sentences"])) if sc.get("sentences") is not None else None,
                  flags_txt), "measured", files["finder"], 4)
    else:
        stat("sentences", "sentences in scope of the proofreader", sc.get("sentences"),
             join(("in %s paragraphs" % fmt(sc["paragraphs"])) if sc.get("paragraphs") is not None else None,
                  flags_txt), "in scope", "scope_stats.py", 4,
             scope_stats.METHOD["sentences"])
    nref = rc.get("refchecker_checked", rc.get("references"))
    rinfo = refs_summary(findings.get("refs_check", []))
    stat("refs", "references checked against databases", nref,
         join(("of %s cited" % fmt(rc["references"])) if rc.get("references") is not None else None,
              ("%s not found" % fmt(rinfo["not_found"])) if rinfo["not_found"] is not None else None,
              ("%s differ from the record" % fmt(rinfo["differs"])) if rinfo["differs"] else None,
              ("DOIs %s of %s resolved" % (fmt(rc["dois_looked_up"]), fmt(rc["dois"])))
              if rc.get("dois") and rc.get("dois_looked_up") is not None else None,
              ("arXiv IDs %s of %s looked up" % (fmt(rc["arxiv_looked_up"]), fmt(rc["arxiv_ids"])))
              if rc.get("arxiv_ids") and rc.get("arxiv_looked_up") is not None else None),
         "measured", "refs_check.py", 5)
    if fc.get("cross_references") is not None or fc.get("citations") is not None:
        stat("crossrefs", "cross-references and citations",
             (fc.get("cross_references") or 0) + (fc.get("citations") or 0),
             join(("%s cross-references" % fmt(fc["cross_references"]))
                  if fc.get("cross_references") is not None else None,
                  ("%s citations of %s keys" % (fmt(fc["citations"]), fmt(fc["cited_keys"])))
                  if fc.get("citations") is not None and fc.get("cited_keys") is not None else
                  (("%s citations" % fmt(fc["citations"])) if fc.get("citations") is not None else None)),
             "measured", "form_check.py", 6)
    if sc.get("tables") is not None:
        stat("objects", "tables and figures", sc["tables"] + sc.get("figures", 0),
             join("%s, %s" % (qty(sc["tables"], "table floats"), qty(sc.get("figures", 0), "figures")),
                  qty(sc["tabulars"], "tabular environments") if sc.get("tabulars") else None,
                  qty(sc["equations"], "display equations") if sc.get("equations") else None,
                  "in scope of the reader"), "in scope", "scope_stats.py", 7)
    vs = None
    try:
        with open(os.path.join(work, "venue-status.json"), encoding="utf-8") as fh:
            vs = json.load(fh)
    except (OSError, ValueError):
        pass
    rules = (vs or {}).get("rules") or []
    if vs is not None:
        cnt = {s: sum(1 for r in rules if r.get("status") == s) for s in ("violated", "confirm", "unknown", "met")}
        stat("venue", "venue rules judged", len(rules),
             join(*["%d %s" % (cnt[s], w) for s, w in (("violated", "violated"), ("confirm", "to confirm"),
                                                       ("unknown", "cannot tell"), ("met", "met")) if cnt[s]]),
             "measured", "work/venue-status.json", 8)
    if sc.get("cited_numbers") is not None:
        stat("cited", "numbers cited from tables and figures*", sc["cited_numbers"],
             "in sentences that refer to a table or figure", "estimate", "scope_stats.py", 9,
             scope_stats.METHOD["cited_numbers"])
    stat("flags", "candidate typos judged", j, join(("%s certain" % fmt(kc)) if kc is not None else None,
                                                    ("%s likely" % fmt(kl)) if kl is not None else None,
                                                    "verifier"), bj, files["verifier"], 10)
    ec = bs.get("entries_compared")
    stat("bib_style", ".bib entries compared for style", ec,
         join(("of %s in the .bib" % fmt(sc["bib_entries"])) if sc.get("bib_entries") is not None else None,
              ("%s features" % fmt(bs["features"])) if bs.get("features") is not None else None),
         "measured", "bib_style.py", 11)
    if ec is None and sc.get("bib_entries") is not None:
        stat("bib_entries", ".bib entries", sc["bib_entries"], "in scope: reader, refs_check", "in scope",
             "scope_stats.py", 11)
    v, b = agent("reader", "bib_entries_looked_up")
    stat("reader_bib", "bibliography entries looked up by the reader", v, "reader", b, files["reader"], 12)
    stat("links", "links tested", fc.get("links_tested"),
         ("of %s in the paper" % fmt(fc["links_found"])) if fc.get("links_found") is not None else "",
         "measured", "form_check.py", 13)
    stat("sources", "source lines scanned", fc.get("source_lines", sc.get("source_lines")),
         qty(fc.get("source_files", sc.get("source_files")), "files")
         if fc.get("source_files", sc.get("source_files")) is not None else "the sources", "measured",
         "form_check.py" if fc.get("source_lines") is not None else "scope_stats.py", 14)
    stat("warnings", "LaTeX warnings and bad boxes reviewed",
         (fc["log_warnings"] + fc.get("log_bad_boxes", 0)) if fc.get("log_warnings") is not None else None,
         join("%s warnings" % fmt(fc.get("log_warnings")),
              ("%s bad boxes" % fmt(fc["log_bad_boxes"])) if fc.get("log_bad_boxes") is not None else None),
         "measured", "form_check.py", 15)
    stat("fonts", "fonts embedded", fc.get("fonts_embedded"),
         ("of %s" % fmt(fc["fonts"])) if fc.get("fonts") is not None else "", "measured", "form_check.py", 16)
    nag = sum(1 for k in ("reader", "numbers", "verifier") if checkers[k]["present"])
    nsc = sum(1 for s in SCRIPTS if ran[s])
    dm, _ = agent("merge", "duplicates_merged")
    stat("checkers", "independent checkers", nag + nsc if nag + nsc else None,
         join("%d agents + %d scripts" % (nag, nsc), ("%s duplicates merged" % fmt(dm)) if dm is not None else None),
         "measured", "work/", 17)
    v, b = agent("reader", "pages_viewed")
    f2, _ = agent("reader", "figures_viewed")
    stat("viewed", "pages looked at by the reader", v, qty(f2, "figures") if f2 is not None else "reader",
         b, files["reader"], 18)
    stats.sort(key=lambda s: s["rank"])

    # ------------------------------------------------ check rows
    cats = {c: [] for c, _ in CATEGORIES}

    def row(cat, rid, what, by, amount, basis, status, problems=0, flags=0, its=(), reason=""):
        cats[cat].append(dict(id=rid, what=what, by=by, amount=amount, basis=basis, status=status,
                              problems=problems, flags=flags, items=sorted(set(its)), reason=plain_reason(reason)))

    def n_of(v, what):
        return qty(v, what) if v is not None else None

    sl = fc.get("source_lines", sc.get("source_lines"))
    sf = fc.get("source_files", sc.get("source_files"))
    words = n_of(fc.get("words"), "words of PDF text")
    pg = n_of(pages, "pages")

    # venue rules
    if vs is not None:
        cnt = {s: sum(1 for r in rules if r.get("status") == s) for s in ("met", "violated", "confirm", "unknown")}
        its = [i for r in rules for i in r.get("items") or []]
        its += [n for n, sec, _ in items if sec.lower().startswith("desk")]
        bad = cnt["violated"] + cnt["confirm"]
        row("venue", "venue_rules", "Rules of the call and the guide for authors, one by one",
            "venue agent", "%d rules: %d met, %d violated, %d to confirm, %d cannot tell" % (
                len(rules), cnt["met"], cnt["violated"], cnt["confirm"], cnt["unknown"]), "measured",
            "problems" if its else ("flagged" if bad else "ok"), flags=0 if its else bad,
            problems=len(set(its)), its=its)
    else:
        row("venue", "venue_rules", "Rules of the call and the guide for authors", "venue agent", "", "",
            "not_checked", reason="no work/venue-status.json")

    # script findings
    fact_rows = {rid: [] for _, rid, _, _ in FACT_ROWS}
    other = []
    for r in findings.get("form_check", []):
        if r["sev"] not in ("FAIL", "CHECK"):
            continue
        for _, rid, _, rx in FACT_ROWS:
            if re.search(rx, r["kind"], re.I):
                fact_rows[rid].append(r)
                break
        else:
            other.append(r)
    for r in findings.get("form_check", []):   # INFO findings that a publisher may reject: flags of their row
        if r["sev"] == "INFO" and re.search(INFO_FLAGS, r["kind"], re.I):
            fact_rows["fonts"].append(r)
    skipped = [r["raw"] for r in findings.get("form_check", []) if r["sev"] == "SKIPPED"]
    lines = n_of(sl, "source lines")
    amounts = {
        "log": join(n_of(fc.get("log_warnings"), "warnings"), n_of(fc.get("log_bad_boxes"), "bad boxes")),
        "fonts": join(n_of(fc.get("fonts"), "fonts"), n_of(fc.get("fonts_embedded"), "embedded")),
        "labels": join(n_of(fc.get("labels"), "labels"), n_of(fc.get("cross_references"), "cross-references")),
        "citations": join(n_of(fc.get("citations"), "citations"), n_of(fc.get("cited_keys"), "keys")),
        "links": ("%s of %s links tested" % (fmt(fc["links_tested"]), fmt(fc["links_found"])))
        if fc.get("links_tested") is not None and fc.get("links_found") is not None else None,
        "figure_files": n_of(fc.get("figure_files"), "figure files"),
        "layout": pg, "floats": join(pg, n_of(sc.get("tables", None) is not None and
                                              sc["tables"] + sc.get("figures", 0) or None, "floats")),
        "hidden": join(lines, words), "hygiene": lines, "notes": lines, "doubled": join(lines, words),
        "comments": n_of(sf, "source files"), "anonymity": join(pg, "metadata, comments"), "venue_form": pg,
        "bib_tex": join(n_of(fc.get("cited_keys"), "cited keys"), n_of(sc.get("bib_entries"), ".bib entries")),
    }
    for cat, rid, what, _ in FACT_ROWS:
        rs = fact_rows[rid]
        amount = amounts.get(rid) or {"log": "the LaTeX log", "fonts": "the PDF", "links": "the PDF",
                                       "comments": "the source comments"}.get(rid, "the whole paper")
        if rid == "links" and fc.get("links_tested") is None and ran["form_check"]:
            row(cat, rid, what, "form_check", "", "", "not_checked",
                reason="no link test in this run (offline or older output)")
            continue
        if not ran["form_check"]:
            row(cat, rid, what, "form_check", "", "", "not_checked", reason="no form_check output (facts.txt)")
            continue
        sk = [s for s in skipped if rid == "layout" and "font-size" in s]
        where = [w for r in rs for w in r["where"]]
        its = items_for(items, where) if rs else []
        if rs and not its and any(r["sev"] != "INFO" for r in rs):
            # findings without a location: the items of the category that the facts raised
            its = [n for n, _, text in items if item_cat[n] == cat and "facts" in checkers_of(text)]
        st = "problems" if its else ("flagged" if rs else "ok")
        reason = ("partly skipped: " + sk[0].split(" | ", 1)[1]) if sk else ""
        row(cat, rid, what, "form_check", amount, "measured", st, problems=len(its), flags=len(rs), its=its,
            reason=reason)
    if other:
        where = [w for r in other for w in r["where"]]
        its = items_for(items, where)
        row("build", "other_facts", "Other measured findings (%s)" % ", ".join(sorted({r["kind"] for r in other})[:4]),
            "form_check", "%d findings" % len(other), "measured", "problems" if its else "flagged",
            problems=len(its), flags=len(other), its=its)

    # references against the databases
    rrows = [r for r in findings.get("refs_check", []) if r["sev"] in ("FAIL", "CHECK")]
    if ran["refs_check"]:
        keys = [w for r in rrows for w in r["where"]]
        its = items_for([x for x in items if item_cat[x[0]] == "bib"], (), keys) if rrows else []
        rsk = [r["raw"].split(" | ", 1)[1] for r in findings["refs_check"] if r["sev"] == "SKIPPED"]
        amount = join(n_of(rc.get("references"), "references"),
                      ("%s of %s DOIs" % (fmt(rc["dois_looked_up"]), fmt(rc["dois"])))
                      if rc.get("dois") is not None and rc.get("dois_looked_up") is not None else None,
                      ("%s of %s arXiv IDs looked up" % (fmt(rc["arxiv_looked_up"]), fmt(rc["arxiv_ids"])))
                      if rc.get("arxiv_ids") is not None and rc.get("arxiv_looked_up") is not None else None)
        row("bib", "refs_db", "Each cited entry against DBLP, Crossref, OpenAlex, its DOI and arXiv record",
            "refs_check", amount or n_of(fc.get("cited_keys"), "cited keys") or "every cited entry",
            "measured" if rc else "in scope", "problems" if its else ("flagged" if rrows else "ok"),
            problems=len(its), flags=len(rrows), its=its, reason=("partly: " + rsk[0]) if rsk else "")
    else:
        row("bib", "refs_db", "Every cited entry against the reference databases", "refs_check", "", "",
            "not_checked", reason="no refs_check output")
    bib_items = [n for n in item_cat if item_cat[n] == "bib"]
    v, b = agent("reader", "bib_entries_looked_up")
    rd = [n for n in bib_items if "reader" in checkers_of(dict((i, t) for i, _, t in items)[n])]
    if v is None:
        v, b = fc.get("cited_keys", sc.get("bib_entries")), "in scope"
    row("bib", "reader_bib", "Each cited entry against its DBLP or publisher record", "reader",
        (("%s entries looked up" if b != "in scope" else "%s cited entries (in scope)") % fmt(v))
        if v is not None else "every cited entry", b if v is not None else "in scope",
        "problems" if rd else ("ok" if checkers["reader"]["present"] else "not_checked"), problems=len(rd), its=rd,
        reason="" if checkers["reader"]["present"] else "no work/reader.md")
    brows = [r for r in findings.get("bib_style", []) if r["sev"] == "CHECK"]
    if ran["bib_style"]:
        st_items = [n for n in bib_items if re.search(r"written|forms?\b|inconsisten|style|field set|"
                                                       r"abbreviated", dict((i, t) for i, _, t in items)[n], re.I)]
        row("bib", "bib_style", "Uniform .bib style: fields, venue and author names, pages, months", "bib_style",
            join(n_of(bs.get("entries_compared"), "entries"), n_of(bs.get("features"), "features compared"))
            or n_of(sc.get("bib_entries"), ".bib entries") or "the whole .bib", "measured" if bs else "in scope",
            "problems" if st_items else ("flagged" if brows else "ok"), problems=len(st_items), flags=len(brows),
            its=st_items)
    else:
        row("bib", "bib_style", "Style uniformity of the .bib", "bib_style", "", "", "not_checked",
            reason="no bib_style output")

    # agent rows: the checker's Coverage block when it has one, else what the paper puts in its scope
    def by_cat(c):
        return [n for n in item_cat if item_cat[n] == c]

    def agent_amount(k, keys, scope_parts):
        got = []
        for key in keys:
            v, b = agent(k, key)
            if v is not None and b == "measured":
                got.append(qty(v, key.replace("_", " ")))
        if got:
            return "; ".join(got), "measured"
        sp = join(*scope_parts)
        return ((sp + " (in scope)") if sp else "the whole paper"), "in scope"

    def agent_row(cat, rid, what, k, keys, scope_parts, its, by):
        amount, basis = agent_amount(k, keys, scope_parts)
        if not checkers[k]["present"]:
            if its:   # the report has items for it: they count, the checker's file is missing
                row(cat, rid, what, by, amount, basis, "problems", problems=len(its), its=its,
                    reason="no %s; items from report.md" % checkers[k]["file"])
            else:
                row(cat, rid, what, by, "", "", "not_checked", reason="no %s" % checkers[k]["file"])
            return
        row(cat, rid, what, by, amount, basis, "problems" if its else "ok", problems=len(its), its=its)

    agent_row("numbers", "numbers_agent", "Numbers against tables and figures, derived values, bold marks, "
              "over- and understatements, claims across abstract, intro, conclusions", "numbers",
              ("numbers_checked", "derived_values_recomputed", "claims_traced", "tables_checked",
               "table_cells_checked"),
              (n_of(sc.get("numbers_text"), "numbers in the text"), n_of(sc.get("table_cells"), "table cells"),
               n_of(sc.get("claims"), "comparative statements*")), by_cat("numbers"), "numbers, reader")
    agent_row("figures", "figures_agent", "Figures and tables: legibility, captions, legends, marks", "reader",
              ("figures_viewed", "tables_checked", "pages_viewed"),
              (n_of(sc.get("figures"), "figures"), n_of(sc.get("tables"), "tables")), by_cat("figures"), "reader")
    agent_row("refs", "crossrefs_agent", "References and citations point at the right object", "reader",
              ("crossrefs_checked",), (n_of(fc.get("cross_references"), "cross-references"),
                                       n_of(fc.get("citations"), "citations")), by_cat("refs"), "reader")
    agent_row("build", "layout_agent", "Pages looked at for layout defects", "reader", ("pages_viewed",),
              (pg,), by_cat("build"), "reader")
    agent_row("notation", "notation_agent", "Notation, symbols, undefined terms and acronyms", "reader", (),
              (n_of(sc.get("sentences"), "sentences"), n_of(sc.get("equations"), "display equations")),
              by_cat("notation"), "reader")
    agent_row("leftovers", "leftovers_agent", "Leftovers and source notes found by reading", "reader", (),
              (n_of(sc.get("paragraphs"), "paragraphs"), pg), by_cat("leftovers"), "reader")
    # language: two-stage proofreader
    lang = by_cat("language")
    if checkers["finder"]["present"]:
        amount, basis = agent_amount("finder", ("chunks_read", "sentences_read", "flags"),
                                     (n_of(sc.get("sentences"), "sentences"),
                                      n_of(sc.get("paragraphs"), "paragraphs")))
        if flag_lines is not None and basis != "measured":
            amount += "; %s flags" % fmt(flag_lines)
        row("language", "finder", "Proofreader 1: every sentence, eight families of slips", "finder", amount, basis,
            "passed" if flag_lines else "ok", flags=flag_lines or 0)
    else:
        row("language", "finder", "Proofreader 1: every sentence", "finder", "", "", "not_checked",
            reason="no work/candidates.md")
    if checkers["verifier"]["present"]:
        parts = []
        for key in ("flags_judged", "kept_certain", "kept_likely", "dropped"):
            v, _ = agent("verifier", key)
            if key == "flags_judged" and v is None and flag_lines is not None:
                v = flag_lines
            if key == "dropped" and v is None and flag_lines is not None and kept_c is not None and \
                    checkers["verifier"]["block"] is None:
                v = flag_lines - kept_c - kept_l
            name = key.replace("_", " ")
            if key == "flags_judged" and checkers["verifier"]["block"] is None:
                name = "flags given"
            if v is not None:
                parts.append(qty(v, name))
        kept = None
        kc2, _ = agent("verifier", "kept_certain")
        kl2, _ = agent("verifier", "kept_likely")
        if kc2 is not None and kl2 is not None:
            kept = kc2 + kl2
        why = ""
        if lang and kept is not None and len(lang) > kept:
            why = ("%s in report sections %s: %s from this proofreader, %s from the other checkers" % (
                qty(len(lang), "items"), " and ".join(sorted({str(sec_no.get(n, "?")) for n in lang})),
                fmt(kept), fmt(len(lang) - kept)))
        elif lang and kept is not None and len(lang) < kept:
            why = "%s from %s confirmed flags (some flags share an item)" % (qty(len(lang), "items"), fmt(kept))
        row("language", "verifier", "Proofreader 2: each flag judged in context",
            "verifier", "; ".join(parts) or "every flag of proofreader 1",
            "measured" if checkers["verifier"]["block"] else "counted from outputs",
            "problems" if lang else "ok", problems=len(lang), its=lang, reason=why)
    else:
        row("language", "verifier", "Proofreader 2: each flag judged in context", "verifier",
            "items of report.md" if lang else "", "", "problems" if lang else "not_checked", problems=len(lang),
            its=lang, reason="no work/typos.md" + ("; items from report.md" if lang else ""))

    # AI-use artifacts
    ai = None
    try:
        with open(os.path.join(work, "ai-traces.json"), encoding="utf-8") as fh:
            ai = json.load(fh)
    except (OSError, ValueError):
        pass
    ai_scope = {"chatbot": join(lines, words), "hidden": join(lines, words), "markdown": lines, "unicode": lines,
                "spaces": lines, "comments": n_of(sf, "source files"),
                "references": n_of(rc.get("references", fc.get("cited_keys")), "references")}
    if ai:
        for a in ai.get("artifacts", []):
            st = {"none": "ok", "fail": "problems", "check": "flagged", "not_checked": "not_checked"}.get(
                a.get("status"), "not_checked")
            its = a.get("items") or []
            if st in ("problems", "flagged") and its:
                st = "problems"
            elif st == "problems":
                st = "flagged"
            amount = ai_scope.get(a["id"]) or "the whole paper"
            if a.get("count"):
                amount += "; %d location%s" % (a["count"], "" if a["count"] == 1 else "s")
            row("ai", "ai_" + a["id"], a.get("label", a["id"]), "ai_traces", "" if st == "not_checked" else amount,
                "measured", st, problems=len(its), flags=a.get("fail", 0) + a.get("check", 0), its=its,
                reason="no output for it in facts.txt" if st == "not_checked" else "")
        stt = ((ai.get("disclosure") or {}).get("statement") or {})
        row("ai", "ai_statement", "LLM-use statement in the sources", "ai_traces",
            ("found at %s" % stt.get("where")) if stt.get("found") else "none in the sources", "measured", "ok",
            its=(ai.get("disclosure") or {}).get("items") or [])
        if cats["ai"][-1]["items"]:
            cats["ai"][-1].update(status="problems", problems=len(cats["ai"][-1]["items"]))
    else:
        row("ai", "ai_all", "Chatbot leftovers, Markdown, hidden prompts, unverified references, LLM-use statement",
            "ai_traces", "", "", "not_checked", reason="no work/ai-traces.json")

    categories = [dict(id=c, label=l, checks=cats[c]) for c, l in CATEGORIES if cats[c]]
    linked = {i for c in categories for ch in c["checks"] for i in ch["items"]}
    unlinked = sorted(n for n, _, _ in items if n not in linked)
    if unlinked:
        notes.append("report items in no check row: %s" % ", ".join(map(str, unlinked)))
    return dict(version=2, stats=stats, scope=scope, methods=scope_stats.METHOD, categories=categories,
                checkers=checkers,
                items={"total": len(items), "by_category": {c: len(by_cat(c)) for c, _ in CATEGORIES}},
                notes=notes)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out_dir")
    ap.add_argument("--out", default=None, help="default: OUT_DIR/work/checks.json")
    a = ap.parse_args()
    if not os.path.isdir(os.path.join(a.out_dir, "work")):
        print("no work/ in %s" % a.out_dir, file=sys.stderr)
        return 1
    data = build(a.out_dir)
    out = a.out or os.path.join(a.out_dir, "work", "checks.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print("checks.json written: %s" % out)
    print("  %d check rows in %d categories; %d report items" % (
        sum(len(c["checks"]) for c in data["categories"]), len(data["categories"]), data["items"]["total"]))
    print("  %d statistics: %s" % (len(data["stats"]), ", ".join("%s %s" % (fmt(s["value"]), s["id"])
                                                              for s in data["stats"][:8])))
    for n in data["notes"]:
        print("  note: " + n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
