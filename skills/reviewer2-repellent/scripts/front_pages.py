#!/usr/bin/env python3
"""Write the front pages of the annotated PDF (step 6), as LaTeX that the marked copy \\input's right after
\\begin{document} (needs \\usepackage[front]{r2changes}). The layout (page order, sections, data files, rules, fill
levels, visual conventions) is specified in references/pdf-layout.md: the summary (cover), "Venue rules",
"Bibliography" (work/bib-status.json of bib_status.py), "Decisions for you", "What we checked", "Traces of AI use",
then the paper. Item links go to the item's first mark in the paper (the .aux of the previous run); the item check
boxes come from r2states.tex next to the marked root (apply_edits.py). Every page has the same frame: top band, a
navigation line linking every front page and the paper, the title and one intro line.

Usage: python3 front_pages.py RUN_DIR MARKED_ROOT.tex [--out rrfront.tex] [--date YYYY-MM-DD] [--level PAGE=N ...]
                              [--title TEXT] [--authors TEXT] [--report P] [--venue P] [--status P] [--log P] [--ai P]
                              [--checks P]

RUN_DIR is the output folder of the run: report.md, work/venue.md, work/venue-status.json, work/edits.tsv (the log
of apply_edits.py) are read from it unless given. The .aux next to MARKED_ROOT.tex (previous LaTeX run) gives the
page of each item (labels rr-n); run this before every LaTeX run until the pages are stable. --out defaults to
rrfront.tex next to MARKED_ROOT.tex. Title and authors come from \\title and \\author in MARKED_ROOT.tex unless given.
--level sets the layout level of a page (cover, venue, checks, decisions; pdf-layout.md): build_changes.py chooses
the levels from the fill that the previous LaTeX run wrote to the log ("rrfront fill: ..."); this script prints that
fill and warns about a page under 80% (FILL_MIN).

Severity of an item: its "Severity:" in report.md (desk-reject, major, minor, optional; older words mapped), else
its section's default. The readiness line and the desk-reject tile count only items of severity desk-reject; the
Most Important Errors are ranked by severity; a venue rule judged violated whose items are all minor or optional is
shown as "to confirm". The apply box names --final-dir (default RUN_DIR); a temporary folder there is an error.
Kind of an item, from the log: placeholder (any `missing` edit) > to confirm (a question and an applied change) >
to check (a question, nothing changed) > fixed (fix or raw) > optional (style) > note only > not applied (log rows
and items with no edit). A `log` row whose status starts with "applied" counts as fixed.
Decisions sheet: one row per placeholder / to-confirm / to-check item, in page order, with a clickable PDF check box
(hyperref form field), the linked item number and page, the kind and one question: the item's question in section 9
of report.md, else the question of its edits, else "Give: <what>" of its placeholder; under it a text field
"answer-<item>" (\rranswer of r2changes.sty) where the author types the answer, read back by read_choices.py. Pages
are balanced by height (a row counts its question's lines plus ANSWER_UNITS for its field).

work/venue-status.json (written by the agent; the script judges nothing):
  {"rules": [{"id": "highlights",                       short id, unique
              "rule": "Highlights: separate file, 3-5 bullets",  what the rule asks (short, plain text)
              "quote": "Highlights are mandatory",       a verbatim piece of the rule in venue.md (checked)
              "status": "violated",                      met | violated | confirm | unknown
              "items": [1],                              report items about it (may be empty)
              "note": "no Highlights file among the sources",   this paper, one line (plain text)
              "source": "ARCHIVED 2024-04-22",          VERIFIED | ARCHIVED <YYYY-MM-DD> | UNKNOWN
              "url": "https://web.archive.org/..."}],    where the rule was read (must occur in venue.md)
   "blocked": [{"url": "https://...", "note": "HTTP 403 on 2026-11-09"}]}   live pages that could not be read:
                                                         a caveat banner (urls must occur in venue.md)
Text fields are plain text with Markdown `code`, **bold** and *italics*. Every error is listed; exit status 1.

"What we checked" page, only when work/checks.json exists (written by check_stats.py, format there): every
statistic, then one row per check grouped by category. Checked (errors, nothing written): a statistic without a
value or with an unknown basis, an estimate without its method, a row without an amount, items not in report.md, and
the words "not counted" anywhere in the pages.

"Traces of AI use" page, only when work/ai-traces.json exists (written by ai_traces.py,
format there, plus the agent's assessment and disclosure fields): 1. what was found in this paper, (a) objective
artifacts linked to their items, (b) style signals labelled "perception only, not evidence" with the baseline caveat
and the sections where they concentrate; 2. what venues do now, from references/ai-venue-actions.md (dated, with
URLs; edit that file, not this code) plus the target venue's rule; 3. the disclosure: the venue's rule, the statement
the paper has now, and a suggested sentence only when evidence.strong (else "no change needed beyond the venue's
rule"). Checked: items exist, venue_quote is verbatim in venue.md, a suggestion needs evidence.strong, the agent may
lower but not raise the rule's verdict, no text calls the paper AI-written or suggests hiding or softening AI use.
Python stdlib only.
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys

STATUSES = ('met', 'violated', 'confirm', 'unknown')
KINDS = [  # key, tile label, tile sub-label, colour
    ('fixed', 'fixed', 'red; applied in the copy', 'rrred'),
    ('confirm', 'to confirm', 'orange; applied, your call', 'rrorange'),
    ('facts', 'need your facts', r'orange [\#n: \dots] placeholder', 'rrorange!60!white'),
    ('check', 'to check', 'orange tag; nothing changed', 'rrorange!60!black'),
    ('optional', 'optional wording', 'purple; skim or skip', 'rrpurple'),
    ('note', 'note only', 'explained in a margin note', 'rrblueframe'),
    ('notapplied', 'not applied', 'see edits.md', 'rrnotapplied'),
]
DECIDE = {'facts': r'\textcolor{rrorange}{\textbf{your facts}}', 'confirm': r'\textcolor{rrorange}{\textbf{confirm}}',
          'check': r'\textcolor{rrorange!60!black}{\textbf{check}}'}
UNI = {'–': '--', '—': '---', '‘': '`', '’': "'", '“': '``', '”': "''", '…': r'\dots{}', '×': r'$\times$',
       '≤': r'$\le$', '≥': r'$\ge$', '≈': r'$\approx$', '→': r'$\to$', '←': r'$\leftarrow$', '∈': r'$\in$',
       '±': r'$\pm$', '·': r'$\cdot$', '−': '-', '\u00a0': '~', '\u2009': r'\,', '\u202f': r'\,', '≠': r'$\neq$',
       'µ': r'$\mu$', '°': r'$^\circ$', 'Θ': r'$\Theta$', 'θ': r'$\theta$', 'Ω': r'$\Omega$', 'ω': r'$\omega$',
       'α': r'$\alpha$', 'β': r'$\beta$', 'γ': r'$\gamma$', 'δ': r'$\delta$', 'ε': r'$\varepsilon$',
       'λ': r'$\lambda$', 'π': r'$\pi$', 'σ': r'$\sigma$', 'τ': r'$\tau$', 'φ': r'$\varphi$', 'Δ': r'$\Delta$',
       '∞': r'$\infty$', '√': r'$\surd$', '∑': r'$\sum$', '∪': r'$\cup$', '∩': r'$\cap$', 'é': r"\'e",
       'ü': r'\"u', 'ö': r'\"o', '✓': 'yes', '✗': 'no', '⇒': r'$\Rightarrow$', '∼': r'$\sim$'}
SPECIAL = {'\\': r'\textbackslash{}', '{': r'\{', '}': r'\}', '$': r'\$', '&': r'\&', '#': r'\#', '_': r'\_',
           '%': r'\%', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}', '<': r'\textless{}',
           '>': r'\textgreater{}'}


def esc(s):
    out = []
    for ch in s:
        if ch in SPECIAL:
            out.append(SPECIAL[ch])
        elif ch in UNI:
            out.append(UNI[ch])
        elif ord(ch) > 0x17f:
            out.append('?')
        else:
            out.append(ch)
    return ''.join(out)


def md(s):
    """Inline Markdown (code, bold, italics) to LaTeX; everything else escaped; "x" -> ``x''."""
    s = re.sub(r'(?<![\w"])"([^"\n]+)"(?![\w"])', '“\\1”', s)
    out, pos = [], 0
    for m in re.finditer(r'`([^`]+)`|\*\*(.+?)\*\*|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])', s):
        out.append(esc(s[pos:m.start()]))
        if m.group(1) is not None:
            out.append(r'\texttt{%s}' % esc(m.group(1)))
        elif m.group(2) is not None:
            out.append(r'\textbf{%s}' % md(m.group(2)))
        else:
            out.append(r'\emph{%s}' % md(m.group(3)))
        pos = m.end()
    out.append(esc(s[pos:]))
    return ''.join(out)


def norm_ws(s):
    s = s.replace('“', '"').replace('”', '"').replace('’', "'").replace('‘', "'")
    return ' '.join(s.split()).lower()


# ---------------------------------------------------------------- report.md
def parse_report(path):
    """{'sections': [(num, title, [items])], 'questions': {n: text}, 'first': [(items, text)], 'items': set}"""
    with open(path, encoding='utf-8') as fh:
        text = fh.read()
    sections, cur = [], None
    questions, first, texts = {}, [], {}
    in_first, last = False, None
    item_re = re.compile(r'^\s*(?:[-*]\s+)?(?:\*\*)?(\d+)\.(?:\*\*)?\s')
    for ln in text.split('\n'):
        h = re.match(r'^##\s+(\d+)\.\s+(.*?)\s*$', ln)
        if h:
            cur = [int(h.group(1)), h.group(2), []]
            sections.append(cur)
            in_first, last = False, None
            continue
        if cur is None:
            continue
        title = cur[1].lower()
        if title.startswith('summary'):
            if re.search(r'fix (these )?first', ln, re.I):
                in_first = True
                continue
            m = re.match(r'^\s*\d+\.\s+(.*)$', ln)
            if in_first and m:
                its = [int(x) for x in re.findall(r'(?:Item|#)\s*(\d+)', m.group(1))]
                body = re.sub(r'^\*\*Items?\s+[\d, ]+\*\*\s*:?\s*', '', m.group(1))
                first.append((its, body))
            continue
        if title.startswith('question'):
            m = re.match(r'^\s*[-*]\s+\*\*#?(\d+)\*\*\s*:?\s*(.*)$', ln)
            if m:
                questions.setdefault(int(m.group(1)), m.group(2).strip())
            continue
        if title.startswith('dropped'):
            continue
        m = item_re.match(ln)
        if m and not ln.startswith((' ', '\t', '-', '*')) or (m and ln.startswith('**')):
            cur[2].append(int(m.group(1)))
            last = int(m.group(1))
            texts[last] = ln[m.end():]
        elif m:
            cur[2].append(int(m.group(1)))
        elif last is not None and ln.strip():
            texts[last] += '\n' + ln
    secs = [(n, t, sorted(set(its))) for n, t, its in sections
            if its and not t.lower().startswith(('summary', 'question', 'dropped'))]
    items = set()
    for _, _, its in secs:
        items.update(its)
    severity, given, order = {}, set(), []
    for _, t, its in sections:
        if t.lower().startswith(('summary', 'question', 'dropped')):
            continue
        for i in its:
            if i in order:
                continue
            order.append(i)
            sv = severity_of(texts.get(i, ''))
            if sv:
                given.add(i)
            severity[i] = sv or section_severity(t)
    return {'sections': secs, 'all_sections': [(n, t, sorted(set(its))) for n, t, its in sections],
            'questions': questions, 'first': first, 'items': items, 'texts': texts, 'severity': severity,
            'severity_given': given, 'order': order}


# ---------------------------------------------------------------- severity
# one severity per item (references/merge-agent.md): every page uses it, and report.md states it ("Severity: major")
SEVERITIES = ('desk-reject', 'major', 'minor', 'optional')
SEV_RANK = {s: k for k, s in enumerate(SEVERITIES)}
SEV_COL = {'desk-reject': 'rrred', 'major': 'rrorange!80!black', 'minor': 'rrmuted', 'optional': 'rrpurple'}


def normalize_severity(raw):
    """'desk-reject (unless ...)' -> desk-reject; older words: reviewer-visible -> major, low / cosmetic -> minor."""
    r = ' '.join((raw or '').lower().split())
    if not r:
        return None
    if r.startswith('desk'):
        return 'desk-reject'
    if r.startswith('optional'):
        return 'optional'
    if r.startswith(('minor', 'low', 'cosmetic')) or '(minor)' in r:
        return 'minor'
    if r.startswith(('major', 'reviewer-visible', 'high', 'critical')):
        return 'major'
    return None


def severity_of(text):
    m = re.search(r'\bSeverity:\*{0,2}\s*([A-Za-z][\w-]*(?:[ -]visible)?(?:\s*\([^)]*\))?)', text or '')
    return normalize_severity(m.group(1)) if m else None


def section_severity(title):
    """The severity of an item that states none, from its report section."""
    t = title.lower()
    if t.startswith('desk'):
        return 'desk-reject'
    if t.startswith(('numbers', 'other')):
        return 'major'
    if t.startswith('appendix'):
        return 'optional'
    return 'minor'


# ---------------------------------------------------------------- log
def read_log(path):
    with open(path, encoding='utf-8', newline='') as fh:
        rows = list(csv.DictReader(fh, delimiter='\t', quoting=csv.QUOTE_NONE))
    for need in ('item', 'kind', 'status'):
        if rows and need not in rows[0]:
            raise ValueError('%s: no column %r (rerun apply_edits.py)' % (path, need))
    return rows


def classify(rows, questions=()):
    """item -> (kind key, [questions], [whats]). An applied item with a question in section 9 of report.md is to
    confirm, as one with a question in its edits."""
    by = {}
    for r in rows:
        try:
            n = int(r['item'])
        except (TypeError, ValueError):
            continue
        by.setdefault(n, []).append(r)
    out = {}
    for n, rs in by.items():
        kinds = {r['kind'] for r in rs}
        qs = [r.get('question') or '' for r in rs if (r.get('question') or '').strip()]
        whats = [r.get('what') or '' for r in rs if r['kind'] == 'missing' and (r.get('what') or '').strip()]
        applied = kinds & {'fix', 'check', 'style', 'raw'} or any(
            r['kind'] == 'log' and r['status'].lower().startswith('applied') for r in rs)
        if 'missing' in kinds:
            k = 'facts'
        elif qs or 'check' in kinds or n in questions:
            k = 'confirm' if applied else 'check'
        elif kinds & {'fix', 'raw'} or any(r['kind'] == 'log' and r['status'].lower().startswith('applied')
                                           for r in rs):
            k = 'fixed'
        elif 'style' in kinds:
            k = 'optional'
        elif 'note' in kinds:
            k = 'note'
        else:
            k = 'notapplied'
        out[n] = (k, list(dict.fromkeys(qs)), list(dict.fromkeys(whats)))
    return out


# ---------------------------------------------------------------- paper
def braced(s, i):
    """s[i] == '{': (content, index after the closing brace)."""
    d, j = 0, i
    while j < len(s):
        c = s[j]
        if c == '\\':
            j += 2
            continue
        if c == '{':
            d += 1
        elif c == '}':
            d -= 1
            if d == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)


def cmd_args(text, name):
    out = []
    for m in re.finditer(r'\\%s\*?\s*(?:\[[^\]]*\]\s*)?\{' % name, text):
        out.append(braced(text, m.end() - 1)[0])
    return out


DROP = ('thanks', 'footnote', 'tnoteref', 'fnref', 'orcid', 'orcidlink', 'inst', 'email', 'affiliation', 'label',
        'IEEEauthorblockA', 'IEEEauthorrefmark', 'textsuperscript', 'cormark', 'corref', 'affil', 'address', 'url')


def unmark(s):
    """The corrected text of r2changes marks: \\rrfix{n}{old}{new} -> new, \\rrfixplain{n}{new} -> new, ..."""
    nargs = {'rrfix': (3, 2), 'rrstyle': (3, 2), 'rrcheck': (4, 2), 'rrfixplain': (2, 1), 'rrstyleplain': (2, 1),
             'rrcheckplain': (3, 1), 'rrmissing': (2, None), 'rrcheckmark': (1, None), 'rrnote': (2, None),
             'rrtag': (2, None)}
    while True:
        m = re.search(r'\\(%s)(?![A-Za-z])\s*(?:\[[^\]]*\])?(?=\{)' % '|'.join(sorted(nargs, key=len, reverse=True)), s)
        if not m:
            return s
        n, keep = nargs[m.group(1)]
        args, j = [], m.end()
        for _ in range(n):
            while j < len(s) and s[j].isspace():
                j += 1
            if j >= len(s) or s[j] != '{':
                break
            a, j = braced(s, j)
            args.append(a)
        s = s[:m.start()] + (args[keep] if keep is not None and keep < len(args) else '') + s[j:]


def clean_tex(s):
    s = unmark(s)
    for name in DROP:
        while True:
            m = re.search(r'\\%s\*?\s*(?:\[[^\]]*\]\s*)?(\{)?' % name, s)
            if not m:
                break
            end = braced(s, m.end() - 1)[1] if m.group(1) else m.end()
            s = s[:m.start()] + s[end:]
    s = re.sub(r'\\IEEEauthorblockN\s*', '', s)
    return ' '.join(s.replace('\\\\', ' ').split())


def paper_meta(root):
    with open(root, encoding='utf-8', errors='replace') as fh:
        t = fh.read()
    t = '\n'.join(re.sub(r'(?<!\\)%.*$', '', ln) for ln in t.split('\n'))
    titles = cmd_args(t, 'title')
    title = clean_tex(titles[0]) if titles else ''
    authors = []
    for a in cmd_args(t, 'author'):
        for part in re.split(r'\\and\b|\\AND\b', a):
            part = part.split('\\\\')[0]
            c = clean_tex(part).strip(' ,')
            if c:
                authors.append(c)
    return title, ', '.join(authors)


def item_links(aux):
    """Where each item's links go, from the .aux of the previous LaTeX run: {item: (anchor, page)}. The anchor is the
    item's first mark in page order (rrmark-m, from the \\rr@markat records), else its note (rr-n); the page is the
    page of the paper in this copy (absolute page minus the front pages, from \\rr@paperstart). Also returns the
    absolute page where the paper starts, and the number of marks per paper page."""
    if not os.path.isfile(aux):
        return {}, None, {}
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import check_notes
    t = check_notes.read_aux(aux)
    m = re.findall(r'\\rr@paperstart\{(\d+)\}', t)
    start = int(m[-1]) if m else None
    first, per = {}, {}
    for mk, it, pg in re.findall(r'\\rr@markat\{(\d+)\}\{(\d+)\}\{(\d+)\}', t):
        mk, it, pg = int(mk), int(it), int(pg)
        if start is not None and pg < start:
            continue
        if it not in first or (pg, mk) < first[it]:
            first[it] = (pg, mk)
        if start is not None:
            per[pg - start + 1] = per.get(pg - start + 1, 0) + 1
    out = {}
    for it, (pg, mk) in first.items():
        out[it] = ('rrmark-%d' % mk, str(pg - start + 1) if start is not None else '')
    for it, pg in re.findall(r'\\newlabel\{rr-(\d+)\}\{\{[^{}]*\}\{([^{}]*)\}', t):
        out.setdefault(int(it), ('rr-%s' % it, pg))
    return out, start, per


def read_states(path):
    """{item: (ticked, read_only, reason)} from r2states.tex (apply_edits.py), or {}."""
    out = {}
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as fh:
            for m in re.finditer(r'\\rritemstate\{(\d+)\}\{([01])\}\{([01])\}\{([^\n]*)\}\s*$', fh.read(), re.M):
                out[int(m.group(1))] = (m.group(2) == '1', m.group(3) == '1', m.group(4))
    return out


TEMP_ROOTS = ('/tmp', '/private/tmp', '/var/tmp', '/private/var/tmp', '/var/folders', '/private/var/folders')


def is_temporary(path):
    """True for a path in a temporary or scratch folder (the system temp folder, /tmp, a 'scratchpad' folder): the
    user would not find the files there later."""
    import tempfile
    p = os.path.realpath(os.path.abspath(path))
    roots = set(TEMP_ROOTS) | {os.path.realpath(tempfile.gettempdir())}
    if any(p == r or p.startswith(r.rstrip('/') + '/') for r in roots):
        return True
    return 'scratchpad' in p.split(os.sep)


def page_key(p):
    return int(p) if p and p.isdigit() else 10 ** 6


# ---------------------------------------------------------------- venue
def load_status(path, venue_text, report_items, errors):
    try:
        with open(path, encoding='utf-8') as fh:
            st = json.load(fh)
    except (OSError, ValueError) as ex:
        errors.append('%s: %s' % (path, ex))
        return {'rules': [], 'blocked': []}
    vt = norm_ws(venue_text)
    rules = st.get('rules', [])
    if not isinstance(rules, list):
        errors.append('venue-status.json: "rules" must be a list')
        rules = []
    ids = set()
    for i, r in enumerate(rules):
        lab = 'venue-status.json rule %d (%s)' % (i + 1, r.get('id', '?'))
        if r.get('id') in ids or not r.get('id'):
            errors.append('%s: missing or repeated id' % lab)
        ids.add(r.get('id'))
        if r.get('status') not in STATUSES:
            errors.append('%s: status must be one of %s' % (lab, ', '.join(STATUSES)))
        if not (r.get('rule') or '').strip():
            errors.append('%s: no "rule" text' % lab)
        q = (r.get('quote') or '').strip()
        if not q:
            errors.append('%s: no "quote" (a verbatim piece of the rule in venue.md)' % lab)
        elif norm_ws(q) not in vt:
            errors.append('%s: quote not found in venue.md: %r' % (lab, q[:80]))
        src = r.get('source', '')
        if not re.fullmatch(r'VERIFIED|ARCHIVED \d{4}-\d{2}-\d{2}|UNKNOWN', src or ''):
            errors.append('%s: source must be VERIFIED, ARCHIVED <YYYY-MM-DD> or UNKNOWN' % lab)
        url = r.get('url') or ''
        if src != 'UNKNOWN' and not url:
            errors.append('%s: no url' % lab)
        if url and url not in venue_text:
            errors.append('%s: url not in venue.md: %s' % (lab, url))
        for it in r.get('items', []) or []:
            if not isinstance(it, int) or (report_items and it not in report_items):
                errors.append('%s: item %r is not an item of report.md' % (lab, it))
    blocked = st.get('blocked', []) or []
    for b in blocked:
        if not b.get('url') or b['url'] not in venue_text:
            errors.append('venue-status.json blocked: url not in venue.md: %s' % b.get('url'))
    return {'rules': rules, 'blocked': blocked}


# ---------------------------------------------------------------- LaTeX
PRE = r"""%% generated by front_pages.py: do not edit (it is rewritten before every LaTeX run)
\rrbeginfront
\begingroup
\definecolor{rrink}{RGB}{28,36,52}\definecolor{rrmuted}{RGB}{95,105,120}\definecolor{rrrule}{RGB}{215,222,232}
\definecolor{rrok}{RGB}{20,135,80}\definecolor{rrunk}{RGB}{135,140,150}\definecolor{rrband}{RGB}{243,246,250}
\definecolor{rrnotapplied}{RGB}{175,180,188}
\newcommand{\rrFok}{\tikz[baseline=-0.6ex]{\fill[rrok] (0,0) circle (4.2pt);\draw[white,line width=1.1pt,line cap=round,line join=round] (-2.1pt,0.1pt)--(-0.6pt,-1.5pt)--(2.2pt,1.7pt);}}
\newcommand{\rrFbad}{\tikz[baseline=-0.6ex]{\fill[rrred] (0,0) circle (4.2pt);\draw[white,line width=1.1pt,line cap=round] (-1.7pt,-1.7pt)--(1.7pt,1.7pt) (-1.7pt,1.7pt)--(1.7pt,-1.7pt);}}
\newcommand{\rrFconf}{\tikz[baseline=-0.6ex]{\fill[rrorange] (0,0) circle (4.2pt);\node[white,font=\sffamily\bfseries\fontsize{6.5}{6.5}\selectfont,inner sep=0] at (0,0.1pt) {!};}}
\newcommand{\rrFunk}{\tikz[baseline=-0.6ex]{\fill[rrunk] (0,0) circle (4.2pt);\node[white,font=\sffamily\bfseries\fontsize{6.5}{6.5}\selectfont,inner sep=0] at (0,0.1pt) {?};}}
\newcommand{\rrFdef}[3]{\expandafter\def\csname rrFa@#1\endcsname{#2}\expandafter\def\csname rrFp@#1\endcsname{#3}}
\newcommand{\rrFitem}[1]{\ifcsname rrFa@#1\endcsname\hyperlink{\csname rrFa@#1\endcsname}{\textbf{\##1}}\else\textbf{\##1}\fi}
\newcommand{\rrFpage}[1]{\ifcsname rrFa@#1\endcsname\hyperlink{\csname rrFa@#1\endcsname}{\csname rrFp@#1\endcsname}\else--\fi}
\newcommand{\rrFheadl}[2]{{\fontsize{8}{10}\selectfont\color{rrmuted}\bfseries\MakeUppercase{#1}\hfill\mdseries #2}\par\vspace{3pt}}
\newcommand{\rrFhead}[1]{{\fontsize{8}{10}\selectfont\color{rrmuted}\bfseries\MakeUppercase{#1}}\par\vspace{3pt}}
\newcommand{\rrFtile}[4]{%%
  \begin{tikzpicture}
    \node[draw=rrrule,fill=white,rounded corners=3pt,minimum width=\rrFtilew,minimum height=\rrFtileH,inner sep=0] (b) {};
    \fill[#3] ([xshift=0.6pt,yshift=0.6pt]b.south west) rectangle ([xshift=3.4pt,yshift=-0.6pt]b.north west);
    \node[anchor=north west,font=\sffamily\fontsize{\rrFtileN}{\rrFtileN}\selectfont\bfseries,text=#3] at ([xshift=9pt,yshift=-3.5pt]b.north west) {#1};
    \node[anchor=base west,font=\sffamily\fontsize{7.6}{8.6}\selectfont\bfseries,text=rrink,inner sep=0] at ([xshift=9pt,yshift=15.5pt]b.south west) {#2};
    \node[anchor=base west,font=\sffamily\fontsize{6.6}{7.4}\selectfont,text=rrmuted,inner sep=0] at ([xshift=9pt,yshift=6.5pt]b.south west) {#4};
  \end{tikzpicture}}
\def\rrFtileH{44bp}\def\rrFtileN{21}
\newcommand{\rrFtopband}{\begin{tikzpicture}[remember picture,overlay]\fill[rrink] (current page.north west) rectangle ([yshift=-5bp]current page.north east);\end{tikzpicture}}
\newcommand{\rrFkicker}[1]{{\fontsize{7.2}{9}\selectfont\color{rrmuted}\bfseries #1\hfill\mdseries %(date)s\enspace$\cdot$\enspace prepared by reviewer2-repellent}\par}
\newcommand{\rrFnavon}[1]{\textcolor{rrink}{#1}}
\newcommand{\rrFnavsep}{\enspace{\color{rrrule}|}\enspace}
\newcommand{\rrFtitle}[2]{{\fontsize{18}{21}\selectfont\bfseries #1\par}\vspace{4pt}{\raggedright\fontsize{8.2}{10.4}\selectfont\color{rrmuted}#2\par}}
\newcommand{\rrFcont}[2]{{\fontsize{13}{16}\selectfont\bfseries #1\hfill{\fontsize{7.6}{9}\selectfont\mdseries\color{rrmuted}#2}\par}}
\newcommand{\rrFchip}[1]{\tikz[baseline=-0.1ex]{\fill[#1] (0,0) rectangle (7pt,6pt);}}
\newcommand{\rrFchg}{\tikz[baseline=-0.6ex]{\fill[rrred] (0,0) circle (4.2pt);\draw[white,line width=1.1pt,line cap=round,line join=round] (-1.9pt,-1.9pt)--(1.4pt,1.4pt) (-0.2pt,1.6pt)--(1.6pt,1.6pt)--(1.6pt,-0.2pt);}}
\newcommand{\rrFpass}{\tikz[baseline=-0.6ex]{\fill[rrblueframe] (0,0) circle (4.2pt);\draw[white,line width=1.1pt,line cap=round,line join=round] (-2pt,0)--(1.8pt,0) (0.3pt,-1.6pt)--(1.9pt,0)--(0.3pt,1.6pt);}}
%% headline tiles of the summary: big (number, label, detail, colour) and small (number, label, detail)
\newcommand{\rrFbig}[4]{\begin{tikzpicture}
    \node[draw=#4!45,fill=#4!5,rounded corners=3pt,minimum width=1.7\rrFtilew,minimum height=50bp,inner sep=0] (b) {};
    \fill[#4] ([xshift=0.6pt,yshift=0.6pt]b.south west) rectangle ([xshift=4pt,yshift=-0.6pt]b.north west);
    \node[anchor=base west,font=\sffamily\fontsize{30}{30}\selectfont\bfseries,text=#4,inner sep=0] (n) at ([xshift=11pt,yshift=-28pt]b.north west) {#1};
    \node[anchor=base west,font=\sffamily\fontsize{11}{12}\selectfont\bfseries,text=rrink,inner sep=0] at ([xshift=7pt]n.base east) {#2};
    \node[anchor=base west,font=\sffamily\fontsize{7}{8}\selectfont,text=rrmuted,inner sep=0,text width=1.7\rrFtilew-20pt] at ([xshift=11pt,yshift=7pt]b.south west) {#3};
  \end{tikzpicture}}
\newcommand{\rrFsmall}[3]{\begin{tikzpicture}
    \node[draw=rrrule,fill=white,rounded corners=3pt,minimum width=\rrFtilew,minimum height=50bp,inner sep=0] (b) {};
    \node[anchor=base west,font=\sffamily\fontsize{15}{15}\selectfont\bfseries,text=rrink,inner sep=0] at ([xshift=7pt,yshift=-21pt]b.north west) {#1};
    \node[anchor=base west,font=\sffamily\fontsize{7.2}{8}\selectfont\bfseries,text=rrink,inner sep=0] at ([xshift=7pt,yshift=15pt]b.south west) {#2};
    \node[anchor=base west,font=\sffamily\fontsize{6.4}{7}\selectfont,text=rrmuted,inner sep=0] at ([xshift=7pt,yshift=6pt]b.south west) {#3};
  \end{tikzpicture}}
\newcommand{\rrFstat}[2]{\parbox[t]{\rrFtilew}{\raggedright{\fontsize{12}{13}\selectfont\bfseries #1}\par{\fontsize{6.8}{7.8}\selectfont #2\par}}}
\newlength{\rrFcellw}
\newcommand{\rrFrow}[5]{\par\noindent\colorbox{#1}{\parbox[t]{\rrFwa}{\strut#2}\parbox[t]{\rrFwb}{\raggedright\strut#3\strut}\parbox[t]{\rrFwc}{\raggedright\strut#4\strut}\parbox[t]{\rrFwd}{\raggedright\strut#5\strut}}\par\nointerlineskip}
\newcommand{\rrFdrow}[6]{\par\noindent\colorbox{#1}{\parbox[t]{0.04\linewidth}{\strut#2}\parbox[t]{0.07\linewidth}{\strut#3}\parbox[t]{0.07\linewidth}{\strut#4}\parbox[t]{0.11\linewidth}{\strut#5}\parbox[t]{\dimexpr0.71\linewidth-2\fboxsep\relax}{\raggedright\strut#6\strut}}\par\nointerlineskip}
\newcommand{\rrFdans}[2]{\par\noindent\colorbox{#1}{\parbox[t]{\dimexpr0.29\linewidth-4pt\relax}{\vspace{0pt}\raggedleft\fontsize{6.6}{7.6}\selectfont\color{rrmuted}\strut your answer\par}\hspace{4pt}\parbox[t]{\dimexpr0.71\linewidth-2\fboxsep\relax}{\vspace{0pt}\rranswer{#2}{\linewidth}{\rranswerheight}}}\par\nointerlineskip}
\newcommand{\rrFcell}[2]{\parbox[t]{\dimexpr\csname rrFw#1\endcsname-7pt\relax}{\raggedright#2}}
\newcommand{\rrFrowe}[6]{\par\noindent\colorbox{#1}{\parbox[t]{\rrFwa}{\strut#2}\parbox[t]{\rrFwb}{\raggedright\strut#3\strut}\parbox[t]{\rrFwc}{\raggedright\strut#4\strut}\parbox[t]{\rrFwd}{\raggedright\strut#5\strut}\parbox[t]{\rrFwe}{\raggedright\strut#6\strut}}\par\nointerlineskip}
\newlength{\rrFtilew}\newlength{\rrFbarw}\newlength{\rrFwa}\newlength{\rrFwb}\newlength{\rrFwc}\newlength{\rrFwd}\newlength{\rrFwe}
"""


VENUE_SYM = {'met': r'\rrFok', 'violated': r'\rrFbad', 'confirm': r'\rrFconf', 'unknown': r'\rrFunk'}
VENUE_ORDER = {'violated': 0, 'confirm': 1, 'unknown': 2, 'met': 3}
VENUE_DENS = [(7.2, 8.4, 2.0, False), (7.8, 9.3, 2.8, False), (8.4, 10.2, 3.6, False), (8.8, 10.8, 4.4, False),
              (7.2, 8.4, 2.0, True), (7.8, 9.3, 2.6, True)]


def venue_counts(rules):
    return {s: sum(1 for r in rules if r.get('status') == s) for s in STATUSES}


def venue_urls(rules):
    urls = []
    for r in rules:
        if r.get('url') and r['url'] not in urls:
            urls.append(r['url'])
    return urls


TAGCOL = {'fixed': 'rrred', 'confirm': 'rrorange', 'facts': 'rrorange', 'check': 'rrorange!60!black',
          'optional': 'rrpurple', 'note': 'rrblueframe', 'notapplied': 'rrunk'}


def copy_tag(its, cls):
    """The state in the copy of the items of a row: fixed, to confirm, your facts, ... (kinds of work/edits.tsv)."""
    kinds = list(dict.fromkeys(cls.get(i, ('notapplied',))[0] for i in its))
    return ', '.join(r'\textcolor{%s}{\textbf{%s}}' % (TAGCOL[k], SHORT[k]) for k in kinds)


def venue_tex(vs, cls, level=0, part=None, report=None):
    """The venue table. level: 0 compact, 1-3 larger type and rows, 4-5 with the verbatim quote of each rule.
    part=(k, whole vs) when the table is split: counts and caveat on part 1, legend and sources on part 2."""
    whole = part[1] if part else vs
    if report is not None:      # the item severity decides whether a rule is violated (effective_status)
        whole = dict(whole, rules=[dict(r, status=effective_status(r, report)) for r in whole['rules']])
        vs = dict(vs, rules=[dict(r, status=effective_status(r, report)) for r in vs['rules']])
    rules = vs['rules']
    fs, lead, pad, quotes = VENUE_DENS[max(0, min(level, len(VENUE_DENS) - 1))]
    cnt = venue_counts(whole['rules'])
    urls = venue_urls(whole['rules'])
    first, last = (not part or part[0] == 1), (not part or part[0] == 2)
    out = [] if not first else [r'{\fontsize{8}{10}\selectfont\color{rrmuted}\bfseries %d RULES\hfill'
           r'\mdseries\textcolor{rrink}{\rrFbad\,%d violated\quad\rrFconf\,%d to confirm\quad\rrFunk\,%d cannot '
           r'tell\quad\rrFok\,%d met}}\par\vspace{3pt}' % (len(whole['rules']), cnt['violated'], cnt['confirm'],
                                                           cnt['unknown'], cnt['met'])]
    if first and (vs['blocked'] or any(r.get('source', '').startswith(('ARCHIVED', 'UNKNOWN'))
                                       for r in whole['rules'])):
        bits = []
        for b in vs['blocked']:
            bits.append(r'The live page \url{%s} could not be read%s.' % (
                b['url'], (' (' + md(b['note']) + ')') if b.get('note') else ''))
        if any(r.get('source', '').startswith('ARCHIVED') for r in whole['rules']):
            bits.append(r'Rules marked \textbf{ARCHIVED} come from an archived copy of the date shown: '
                        r're-check them on the live page before submitting.')
        if any(r.get('source') == 'UNKNOWN' for r in whole['rules']):
            bits.append(r'Rules marked \textbf{UNKNOWN} could not be verified on any source.')
        out.append(r'\noindent\fcolorbox{rrorange!60}{rrorange!10}{\parbox{\dimexpr\linewidth-2\fboxsep-2\fboxrule'
                   r'\relax}{\raggedright\fontsize{7.4}{8.9}\selectfont\urlstyle{same}\textbf{\textcolor{rrorange}'
                   r'{Source caveat.}} %s}}\par\vspace{4pt}' % ' '.join(bits))
    out.append(r'{\fontsize{%s}{%s}\selectfont\setlength{\fboxsep}{%spt}'
               r'\setlength{\rrFwa}{14pt}\setlength{\rrFwb}{0.33\linewidth}\setlength{\rrFwd}{0.085\linewidth}'
               r'\setlength{\rrFwe}{0.135\linewidth}\setlength{\rrFwc}{\dimexpr\linewidth-\rrFwa-\rrFwb-\rrFwd-\rrFwe'
               r'-2\fboxsep\relax}' % (fs, lead, pad))
    out.append(r'\rrFrowe{white}{}{\textcolor{rrmuted}{\textbf{Rule}}%s}{\textcolor{rrmuted}{\textbf{This paper '
               r'(item, page)}}}{\textcolor{rrmuted}{\textbf{In the copy}}}{\textcolor{rrmuted}{\textbf{Source}}}' % (
                   r' {\color{rrmuted}and its words in the guide}' if quotes else ''))
    for i, r in enumerate(sorted(rules, key=lambda r: VENUE_ORDER.get(r.get('status'), 9))):
        its = r.get('items') or []
        paper = ' '.join(r'\rrFitem{%d}' % n for n in its)
        if its:
            paper += r' (p.~\rrFpage{%d})' % its[0]
        note = md(r.get('note') or '')
        paper = (paper + ' ' + note).strip()
        src = r.get('source', '')
        ref = (r'[%d]' % (urls.index(r['url']) + 1)) if r.get('url') else ''
        srctex = r'{\color{rrmuted}\fontsize{%s}{%s}\selectfont %s\,\mbox{%s}}' % (
            round(fs - 0.6, 1), round(lead - 0.5, 1), ref,
            esc(src.replace('ARCHIVED ', 'archived ').replace('VERIFIED', 'verified').replace('UNKNOWN', 'unknown')))
        rule = md(r['rule'])
        if quotes and r.get('quote'):
            rule += r"\par{\color{rrmuted}\fontsize{%s}{%s}\selectfont\itshape ``%s''\par}" % (
                round(fs - 0.6, 1), round(lead - 0.6, 1), esc(r['quote'] if len(r['quote']) <= 160 else
                                          r['quote'][:157].rsplit(' ', 1)[0] + '...'))
        out.append(r'\rrFrowe{%s}{%s}{\rrFcell{b}{%s}}{\rrFcell{c}{%s}}{%s}{%s}' % (
            'rrband' if i % 2 == 0 else 'white', VENUE_SYM.get(r.get('status'), '?'), rule, paper,
            copy_tag(its, cls) if its else '', srctex))
    out.append(r'}\par\rrFgap{4pt}')
    if not last:
        return '\n'.join(out)
    out.append(r'{\fontsize{6.6}{7.9}\selectfont\color{rrmuted}\urlstyle{same}\raggedright'
               r'\rrFok\ meets the rule\quad\rrFbad\ violates it\quad\rrFconf\ to confirm\quad\rrFunk\ cannot tell '
               r'from the sources.\quad \textbf{In the copy}: what this copy did with the rule\textquoteright{}s items '
               r'(\textcolor{rrred}{fixed}; \textcolor{rrorange}{to confirm} or \textcolor{rrorange}{your facts}: '
               r'on the decision sheet; \textcolor{rrpurple}{optional wording}; \textcolor{rrunk}{not applied}).'
               r'\par\vspace{2pt}')
    for i, u in enumerate(urls):
        out.append(r'[%d] \url{%s}\par' % (i + 1, u))
    for b in vs['blocked']:
        out.append(r'live, blocked: \url{%s}\par' % b['url'])
    out.append('}')
    return '\n'.join(out)


def venue_page(vs, venue_name, cls, nav, level=0, split=False, report=None):
    """The venue rules page; split=True spreads the table over two pages (build_changes.py asks for it when the page
    overflows at level 0)."""
    intro = (r'Every rule of the call and of the guide for authors of \textbf{%s} that applies to this paper, judged '
             r'on the sources: violated (only when a desk-reject item says so) first, then to confirm, cannot tell, met; for each, '
             r'the report items, the state of the change in this copy and where the rule was read.' % esc(venue_name))
    out = [page_open('venue', 'rr-venue'), page_head(nav, 'venue', full_title('venue'), intro), r'\rrFgap[0.25]{8pt}']
    rules = sorted(vs['rules'], key=lambda r: VENUE_ORDER.get(effective_status(r, report) if report else
                                                            r.get('status'), 9))
    if split and len(rules) > 1:
        h = -(-len(rules) // 2)
        out.append(venue_tex(dict(vs, rules=rules[:h]), cls, level, part=(1, vs), report=report))
        out.append(r'\end{rrfullpage}')
        out.append(page_open('venue-2') + page_head(nav, 'venue', full_title('venue'), '', cont='page 2 of 2'))
        out.append(venue_tex(dict(vs, rules=rules[h:]), cls, level, part=(2, vs), report=report))
    else:
        out.append(venue_tex(dict(vs, rules=rules), cls, level, report=report))
    out.append(r'\end{rrfullpage}')
    return '\n'.join(out)


# ---------------------------------------------------------------- traces of AI use
AI_ACTIONS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'references',
                          'ai-venue-actions.md')
AI_ICON = {'none': r'\rrFok', 'fail': r'\rrFbad', 'check': r'\rrFconf', 'not_checked': r'\rrFunk'}
FORBID_AUTHOR = re.compile(r'\b(ai|llm|chatgpt|gpt|machine|chatbot)[- ](written|generated|authored)\b|'
                           r'\bwritten (by|with) (an? )?(ai|llm|chatbot|language model)\b', re.I)
FORBID_HIDE = re.compile(r'humani[sz]|undetect|\b(avoid|evade|pass|beat|bypass)\w*\s+(\w+\s+){0,2}(detect|checker)|'
                         r'\b(remove|delete|drop|soften|hide|omit)\w*\s+(\w+\s+){0,3}(statement|declaration|disclosure)',
                         re.I)


def read_actions(path, errors):
    out = {'asof': '', 'actions': [], 'closing': ''}
    if not os.path.isfile(path):
        errors.append('missing data file of the AI page: %s' % path)
        return out
    sec = ''
    with open(path, encoding='utf-8') as fh:
        for ln in fh.read().split('\n'):
            m = re.match(r'^As of:\s*(\d{4}-\d{2}-\d{2})\s*$', ln)
            if m:
                out['asof'] = m.group(1)
            h = re.match(r'^##\s+(.*)', ln)
            if h:
                sec = h.group(1).lower()
                continue
            if not ln.startswith('- '):
                continue
            if sec.startswith('action'):
                parts = [x.strip() for x in ln[2:].split(' | ')]
                if len(parts) != 4 or not re.match(r'https?://\S+$', parts[3]):
                    errors.append('%s: an action line needs "- when | venue | what | URL": %s' % (path, ln[:80]))
                    continue
                out['actions'].append(parts)
            elif sec.startswith('closing'):
                out['closing'] = ln[2:].strip()
    if not out['asof']:
        errors.append('%s: no "As of: YYYY-MM-DD" line' % path)
    if not out['actions'] or len(out['actions']) > 6:
        errors.append('%s: give 1 to 6 action lines (found %d)' % (path, len(out['actions'])))
    return out


def load_ai(path, venue_text, report_items, errors):
    try:
        with open(path, encoding='utf-8') as fh:
            ai = json.load(fh)
    except (OSError, ValueError) as ex:
        errors.append('%s: %s' % (path, ex))
        return None
    lab = 'ai-traces.json'
    disc = ai.get('disclosure') or {}
    ev = ai.get('evidence') or {}
    for a in ai.get('artifacts', []):
        for it in a.get('items', []) or []:
            if not isinstance(it, int) or (report_items and it not in report_items):
                errors.append('%s artifact %s: item %r is not an item of report.md' % (lab, a.get('id'), it))
    for it in disc.get('items', []) or []:
        if not isinstance(it, int) or (report_items and it not in report_items):
            errors.append('%s disclosure: item %r is not an item of report.md' % (lab, it))
    if ev.get('strong') and not ev.get('rule_strong'):
        errors.append('%s: evidence.strong is true but the rule of ai_traces.py says false: the agent may lower the '
                      'verdict (with "why"), never raise it' % lab)
    if ev.get('rule_strong') and ev.get('strong') is False and not (ev.get('why') or '').strip():
        errors.append('%s: evidence.strong lowered to false without a "why"' % lab)
    sug = ai.get('suggestion') or {}
    if sug and not ev.get('strong'):
        errors.append('%s: a disclosure suggestion needs strong evidence (evidence.strong); without it the page says '
                      'that no change is needed beyond the venue\'s rule' % lab)
    if sug and not (sug.get('text') or '').strip():
        errors.append('%s: suggestion without "text"' % lab)
    texts = [('assessment', ai.get('assessment')), ('disclosure.advice', disc.get('advice'))]
    texts += [('artifact %s note' % a.get('id'), a.get('note')) for a in ai.get('artifacts', [])]
    for name, t in texts:
        if t and FORBID_AUTHOR.search(t):
            errors.append('%s %s: never call the paper AI-written or AI-generated (%r)' % (
                lab, name, FORBID_AUTHOR.search(t).group(0)))
    for name, t in texts + [('suggestion', sug.get('text')), ('suggestion.where', sug.get('where'))]:
        if t and FORBID_HIDE.search(t):
            errors.append('%s %s: never suggest hiding, softening or removing AI use or its disclosure (%r)' % (
                lab, name, FORBID_HIDE.search(t).group(0)))
    if len((ai.get('assessment') or '').split()) > 80:
        errors.append('%s: assessment over 80 words' % lab)
    q = (disc.get('venue_quote') or '').strip()
    if q and norm_ws(q) not in norm_ws(venue_text):
        errors.append('%s: disclosure.venue_quote not found in venue.md: %r' % (lab, q[:80]))
    return ai


def url_tex(u):
    return r'\url{%s}' % u.replace('%', r'\%').replace('#', r'\#')


def ai_tex(ai, acts, venue_name, nav):
    disc = ai.get('disclosure') or {}
    st = disc.get('statement') or {}
    ev = ai.get('evidence') or {}
    paper = ai.get('paper') or {}
    urls = []

    def ref(u):
        if not u:
            return ''
        if u not in urls:
            urls.append(u)
        return r'\,{\color{rrmuted}[%d]}' % (urls.index(u) + 1)

    intro = (r'Venues sanction verifiable artifacts (fabricated references, hidden prompts, chatbot leftovers, a '
             r'missing disclosure), not writing style. Part~1 lists what this paper has of each, then style '
             r'measurements that some readers associate with AI text. Nothing on this page says who or what wrote '
             r'the paper: no style count or detector can tell, and both misfire most on non-native authors.')
    out = [page_open('ai', 'rr-aitraces'), page_head(nav, 'ai', full_title('ai'), intro), r'\rrFgap[0.25]{8pt}']
    out.append(r'\noindent\begin{minipage}[t]{0.615\linewidth}')
    out.append(r'\rrFhead{1\enspace What we found in this paper}')
    out.append(r'{\fontsize{8.4}{10}\selectfont\textbf{a.\ Objective artifacts}\enspace{\fontsize{7.2}{9}\selectfont'
               r'\color{rrmuted}defects whoever wrote them; \#n is the report item}\par}\vspace{3pt}')
    out.append(r'{\fontsize{7.2}{8.6}\selectfont\setlength{\fboxsep}{2pt}\setlength{\rrFwa}{14pt}'
               r'\setlength{\rrFwb}{0.27\linewidth}\setlength{\rrFwd}{0.15\linewidth}'
               r'\setlength{\rrFwc}{\dimexpr\linewidth-\rrFwa-\rrFwb-\rrFwd-2\fboxsep\relax}')
    out.append(r'\rrFrow{white}{}{\textcolor{rrmuted}{\textbf{Check}}}{\textcolor{rrmuted}{\textbf{This paper}}}'
               r'{\textcolor{rrmuted}{\textbf{Item (page)}}}')
    rows = []
    for a in ai.get('artifacts', []):
        n, where = a.get('count', 0), a.get('where') or []
        if a.get('note'):
            txt = md(a['note'])
        elif a['status'] == 'none':
            txt = 'None found.'
        elif a['status'] == 'not_checked':
            txt = r'Not checked in this run.'
        elif a['id'] == 'references':
            txt = '%d not found in the databases or with a wrong identifier: %s' % (n, esc(', '.join(where)))
            if not a.get('items'):
                txt += '; the report raises no item about it'
            txt += '.'
        else:
            kinds = '; '.join(a.get('kinds') or [])
            txt = '%d location%s (%s): %s.' % (n, '' if n == 1 else 's', esc(kinds), esc(', '.join(where)))
            if a.get('fail') and a.get('check'):
                txt += ' %d to fix, %d to check.' % (a['fail'], a['check'])
            elif a.get('check') and not a.get('fail'):
                txt += ' To check: prints, but inconsistent or invisible in the source.' if a['id'] in (
                    'unicode', 'spaces') else ' To check.'
        its = a.get('items') or []
        itt = ' '.join(r'\rrFitem{%d}' % i for i in its[:4]) + ((r' (p.~\rrFpage{%d})' % its[0]) if its else '')
        rows.append((AI_ICON.get(a['status'], r'\rrFunk'), md(a.get('label', a['id'])), txt, itt))
    # the LLM-use statement
    placement = re.search(r'immediately before the references', disc.get('venue_lines') or '', re.I)
    if st.get('found'):
        txt = r'Present at %s%s, followed by %s.' % (esc(st.get('where', '')), (r' (\emph{%s})' % esc(
            st['heading'])) if st.get('heading') else '', esc(st.get('followed_by') or 'nothing'))
        bad = placement and not st.get('before_references')
        if bad:
            txt += ' The venue wants it immediately before the references.'
        # as on the "What we checked" page: a problem raised as a report item is red, without an item orange
        icon = (r'\rrFbad' if disc.get('items') else r'\rrFconf') if bad else r'\rrFok'
    else:
        txt = 'None in the sources; see part 3 for the venue\'s rule.'
        icon = r'\rrFconf' if disc.get('venue_lines') else r'\rrFunk'
    its = disc.get('items') or []
    rows.append((icon, 'LLM-use statement', txt, ' '.join(r'\rrFitem{%d}' % i for i in its[:4]) +
                 ((r' (p.~\rrFpage{%d})' % its[0]) if its else '')))
    for i, (icon, label, txt, itt) in enumerate(rows):
        out.append(r'\rrFrow{%s}{%s}{%s}{%s}{%s}' % ('rrband' if i % 2 == 0 else 'white', icon, label, txt, itt))
    out.append(r'}\par\vspace{2pt}{\fontsize{6.6}{7.9}\selectfont\color{rrmuted}\rrFok\ none found\quad\rrFbad\ to '
               r'fix\quad\rrFconf\ to check\quad\rrFunk\ not checked\par}\vspace{8pt}')
    # style signals
    out.append(r'\noindent\fcolorbox{rrrule}{rrband}{\parbox{\dimexpr\linewidth-2\fboxsep-2\fboxrule\relax}{'
               r'\fontsize{8.4}{10}\selectfont\textbf{b.\ Style signals}\enspace\textcolor{rrorange!75!black}'
               r'{\textbf{perception only, not evidence}}\par\vspace{2pt}'
               r'{\fontsize{7.2}{8.8}\selectfont\color{rrmuted}Some readers associate these with AI text, but human '
               r'authors produce all of them (templates, page limits, lab style) and newer models avoid several. No '
               r'calibrated baseline for computer science papers exists yet, so a value here is neither high nor low: '
               r'it is only this paper\textquoteright{}s.\par}\vspace{3pt}')
    out.append(r'{\fontsize{7.2}{8.6}\selectfont\setlength{\fboxsep}{1.5pt}\setlength{\rrFwa}{0pt}'
               r'\setlength{\rrFwb}{0.25\linewidth}\setlength{\rrFwd}{0.36\linewidth}'
               r'\setlength{\rrFwc}{\dimexpr\linewidth-\rrFwa-\rrFwb-\rrFwd-2\fboxsep\relax}')
    out.append(r'\rrFrow{rrband}{}{\textcolor{rrmuted}{\textbf{Signal}}}{\textcolor{rrmuted}{\textbf{This paper}}}'
               r'{\textcolor{rrmuted}{\textbf{Reference point}}}')
    for s in ai.get('style', []):
        b = s.get('baseline')
        if b:
            point = md(b['text']) + (r' (calibrated)' if b.get('calibrated') else
                                   r'; not a calibrated baseline') + ref(b.get('url'))
        else:
            point = r'none yet'
        val = esc(s.get('text', ''))
        if s.get('id') == 'excess_words' and s.get('examples'):
            val += r'; e.g.\ ' + esc(s['examples'][0])
        out.append(r'\rrFrow{rrband}{}{%s}{%s}{\color{rrmuted}%s}' % (esc(s['label']), val, point))
    out.append('}')
    cl = ai.get('clusters') or []
    names = {'em_dash': 'em dashes', 'excess_words': 'excess words', 'participle_tails': 'participle tails',
             'bold_runins': 'bold run-ins', 'items': 'list items'}
    if cl:
        ctext = '; '.join(r'%s (%s, %s)' % (esc(c['section']), esc(c['where']), ', '.join(
            names.get(x, x) for x in c['signals'])) for c in cl[:4])
    else:
        ctext = r'no section stands out.'
    out.append(r'\vspace{3pt}{\fontsize{7.2}{8.8}\selectfont\textbf{Where they concentrate} (twice the '
               r'paper\textquoteright{}s own rate on two or more signals): %s\par}' % ctext)
    out.append(r'\vspace{2pt}{\fontsize{6.6}{7.9}\selectfont\color{rrmuted}Measured on the text outside math, tables, '
               r'verbatim and comments: %s words, %s paragraphs, %s pages of body.\par}}}\par' % (
                   fmtn(paper.get('words', '?')), fmtn(paper.get('paragraphs', '?')),
                   fmtn(paper.get('body_pages', '?'))))
    if ai.get('assessment'):
        out.append(r'\vspace{8pt}\noindent\fcolorbox{rrrule}{white}{\parbox{\dimexpr\linewidth-2\fboxsep-2\fboxrule'
                   r'\relax}{\fontsize{8.2}{10.2}\selectfont\textbf{Our reading.} %s}}\par' % md(ai['assessment']))
    split_at = len(out)
    out.append(r'\end{minipage}\hfill\begin{minipage}[t]{0.355\linewidth}')
    # venues
    out.append(r'\rrFhead{2\enspace What venues do now}')
    lines = []
    for when, venue, what, u in acts['actions']:
        lines.append(r'\textbf{%s} {\color{rrmuted}(%s)} %s%s' % (esc(venue), esc(when), md(what), ref(u)))
    vrule = disc.get('venue_rule') or disc.get('venue_rule_found') or ''
    if vrule:
        lines.append(r'\textbf{Your venue, %s:} %s%s' % (esc(venue_name), md(vrule), ref(disc.get('venue_url'))))
    out.append(r'\noindent\fcolorbox{rrblueframe}{white}{\parbox{\dimexpr\linewidth-2\fboxsep-2\fboxrule\relax}{'
               r'\raggedright\fontsize{7.4}{9}\selectfont{\color{rrmuted}As of %s:}\par\vspace{2pt}%s%s}}\par' % (
                   esc(acts['asof']), r'\par\vspace{2.5pt}'.join(lines),
                   (r'\par\vspace{2.5pt}\emph{%s}' % md(acts['closing'])) if acts['closing'] else ''))
    # disclosure
    out.append(r'\vspace{9pt}\rrFhead{3\enspace Your disclosure}')
    out.append(r'{\raggedright\fontsize{7.6}{9.4}\selectfont')
    vq = disc.get('venue_quote') or disc.get('venue_quote_found') or ''
    if vrule or vq:
        out.append(r'\textbf{Venue rule.} %s%s%s\par\vspace{3pt}' % (
            md(vrule), (" ``%s''" % esc(vq)) if vq else '', ref(disc.get('venue_url'))))
    else:
        out.append(r'\textbf{Venue rule.} venue.md says nothing on LLM use: check the venue\textquoteright{}s '
                   r'policy.\par\vspace{3pt}')
    if st.get('found'):
        t = st.get('text') or ''
        out.append(r'\textbf{Your statement now} (%s, followed by %s)%s \emph{%s}\par\vspace{5pt}' % (
            esc(st.get('where', '')), esc(st.get('followed_by') or 'nothing'),
            (r': \textbf{%s}.' % esc(st['heading'])) if st.get('heading') else ':', esc(t)))
    else:
        out.append(r'\textbf{Your statement now:} none in the sources.\par\vspace{5pt}')
    sug = ai.get('suggestion') or {}
    if ev.get('strong'):
        body = r'\textbf{Strong traces of AI use in the writing:} %s.' % esc('; '.join(ev.get('reasons') or []))
        if sug:
            body += (r' \textbf{Your choice, and only if it matches what you actually did}, a statement that would '
                     r'cover them: \emph{%s}%s' % (md(sug['text']), (r' Where: %s.' % md(sug['where']))
                                                   if sug.get('where') else ''))
        else:
            body += r' Check that your statement covers them; we suggest no wording.'
        out.append(r'\noindent\fcolorbox{rrorange!60}{rrorange!8}{\parbox{\dimexpr\linewidth-2\fboxsep-2\fboxrule'
                   r'\relax}{\raggedright %s}}\par' % body)
    else:
        body = r'\textbf{No change needed beyond the venue\textquoteright{}s rule.}'
        if ev.get('rule_strong'):
            body += r' (The rule found %s; set aside: %s.)' % (esc('; '.join(ev.get('reasons') or [])),
                                                                 md(ev.get('why') or ''))
        else:
            body += r' The sources show no strong trace of AI use in the writing (style counts never count as one).'
        if disc.get('advice'):
            body += ' ' + md(disc['advice'])
        out.append(r'\noindent\fcolorbox{rrok!55}{rrok!6}{\parbox{\dimexpr\linewidth-2\fboxsep-2\fboxrule\relax}'
                   r'{\raggedright %s}}\par' % body)
    out.append(r'\vspace{4pt}{\fontsize{6.8}{8.2}\selectfont\color{rrmuted}Keep any disclosure you made: disclosed '
               r'language editing is allowed at every venue reviewed, and undisclosed use found later counts as '
               r'misconduct.\par}}')
    out.append(r'\end{minipage}')
    # the sources of the page under the left column (it is the shorter one)
    out.insert(split_at, r'\vspace{9pt}{\raggedright\fontsize{6.6}{8.2}\selectfont\color{rrmuted}\urlstyle{same}'
               r'\textbf{Sources.}\par ' + r'\par '.join(r'[%d]~%s' % (i + 1, url_tex(u)) for i, u in enumerate(urls))
               + r'\par}')
    out.append(r'\end{rrfullpage}')
    return '\n'.join(out), len(urls)


CHECK_ICON = {'ok': r'\rrFok', 'problems': r'\rrFbad', 'flagged': r'\rrFconf', 'passed': r'\rrFpass',
              'not_checked': r'\rrFunk'}
CHECK_STATUSES = tuple(CHECK_ICON)


BASES = ('measured', 'in scope', 'estimate', 'counted from outputs')
EMPTY_RX = re.compile(r'not counted|^\s*(?:--?|\u2014|\?|n/?a)\s*$', re.I)


def load_checks(path, report_items, errors):
    """checks.json of check_stats.py. Every statistic has a value; no text is empty or says "not counted"
    (references/pdf-layout.md: drop a row rather than show an empty one)."""
    try:
        with open(path, encoding='utf-8') as fh:
            ck = json.load(fh)
    except (OSError, ValueError) as ex:
        errors.append('%s: %s' % (path, ex))
        return None
    for c in ck.get('categories', []):
        for ch in c.get('checks', []):
            lab = 'checks.json %s/%s' % (c.get('id'), ch.get('id'))
            if ch.get('status') not in CHECK_STATUSES:
                errors.append('%s: status must be one of %s' % (lab, ', '.join(CHECK_STATUSES)))
            if ch.get('status') == 'not_checked' and not (ch.get('reason') or '').strip():
                errors.append('%s: not_checked needs a reason' % lab)
            amount = (ch.get('amount') or '').strip()
            if ch.get('status') != 'not_checked' and (not amount or EMPTY_RX.search(amount)):
                errors.append('%s: empty amount cell (%r): give what the check covered, or drop the row' % (
                    lab, amount))
            for it in ch.get('items') or []:
                if not isinstance(it, int) or (report_items and it not in report_items):
                    errors.append('%s: item %r is not an item of report.md' % (lab, it))
    for s in ck.get('stats', []):
        lab = 'checks.json stat %s' % s.get('id')
        if not isinstance(s.get('value'), (int, float)) or isinstance(s.get('value'), bool):
            errors.append('%s: empty statistic (value %r): leave the statistic out instead' % (lab, s.get('value')))
        if s.get('basis') not in BASES:
            errors.append('%s: basis must be one of %s' % (lab, ', '.join(BASES)))
        if s.get('basis') == 'estimate' and not (s.get('method') or '').strip():
            errors.append('%s: an estimate needs its method (footnote)' % lab)
        for f in ('label', 'text'):
            if EMPTY_RX.search(s.get(f) or '') or (f == 'label' and not (s.get(f) or '').strip()):
                errors.append('%s: empty or "not counted" %s: %r' % (lab, f, s.get(f)))
    return ck


def stat_mark(s):
    return {'estimate': '*', 'counted from outputs': r'$^\dagger$'}.get(s.get('basis'), '')


def stat_label(s):
    """The label without the '*' check_stats.py may put in it (the mark is added from the basis)."""
    return esc((s.get('label') or '').rstrip('*'))


def stat_notes(stats):
    """The footnote for the marks used: the method of each estimate, the meaning of the dagger."""
    out = []
    est = [s for s in stats if s.get('basis') == 'estimate']
    if est:
        out.append('*\\,estimate, counted by pattern on the sources: ' + '; '.join(
            '%s: %s' % (stat_label(s), esc(s.get('method') or '')) for s in est))
    if any(s.get('basis') == 'counted from outputs' for s in stats):
        out.append(r'$^\dagger$\,counted in a checker\textquoteright{}s output file')
    if any(s.get('basis') == 'in scope' for s in stats):
        out.append(r'\emph{in scope}: counted on the sources; the checker reads all of it by design')
    return '. '.join(out) + ('.' if out else '')


def items_tex(its, k=10, keep=frozenset()):
    """The first k items, linked, then "+N more" (items of keep, those with no mark in the paper, are always shown)."""
    shown = list(its[:k]) + [i for i in its[k:] if i in keep]
    t = ' '.join(r'\rrFitem{%d}' % i for i in shown)
    return t + ((r' {\color{rrmuted}+%d more}' % (len(its) - len(shown))) if len(its) > len(shown) else '')


def stat_cell(s, width=r'\rrFtilew', big=11.5):
    return (r'\parbox[t]{%s}{\raggedright{\fontsize{%s}{%s}\selectfont\bfseries %s%s}\par'
            r'{\fontsize{8}{9.2}\selectfont\bfseries %s\par}{\fontsize{7.2}{8.4}\selectfont\color{rrmuted}%s'
            r'\par}}' % (width, big, big + 1, esc('{:,}'.format(s['value'])), stat_mark(s), stat_label(s),
                         md(s.get('text') or '')))


# density levels of the table pages (build_changes.py raises the level while a page is less than 80% full)
# font, leading, row padding; level 0 (tightest) also puts five statistics in a row
CHECK_DENS = [(8.0, 9.3, 1.2), (8.2, 9.7, 1.6), (8.5, 10.2, 2.0), (8.8, 10.7, 2.4), (9.1, 11.2, 2.8)]


def merged_categories(ck):
    """[(category, rows)] as the table prints them: the checks of one checker that found nothing in a category are
    merged into one row (their amounts joined)."""
    cats = []
    for c in ck.get('categories', []):
        chs = c.get('checks') or []
        for by in list(dict.fromkeys(ch.get('by') for ch in chs)):
            quiet = [ch for ch in chs if ch.get('status') == 'ok' and not ch.get('items') and not ch.get('flags')
                     and ch.get('by') == by]
            if len(quiet) > 1:
                k = chs.index(quiet[0])
                parts = []
                for q in quiet:
                    for a in (q.get('amount') or '').split('; '):
                        if a and a not in parts:
                            parts.append(a)
                merged = dict(quiet[0], what='; '.join(q.get('what', '') for q in quiet), amount='; '.join(parts))
                chs = [ch for ch in chs if ch not in quiet]
                chs.insert(k, merged)
        cats.append((c, chs))
    return cats


def checks_tex(ck, total, nav, report_items=(), split=False, level=1, unmarked=(), rows=(), report=None, cls=None):
    """The "What we checked" page (body text at least 8pt); split=True spreads the table over two pages
    (build_changes.py asks for it when one page overflows at level 0). unmarked: the items with no mark in the
    paper, listed at the end with their state in the copy (their links land there)."""
    fs, lead, pad = CHECK_DENS[max(0, min(level, len(CHECK_DENS) - 1))]
    intro = (r'Every check of this run, by category: what it looked at, how much, what it found. %s. Every number '
             r'was measured in this run: by the scripts, by the checkers on what they read, on the venue rules, on the '
             r'report, and on the sources (\emph{in scope}: what a checker reads by design).' % checks_line(ck, report_items or range(1, total + 1),
                                                                                 total))
    out = [page_open('checks', 'rr-checks') + r'\typeout{rrfront: checks page \thepage}',
           page_head(nav, 'checks', 'What we checked', intro), r'\rrFgap[0.25]{7pt}']
    stats = ck.get('stats') or []
    per = 4
    out.append(r'\setlength{\rrFtilew}{\dimexpr(\linewidth-%dbp)/%d\relax}' % (10 * (per - 1), per))
    cells = [stat_cell(s) for s in stats]
    for i in range(0, len(cells), per):
        out.append(r'\noindent' + r'\hspace{10bp}'.join(cells[i:i + per]) + r'\par\vspace{4pt}')
    notes = stat_notes(stats)
    if notes:
        out.append(r'{\raggedright\fontsize{6.8}{8}\selectfont\color{rrmuted}%s\par}' % notes)
    cats = merged_categories(ck)
    mentions = sum(len({i for ch in chs for i in ch.get('items') or []}) for _, chs in cats)
    uniq = len({i for _, chs in cats for ch in chs for i in ch.get('items') or []})
    head = (r'{\fontsize{%s}{%s}\selectfont\setlength{\fboxsep}{%spt}\setlength{\rrFwa}{13pt}'
            r'\setlength{\rrFwb}{0.40\linewidth}\setlength{\rrFwc}{0.25\linewidth}'
            r'\setlength{\rrFwd}{\dimexpr\linewidth-\rrFwa-\rrFwb-\rrFwc-2\fboxsep\relax}'
            '\n' r'\rrFrow{white}{}{\textcolor{rrmuted}{\textbf{Check} (by)}}{\textcolor{rrmuted}{\textbf{How much}}}'
            r'{\textcolor{rrmuted}{\textbf{Result} (\#n = report item)}}') % (fs, lead, pad)
    legend = (r'}\par\rrFgap{3pt}{\raggedright\fontsize{7}{8.4}\selectfont\color{rrmuted}\rrFok\ nothing found\quad'
              r'\rrFbad\ problems, as report items\quad\rrFconf\ flagged by a script, not an item of the report '
              r'(judged not a problem)\quad\rrFpass\ flags passed to the next checker\quad'
              r'\rrFunk\ not checked.%s\par}' % (
                  (r' An item can belong to several categories: the category heads count %s item mentions for %s '
                   r'distinct items.' % (fmtn(mentions), fmtn(uniq))) if mentions != uniq else ''))
    out.append(r'\vspace{6pt}{\color{rrrule}\hrule}\vspace{5pt}')
    out.append(head)
    brk = None
    if split and len(cats) > 1:   # break before the category that passes half of the rows
        nrows = [len(chs) + 1 for _, chs in cats]
        acc = 0
        for j, n in enumerate(nrows):
            acc += n
            if acc >= sum(nrows) / 2:
                brk = max(j, 1) if j + 1 < len(cats) else len(cats) - 1
                break
    anchored = set()
    for j, (c, chs) in enumerate(cats):
        if j == brk:
            out.append(r'}\par\rrFgap{0pt}')
            out.append(r'\end{rrfullpage}')
            out.append(page_open('checks-2') + page_head(nav, 'checks', 'What we checked', '', cont='page 2 of 2'))
            out.append(head)
        nits = len({i for ch in chs for i in ch.get('items') or []})
        sub = AVOID.get(c.get('id'))
        out.append(r'\par\vspace{%spt}\noindent{\fontsize{%s}{%s}\selectfont\bfseries %s%s}\hfill{\fontsize{7}'
                   r'{8.2}\selectfont\color{rrmuted}%d check%s, %s\par}\vspace{0.3pt}' % (
                       round(2 + pad, 1), round(fs + 0.6, 1), round(lead + 0.9, 1), esc(c.get('label', '')),
                       (r'\,{\mdseries\color{rrmuted} --- %s}' % sub) if sub else '', len(chs),
                       '' if len(chs) == 1 else 's',
                       ('%d report item%s' % (nits, '' if nits == 1 else 's')) if nits else 'no report item'))
        for i, ch in enumerate(chs):
            out.append(check_row(ch, i, set(unmarked), anchored))
    if unmarked:
        out.append(r'\par\vspace{%spt}\noindent{\fontsize{%s}{%s}\selectfont\bfseries Items with no mark in the paper}'
                   r'\hfill{\fontsize{7}{8.2}\selectfont\color{rrmuted}their links land here\par}\vspace{0.3pt}' % (
                       round(2 + pad, 1), round(fs + 0.6, 1), round(lead + 0.9, 1)))
        for i, n in enumerate(unmarked):
            st = '; '.join(dict.fromkeys(r['status'] for r in rows if r.get('item') == str(n) and r.get('status')))
            locs = ', '.join(dict.fromkeys('%s:%s' % (r['file'], r['line']) for r in rows
                                           if r.get('item') == str(n) and r.get('file') and r.get('line')))
            kind = (cls or {}).get(n, ('notapplied',))[0]
            what = item_line((report or {}).get('texts', {}).get(n, ''))
            out.append(r'\rrFrow{%s}{}{\rrFcell{b}{\hypertarget{rrrow-%d}{}\textbf{\#%d}\enspace %s}}{\rrFcell{c}{%s}}'
                       r'{\textcolor{%s}{%s}%s}' % (
                           'rrband' if i % 2 == 0 else 'white', n, n, what,
                           esc('corrected/' + locs) if locs else 'no change in the sources', TAGCOL[kind],
                           SHORT[kind], (': ' + esc(st)) if st and st not in ('applied', 'note') else ''))
    out.append(legend)
    out.append(r'\end{rrfullpage}')
    return '\n'.join(out)


def check_row(ch, i, unmarked=frozenset(), anchored=None):
    st = ch.get('status')
    its = ch.get('items') or []
    if st == 'problems':
        res = r'%d item%s: %s' % (len(its), '' if len(its) == 1 else 's', items_tex(its, 10, unmarked))
        if ch.get('flags'):
            res = r'%d flagged; ' % ch['flags'] + res
    elif st == 'flagged':
        res = r'%d flagged, no report item about %s' % (ch.get('flags', 0), 'it' if ch.get('flags') == 1 else 'them')
    elif st == 'passed':
        res = r'%s flags passed to the next checker' % fmtn(ch.get('flags', 0))
    elif st == 'ok':
        res = r'nothing found'
    else:
        res = r'not checked'
    if ch.get('reason') and st != 'not_checked':
        res += r' {\color{rrmuted}(%s)}' % md(ch['reason'])
    if st == 'not_checked':
        amount = r'{\color{rrmuted}%s}' % md(ch.get('reason') or '')
    else:
        amount = md(ch.get('amount') or '')
        if ch.get('basis') == 'counted from outputs':
            amount += r'$^\dagger$'
    what = r'%s {\color{rrmuted}(%s)}' % (md(ch.get('what', '')), esc(ch.get('by', ''))) if ch.get('by') \
        else md(ch.get('what', ''))
    return r'\rrFrow{%s}{%s}{\rrFcell{b}{%s}}{\rrFcell{c}{%s}}{%s}' % (
        'rrband' if i % 2 == 0 else 'white', CHECK_ICON.get(st, r'\rrFunk'), what, amount, res)


def build(args):
    errors = []
    run = os.path.abspath(args.run_dir)
    p = lambda given, *rel: given or os.path.join(run, *rel)
    report_p, venue_p = p(args.report, 'report.md'), p(args.venue, 'work', 'venue.md')
    status_p, log_p = p(args.status, 'work', 'venue-status.json'), p(args.log, 'work', 'edits.tsv')
    for f in (report_p, venue_p, status_p, log_p, args.root):
        if not os.path.isfile(f):
            errors.append('missing file: %s' % f)
    if errors:
        return None, errors
    report = parse_report(report_p)
    if not report['items']:
        errors.append('report.md: no numbered items found (sections "## N. Title", items "**n.**" or "n. ")')
    with open(venue_p, encoding='utf-8') as fh:
        venue_text = fh.read()
    venue_name = venue_text.strip().split('\n')[0].strip().lstrip('# ').strip()
    vs = load_status(status_p, venue_text, report['items'], errors)
    try:
        rows = read_log(log_p)
    except ValueError as ex:
        errors.append(str(ex))
        rows = []
    cls = classify(rows, report['questions'])
    extra = sorted(set(cls) - report['items'])
    warnings = ['log items not in report.md: %s' % extra] if extra and report['items'] else []
    total = len(report['items'])
    counts = item_counts(report['items'], cls)
    ai_p = getattr(args, 'ai', None) or os.path.join(run, 'work', 'ai-traces.json')
    ai, acts = None, None
    if os.path.isfile(ai_p):
        ai = load_ai(ai_p, venue_text, report['items'], errors)
        acts = read_actions(AI_ACTIONS, errors)
    elif getattr(args, 'ai', None):
        errors.append('missing file: %s' % ai_p)
    ck_p = getattr(args, 'checks', None) or os.path.join(run, 'work', 'checks.json')
    checks = None
    if os.path.isfile(ck_p):
        checks = load_checks(ck_p, report['items'], errors)
    elif getattr(args, 'checks', None):
        errors.append('missing file: %s' % ck_p)
    bib_p = getattr(args, 'bib', None) or os.path.join(run, 'work', 'bib-status.json')
    bib = None
    if os.path.isfile(bib_p):
        bib = load_bib(bib_p, report['items'], errors)
    links, paper_start, per_page = item_links(os.path.splitext(args.root)[0] + '.aux')
    states = read_states(os.path.join(os.path.dirname(os.path.abspath(args.root)), 'r2states.tex'))
    title, authors = paper_meta(args.root)
    title = args.title if args.title is not None else title
    authors = args.authors if args.authors is not None else authors
    if errors:
        return None, errors

    page_of = lambda i: links.get(i, ('', ''))[1]
    decide = sorted((it for it in report['items'] if cls.get(it, ('',))[0] in DECIDE),
                    key=lambda i: (page_key(page_of(i)), i))
    need = len(decide)
    na = [i for i in sorted(report['items']) if cls.get(i, ('notapplied',))[0] == 'notapplied']
    # items with no mark in the paper (known once LaTeX has run: the .aux says where the paper starts)
    unmarked = sorted(i for i in report['items'] if i not in links) if paper_start is not None else []

    lv = dict(DEFAULT_LEVELS, **(getattr(args, 'levels', None) or {}))
    ctx = dict(title=title, authors=authors, venue_name=venue_name, total=total, counts=counts, need=need,
               na=na, report=report, cls=cls, vs=vs, checks=checks, ai=ai, decide=decide, bib=bib, states=states,
               links=links, per_page=per_page, paper_start=paper_start,
               pdf=os.path.join(getattr(args, 'final_dir', None) or run, 'changes.pdf'))
    if is_temporary(ctx['pdf']):
        errors.append('the apply box would name a temporary folder (%s): give the output folder where the user '
                      'finds the files (build_changes.py --final-dir)' % os.path.dirname(ctx['pdf']))
        return None, errors
    have = {'cover': True, 'decisions': bool(decide), 'venue': bool(vs['rules']), 'checks': checks is not None,
            'ai': ai is not None, 'bib': bib is not None}
    nav = [(key, anchor, NAV[key]) for key, anchor, _ in PAGES if have[key]]
    split = getattr(args, 'split', None) or set()
    for k in ('venue', 'checks'):
        if getattr(args, k + '_split', False):
            split = set(split) | {k}
    body = {'cover': lambda: cover_tex(ctx, lv['cover'], nav),
            'decisions': lambda: decisions_tex(decide, cls, report, need, nav, lv['decisions'], states),
            'venue': lambda: venue_page(vs, venue_name, cls, nav, lv['venue'], 'venue' in split, report),
            'bib': lambda: bib_tex(bib, cls, nav, lv['bib'], checks),
            'checks': lambda: checks_tex(checks, total, nav, report['items'], 'checks' in split, lv['checks'],
                                         unmarked=unmarked, rows=rows, report=report, cls=cls),
            'ai': lambda: ai_tex(ai, acts, venue_name, nav)[0]}
    bid = getattr(args, 'build_id', None)
    out = [PRE % {'date': esc(args.date) + ((r'\enspace$\cdot$\enspace build %s' % esc(bid)) if bid else '')}]
    for i in sorted(report['items']):   # where each item's links go (pdf-layout.md, Links)
        if i in links:
            out.append(r'\rrFdef{%d}{%s}{%s}' % (i, links[i][0], links[i][1]))
        else:
            out.append(r'\rrFdef{%d}{rrrow-%d}{--}' % (i, i))
    for key, _, _ in nav:
        out.append(body[key]())
    out.append(r'\endgroup')
    out.append(r'\rrbeginpaper')
    tex = '\n'.join(out) + '\n'
    bad = sorted(set(m.group(0) for m in re.finditer(r'not counted', tex, re.I)))
    if bad:
        return None, ['the front pages would print "%s": leave the statistic or the row out (pdf-layout.md)' % bad[0]]
    for r in vs['rules']:
        if effective_status(r, report) != r.get('status'):
            warnings.append('venue rule %s is "violated" but none of its items (%s) has severity desk-reject: shown as '
                            '"to confirm"' % (r.get('id'), ', '.join('#%d' % i for i in r.get('items') or [])))
    if checks is None and unmarked:
        warnings.append('items with no mark in the paper and no checks page to anchor them: %s' % unmarked)
    return tex, warnings


def item_counts(items, cls):
    counts = {}
    for it in items:
        k = cls.get(it, ('notapplied',))[0]
        counts[k] = counts.get(k, 0) + 1
    assert sum(counts.values()) == len(items)
    return counts


# ---------------------------------------------------------------- page frame
# the front pages, in this order (pdf-layout.md): the summary; the venue's rules (desk-reject risks); the
# bibliography (wrong references are an easy reject); the author's to-do list; the depth of the check; AI use
PAGES = [('cover', 'rr-cover', 'Summary'), ('venue', 'rr-venue', 'Venue rules'),
         ('bib', 'rr-bib', 'Bibliography'), ('decisions', 'rr-decisions', 'Decisions for you'),
         ('checks', 'rr-checks', 'What we checked'), ('ai', 'rr-aitraces', 'Traces of AI use')]
NAV = {'cover': 'Summary', 'venue': 'Venue rules', 'bib': 'Bibliography', 'decisions': 'Decisions',
       'checks': 'What we checked', 'ai': 'AI use'}
# the reviewer pretext each check prevents: page titles, the summary's index and the categories of "What we checked"
AVOID = {'venue': 'Avoid Desk Reject', 'bib': 'Avoid Easy Reject for Wrong References',
         'build': "Avoid `formatting violations'", 'refs': "Avoid `broken references and citations'",
         'numbers': "Avoid `the results do not support the claims'", 'figures': "Avoid `unreadable figures'",
         'language': "Avoid `the paper needs careful proofreading'",
         'notation': "Avoid `undefined notation, hard to follow'",
         'leftovers': "Avoid `the authors did not even reread it'", 'ai': "Avoid `written by ChatGPT'"}
TITLES = {'venue': 'Venue rules', 'bib': 'Bibliography', 'decisions': 'Decisions for you',
          'checks': 'What we checked', 'ai': 'Traces of AI use'}
PAPER_ANCHOR = 'page.1'   # hyperref's anchor of the paper's first page (numbered 1 again after the front pages)


def full_title(key, plain=False):
    """"Venue rules — Avoid Desk Reject": the page title with the pretext it prevents."""
    t = TITLES.get(key, key)
    if key in AVOID:
        return (t + ' --- ' + AVOID[key]) if plain else \
            r'%s\,{\mdseries ---\,%s}' % (t, AVOID[key])
    return t


def nav_tex(nav, cur):
    """The kicker's navigation: every front page and the paper, each a link; the current page in ink."""
    out = []
    for key, anchor, label in nav:
        lab = esc(label.upper())
        out.append(r'\rrFnavon{%s}' % lab if key == cur else r'\hyperlink{%s}{%s}' % (anchor, lab))
    out.append(r'\hyperlink{%s}{PAPER}' % PAPER_ANCHOR)
    return r'\rrFnavsep'.join(out)


def pageno(anchor):
    """The page number of a front page, as a link (the label rrF-<anchor> is set by page_open)."""
    return r'\hyperlink{%s}{\pageref*{rrF-%s}}' % (anchor, anchor)


def page_open(pid, anchor=None):
    out = r'\begin{rrfullpage}[%s]\sffamily\color{rrink}\rrFtopband' % pid
    if anchor:
        out += r'\hypertarget{%s}{}\label{rrF-%s}' % (anchor, anchor)
    return out


def page_head(nav, cur, title, intro, cont=None):
    """Kicker (navigation, date), then the title and one intro line; a continued page: the title, "continued"."""
    out = [r'\rrFkicker{%s}\vspace{9pt}' % nav_tex(nav, cur)]
    if cont:
        out.append(r'\rrFcont{%s (continued)}{%s}\vspace{6pt}' % (title, cont))
    else:
        out.append(r'\rrFtitle{%s}{%s}' % (title, intro))
    return '\n'.join(out)


# ---------------------------------------------------------------- cover
# cover levels (build_changes.py fits the cover through them; the apply box and its strip are on every level): the
# number of "Most Important Errors" listed grows with the level; from 8 errors on, the page strip of the paper
COVER_DENS = [dict(errors=e, strip=e >= 8, fs=8.2, lead=10.0) for e in (3, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28)]
COVER_STATS = ('pages', 'refs', 'numbers', 'sentences', 'venue', 'checkers')   # the cover's depth statistics
DEC_DENS = [(8.6, 10.8, 2.4), (9, 11.5, 3.0), (9.4, 12.2, 3.6), (9.8, 12.9, 4.2), (10.2, 13.6, 4.8)]
BIB_DENS = [(8.0, 9.5, 1.3, 44, 64), (8.0, 9.5, 1.3, 50, 72), (8.0, 9.5, 1.3, 56, 80), (8.0, 9.5, 1.3, 62, 88),
            (8.0, 9.5, 1.3, 68, 96)]   # font, leading, padding, row units on the first page and on the next
DEFAULT_LEVELS = {'cover': 4, 'venue': 0, 'checks': 1, 'decisions': 1, 'ai': 0, 'bib': 2}
MAX_LEVELS = {'cover': len(COVER_DENS) - 1, 'venue': len(VENUE_DENS) - 1, 'checks': len(CHECK_DENS) - 1,
              'decisions': len(DEC_DENS) - 1, 'ai': 0, 'bib': len(BIB_DENS) - 1}
KIND = {k[0]: k for k in KINDS}
SHORT = {'fixed': 'fixed', 'confirm': 'to confirm', 'facts': 'your facts', 'check': 'to check',
         'optional': 'optional wording', 'note': 'note only', 'notapplied': 'not applied'}


def cover_stats(stats, k=6):
    """The cover's statistics: those of COVER_STATS that the run has, topped up by rank."""
    by = {s.get('id'): s for s in stats}
    pick = [by[i] for i in COVER_STATS if i in by]
    for s in stats:
        if len(pick) >= k:
            break
        if s not in pick:
            pick.append(s)
    return pick[:k]


def section_items(report, prefix):
    """(number, items) of the report section whose title starts with prefix, or None."""
    for num, title, its in report['all_sections']:
        if title.lower().startswith(prefix):
            return num, its
    return None


def kind_split(counts, keys):
    return ', '.join('%d %s' % (counts[k], SHORT[k]) for k in keys if counts.get(k))


def kind_bar(counts, total, na=()):
    """All items of the report as one bar, a segment per kind, with the one-line legend under it."""
    shown = [k for k in KINDS if counts.get(k[0])]
    out = [r'\setlength{\rrFbarw}{\linewidth}\noindent\begin{tikzpicture}[x=1bp,y=1bp]']
    acc = 0
    for key, label, sub, col in shown:
        out.append(r'\fill[%s] ({\rrFbarw*%.5f},0) rectangle ({\rrFbarw*%.5f-0.8},6);' % (
            col, acc / total, (acc + counts[key]) / total))
        acc += counts[key]
    out.append(r'\end{tikzpicture}\par\vspace{3pt}')
    leg = []
    for key, label, sub, col in shown:
        t = r'\textbf{%d} %s' % (counts[key], SHORT[key])
        if key == 'facts':
            t += r' {\color{rrmuted}(placeholders} \textcolor{rrorange}{[\#n:\,\dots]}{\color{rrmuted})}'
        if key == 'notapplied' and 0 < len(na) <= 3:
            t += ' (%s)' % ' '.join(r'\rrFitem{%d}' % i for i in na)
        leg.append(r'\mbox{\rrFchip{%s}\,%s}' % (col, t))
    out.append(r'{\raggedright\fontsize{7.2}{9}\selectfont %s\par}' % r'\quad '.join(leg))
    return '\n'.join(out)


def section_bars(report, cls, fs):
    """Items of each report section as a thin bar coloured by kind (colours of the bar above), the count on the right;
    bars to the scale of the largest section."""
    secs = report['sections']
    if not secs:
        return ''
    mx = max(len(its) for _, _, its in secs)
    out = [r'\rrFhead{Items by report section}']
    for num, title, its in secs:
        t = re.sub(r'^Appendix:\s*', '', title)
        lab = '%d. %s' % (num, t[:1].upper() + t[1:])
        segs = []
        for key, _, _, col in KINDS:
            v = sum(1 for i in its if cls.get(i, ('notapplied',))[0] == key)
            if v:
                segs.append(r'\textcolor{%s}{\rule{\dimexpr(\linewidth-24pt)*%d/%d\relax}{5pt}}' % (col, v, mx))
        out.append(r'\noindent{\fontsize{%s}{%s}\selectfont %s}\par\nointerlineskip\vspace{1.5pt}\noindent'
                   r'%s\hspace{4pt}{\fontsize{%s}{%s}\selectfont\bfseries %d}\par\vspace{3.5pt}' % (
                       round(fs - 0.8, 1), round(fs + 0.6, 1), md(lab), ''.join(segs),
                       round(fs - 0.8, 1), round(fs, 1), len(its)))
    return '\n'.join(out)


def checks_summary(ck, report_items):
    """(rows, categories, {status: rows}, items raised) of the "What we checked" table, as it is printed."""
    cats = merged_categories(ck)
    rows = [ch for _, chs in cats for ch in chs]
    st = {}
    for ch in rows:
        st[ch.get('status')] = st.get(ch.get('status'), 0) + 1
    raised = {i for ch in rows for i in ch.get('items') or []} & set(report_items)
    return len(rows), len(cats), st, raised


def checks_line(ck, report_items, total):
    n, ncat, st, raised = checks_summary(ck, report_items)
    bits = []
    for key, txt in (('problems', '%d raised report items'), ('ok', '%d found nothing'),
                     ('passed', '%d passed flags to the next checker'),
                     ('flagged', '%d flagged with no item'), ('not_checked', '%d not run')):
        if st.get(key):
            bits.append(txt % st[key])
    its = ('all %s items' % fmtn(total)) if len(raised) == total else \
        ('%s of the %s items' % (fmtn(len(raised)), fmtn(total)))
    return '%d checks in %d categories: %s; together they raised %s of report.md' % (n, ncat, ', '.join(bits), its)


def fmtn(n):
    return '{:,}'.format(n) if isinstance(n, int) else str(n)


def ai_line(ai):
    arts = ai.get('artifacts') or []
    st = {}
    for a in arts:
        st[a.get('status')] = st.get(a.get('status'), 0) + 1
    bits = ['%d of %d artifact checks found nothing' % (st.get('none', 0), len(arts))]
    for key, txt in (('fail', '%d to fix'), ('check', '%d to check'), ('not_checked', '%d not checked')):
        if st.get(key):
            bits.append(txt % st[key])
    st_ = ((ai.get('disclosure') or {}).get('statement') or {})
    its = (ai.get('disclosure') or {}).get('items') or []
    stmt = 'LLM-use statement present' if st_.get('found') else 'no LLM-use statement in the sources'
    if its:
        stmt += ' (%s)' % ' '.join(r'\rrFitem{%d}' % i for i in its[:3])
    return '%s; %s; style signals measured, never counted as evidence' % (', '.join(bits), stmt)


def bib_line(bib):
    c = bib.get('counts') or {}
    bits = []
    if c.get('refchecker_checked') is not None:
        bits.append('%s entries checked against the databases' % fmtn(c['refchecker_checked']))
    if c.get('not_found'):
        bits.append('%s not found' % fmtn(c['not_found']))
    if c.get('differs'):
        bits.append('%s differ from the record' % fmtn(c['differs']))
    if c.get('changed_in_copy') is not None:
        bits.append('%s changed in this copy' % fmtn(c['changed_in_copy']))
    return ', '.join(bits) or '%d cited entries' % len(bib.get('entries') or [])


def verdict(c):
    """One line from the data: is the paper ready to submit? (violated venue rules the copy does not fix, decisions
    left to the author)."""
    # only real desk-reject risks count: items of severity desk-reject not fixed in the copy, and violated rules
    # with no report item
    open_items = [i for i in desk_items(c['report']) if c['cls'].get(i, ('notapplied',))[0] != 'fixed']
    bare = [r for r in c['vs']['rules'] if r.get('status') == 'violated' and not r.get('items')]
    bits = []
    n = len(open_items) + len(bare)
    if n:
        ref = ' '.join(r'\rrFitem{%d}' % i for i in open_items)
        bits.append(r'%d desk-reject risk%s open in the copy%s' % (n, '' if n == 1 else 's',
                                                                   (' (%s)' % ref) if ref else ''))
    if c['need']:
        bits.append(r'%d decision%s for you (p.~%s)' % (c['need'], '' if c['need'] == 1 else 's',
                                                        pageno('rr-decisions')))
    if bits:
        return r'\textcolor{rrred}{\textbf{Not ready yet:}} ' + '; '.join(bits) + '.'
    return r'\textcolor{rrok}{\textbf{Ready once you review the ticked changes.}} No desk-reject risk is left ' \
        r'open and no decision is left to you.'


def apply_box(c):
    """How to apply the changes: the check-box workflow, with its visual strip (always on the summary page)."""
    path = c['pdf']
    return (r'\noindent\fcolorbox{rrblueframe}{white}{\parbox{\dimexpr\linewidth-2\fboxsep-2\fboxrule\relax}{'
            r'\setlength{\parskip}{0pt}\raggedright\vspace{2pt}{\fontsize{11}{13}\selectfont\bfseries How to apply '
            r'the changes\par}\vspace{5pt}'
            r'\rrFstrip\par\vspace{6pt}'
            r'{\fontsize{9.4}{12}\selectfont'
            r'\hangindent=13pt\hangafter=1\makebox[13pt][l]{\textbf{1.}}\textbf{Mark:} in this PDF, every change has '
            r'a box: \rrboxsym{1}\,will be applied, \rrboxsym{0}\,will not. We pre-set them by how sure we are; '
            r'click to change, and type your answers under the questions of \textit{Decisions}. Save the PDF.'
            r'\par\vspace{3pt}'
            r'\hangindent=13pt\hangafter=1\makebox[13pt][l]{\textbf{2.}}\textbf{Ask your agent:} '
            r"``Apply my choices in {\urlstyle{tt}\path{%s}}''\par}"
            r'\vspace{4pt}{\fontsize{7.6}{9.4}\selectfont\color{rrmuted}The folder corrected/ next to this PDF '
            r'already holds the pre-set choices; \rrboxsym{2}\,items wait for your facts.\par}\vspace{1pt}}}\par' % path)


def minimap(per, npages=None):
    """The paper's pages as a strip of cells coloured by the number of marks on each (from the .aux), each a link."""
    if not per:
        return ''
    n = max(max(per), npages or 0)
    mx = max(per.values())
    cells = []
    for pg in range(1, n + 1):
        v = per.get(pg, 0)
        shade = 0 if not v else max(15, int(100 * v / mx))
        col = 'rrrule!40!white' if not v else 'rrred!%d!white' % shade
        cells.append(r'\hyperlink{page.%d}{\tikz[baseline=0]{\fill[%s] (0,0) rectangle (\rrFcellw-0.6bp,9bp);}}' % (
            pg, col))
    return (r'\rrFheadl{Changes per page of the paper}{darker = more changes; click a page}' '\n'
            r'\setlength{\rrFcellw}{\dimexpr\linewidth/%d\relax}\noindent%s\par\vspace{1pt}'
            r'{\fontsize{6.4}{7.4}\selectfont\color{rrmuted}p.~1\hfill p.~%d\par}' % (n, ''.join(cells), n))


def detex_line(t):
    """LaTeX source quoted in report.md, made readable: $x$ -> x, \\emph{x} -> x, \\name{} -> name, \\% -> %."""
    t = re.sub(r'(?<!\\)\$([^$]*)\$', r'\1', t)
    for _ in range(3):
        t = re.sub(r'\\(?:emph|textbf|textit|texttt|textsc|mathrm|mathit|text|mbox)\{([^{}]*)\}', r'\1', t)
    t = re.sub(r'(?<![\w\\])~(?=\d)', '\u2248', t)   # "~2x" in prose: about
    t = t.replace('\\times', '\u00d7').replace('\\%', '%').replace('\\,', ' ').replace('~', ' ')
    t = re.sub(r'\\([a-zA-Z]+)\{\}', r'\1', t)
    t = re.sub(r'\\([a-zA-Z]+)(?![a-zA-Z{])', r'\1', t)
    return t


def item_line(text, question=None):
    """One line for an item: its question in section 9 of report.md, else the first sentence of its text that is not
    a quotation or a location (the item's text after its `file:line`: prefix), as LaTeX. Never cut: it wraps."""
    if question:
        return md(detex_line(question))
    t = ' '.join((text or '').split())
    t = detex_line(t)
    t = re.sub(r'\s*\*\*\[to check\]\*\*.*$', '', t)
    t = re.sub(r'\s*(?:Fix|Severity|Checkers|\*In the copy)\b.*$', '', t)
    t = re.sub(r'^(?:\s*(?:`[^`]*`|,|and|vs\.?|\([^)]*\)|pp?\.\s*[\d\u2013-]+)\s*)+:\s*', '', t)
    parts = re.split(r'(?<!Trans)(?<!Fig)(?<!Figs)(?<!Proc)(?<! al)(?<! vs)(?<!e\.g)(?<!i\.e)(?<!Sec)(?<!Eq)(?<!Vol)'
                     r'(?<! No)(?<=[a-z0-9)\]`"%])\.\s+(?=[A-Z`"])', t)
    pick = next((x for x in parts if x and not x.startswith(('"', '`', '“'))), parts[0] if parts else '')
    pick = pick.strip().rstrip('.:') + '.'
    return md(pick[:1].upper() + pick[1:])


def important_items(report):
    """The "Most Important Errors": every desk-reject and major item, and the minor items of the desk-reject, numbers
    and other reviewer-visible sections; ranked by severity (desk-reject, major, minor), then numbers and claims
    before the other sections, then the order of the report (never by item number). Optional items are left out."""
    sev = report.get('severity') or {}
    order = report.get('order') or sorted(report['items'])
    sec_rank = {}
    for rank, prefix in enumerate(('desk-reject', 'numbers', 'other')):
        sec = section_items(report, prefix)
        for i in (sec[1] if sec else []):
            sec_rank.setdefault(i, rank)
    pick = [i for i in order if sev.get(i) in ('desk-reject', 'major') or
            (i in sec_rank and sev.get(i, 'minor') == 'minor')]
    return sorted(pick, key=lambda i: (SEV_RANK.get(sev.get(i, 'minor'), 9), sec_rank.get(i, 3), order.index(i)))


def desk_items(report):
    """The items whose severity is desk-reject (the only real desk-reject risks)."""
    sev = report.get('severity') or {}
    return [i for i in (report.get('order') or sorted(report['items'])) if sev.get(i) == 'desk-reject']


def effective_status(rule, report):
    """A rule judged violated whose items are all minor or optional is shown as "to confirm": only a desk-reject item
    makes a rule violated (an optional item cannot)."""
    st = rule.get('status')
    its = rule.get('items') or []
    sev = report.get('severity') or {}
    if st == 'violated' and its and not any(sev.get(i) == 'desk-reject' for i in its):
        return 'confirm'
    return st


def cover_tex(c, level, nav):
    D = COVER_DENS[max(0, min(level, len(COVER_DENS) - 1))]
    report, counts, total, need = c['report'], c['counts'], c['total'], c['need']
    out = [page_open('cover', 'rr-cover')]
    out.append(r'\rrFkicker{%s}\vspace{8pt}' % nav_tex(nav, 'cover'))
    logo = r'\IfFileExists{r2logo.png}{\includegraphics[width=74bp]{r2logo.png}}{}'
    out.append(r'\noindent\begin{minipage}[t]{\dimexpr\linewidth-86bp\relax}\vspace{0pt}')
    out.append(r'{\fontsize{8}{10}\selectfont\color{rrmuted}\bfseries PRE-SUBMISSION CHECK\enspace$\cdot$\enspace '
               r'ANNOTATED COPY\par}\vspace{2pt}')
    out.append(r'{\fontsize{18}{21}\selectfont\bfseries\raggedright %s\par}\vspace{3pt}' % (
        c['title'] or 'Untitled paper'))
    out.append(r'{\raggedright\fontsize{9}{11}\selectfont %s\par}{\fontsize{9}{11}\selectfont\color{rrmuted}Target '
               r'venue: \textcolor{rrink}{\textbf{%s}}\par}' % (c['authors'] or 'Authors not found', esc(c['venue_name'])))
    out.append(r'\vspace{7pt}{\raggedright\fontsize{10}{12.4}\selectfont %s\par}' % verdict(c))
    if not c['vs']['rules']:
        out.append(r'\vspace{3pt}{\raggedright\fontsize{8.6}{10.4}\selectfont\textcolor{rrorange}{\textbf{Venue rules '
                   r'not retrieved:}} check the page limit, anonymity and template in the call yourself.\par}')
    out.append(r'\end{minipage}\hfill\begin{minipage}[t]{74bp}\vspace{0pt}%s\end{minipage}\par' % logo)
    out.append(r'\rrFgap[0.3]{6pt}')
    # ---- headline: what needs the author and the desk-reject risks dominate; the other numbers are smaller
    desk = desk_items(report)
    tiles = []
    if need:
        tiles.append(r'\rrFbig{%d}{\hyperlink{rr-decisions}{need you}}{%s}{rrorange}' % (
            need, kind_split(counts, ('confirm', 'facts', 'check'))))
    else:
        tiles.append(r'\rrFbig{0}{need you}{no decision left to you}{rrok}')
    if desk:
        tiles.append(r'\rrFbig{%d}{desk-reject risk%s}{items of severity desk-reject: %s}{rrred}' % (
            len(desk), '' if len(desk) == 1 else 's', ' '.join(r'\rrFitem{%d}' % i for i in desk[:6])))
    small = [(fmtn(total), 'problems found', 'items of report.md')]
    num = section_items(report, 'numbers')
    if num:
        small.append((fmtn(len(num[1])), 'numbers and claims', 'report section %d' % num[0]))
    applied = counts.get('confirm', 0)
    small.append((fmtn(counts.get('fixed', 0)), 'fixed in the copy',
                  ('+%d to confirm' % applied) if applied else 'red in this copy'))
    st = c['states']
    if st:
        tick = sum(1 for v in st.values() if v[0])
        small.append((fmtn(tick), r'pre-set \rrboxsym{1}', 'of %d boxes' % len(st)))
    nb, ns = len(tiles), len(small)
    out.append(r'\setlength{\rrFtilew}{\dimexpr(\linewidth-%dbp)*10/%d\relax}' % (6 * (nb + ns - 1) + 4 * (nb + ns),
                                                                                  10 * ns + 17 * nb))
    out.append(r'\noindent' + r'\hspace{6bp}'.join(tiles + [r'\rrFsmall{%s}{%s}{%s}' % x for x in small]) +
               r'\par\vspace{6pt}')
    # ---- how deep we looked: one row of six statistics
    stats = cover_stats((c['checks'] or {}).get('stats') or [])
    if stats:
        out.append(r'\rrFheadl{How deep we looked}{every check, also those that found nothing: '
                   r'\hyperlink{rr-checks}{\textbf{What we checked}}, p.~%s}' % pageno('rr-checks'))
        out.append(r'\setlength{\rrFtilew}{\dimexpr(\linewidth-%dbp)/%d\relax}\noindent' % (6 * (len(stats) - 1),
                                                                                            len(stats)) +
                   r'\hspace{6bp}'.join(r'\rrFstat{%s%s}{%s}' % (esc('{:,}'.format(s['value'])), stat_mark(s),
                                                               stat_label(s)) for s in stats) + r'\par')
        notes = stat_notes(stats)
        if notes:
            out.append(r'\vspace{1pt}{\raggedright\fontsize{6.2}{7.2}\selectfont\color{rrmuted}%s\par}' % notes)
    out.append(r'\vspace{7pt}' + kind_bar(counts, total, c['na']))
    out.append(r'\rrFgap[0.5]{9pt}')
    out.append(apply_box(c))
    out.append(r'\rrFgap{9pt}')
    # ---- the most important errors, as many as the level allows
    imp = important_items(report)
    if imp:
        shown = imp[:D['errors']]
        more = (r'%d of %d; the rest: \hyperlink{rr-decisions}{decision sheet} and report.md' % (
            len(shown), len(imp))) if len(shown) < len(imp) else r'all %d' % len(imp)
        out.append(r'\rrFheadl{Most Important Errors}{by severity; %s}' % more)
        out.append(r'{\fontsize{%s}{%s}\selectfont' % (D['fs'], D['lead']))
        for k, i in enumerate(shown):
            stt = st.get(i)
            box = (r'\rrboxsym{%d}' % int(stt[0])) if stt and not stt[1] else \
                (r'\rrboxsym{2}' if stt else r'\phantom{\rrboxsym{0}}')
            pg = (r'p.~\rrFpage{%d}' % i) if i in c['links'] else ''
            kind = c['cls'].get(i, ('notapplied',))[0]
            sv = report.get('severity', {}).get(i, 'minor')
            out.append(r'\noindent\colorbox{%s}{\parbox[t]{\dimexpr\linewidth-2\fboxsep\relax}{\makebox[10pt][l]{%s}'
                       r'\makebox[24pt][l]{\rrFitem{%d}}\makebox[44pt][l]{\textcolor{%s}{\fontsize{6.4}{7}\selectfont'
                       r'\bfseries %s}}\parbox[t]{\dimexpr\linewidth-144pt\relax}{\raggedright %s}'
                       r'\hfill\makebox[24pt][r]{%s}\hspace{2pt}\makebox[34pt][r]{\textcolor{%s}{\fontsize{6.4}{7}'
                       r'\selectfont %s}}}}\par\nointerlineskip' % (
                           'rrband' if k % 2 == 0 else 'white', box, i, SEV_COL[sv], sv,
                           item_line(report['texts'].get(i, ''), report['questions'].get(i)), pg,
                           TAGCOL[kind], SHORT[kind].replace(' wording', '')))
        out.append(r'}\par')
    if D['strip'] and c['per_page']:
        out.append(r'\rrFgap[0.5]{9pt}' + minimap(c['per_page']))
    out.append(r'\end{rrfullpage}')
    return '\n'.join(out)


# ---------------------------------------------------------------- bibliography
def load_bib(path, report_items, errors):
    """work/bib-status.json of bib_status.py (format there): items must be items of report.md."""
    try:
        with open(path, encoding='utf-8') as fh:
            bs = json.load(fh)
    except (OSError, ValueError) as ex:
        errors.append('%s: %s' % (path, ex))
        return None
    for e in bs.get('entries', []):
        for it in e.get('items') or []:
            if not isinstance(it, int) or (report_items and it not in report_items):
                errors.append('bib-status.json %s: item %r is not an item of report.md' % (e.get('key'), it))
        if e.get('db') not in ('matched', 'differs', 'not_found', 'not_checked'):
            errors.append('bib-status.json %s: db must be matched, differs, not_found or not_checked' % e.get('key'))
    return bs


def bib_tex(bs, cls, nav, level=1, checks=None):
    """The bibliography page(s): the counts of the run's reference checks, then one row per cited entry that the
    databases flagged, that an item changes for its content, or whose identifiers could not be looked up; the
    entries changed only for a uniform style, or with nothing to say, in a compact list at the end."""
    fs, lead, pad, first_cap, per_cap = BIB_DENS[max(0, min(level, len(BIB_DENS) - 1))]
    c = bs.get('counts') or {}
    E = bs.get('entries') or []
    style_items = set()
    for cat in (checks or {}).get('categories', []):
        for ch in cat.get('checks', []):
            if ch.get('id') == 'bib_style':
                style_items |= set(ch.get('items') or [])
    matched = sum(1 for e in E if e.get('db') == 'matched')
    cells = []

    def cell(v, label, text):
        cells.append(r'\parbox[t]{\rrFtilew}{\raggedright{\fontsize{12.5}{13.5}\selectfont\bfseries %s}\par'
                     r'{\fontsize{8}{9.2}\selectfont\bfseries %s\par}{\fontsize{7.2}{8.4}\selectfont\color{rrmuted}%s'
                     r'\par}}' % (v, label, text))
    if c.get('cited') is not None:
        cell(fmtn(c['cited']), 'entries cited', ('of %s in the .bib' % fmtn(c['bib_entries']))
             if c.get('bib_entries') is not None else 'every cited entry is listed here')
    if c.get('refchecker_checked') is not None:
        cell(fmtn(c['refchecker_checked']), 'checked against the databases',
             'RefChecker (DBLP, Crossref, OpenAlex, ...): %s match, %s differ, %s not found' % (
                 fmtn(matched), fmtn(c.get('differs', 0)), fmtn(c.get('not_found', 0))))
    if c.get('dois') is not None:
        cell('%s of %s' % (fmtn(c.get('dois_looked_up', 0)), fmtn(c['dois'])), 'DOIs resolved',
             'each DOI looked up (Crossref, DataCite) and its title compared')
    if c.get('arxiv_ids') is not None:
        sk = [x for x in bs.get('skipped') or [] if 'arxiv' in x.lower()]
        cell('%s of %s' % (fmtn(c.get('arxiv_looked_up', 0)), fmtn(c['arxiv_ids'])), 'arXiv IDs looked up',
             md(sk[0]) if sk else 'arXiv API')
    if c.get('preprints') is not None:
        cell('%s of %s' % (fmtn(c.get('preprints_checked', 0)), fmtn(c['preprints'])), 'preprints checked',
             'for a published version (local DBLP database, arXiv record)')
    if c.get('style_differences') is not None:
        cell(fmtn(c['style_differences']), 'style differences',
             'in %s entries; %s features compared on %s entries' % (
                 fmtn(c.get('style_flagged_entries', 0)), fmtn(c.get('style_features', 0)),
                 fmtn(c.get('style_entries', 0))))
    if c.get('changed_in_copy') is not None:
        nit = len({i for e in E for i in e.get('items') or []})
        cell(fmtn(c['changed_in_copy']), 'entries changed in this copy', 'by %s report items' % fmtn(nit))
    tocheck = [e for e in E if e.get('db') in ('not_found', 'differs') and not e.get('items')
               and not e.get('db_artefact')]
    cell(fmtn(len(tocheck)), 'to check by you', 'flagged by the databases, no item changes them')

    def kinds(its):
        return ' '.join(r'\rrFitem{%d}' % i for i in its) + (r'\enspace ' + copy_tag(its, cls) if its else '')

    def link(key):
        shown = re.sub(r'([_\-:.]|[a-z](?=[0-9])|.{12}(?=.))', lambda m: m.group(0) + '\x00', key)
        return r'\hyperlink{cite.%s}{\texttt{%s}}' % (key, esc(shown).replace('\x00', r'\allowbreak{}'))
    # a database "difference" that is only a parse artefact (braces, an escaped _, a title cut at its colon) is no
    # flag: such an entry is listed with the matching ones unless an item changes it
    flagged = lambda e: e.get('db') != 'matched' and not e.get('db_artefact')
    full = [e for e in E if flagged(e) or set(e.get('items') or []) - style_items]
    order = {'not_found': 0, 'differs': 1, 'not_checked': 2, 'matched': 3}
    full.sort(key=lambda e: (order.get(e.get('db'), 9), e['key'].lower()))
    rest = [e for e in E if e not in full]
    rows = []
    for e in full:
        db = {'matched': 'matches the record', 'not_found': r'\textbf{not found} in any database',
              'differs': r'differs: ', 'not_checked': 'not checked'}[e.get('db')]
        if e.get('db_artefact'):
            db = 'matches the record'
        elif e.get('db') in ('differs', 'not_found') and e.get('db_detail'):
            db += md(e['db_detail']) if e.get('db') == 'differs' else ' (%s)' % md(e['db_detail'])
        ids = []
        if e.get('doi'):
            ids.append('DOI ' + ('resolved' if e.get('doi_checked') else 'not looked up'))
        if e.get('arxiv'):
            ids.append('arXiv ' + ('looked up' if e.get('arxiv_checked') else r'\textcolor{rrorange}{not looked up}'))
        if e.get('preprint'):
            ids.append('preprint ' + ('searched' if e.get('preprint_checked') else 'not searched'))
        its = e.get('items') or []
        ids = ids or [r'{\color{rrmuted}no DOI or arXiv ID}']
        applied = [i for i in its if cls.get(i, ('notapplied',))[0] in ('fixed', 'confirm', 'optional')]
        if applied:
            icon = r'\rrFchg'          # changed in the copy
        elif its:
            icon = r'\rrFbad'          # a problem found (report item), nothing changed in the copy
        elif flagged(e) and e.get('db') in ('not_found', 'differs'):
            icon = r'\rrFconf'
        elif e.get('arxiv_checked') is False and e.get('db') != 'matched':
            icon = r'\rrFunk'
        else:
            icon = r'\rrFok'
        # lines of the row (the widest column decides): characters per line of each column at 8pt
        plain = lambda t: re.sub(r'\\[a-zA-Z]+\*?|[{}]', '', t)
        units = 0.25 + max(-(-(len(e['key']) + 5) // 30), -(-len(plain(db)) // 46), -(-len(plain(', '.join(ids))) // 21),
                           -(-(5 * len(its) + 10) // 24) if its else 1)
        rows.append((units, r'\rrFrowe{@@BG@@}{%s}{\rrFcell{b}{%s {\color{rrmuted}%s}}}{\rrFcell{c}{%s}}{%s}{%s}' % (
            icon, link(e['key']), esc(e.get('year') or ''), db, ', '.join(ids) or '--',
            kinds(its) if its else (r'{\color{rrmuted}%d style flag%s}' % (len(e.get('style') or []), '' if len(
                e.get('style') or []) == 1 else 's') if e.get('style') else ''))))
    def paginate(f):
        pages, cur, cap, used = [], [], first_cap * f, 0
        for u, r in rows:
            if used + u > cap and cur:
                pages.append(cur)
                cur, used, cap = [], 0, per_cap * f
            cur.append(r)
            used += u
        pages.append(cur)
        return pages
    pages = paginate(1.0)   # each page filled in turn: the compact list at the end goes on the last one
    head = (r'{\fontsize{%s}{%s}\selectfont\setlength{\fboxsep}{%spt}\setlength{\rrFwa}{13pt}'
            r'\setlength{\rrFwb}{0.24\linewidth}\setlength{\rrFwd}{0.17\linewidth}\setlength{\rrFwe}{0.19\linewidth}'
            r'\setlength{\rrFwc}{\dimexpr\linewidth-\rrFwa-\rrFwb-\rrFwd-\rrFwe-2\fboxsep\relax}' '\n'
            r'\rrFrowe{white}{}{\textcolor{rrmuted}{\textbf{Entry} (year)}}{\textcolor{rrmuted}{\textbf{Databases '
            r'(RefChecker)}}}{\textcolor{rrmuted}{\textbf{Identifiers}}}{\textcolor{rrmuted}{\textbf{In the copy}}}'
            % (fs, lead, pad))
    intro = (r'Every cited entry of the .bib: what the reference databases say about it, whether its DOI and arXiv '
             r'IDs could be looked up, and what this copy changed, from the reference checks of this run and the '
             r'report. Click an entry for its place in the '
             r'marked bibliography, \#n for the change.')
    out = []
    for k, pg in enumerate(pages):
        pid = 'bib' if k == 0 else 'bib-%d' % (k + 1)
        out.append(page_open(pid, 'rr-bib' if k == 0 else None))
        if k == 0:
            out.append(page_head(nav, 'bib', full_title('bib'), intro))
            out.append(r'\vspace{9pt}\setlength{\rrFtilew}{\dimexpr(\linewidth-30bp)/4\relax}')
            for i in range(0, len(cells), 4):
                out.append(r'\noindent' + r'\hspace{10bp}'.join(cells[i:i + 4]) + r'\par\vspace{5pt}')
            out.append(r'\vspace{4pt}{\color{rrrule}\hrule}\vspace{5pt}')
        else:
            out.append(page_head(nav, 'bib', full_title('bib'), '', cont='page %d of %d' % (k + 1, len(pages))))
        out.append(head)
        for i, r in enumerate(pg):
            out.append(r.replace('@@BG@@', 'rrband' if i % 2 == 0 else 'white'))
        out.append(r'}\par')
        if k < len(pages) - 1:
            out.append(r'\rrFgap{0pt}')
        if k == len(pages) - 1:
            if rest:
                out.append(r'\vspace{8pt}{\raggedright\fontsize{%s}{%s}\selectfont\textbf{%d more entries match the '
                           r'record}; the copy changes them only for a uniform style (%s) or not at all. '
                           r'{\color{rrorange}Orange}: its arXiv ID could not be looked up.\par\vspace{2pt}'
                           r'%s\par}' % (fs, lead + 1, len(rest), ' '.join(r'\rrFitem{%d}' % i for i in sorted(
                               {i for e in rest for i in e.get('items') or []})),
                                         r' \enspace '.join(r'\mbox{%s%s%s}' % (
                                             r'\color{rrorange}' if e.get('arxiv_checked') is False else '',
                                             link(e['key']), (
                                             r'\,{\color{rrmuted}\fontsize{6.6}{7}\selectfont %s}' % ' '.join(
                                                 r'\#%d' % i for i in e['items'])) if e.get('items') else '')
                                                           for e in rest)))
            out.append(r'\rrFgap{4pt}{\raggedright\fontsize{7}{8.4}\selectfont\color{rrmuted}\rrFok\ matches the '
                       r'record, nothing to change\quad\rrFchg\ changed in the copy (report item)\quad\rrFbad\ problem found (report '
                       r'item), not changed: see the item\quad\rrFconf\ '
                       r'flagged, no item: check it\quad\rrFunk\ not checked. A database disagreement is often a '
                       r'false alarm (an arXiv year, a software page): the items say which ones were real.\par}')
        out.append(r'\end{rrfullpage}')
    return '\n'.join(out)


# ---------------------------------------------------------------- decisions
DEC_PER_PAGE = 30     # row units per page: a line of question is 1 unit, an answer field ANSWER_UNITS more
ANSWER_UNITS = 3.0


def decision_question(it, cls, report):
    """(LaTeX text of the row's question, whether it gets an answer field): the item's question in section 9 of
    report.md, else the question of its edits, else "Give: <what>" of its placeholder (all answerable in words)."""
    k, qs, whats = cls[it]
    if it in report['questions']:
        return md(report['questions'][it]), True
    if qs:
        return esc_prose(qs[0]), True
    if whats:
        return 'Give: ' + esc_prose(whats[0]), True
    return 'See the margin note.', False


def decision_chunks(units):
    """Split rows of the given units into pages of at most about DEC_PER_PAGE units, every page about as full:
    [[row index, ...], ...]."""
    total = sum(units)
    if not units:
        return []
    npages = max(1, -(-int(total * 100) // (DEC_PER_PAGE * 100)))
    target = total / npages
    chunks, cum = [[] for _ in range(npages)], 0.0
    for i, u in enumerate(units):
        chunks[min(npages - 1, int((cum + u / 2) / target))].append(i)
        cum += u
    return [c for c in chunks if c]


def decisions_tex(decide, cls, report, need, nav, level=1, states=None):
    states = states or {}
    fs, lead, pad = DEC_DENS[max(0, min(level, len(DEC_DENS) - 1))]
    qa = {it: decision_question(it, cls, report) for it in decide}
    # a row's units: its question's lines (about 95 characters each) plus the answer field
    chunks = [[decide[i] for i in c] for c in decision_chunks([
        max(1, -(-len(qa[it][0]) // 95)) + (ANSWER_UNITS if qa[it][1] else 0) for it in decide])]
    out = [r'\rrbeginform']
    kc = {}
    for it in decide:
        kc[cls[it][0]] = kc.get(cls[it][0], 0) + 1
    split = ', '.join(r'%d %s' % (kc[k], SHORT[k]) for k in ('confirm', 'facts', 'check') if kc.get(k))
    meaning = {'confirm': 'a fix is applied in orange: keep or revert it',
               'facts': 'an orange placeholder awaits a fact only you have',
               'check': 'nothing changed: something to verify'}
    intro = (r'\textcolor{rrink}{\textbf{%d item%s}, in the order of the paper\textquoteright{}s pages: %s.} %s. '
             r'The box is the item\textquoteright{}s choice, the same as next to its change in the paper: '
             r'\rrboxsym{1}\,= will be applied, \rrboxsym{0}\,= will not; click to change, then save the PDF. '
             r'\rrboxsym{2}\,= waits for your facts and cannot be ticked. Click \#n or the page to jump to the change; '
             r'its margin note gives the evidence. \textbf{Answers in words} (a value, a reason, which of two numbers '
             r'is right): type them in the box under the question (or tell your agent in the chat); save the PDF '
             r'and ask your agent to apply your choices: it reads the boxes and the answers.' % (
                 need, '' if need == 1 else 's', split,
                 '; '.join('%s = %s' % (DECIDE[k], meaning[k]) for k in ('confirm', 'facts', 'check') if kc.get(k))))
    for c, chunk in enumerate(chunks):
        out.append(page_open('decisions-%d' % (c + 1), 'rr-decisions' if c == 0 else None))
        out.append(page_head(nav, 'decisions', 'Decisions for you', intro,
                             cont=('page %d of %d' % (c + 1, len(chunks))) if c else None))
        out.append(r'\vspace{10pt}' if c == 0 else '')
        out.append(r'{\fontsize{%s}{%s}\selectfont\setlength{\fboxsep}{%spt}' % (fs, lead, pad))
        out.append(r'\rrFdrow{white}{}{\textcolor{rrmuted}{\textbf{Item}}}{\textcolor{rrmuted}{\textbf{Page}}}'
                   r'{\textcolor{rrmuted}{\textbf{Kind}}}{\textcolor{rrmuted}{\textbf{Decision or fact '
                   r'needed}}}')
        for i, it in enumerate(chunk):
            k = cls[it][0]
            q, answerable = qa[it]
            box = (r'\raisebox{-1pt}{\rritembox{%d}}' % it) if it in states else ''
            bg = 'rrband' if i % 2 == 0 else 'white'
            out.append(r'\rrFdrow{%s}{%s}{\rrFitem{%d}}{\rrFpage{%d}}{%s}{%s}' % (
                bg, box, it, it, DECIDE[k],
                r'{\fontsize{6.6}{7.6}\selectfont\bfseries\color{%s}%s}\enspace %s' % (
                    SEV_COL[report.get('severity', {}).get(it, 'minor')], report.get('severity', {}).get(it, 'minor'), q)))
            if answerable:   # the text field "answer-<item>" right under the question (read_choices.py reads it)
                out.append(r'\rrFdans{%s}{%d}' % (bg, it))
        out.append(r'}')
        out.append(r'\end{rrfullpage}')
    out.append(r'\rrendform')
    return '\n'.join(out)


FILL_MIN = 0.80   # a front page with less content than this share of its height gets a warning (pdf-layout.md)
FILL_TARGET = 0.90   # build_changes.py raises the level of a page under this share while the page has a next level


def fill_of(log_text):
    """[{id, key, page, natural, full, ratio}] from the "rrfront fill" lines of a LaTeX log (last run only)."""
    out = []
    for m in re.finditer(r'rrfront fill: id=(\S+) page=(\S+) natural=([\d.]+)pt full=([\d.]+)pt', log_text):
        nat, full = float(m.group(3)), float(m.group(4))
        out.append(dict(id=m.group(1), key=re.sub(r'-\d+$', '', m.group(1)), page=m.group(2), natural=nat,
                        full=full, ratio=nat / full if full else 0.0))
    return out


def fill_warnings(fills):
    msgs = []
    for f in fills:
        if f['ratio'] > 1.0:
            msgs.append('front page %s (%s) overflows: %.0f%% of the page' % (f['page'], f['id'], 100 * f['ratio']))
        elif f['ratio'] < FILL_MIN:
            msgs.append('front page %s (%s) is only %.0f%% full (under %.0f%%): add content or raise its level '
                        '(pdf-layout.md)' % (f['page'], f['id'], 100 * f['ratio'], 100 * FILL_MIN))
    return msgs


def esc_prose(s):
    """Question and placeholder texts of the edit log are LaTeX prose, as in the margin notes."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    from apply_edits import esc_prose as ep
    return ep(s)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('run_dir')
    ap.add_argument('root')
    ap.add_argument('--out', default=None)
    ap.add_argument('--date', default=datetime.date.today().isoformat())
    ap.add_argument('--title', default=None)
    ap.add_argument('--authors', default=None)
    ap.add_argument('--level', action='append', default=[], metavar='PAGE=N',
                    help='layout level of a page (cover, venue, checks, decisions; see pdf-layout.md); repeatable')
    for f in ('report', 'venue', 'status', 'log'):
        ap.add_argument('--' + f, default=None)
    ap.add_argument('--ai', default=None, help='work/ai-traces.json (default: in RUN_DIR; no page if it is missing)')
    ap.add_argument('--checks', default=None,
                    help='work/checks.json of check_stats.py (default: in RUN_DIR; no page if it is missing)')
    ap.add_argument('--final-dir', default=None,
                    help='the output folder as the user will find it (the apply box names it; default RUN_DIR, which '
                         'must then not be a temporary folder)')
    ap.add_argument('--build-id', default=None, help='printed in the kicker of every front page')
    args = ap.parse_args()
    args.levels = {}
    for lv in args.level:
        k, _, v = lv.partition('=')
        if k not in MAX_LEVELS or not v.isdigit():
            ap.error('--level PAGE=N with PAGE in %s' % ', '.join(MAX_LEVELS))
        args.levels[k] = int(v)
    tex, msgs = build(args)
    if tex is None:
        print('ERRORS (%d): front pages not written' % len(msgs), file=sys.stderr)
        for m in msgs:
            print('  ' + m, file=sys.stderr)
        return 1
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.root)), 'rrfront.tex')
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(tex)
    log = os.path.splitext(os.path.abspath(args.root))[0] + '.log'
    if os.path.isfile(log):   # the fill of the previous LaTeX run
        with open(log, encoding='latin-1') as fh:
            fills = fill_of(fh.read())
        if fills:
            print('fill of the last LaTeX run: ' + ', '.join('%s %.0f%%' % (f['id'], 100 * f['ratio']) for f in fills))
        msgs = msgs + fill_warnings(fills)
    for m in msgs:
        print('warning: ' + m)
    print('front pages written: %s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
