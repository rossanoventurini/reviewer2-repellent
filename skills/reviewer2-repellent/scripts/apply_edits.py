#!/usr/bin/env python3
"""Apply the fixes of a report to a LaTeX paper (step 6): a clean corrected copy and a marked copy for the
annotated PDF, with every change wrapped in the r2changes mark of its item.

Usage: python3 apply_edits.py SPEC.json PAPER_DIR CORRECTED_DIR MARKED_DIR [--log edits.tsv] [--force]
                              [--loc-prefix corrected] [--choices choices.json | --only 3,7,12]

PAPER_DIR is copied to CORRECTED_DIR and MARKED_DIR (both must not exist, or be empty, unless --force), then the
edits of SPEC.json are applied in order. SPEC.json is a list of edits:
  {"item": 12,                     report item number
   "file": "sections/x.tex",       path relative to PAPER_DIR
   "kind": "fix",                  fix | check | style | missing | note | raw | log
   "old": "...", "new": "...",     text replaced in the corrected copy (old "" = insertion at the @@ of ctx)
   "ctx": "...",                   optional: context found exactly once in the file and containing old, or
                                   containing @@ where the text goes (insertions; or where old starts)
   "plain": false,                 use \\rrfixplain/\\rrcheckplain/\\rrstyleplain (math, tables, captions, titles)
   "question": "...",              required for check: the note says "To check: <question>"
   "note": "...",                  margin note (\\rrnote) for the item: what was wrong, the evidence, the change
                                   (up to about 60 words)
   "note_short": "...",            optional short note (up to about 25 words: what was wrong and the change),
                                   printed instead of the note on a crowded page (build_changes.py)
   "note_ctx": "...", "note_file": "...",  where the note goes, if not next to the edit (@@ or end of note_ctx)
   "what": "...",                  missing: what the authors must supply (falls back to "new")
   "mark": "...", "count": 1,      raw: text written in the marked copy (default: new); occurrences (or "all")
   "confidence": "high",           optional: high | medium | low, how sure the agent is that the change is right
                                   (sets the default of the item's check box; all edits of an item count)
   "status": "..."}                optional: overrides the status written in the log (log: required)
Kinds: fix -> \\rrfix{n}{old}{new}; check -> \\rrcheck{n}{old}{new}{question}; style -> \\rrstyle{n}{old}{new};
missing -> \\rrmissing{n}{what} at the @@ of ctx (or after ctx) in the marked copy and "% TODO #n: what" at the end
of that line in the corrected copy; note -> only a margin note at the @@ of ctx (or after ctx); raw -> old replaced
by new in the corrected copy and by mark in the marked copy, for edits the marks cannot express; log -> only a log
line (an item not applied, or applied by another one).
Context is matched exactly first, then with any run of whitespace matching any other (line breaks may differ).
Notes: one \\rrnote[<corrected>/file:line]{n}{text} per item (the texts of its edits are merged; file:line is the
item's change in the corrected copy), placed at the end of the sentence or paragraph holding the item's first edit
with a note, or at the first note / note_ctx of the item. The note of a raw edit goes at the start of its text:
the end of the first sentence of its first paragraph (headings skipped). A note whose place falls inside the text
of a raw edit (a ctx in a moved block) goes at the same place in its mark (found by the text around it), or at the
start of the mark. A note never goes inside a float, table, caption,
footnote, heading, math or verbatim: it moves after that environment or group. An item to check (a question) whose
change shows no mark in the text (preamble, raw edit without a tag, note only) gets an orange \\rrcheckmark{n}
before its note. Items with a note_short get \\rrnotepair[...]{n}{note}{short} instead, the short text being
"To check. " (items with a question) + note_short + " See report #n." (unless it already cites the report).
An item to check whose marks lie far from its note (another file, or more than REPEAT_GAP characters away) gets a
one-line note with the first sentence of its question at each of those marks.
Warnings (not errors): a note over 60 words; a note over 30 words without note_short; nothing invented: the new
text of a fix, check, style or raw edit (not .bib) with a term, a number or a causal explanation ("because",
"thanks to", ...) that the paper's .tex files do not have (numbers may also come from the item's note or question,
where the computation is shown) -- the applied text only restates the paper, mechanisms go to the question or the
note; a missing-facts placeholder about a submission file (highlights, declarations as separate files): a note,
not text. With --strict these lint findings are errors.
Edits of .bib files (kinds fix, check, style, raw) change both copies the same way, without marks: the marked
bibliography comes from mark_bbl.py, and their notes go in its map (a "note" on a .bib edit is an error).
Note, question and what texts are prose: _ % & # are escaped outside math unless already escaped; outside math
they may use inline formatting (\\emph, \\textbf, \\texttt, ...), \\ref, \\cite, \\url, \\href and commands the paper
uses, never structural ones (\\verb, \\label, \\footnote, \\item, \\caption, \\section, \\begin, ...): an error.
A fix, check or style whose old or new text has a line break (\\\\ outside braces and math, as in a TikZ node or a
table cell) is marked line by line, {\\color{..}line}\\\\...\\rrtag{..}{n}, without the struck old text (a warning).
The marked copy gets \\usepackage{r2changes} at the end of its preamble and a copy of ../assets/r2changes.sty.
Choices. Every item with something to apply (fix, check, style, raw edits) gets one check box in changes.pdf
("do it" / "don't"), pre-set from how likely the change is right: fix and raw -> do; check -> do when its confidence
is high or medium (the default for check), else don't; style (optional wording) -> don't unless "confidence": "high";
any edit with "confidence": "low" -> don't. Items with a missing edit ("your facts") get a disabled box, never
ticked: none of their changes is applied until the authors give the facts (the % TODO comments are written);
note-only and log items get none. The defaults go to r2states.tex next to the main file
of the marked copy (\rritemstate{n}{1|0}{readonly 1|0}{reason}, read by r2changes.sty). CORRECTED_DIR gets exactly
the items that are ticked: the defaults, or the author's choices with --choices (work/choices.json of
read_choices.py: "do" items applied, the others not; items it does not list keep their default) or --only (these
items and no other). All edits of an item go together. "% TODO #n" comments of missing facts are always written.
The log status of an edit left out is "not chosen (...)".
Errors (context missing or not unique, old not in ctx, check without question, unbalanced braces or a bare % in a
mark, overlapping edits) are all listed and exit with status 1, and nothing is written.
Log (TSV, one line per edit): item, kind, file, line in the corrected copy, status, question (check items and
questions of notes), what (missing). Python stdlib only.
"""
import argparse
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STY = os.path.join(HERE, '..', 'assets', 'r2changes.sty')
LOGO = os.path.join(HERE, '..', 'assets', 'r2logo.png')
KINDS = ('fix', 'check', 'style', 'missing', 'note', 'raw', 'log')
STATUS = {'fix': 'applied', 'check': 'to check', 'style': 'optional', 'missing': 'missing facts',
          'note': 'note', 'raw': 'applied', 'log': ''}

# ---------------------------------------------------------------- LaTeX helpers

def unescaped(s, i):
    """True if s[i] is not preceded by an odd number of backslashes."""
    k = i - 1
    n = 0
    while k >= 0 and s[k] == '\\':
        n += 1
        k -= 1
    return n % 2 == 0


def brace_balance(s):
    """(final depth, min depth) of unescaped braces in s, ignoring comments."""
    d = mn = 0
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '\\':
            i += 2
            continue
        if ch == '%':
            j = s.find('\n', i)
            i = len(s) if j < 0 else j
            continue
        if ch == '{':
            d += 1
        elif ch == '}':
            d -= 1
            mn = min(mn, d)
        i += 1
    return d, mn


def balanced(s):
    d, mn = brace_balance(s)
    return d == 0 and mn == 0


def has_bare_percent(s):
    return any(ch == '%' and unescaped(s, i) for i, ch in enumerate(s))


REF_CMDS = {'ref', 'eqref', 'cref', 'Cref', 'autoref', 'pageref', 'label', 'url', 'href', 'cite', 'citep', 'citet',
            'citealp', 'citeauthor', 'citeyear', 'nocite', 'input', 'include', 'includegraphics', 'doi'}


def esc_prose(s):
    """Escape _ % & # (and -> < >) in prose (not in math, not already escaped, not in \\ref/\\cite/\\url arguments)."""
    out = []
    i, n = 0, len(s)
    math = None  # closing delimiter while inside math
    while i < n:
        ch = s[i]
        if ch == '\\':
            m = re.match(r'\\([A-Za-z]+)\*?', s[i:])
            if m:
                out.append(m.group(0))
                i += m.end()
                if m.group(1) in REF_CMDS:
                    while i < n and s[i] in '[{':      # copy the arguments verbatim
                        close = ']' if s[i] == '[' else '}'
                        d, j = 0, i
                        while j < n:
                            if s[j] == s[i]:
                                d += 1
                            elif s[j] == close:
                                d -= 1
                                if d == 0:
                                    break
                            j += 1
                        out.append(s[i:j + 1])
                        i = j + 1
                continue
            two = s[i:i + 2]
            if math is None and two in ('\\(', '\\['):
                math = '\\)' if two == '\\(' else '\\]'
            elif math is not None and two == math:
                math = None
            out.append(two)
            i += 2
            continue
        if ch == '$':
            dd = s[i:i + 2] == '$$'
            tok = '$$' if dd else '$'
            if math is None:
                math = tok
            elif math == tok:
                math = None
            out.append(tok)
            i += len(tok)
            continue
        if math is None and s.startswith('->', i):
            out.append('$\\to$')
            i += 2
            continue
        if math is None and ch in '<>':
            out.append('\\textless{}' if ch == '<' else '\\textgreater{}')
        elif ch == '%' or (math is None and ch in '_&#'):
            out.append('\\' + ch)
        else:
            out.append(ch)
        i += 1
    return ''.join(out)


def esc_path(s):
    """A file:line location as LaTeX text (typewriter)."""
    return ''.join({'_': '\\_', '#': '\\#', '%': '\\%', '&': '\\&', '$': '\\$', '~': '\\textasciitilde{}',
                    '^': '\\textasciicircum{}', '{': '\\{', '}': '\\}', '\\': '/'}.get(ch, ch) for ch in s)


# Commands a margin note (note, note_short, question, what) may use outside math: inline formatting, references
# and symbols (\\url, \\href: the annotated build loads hyperref). Any other command the paper's own .tex files use is
# allowed too (its macros, \\citet with natbib, \\eqref, \\cref with cleveref),
# except the structural ones below and PAR_CMDS: a note box is typeset at shipout and silently disappears on them.
NOTE_CMDS = {'textbf', 'textit', 'emph', 'texttt', 'textsc', 'textsf', 'textrm', 'textsl', 'textup', 'textmd',
             'textnormal', 'textsuperscript', 'textsubscript', 'underline', 'mbox', 'url', 'href', 'nolinkurl', 'ref',
             'pageref', 'cite', 'S', 'P',
             'ldots', 'dots', 'textless', 'textgreater', 'textbackslash', 'textasciitilde', 'textasciicircum',
             'textquotesingle', 'textendash', 'textemdash', 'textbullet', 'textdegree', 'ensuremath', 'LaTeX', 'TeX'}
NOTE_DENY = {'verb', 'label', 'footnote', 'footnotemark', 'footnotetext', 'hline', 'cline', 'toprule',
                        'midrule', 'bottomrule', 'cmidrule', 'includegraphics', 'centering', 'vspace', 'vskip',
                        'newcommand', 'renewcommand', 'def', 'rrnote', 'rrnotepair', 'rrfix', 'rrcheck', 'rrstyle',
                        'rrmissing'}


def paper_commands(paper):
    """Names of the commands used (outside comments) in the paper's .tex files."""
    out = set()
    for dp, dns, fns in os.walk(paper):
        for fn in fns:
            if fn.endswith('.tex'):
                with open(os.path.join(dp, fn), encoding='utf-8', errors='replace') as fh:
                    for ln in fh:
                        out.update(re.findall(r'\\([A-Za-z@]+)', re.sub(r'(?<!\\)%.*', '', ln)))
    return out


def bad_note_commands(s, allowed):
    """Commands of note text s, outside math, that a margin note cannot hold (see NOTE_CMDS)."""
    bad, math, i = [], None, 0
    while i < len(s):
        if s[i] == '\\':
            m = re.match(r'\\([A-Za-z@]+)', s[i:])
            if not m:
                two = s[i:i + 2]
                if math is None and two in ('\\(', '\\['):
                    math = '\\)' if two == '\\(' else '\\]'
                elif two == math:
                    math = None
                i += 2
                continue
            name = m.group(1)
            if math is None and (name in NOTE_DENY or name in PAR_CMDS or (name not in NOTE_CMDS and name not in allowed)) \
                    and name not in bad:
                bad.append(name)
            i += m.end()
            continue
        if s[i] == '$':
            tok = '$$' if s.startswith('$$', i) else '$'
            math = tok if math is None else (None if math == tok else math)
            i += len(tok)
            continue
        i += 1
    return bad


def split_breaks(s):
    """[(text, separator)] of s split at its line breaks (\\\\, \\\\*, \\\\[len]) outside braces and math; one
    piece (s, '') when it has none."""
    out, d, math, start, i = [], 0, None, 0, 0
    while i < len(s):
        c = s[i]
        if c == '\\':
            if s.startswith('\\\\', i) and d == 0 and math is None:
                m = re.match(r'\\\\\*?(\s*\[[^\]]*\])?', s[i:])
                out.append((s[start:i], m.group(0)))
                i += m.end()
                start = i
                continue
            two = s[i:i + 2]
            if math is None and two in ('\\(', '\\['):
                math = '\\)' if two == '\\(' else '\\]'
            elif two == math:
                math = None
            i += 2
            continue
        if c == '$':
            tok = '$$' if s.startswith('$$', i) else '$'
            math = tok if math is None else (None if math == tok else math)
            i += len(tok)
            continue
        d += (c == '{') - (c == '}')
        i += 1
    out.append((s[start:], ''))
    return out


MARK_COLOR = {'fix': 'rrred', 'check': 'rrorange', 'style': 'rrpurple'}


# ---------------------------------------------------------------- lint: nothing invented in the applied text
CAUSAL = re.compile(r"\b(because|since|thanks to|due to|owing to|as a result of|caused by|explained by|stems? from|"
                    r"results? from|the reason|which explains|this is why|so that|in order to|which allows|enabled by)\b",
                    re.I)
SUBMISSION_FILE = re.compile(r"\b(highlights|graphical abstract|cover letter|separate (editable )?files?|declaration of "
                             r"(competing|interest)|competing[- ]interests? (statement|declaration)|supplementary "
                             r"(material|files?)|response letter|checklist|copyright form|credit (author )?statement "
                             r"file)\b", re.I)
DICT_FILES = ('/usr/share/dict/words', '/usr/dict/words')
_DICT = None


def dictionary():
    """Ordinary English words (the system word list), or an empty set when there is none."""
    global _DICT
    if _DICT is None:
        _DICT = set()
        for f in DICT_FILES:
            if os.path.isfile(f):
                with open(f, encoding='utf-8', errors='replace') as fh:
                    _DICT = {w.strip().lower() for w in fh if w.strip()}
                break
    return _DICT


def detex_words(s):
    """The prose of a LaTeX snippet: \\ref/\\cite/\\label arguments and command names dropped."""
    s = re.sub(r'(?<!\\)%.*', '', s)
    s = re.sub(r'\\(?:%s)\*?(?:\[[^\]]*\])*\{[^{}]*\}' % '|'.join(sorted(REF_CMDS)), ' ', s)
    s = re.sub(r'\\(?:hypersetup|usepackage|documentclass|begin|end)\*?(?:\[[^\]]*\])?\{[^{}]*\}', ' ', s)
    s = re.sub(r'\[[^\]\n]{0,40}\]', ' ', s)     # optional arguments: float placement, options
    s = re.sub(r'\\[a-zA-Z]+\*?', ' ', s)
    return s


def numbers_in(s):
    """The numbers of a LaTeX snippet as floats: 13\\,090 and 13{,}090 are 13090; 1.9 is 1.9."""
    s = re.sub(r'(?<=\d)(?:\\,|\{,\}|,|\\;|~)(?=\d{3}\b)', '', s)
    out = set()
    for m in re.finditer(r'(?<![\w.])\d+(?:\.\d+)?', s):
        try:
            out.add(float(m.group(0)))
        except ValueError:
            pass
    return out


WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*")


def vocab_of(text):
    v = set()
    for w in WORD.findall(detex_words(text)):
        lw = w.lower()
        v.add(lw)
        if '-' in lw:
            v.add(lw.replace('-', ''))
            v.update(lw.split('-'))
    return v


def known(w, vocab, dic):
    lw = w.lower()
    if lw in vocab or lw.replace('-', '') in vocab:
        return True
    if '-' in lw or re.search(r'[A-Z].*[A-Z]|\d', w):
        return False          # a compound, an acronym or a name with digits: must come from the paper
    if not dic:
        return True           # no word list: plain words pass
    cands = [lw] + [lw[:-len(x)] for x in ('s', 'es', 'ed', 'd', 'ing', 'ly') if lw.endswith(x)] + \
        ([lw[:-3] + 'y'] if lw.endswith('ies') else []) + \
        ([lw[:-3] + 'e'] if lw.endswith('ing') else []) + ([lw[:-1]] if lw.endswith('ed') else [])
    for cand in cands:
        if cand in dic or cand in vocab:
            return True
    return False


def invented(new, old, sources_vocab, sources_numbers, allowed_numbers):
    """What the new text of an applied edit adds that the paper does not have: terms, numbers, causal clauses."""
    dic = dictionary()
    old_vocab = vocab_of(old or '')
    terms = []
    for w in WORD.findall(detex_words(new or '')):
        if w.lower() in old_vocab or known(w, sources_vocab, dic):
            continue
        if w not in terms:
            terms.append(w)
    nums = []
    for x in sorted(numbers_in(new or '') - numbers_in(old or '')):
        if x in sources_numbers or x in allowed_numbers or (x == int(x) and 0 <= x <= 10):
            continue
        nums.append(('%g' % x))
    causal = [m.group(0) for m in CAUSAL.finditer(new or '') if not CAUSAL.search(old or '')]
    return terms, nums, list(dict.fromkeys(c.lower() for c in causal))


def sources_index(paper):
    """Vocabulary and numbers of every .tex file of the paper."""
    vocab, nums = set(), set()
    for dp, dns, fns in os.walk(paper):
        for fn in fns:
            if fn.endswith('.tex'):
                with open(os.path.join(dp, fn), encoding='utf-8', errors='replace') as fh:
                    t = fh.read()
                vocab |= vocab_of(t)
                nums |= numbers_in(t)
    return vocab, nums


def lint_invented(edits, paper):
    """[(item, message)] for applied edits (fix, check, style, raw; not .bib) whose new text contains a term, a
    number or a causal explanation that the paper does not have (references/merge-agent.md: the applied text only
    restates the paper or computes from it; mechanisms and explanations go to the question or the note)."""
    vocab, nums = sources_index(paper)
    allowed = {}
    for e in edits:
        if isinstance(e.d, dict) and isinstance(e.item, int):
            for f in ('question', 'note', 'note_short', 'what'):
                allowed.setdefault(e.item, set()).update(numbers_in(e.d.get(f) or ''))
    out = []
    for e in edits:
        if not isinstance(e.d, dict) or e.kind not in APPLIED_KINDS or e.file.lower().endswith('.bib'):
            continue
        terms, ns, causal = invented(e.d.get('new', ''), e.d.get('old', ''), vocab, nums, allowed.get(e.item, set()))
        bits = []
        if terms:
            bits.append('terms not in the paper: %s' % ', '.join(repr(t) for t in terms[:6]))
        if ns:
            bits.append('numbers not in the paper nor computed in the note or question: %s' % ', '.join(ns[:6]))
        if causal:
            bits.append('a causal explanation (%s)' % ', '.join(repr(c) for c in causal))
        if bits:
            out.append((e.item, '%s: new text adds %s; the applied text may only restate what the paper says or '
                        'compute from it: move explanations and mechanisms to the question or the note' % (
                            e.label(), '; '.join(bits))))
    return out


def lint_submission_files(edits):
    """A missing-facts placeholder about a submission file (highlights, declarations as separate files) belongs in a
    note, not in the text."""
    out = []
    for e in edits:
        if isinstance(e.d, dict) and e.kind == 'missing' and SUBMISSION_FILE.search(
                (e.d.get('what') or '') + ' ' + (e.d.get('new') or '')):
            out.append((e.item, '%s: placeholder about a submission file (%s): make it a note (with its question), '
                        'not text in the paper' % (e.label(), SUBMISSION_FILE.search(
                            (e.d.get('what') or '') + ' ' + (e.d.get('new') or '')).group(0))))
    return out


REPEAT_GAP = 1500   # characters: a mark of an item to check this far from its note gets the one-line question too


def one_line(q, limit=90):
    """The first sentence of a question, at most about `limit` characters (cut at a word, braces balanced)."""
    q = ' '.join((q or '').split())
    m = re.match(r'^(.*?[?.])(?:\s|$)', q)
    q1 = m.group(1) if m else q
    if len(q1) > limit:
        q1 = q1[:limit].rsplit(' ', 1)[0].rstrip(',;:') + '...'
    if len(re.findall(r'(?<!\\)\$', q1)) % 2:
        q1 = q1[:q1.rfind('$')].rstrip() + '...'
    q1 = esc_prose(q1)
    return q1 if balanced(q1) and not has_bare_percent(q1.replace('\\%', '')) else ''


def in_body(text, p):
    """True if position p is inside \\begin{document}...\\end{document}, or the file has no \\begin{document}."""
    m = re.search(r'^[^%\n]*\\begin\{document\}', text, re.M)
    if not m:
        return True
    e = re.search(r'^[^%\n]*\\end\{document\}', text, re.M)
    return m.end() <= p and (e is None or p < e.start())


def visible(e, docs):
    """True if edit e leaves a tag in the marked text of the document body."""
    if e.mseg is None or e.kind not in ('fix', 'check', 'style', 'missing', 'raw'):
        return False
    if e.kind == 'raw' and '\\rr' not in e.d.get('mark', e.d.get('new', '')):
        return False
    dc = docs[e.file]
    try:
        p = dc.pos_of(e.mseg, 's')
    except KeyError:
        return False
    t = dc.stext()
    if in_body(t, p):
        return True
    # \title{...}, \author{...} in the preamble are printed by \maketitle
    return any(fr.kind == 'brace' and fr.name.rstrip('*') in MOVING for fr in enclosing(frames_of(t), p))


FORBIDDEN_ENV = re.compile(r'figure|table|tabular|tabbing|array|matrix|equation|align|gather|multline|eqnarray|'
                           r'math|split|cases|verbatim|lstlisting|minted|listing|algorithm|tikz|picture|minipage|'
                           r'wrap|subfig|box|comment|thebibliography|filecontents|frontmatter|titlepage', re.I)
MATH_ENV = re.compile(r'equation|align|gather|multline|eqnarray|math|split|array|cases|matrix')
VERB_ENVS = ('verbatim', 'verbatim*', 'Verbatim', 'lstlisting', 'minted', 'comment', 'filecontents', 'alltt')
PAR_CMDS = {'begin', 'end', 'item', 'par', 'part', 'chapter', 'section', 'subsection', 'subsubsection', 'paragraph',
            'subparagraph', 'caption', 'bibitem', 'maketitle', 'bibliography', 'printbibliography', 'appendix',
            'clearpage', 'newpage', 'input', 'include'}
MOVING = {'caption', 'part', 'chapter', 'section', 'subsection', 'subsubsection', 'paragraph', 'subparagraph',
          'title', 'shorttitle', 'author', 'shortauthors', 'thanks', 'markboth', 'markright'}
ABBREV = {'e.g', 'i.e', 'al', 'vs', 'cf', 'Fig', 'Figs', 'Eq', 'Eqs', 'Sec', 'Secs', 'Tab', 'resp', 'approx', 'No',
          'Ref', 'Refs', 'Dr', 'Prof', 'Mr', 'Ms', 'Ch', 'Thm', 'Def', 'Alg', 'Lem', 'App', 'pp', 'p', 'vol'}


class Frame:
    __slots__ = ('kind', 'name', 'start', 'end')

    def __init__(self, kind, name, start):
        self.kind, self.name, self.start, self.end = kind, name, start, None


def frames_of(text):
    """Scan LaTeX source; return closed frames (env, brace, math, comment, verb) with [start, end) spans."""
    out, stack = [], []
    i, n = 0, len(text)
    pending = None  # last control word whose arguments may follow

    def close(fr, end):
        fr.end = end
        out.append(fr)

    while i < n:
        ch = text[i]
        if ch == '\\':
            m = re.match(r'\\([A-Za-z@]+)(\*?)', text[i:])
            if not m:
                two = text[i:i + 2]
                if two in ('\\(', '\\['):
                    stack.append(Frame('math', two, i))
                elif two in ('\\)', '\\]'):
                    for k in range(len(stack) - 1, -1, -1):
                        if stack[k].kind == 'math':
                            while len(stack) > k:
                                close(stack.pop(), i + 2)
                            break
                pending = None
                i += 2
                continue
            name = m.group(1)
            j = i + m.end()
            if name in ('begin', 'end'):
                a = re.match(r'\s*\{([^{}]*)\}', text[j:])
                if a:
                    env = a.group(1).strip()
                    k_end = j + a.end()
                    if name == 'begin':
                        fr = Frame('env', env, i)
                        if env in VERB_ENVS:
                            e = text.find('\\end{%s}' % env, k_end)
                            e = n if e < 0 else e + len('\\end{%s}' % env)
                            close(fr, e)
                            i = e
                            pending = None
                            continue
                        stack.append(fr)
                    else:
                        for k in range(len(stack) - 1, -1, -1):
                            if stack[k].kind == 'env' and stack[k].name == env:
                                while len(stack) > k:
                                    close(stack.pop(), k_end)
                                break
                    i = k_end
                    pending = None
                    continue
            if name in ('verb', 'lstinline') and j < n and text[j] not in '{[ ':
                e = text.find(text[j], j + 1)
                e = n if e < 0 else e + 1
                close(Frame('verb', name, i), e)
                i = e
                pending = None
                continue
            pending = name
            i = j
            continue
        if ch == '%':
            e = text.find('\n', i)
            e = n if e < 0 else e + 1
            close(Frame('comment', '%', i), e)
            i = e
            continue
        if ch == '{':
            stack.append(Frame('brace', pending or '', i))
            pending = None
            i += 1
            continue
        if ch == '}':
            for k in range(len(stack) - 1, -1, -1):
                if stack[k].kind == 'brace':
                    while len(stack) > k + 1:
                        close(stack.pop(), i)
                    fr = stack.pop()
                    close(fr, i + 1)
                    pending = fr.name or None   # \cmd{a}{b}: the next group belongs to the same command
                    break
            i += 1
            continue
        if ch == '[' and pending:
            d, j = 0, i
            while j < n:
                if text[j] == '[':
                    d += 1
                elif text[j] == ']':
                    d -= 1
                    if d == 0:
                        break
                elif text[j] in '{}\n':
                    break
                j += 1
            if j < n and text[j] == ']':
                i = j + 1
                continue
        if ch == '$':
            tok = '$$' if text[i:i + 2] == '$$' else '$'
            if stack and stack[-1].kind == 'math' and stack[-1].name == tok:
                close(stack.pop(), i + len(tok))
            else:
                stack.append(Frame('math', tok, i))
            pending = None
            i += len(tok)
            continue
        if not ch.isspace() and ch != '*':
            pending = None
        i += 1
    for fr in stack:
        close(fr, n)
    return out


def enclosing(frames, p):
    """Frames strictly containing position p, outermost first."""
    fs = [f for f in frames if f.start < p < f.end]
    fs.sort(key=lambda f: (f.start, -f.end))
    return fs


def is_forbidden(fr):
    if fr.kind in ('math', 'comment', 'verb', 'brace'):
        return True
    return fr.kind == 'env' and bool(FORBIDDEN_ENV.search(fr.name))


def skip_group(text, i):
    """i at '{' or '['; return the index after the matching close."""
    op = text[i]
    cl = '}' if op == '{' else ']'
    d = 0
    while i < len(text):
        c = text[i]
        if c == '\\':
            i += 2
            continue
        if c == '%' and op == '{':
            j = text.find('\n', i)
            i = len(text) if j < 0 else j
            continue
        if c == op:
            d += 1
        elif c == cl:
            d -= 1
            if d == 0:
                return i + 1
        i += 1
    return len(text)


def skip_math(text, i):
    if text.startswith('$$', i):
        j = text.find('$$', i + 2)
        return len(text) if j < 0 else j + 2
    if text[i] == '$':
        j = i + 1
        while j < len(text):
            if text[j] == '\\':
                j += 2
                continue
            if text[j] == '$':
                return j + 1
            j += 1
        return len(text)
    cl = '\\)' if text.startswith('\\(', i) else '\\]'
    j = text.find(cl, i + 2)
    return len(text) if j < 0 else j + 2


def sentence_end(text, p):
    """Position after the end of the sentence (or of the paragraph) that continues at p, at top level."""
    n = len(text)
    k = p
    while k > 0 and text[k - 1] in '\'")]':
        k -= 1
    if k > 0 and text[k - 1] in '.?!' and (p >= n or text[p].isspace()):
        return p          # the edit itself ends the sentence
    i = p
    last = p
    while i < n:
        ch = text[i]
        if ch == '%':
            j = text.find('\n', i)
            i = n if j < 0 else j
            continue
        if ch == '\n':
            m = re.match(r'\n[ \t\r]*\n', text[i:])
            if m:
                return last
            i += 1
            continue
        if ch == '{':
            i = skip_group(text, i)
            last = i
            continue
        if ch == '}':
            return last
        if ch == '$' or text.startswith('\\(', i) or text.startswith('\\[', i):
            i = skip_math(text, i)
            last = i
            continue
        if ch == '\\':
            m = re.match(r'\\([A-Za-z]+)\*?', text[i:])
            if m:
                if m.group(1) in PAR_CMDS:
                    return last
                i += m.end()
                last = i
                continue
            if text.startswith('\\\\', i):
                return last
            i += 2
            last = i
            continue
        if ch in '.?!':
            w = re.search(r'([A-Za-z.]+)$', text[max(p, i - 12):i])
            word = w.group(1) if w else ''
            j = i + 1
            while j < n and text[j] in '\'")]':
                j += 1
            if (j >= n or text[j].isspace() or text[j] == '%') and \
                    not (ch == '.' and (word.rstrip('.') in ABBREV or re.fullmatch(r'[A-Z]', word))):
                return j
            i = j
            last = j
            continue
        if not ch.isspace():
            last = i + 1
        i += 1
    return last


# ---------------------------------------------------------------- the two copies: one list of segments per file
# Each segment has three views: s (the text later contexts are matched against: the corrected text without TODO
# comments), c (corrected copy) and m (marked copy). Untouched text has s == c == m.

def unmarked_raw(g):
    """A segment of a raw edit whose marked text equals its corrected text (later edits may cut through it)."""
    return g.edit is not None and g.edit.kind == 'raw' and g.m == g.c == g.s and not g.tail


class Seg:
    __slots__ = ('s', 'c', 'm', 'edit', 'tail', 'o')

    def __init__(self, s, c, m, edit=None, tail=False):
        self.s, self.c, self.m, self.edit, self.tail = s, c, m, edit, tail
        self.o = None   # the original text, written in the corrected copy when the item is not chosen


class Doc:
    def __init__(self, text):
        self.segs = [Seg(text, text, text)]

    def stext(self):
        return ''.join(g.s for g in self.segs)

    def ctext(self):
        return ''.join(g.c for g in self.segs)

    def mtext(self):
        return ''.join(g.m for g in self.segs)

    def _split(self, p):
        """Make s-view position p a segment boundary; return the index where an insertion at p goes: after the
        zero-length segments already at p (earlier insertions keep their order), before TODO comments.
        Raises ValueError(edit) if p falls strictly inside an edited segment."""
        pos = 0
        k = 0
        while k < len(self.segs):
            g = self.segs[k]
            L = len(g.s)
            if pos == p and L > 0:
                break
            if pos < p < pos + L:
                if g.edit is not None and not unmarked_raw(g):
                    raise ValueError(g.edit)
                off = p - pos
                suf = Seg(g.s[off:], g.c[off:], g.m[off:], g.edit)
                g.s, g.c, g.m = g.s[:off], g.c[:off], g.m[:off]
                self.segs.insert(k + 1, suf)
                k += 1
                break
            pos += L
            k += 1
        while k > 0 and not self.segs[k - 1].s and self.segs[k - 1].tail and pos == p:
            k -= 1
        return k

    def replace(self, a, b, seg):
        """Replace s-view [a, b) by seg; [a, b) must hold only untouched text. TODO comments inside move to the end
        of the line after seg. An edit inside the text of an earlier raw edit is applied to both its new and its
        mark text (when the changed text occurs exactly once in the mark)."""
        if self._inside_raw(a, b, seg):
            return
        i = self._split(a)
        if b == a:
            self.segs.insert(i, seg)
            return
        j = self._split(b)
        while j > i and not self.segs[j - 1].s:   # zero-length segments at b stay after the replacement
            j -= 1
        moved, absorbed = [], []
        for g in self.segs[i:j]:
            if g.tail:
                moved.append(g)
            elif g.edit is not None and unmarked_raw(g):
                g.s = g.c = g.m = ''          # an earlier unmarked raw edit, rewritten by this one
                absorbed.append(g)
            elif g.edit is not None:
                raise ValueError(g.edit)
        self.segs[i:j] = absorbed + [seg]
        for g in moved:
            t = self.stext()
            e = self.pos_of(seg, 's', end=True)
            eol = t.find('\n', e)
            self.insert_snap(len(t) if eol < 0 else eol, g)

    def _inside_raw(self, a, b, seg):
        pos = 0
        for k, g in enumerate(self.segs):
            L = len(g.s)
            if L and pos <= a and b <= pos + L and g.edit is not None and g.edit.kind == 'raw' \
                    and not (a == b and a in (pos, pos + L)):
                x, y = a - pos, b - pos
                sub = g.s[x:y]
                if g.m == g.s:
                    mx = x
                elif sub and g.m.count(sub) == 1:
                    mx = g.m.find(sub)
                else:
                    raise ValueError(g.edit)
                suf = Seg(g.s[y:], g.c[y:], g.m[mx + len(sub):], g.edit)
                g.s, g.c, g.m = g.s[:x], g.c[:x], g.m[:mx]
                self.segs[k + 1:k + 1] = [seg, suf]
                return True
            pos += L
        return False

    def insert_snap(self, p, seg):
        """Insert at s-view p; if p falls inside an edited segment, insert after that segment."""
        try:
            i = self._split(p)
        except ValueError:
            pos = 0
            for k, g in enumerate(self.segs):
                if pos < p < pos + len(g.s):
                    i = k + 1
                    break
                pos += len(g.s)
        if seg.tail:   # TODO comments go last at their position
            while i < len(self.segs) and not self.segs[i].s:
                i += 1
        self.segs.insert(i, seg)

    def insert_note(self, p, seg):
        """Insert a zero-length note segment at s-view p. Inside the text of a raw edit, the note goes at the same
        place in its mark (map_into); if that place cannot be told, at the start of the mark. Elsewhere as
        insert_snap. Returns 'mapped', 'start' or None."""
        pos = 0
        for k, g in enumerate(self.segs):
            L = len(g.s)
            if pos < p < pos + L and g.edit is not None and g.edit.kind == 'raw' and not g.tail:
                x = p - pos
                y = map_into(g.s, g.m, x)
                if y is None:
                    self.segs.insert(k, seg)
                    return 'start'
                suf = Seg(g.s[x:], g.c[x:], g.m[y:], g.edit)
                g.s, g.c, g.m = g.s[:x], g.c[:x], g.m[:y]
                self.segs[k + 1:k + 1] = [seg, suf]
                return 'mapped'
            pos += L
        self.insert_snap(p, seg)
        return None

    def pos_of(self, seg, view='s', end=False):
        pos = 0
        for g in self.segs:
            if g is seg:
                return pos + (len(getattr(g, view)) if end else 0)
            pos += len(getattr(g, view))
        raise KeyError('segment not found')


def map_into(s, m, x):
    """Offset in m (the mark of a raw edit) of offset x of s (its new text): after the longest text before x that
    occurs once in m, else before the longest text after x that does; None if neither."""
    if s == m:
        return x
    for L in range(min(x, 80), 5, -1):
        sn = s[x - L:x]
        if m.count(sn) == 1:
            return m.find(sn) + L
    for L in range(min(len(s) - x, 80), 5, -1):
        sn = s[x:x + L]
        if m.count(sn) == 1:
            return m.find(sn)
    return None


SKIP_START = PAR_CMDS | {'label', 'noindent', 'indent', 'centering', 'vspace', 'medskip', 'smallskip', 'bigskip'}


def first_prose(text, a, b):
    """First position in text[a:b] that is not blank, a comment or a heading-like command with its arguments."""
    i = a
    while i < b:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch == '%':
            j = text.find('\n', i)
            i = b if j < 0 else j + 1
            continue
        mm = re.match(r'\\([A-Za-z]+)\*?', text[i:b])
        if mm and mm.group(1) in SKIP_START:
            i += mm.end()
            while i < b and text[i] in '[{':
                i = skip_group(text, i)
            continue
        return i
    return None


# ---------------------------------------------------------------- matching contexts

def flex_pattern(s):
    parts = re.split(r'(\s+)', s)
    return ''.join(r'\s+' if p and p.isspace() else re.escape(p) for p in parts)


def find_all(text, needle):
    """Start offsets of needle (exact, overlapping allowed)."""
    out, k = [], text.find(needle)
    while k >= 0:
        out.append(k)
        k = text.find(needle, k + 1)
    return out


def locate(text, ctx):
    """Return (start, end, cursor or None) of ctx in text, or raise LookupError(message)."""
    if ctx.count('@@') > 1:
        raise LookupError('ctx has more than one @@')
    before, at, after = ctx.partition('@@')
    plain = before + after
    if not plain.strip():
        raise LookupError('empty context')
    hits = find_all(text, plain)
    if len(hits) == 1:
        s = hits[0]
        return s, s + len(plain), (s + len(before) if at else None)
    if len(hits) > 1:
        raise LookupError('context found %d times' % len(hits))
    pat = re.compile(flex_pattern(before) + '(?P<cur>)' + flex_pattern(after))
    ms = []
    k = 0
    while True:
        m = pat.search(text, k)
        if not m:
            break
        ms.append(m)
        k = m.start() + 1
    if len(ms) != 1:
        raise LookupError('context found %d times' % len(ms))
    m = ms[0]
    return m.start(), m.end(), (m.start('cur') if at else None)


def locate_in(text, a, b, old):
    """Unique occurrence of old inside text[a:b] (exact, then whitespace-flexible): (start, end)."""
    seg = text[a:b]
    hits = find_all(seg, old)
    if len(hits) == 1:
        return a + hits[0], a + hits[0] + len(old)
    if len(hits) > 1:
        raise LookupError('old found %d times inside ctx' % len(hits))
    ms = list(re.finditer(flex_pattern(old), seg))
    if len(ms) != 1:
        raise LookupError('old not inside ctx' if not ms else 'old found %d times inside ctx' % len(ms))
    return a + ms[0].start(), a + ms[0].end()


# ---------------------------------------------------------------- main

APPLIED_KINDS = ('fix', 'check', 'style', 'raw')
CONF_RANK = {'low': 0, 'medium': 1, 'high': 2}
DEFAULT_CONF = {'fix': 'high', 'raw': 'high', 'check': 'medium', 'style': 'low'}


def item_defaults(edits):
    """{item: (ticked, read_only, reason)} for every item with something to apply or facts to give (Choices in the
    header). An item's edits go together: it is ticked when every applied edit would be."""
    by = {}
    for e in edits:
        if isinstance(e.item, int) and e.kind in APPLIED_KINDS + ('missing',):
            by.setdefault(e.item, []).append(e)
    out = {}
    for n, es in by.items():
        app = [e for e in es if e.kind in APPLIED_KINDS]
        if not app or any(e.kind == 'missing' for e in es):
            # "your facts": a disabled box, never pre-ticked; the item's changes wait for the facts
            out[n] = (False, True, 'needs your facts first')
            continue
        ticks, whys = [], []
        for e in app:
            conf = e.d.get('confidence')
            if conf == 'low':
                ticks.append(False)
                whys.append("default: don't -- low confidence")
            elif e.kind == 'style':
                ticks.append(conf == 'high')
                whys.append('default: do -- wording, high confidence' if conf == 'high'
                            else "default: don't -- optional wording")
            elif e.kind == 'check':
                ticks.append(True)
                whys.append('default: do -- likely right, to confirm')
            else:
                ticks.append(True)
                whys.append('default: do -- ' + ('certain fix' if conf in (None, 'high') else 'likely fix'))
        tick = all(ticks)
        why = next((w for t, w in zip(ticks, whys) if not t), None) if not tick else \
            next((w for w in whys if 'confirm' in w), whys[0])
        out[n] = (tick, False, why)
    return out


class Done(Exception):
    pass


class Edit:
    def __init__(self, idx, d):
        self.idx, self.d = idx, d
        self.item = d.get('item')
        self.kind = d.get('kind', 'fix')
        self.file = d.get('file', '')
        self.seg = None        # segment whose c-view start gives the log line
        self.mseg = None       # segment holding the mark
        self.seg_file = None
        self.anchor = None     # (file, segment, explicit) for the note
        self.status = d.get('status') or STATUS.get(self.kind, '')

    def label(self):
        return 'edit %d (item #%s, %s, %s)' % (self.idx + 1, self.item, self.kind, self.file or '-')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('spec')
    ap.add_argument('paper')
    ap.add_argument('corrected')
    ap.add_argument('marked')
    ap.add_argument('--log', default=None)
    ap.add_argument('--loc-prefix', default='corrected', help='folder name printed in the note locations')
    ap.add_argument('--force', action='store_true', help='replace CORRECTED_DIR and MARKED_DIR if they exist')
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--choices', default=None, help="work/choices.json of read_choices.py: apply the 'do' items")
    g.add_argument('--only', default=None, help='comma-separated items: apply these and no other')
    ap.add_argument('--strict', action='store_true',
                    help='new text with terms, numbers or explanations absent from the paper is an error, not a warning')
    args = ap.parse_args()

    paper = os.path.abspath(args.paper)
    outs = [os.path.abspath(args.corrected), os.path.abspath(args.marked)]
    loc_prefix = args.loc_prefix
    errors, warnings = [], []
    if not os.path.isdir(paper):
        sys.exit('paper folder not found: %s' % paper)
    for o in outs:
        if o == paper or o.startswith(paper + os.sep) or paper.startswith(o + os.sep):
            sys.exit('output folder must be outside the paper folder: %s' % o)
        if os.path.exists(o) and os.listdir(o) and not args.force:
            sys.exit('output folder exists and is not empty (use --force): %s' % o)
    if outs[0] == outs[1]:
        sys.exit('CORRECTED_DIR and MARKED_DIR must differ')
    with open(args.spec, encoding='utf-8') as fh:
        spec = json.load(fh)
    if not isinstance(spec, list):
        sys.exit('SPEC.json must be a list of edits')

    docs = {}

    def doc(f):
        if f not in docs:
            p = os.path.normpath(os.path.join(paper, f))
            if os.path.isabs(f) or not p.startswith(paper + os.sep) or not os.path.isfile(p):
                raise LookupError('file not found in the paper folder: %r' % f)
            with open(p, encoding='utf-8', errors='surrogateescape', newline='') as fh:
                docs[f] = Doc(fh.read())
        return docs[f]

    edits = []
    notes = {}  # item -> {'q': [questions], 'n': [notes], 's': [short notes]}
    paper_cmds = paper_commands(paper)

    def add_note(e, q, text):
        it = e.item
        rec = notes.setdefault(it, {'q': [], 'n': [], 's': []})
        if q and q not in rec['q']:
            rec['q'].append(q)
        if text and text not in rec['n']:
            rec['n'].append(text)
        short = e.d.get('note_short')
        if short and short not in rec['s']:
            rec['s'].append(short)

    def overlap(owner):
        return 'overlaps the text changed by %s (merge them into one edit)' % owner.label()

    for idx, d in enumerate(spec):
        e = Edit(idx, d)
        edits.append(e)
        try:
            if not isinstance(d, dict):
                raise LookupError('not an object')
            if e.kind not in KINDS:
                raise LookupError('unknown kind %r' % e.kind)
            if not isinstance(e.item, int):
                raise LookupError('item must be an integer')
            if d.get('confidence') not in (None, 'high', 'medium', 'low'):
                raise LookupError('confidence must be high, medium or low')
            if e.kind == 'log':
                if not d.get('status'):
                    raise LookupError('log needs a status')
                continue
            if not e.file:
                raise LookupError('no file')
            dc = doc(e.file)
            old, new = d.get('old', ''), d.get('new', '')
            ctx = d.get('ctx')
            q = d.get('question')
            note = d.get('note')
            n = e.item
            if e.kind == 'check' and not (q and q.strip()):
                raise LookupError('check without question')
            for name in ('note', 'note_short', 'question', 'what'):
                if d.get(name) is not None and not balanced(d[name]):
                    raise LookupError('unbalanced braces in %s' % name)
                bad = bad_note_commands(d.get(name) or '', paper_cmds)
                if bad:
                    raise LookupError('%s is prose and cannot hold %s (a margin box would vanish): write it without '
                                      'them; allowed: formatting (\\emph, \\textbf, \\texttt), \\ref, \\cite, '
                                      '\\url, math in $...$ and the paper\'s own macros'
                                      % (name, ', '.join('\\' + b for b in bad)))
            text = dc.stext()
            is_bib = e.file.lower().endswith('.bib')
            if is_bib:
                if e.kind not in ('fix', 'check', 'style', 'raw'):
                    raise LookupError('a .bib edit must be fix, check, style or raw')
                if note or d.get('note_ctx') or d.get('note_short'):
                    raise LookupError('note on a .bib edit: put it in the notes of bbl-map.json (mark_bbl.py)')
            if d.get('note_short') and not (note or q):
                raise LookupError('note_short without note or question')

            if e.kind == 'raw':
                if not old:
                    raise LookupError('raw needs old')
                mark = new if is_bib else d.get('mark', new)
                count = d.get('count', 1)
                if ctx:
                    a0, b0, _ = locate(text, ctx)
                    a, b = locate_in(text, a0, b0, old)
                    spans = [(a, b)]
                else:
                    spans = [(k, k + len(old)) for k in find_all(text, old)]
                    # non-overlapping occurrences only
                    keep, last = [], -1
                    for a, b in spans:
                        if a >= last:
                            keep.append((a, b))
                            last = b
                    spans = keep
                    if count == 'all':
                        if not spans:
                            raise LookupError('raw old not found: %r' % old[:70])
                    elif len(spans) != count:
                        raise LookupError('raw old found %d times (expected %s): %r' % (len(spans), count, old[:70]))
                if brace_balance(mark)[0] != brace_balance(old)[0] or brace_balance(new)[0] != brace_balance(old)[0]:
                    raise LookupError('unbalanced braces in a mark: raw new/mark change the brace depth of old')
                first = None
                for a, b in reversed(spans):
                    sg = Seg(new, new, mark, e)
                    sg.o = text[a:b]
                    try:
                        dc.replace(a, b, sg)
                    except ValueError as ex:
                        raise LookupError(overlap(ex.args[0]))
                    first = sg
                e.seg, e.seg_file = first, e.file
                e.mseg = None if is_bib else first
                if (note or q) and not is_bib:
                    add_note(e, q, note)
                    e.anchor = (e.file, first)
                raise Done()

            # locate the cursor or the old span
            if e.kind in ('missing', 'note'):
                anchor_ctx = ctx if ctx else (old + '@@' if old else None)
                if not anchor_ctx:
                    raise LookupError('%s needs ctx' % e.kind)
                a0, b0, cur = locate(text, anchor_ctx)
                p = cur if cur is not None else b0
                if e.kind == 'note':
                    if not note:
                        raise LookupError('note without text')
                    mk = Seg('', '', '', e)
                    dc.insert_note(p, mk)
                    e.seg, e.seg_file = mk, e.file
                    add_note(e, q, note)
                    e.anchor = (e.file, mk, True)
                    continue
                what = d.get('what') or new
                if not what:
                    raise LookupError('missing needs what')
                if not balanced(what):
                    raise LookupError('unbalanced braces in a mark: what')
                ms = Seg('', '', ' \\rrmissing{%d}{%s}' % (n, esc_prose(what)), e)
                dc.insert_snap(p, ms)
                e.mseg = ms
                eol = text.find('\n', p)
                eol = len(text) if eol < 0 else eol
                if text[max(0, eol - 1):eol] == '\r':
                    eol -= 1
                todo = ' %% TODO #%d: %s' % (n, ' '.join(what.split()))
                ts = Seg('', todo, '', e, tail=True)
                dc.insert_snap(eol, ts)
                e.seg, e.seg_file = ts, e.file
                if note or q:
                    add_note(e, q, note)
                    e.anchor = (e.file, ms)
                raise Done()

            # fix / check / style
            if ctx is None:
                if not old:
                    raise LookupError('insertion without ctx (old is empty)')
                ctx = old
            a0, b0, cur = locate(text, ctx)
            if cur is not None:
                if old:
                    if not text.startswith(old, cur):
                        mm = re.compile(flex_pattern(old)).match(text, cur)
                        if not mm:
                            raise LookupError('old does not start at the @@ of ctx')
                        a, b = cur, mm.end()
                    else:
                        a, b = cur, cur + len(old)
                else:
                    a = b = cur
            else:
                if not old:
                    raise LookupError('insertion (old is empty) needs @@ in ctx')
                a, b = locate_in(text, a0, b0, old)
            old_src = text[a:b]
            if is_bib and brace_balance(old_src)[0] != brace_balance(new)[0]:
                raise LookupError('the .bib edit changes the brace depth (old %r, new %r)' % (old_src[:50], new[:50]))
            for name, val in (() if is_bib else (('old', old_src), ('new', new))):
                if not balanced(val):
                    raise LookupError('unbalanced braces in a mark: %s %r' % (name, val[:70]))
                if has_bare_percent(val):
                    raise LookupError('bare %% (comment) in a mark: %s %r' % (name, val[:70]))
            lines = split_breaks(new)
            if is_bib or (len(lines) == 1 and len(split_breaks(old_src)) == 1):
                lines = None
            if lines:
                # a line break inside the group of a mark (\\rrfix{n}{..}{a\\\\b}) breaks TikZ nodes and table
                # rows: each line is coloured apart, one tag at the end, no struck old text
                col = MARK_COLOR[e.kind]
                mark = ''.join(('{\\color{%s}%s}' % (col, t) if t.strip() else t) + sep for t, sep in lines) + \
                    '\\rrtag{%s}{%d}' % (col, n)
                warnings.append('%s: text with a line break (\\\\): marked line by line, old text not shown'
                                % e.label())
            elif e.kind == 'check':
                qe = esc_prose(q)
                mark = ('\\rrcheckplain{%d}{%s}{%s}' % (n, new, qe)) if d.get('plain') else \
                       ('\\rrcheck{%d}{%s}{%s}{%s}' % (n, old_src, new, qe))
            elif d.get('plain'):
                mark = '\\rr%splain{%d}{%s}' % (e.kind, n, new)
            else:
                mark = '\\rr%s{%d}{%s}{%s}' % (e.kind, n, old_src, new)
            if not d.get('plain') and not lines and re.search(r'\n[ \t\r]*\n', old_src):
                raise LookupError('old spans a paragraph break: split the edit or use raw')
            if is_bib:
                mark = new
            sg = Seg(new, new, mark, e)
            sg.o = old_src
            try:
                dc.replace(a, b, sg)
            except ValueError as ex:
                raise LookupError(overlap(ex.args[0]))
            e.seg, e.seg_file = sg, e.file
            if is_bib:
                raise Done()
            e.mseg = sg
            if note or q:
                add_note(e, q, note)
                e.anchor = (e.file, sg)
        except Done:
            pass
        except LookupError as ex:
            errors.append('%s: %s' % (e.label(), ex.args[0]))
            continue
        # explicit note place
        if d.get('note_ctx') and e.kind not in ('note', 'log'):
            try:
                nf = d.get('note_file', e.file)
                ndc = doc(nf)
                a0, b0, cur = locate(ndc.stext(), d['note_ctx'])
                mk = Seg('', '', '', e)
                ndc.insert_note(cur if cur is not None else b0, mk)
                if not (note or q):
                    errors.append('%s: note_ctx without note or question' % e.label())
                e.anchor = (nf, mk, True)
            except LookupError as ex:
                errors.append('%s: note_ctx: %s' % (e.label(), ex.args[0]))

    # ---------------------------------------------------------------- place one note per item
    for it in sorted(notes):
        rec = notes[it]
        cands = [e for e in edits if e.item == it and e.anchor]
        explicit = [e for e in cands if len(e.anchor) == 3]
        chosen = (explicit or cands or [None])[0]
        if chosen is None:
            continue
        f, sg = chosen.anchor[0], chosen.anchor[1]
        dc = docs[f]
        text = dc.stext()
        p = dc.pos_of(sg, 's', end=True)
        if len(chosen.anchor) == 2 and chosen.kind == 'raw':
            # the note of a raw edit: at the start of its text (end of the first sentence of its first paragraph)
            a = dc.pos_of(sg, 's')
            q0 = first_prose(text, a, p)
            if q0 is not None:
                p = q0
        frames = frames_of(text)
        has_doc = re.search(r'^[^%\n]*\\begin\{document\}', text, re.M) is not None
        if has_doc and not any(fr.kind == 'env' and fr.name == 'document' and fr.start < p < fr.end
                               for fr in frames):
            errors.append('item #%d: its note would fall outside the document body of %s; give note_ctx' % (it, f))
            continue
        bad = [fr for fr in enclosing(frames, p) if is_forbidden(fr)]
        q_after_env = False
        if bad:
            fr = bad[0]
            p = fr.end
            while p < len(text) and text[p] in '{[' and fr.kind == 'brace':
                p = skip_group(text, p)
            q_after_env = fr.kind == 'env'
            if len(chosen.anchor) == 3:
                warnings.append('item #%d: note_ctx inside %s %s; note moved after it' % (it, fr.kind, fr.name))
        if not q_after_env and len(chosen.anchor) != 3:
            p = sentence_end(text, p)
        body = ''
        if rec['q']:
            body = 'To check: ' + ' '.join(esc_prose(x) for x in rec['q'])
        if rec['n']:
            body = (body + ' ' if body else '') + ' '.join(esc_prose(x) for x in rec['n'])
        if not balanced(body):
            errors.append('item #%d: unbalanced braces in the note' % it)
            continue
        words = len(' '.join(rec['q'] + rec['n']).split())
        if words > 60:
            warnings.append('item #%d: note of %d words (keep it under about 60)' % (it, words))
        if not rec['s'] and words > 30:
            warnings.append('item #%d: note of %d words without note_short (crowded pages need one)' % (it, words))
        short = ''
        if rec['s']:
            short = ' '.join(esc_prose(x) for x in rec['s'])
            if rec['q']:
                short = 'To check. ' + short
            if not re.search(r'report\s*\\?#\s*%d\b' % it, short):
                short += ' See report \\#%d.' % it
        cdoc = docs[chosen.seg_file] if chosen.seg is not None else dc
        cline = cdoc.ctext().count('\n', 0, cdoc.pos_of(chosen.seg, 'c')) + 1 if chosen.seg is not None else None
        loc = esc_path('%s/%s:%d' % (loc_prefix, chosen.seg_file, cline)) if cline else ''
        pre = ''
        if rec['q'] and not any(visible(e, docs) for e in edits if e.item == it):
            pre = '\\rrcheckmark{%d}' % it
        if short:
            ns = Seg('', '', '%s\\rrnotepair[%s]{%d}{%s}{%s}' % (pre, loc, it, body, short), chosen)
        else:
            ns = Seg('', '', '%s\\rrnote[%s]{%d}{%s}' % (pre, loc, it, body), chosen)
        if dc.insert_note(p, ns) == 'start':
            warnings.append('item #%d: note place not found in the mark of a raw edit: note at the start of the mark'
                            % it)

    # ---------------------------------------------------------------- repeat the question at every orange mark
    # an item to check whose marks are far from its note (another file, or more than REPEAT_GAP characters away) gets
    # a one-line note with its question at each of them, so no orange mark is left without its question
    for it in sorted(notes):
        rec = notes[it]
        if not rec['q']:
            continue
        line = one_line(rec['q'][0])
        if not line:
            continue
        first = next((e for e in edits if e.item == it and e.anchor), None)
        if first is None:
            continue
        placed = [(first.anchor[0], docs[first.anchor[0]].pos_of(first.anchor[1], 's'))]
        for e in edits:
            if e.item != it or e.kind not in ('check', 'missing') or e.mseg is None or e is first:
                continue
            f = e.file
            dc = docs[f]
            p = dc.pos_of(e.mseg, 's', end=True)
            if any(pf == f and abs(pp - p) < REPEAT_GAP for pf, pp in placed):
                continue
            text = dc.stext()
            frames = frames_of(text)
            bad = [fr for fr in enclosing(frames, p) if is_forbidden(fr)]
            if bad:
                p = bad[0].end
            else:
                p = sentence_end(text, p)
            dc.insert_note(p, Seg('', '', '\\rrnote{%d}{To check: %s}' % (it, line), e))
            placed.append((f, p))

    # marks in math or in moving arguments
    for f in sorted(docs):
        dc = docs[f]
        frames = None
        for e in edits:
            if e.file != f or e.kind not in ('fix', 'check', 'style', 'missing') or e.d.get('plain') or e.mseg is None \
                    or f.lower().endswith('.bib'):
                continue
            if frames is None:
                frames = frames_of(dc.stext())
            p = dc.pos_of(e.mseg, 's')
            encl = enclosing(frames, p) or []
            if any(fr.kind == 'math' or (fr.kind == 'env' and MATH_ENV.search(fr.name)) for fr in encl) and (e.d.get('old') or e.kind == 'missing'):
                errors.append('%s: mark inside math: use "plain"' % e.label())
            elif any(fr.kind == 'brace' and fr.name.rstrip('*') in MOVING for fr in encl):
                warnings.append('%s: mark inside \\%s{...}: "plain" is safer' % (
                    e.label(), [fr.name for fr in encl if fr.name.rstrip('*') in MOVING][0]))

    lint = lint_invented(edits, paper) + lint_submission_files(edits)
    for _, msg in lint:
        (errors if args.strict else warnings).append(msg)

    if errors:
        print('ERRORS (%d): nothing written' % len(errors), file=sys.stderr)
        for x in errors:
            print('  ' + x, file=sys.stderr)
        for x in warnings:
            print('  warning: ' + x, file=sys.stderr)
        sys.exit(1)

    # ---------------------------------------------------------------- choices: which items go to the corrected copy
    states = item_defaults(edits)
    chosen = {n for n, st in states.items() if st[0]}
    how = 'default'
    if args.choices:
        with open(args.choices, encoding='utf-8') as fh:
            ch = json.load(fh)
        listed = {int(k): v for k, v in (ch.get('items') or {}).items()}
        for n, v in listed.items():
            if n in states and not states[n][1]:
                if v.get('choice') == 'do':
                    chosen.add(n)
                else:
                    chosen.discard(n)
        how = 'choices'
    elif args.only is not None:
        want = {int(x) for x in re.findall(r'\d+', args.only)}
        chosen = {n for n in want if n in states and not states[n][1]}
        how = 'only'
    for e in edits:
        if e.item in states and e.item not in chosen and e.kind in APPLIED_KINDS:
            e.status = 'not chosen (%s)' % ('your choice' if how != 'default' else states[e.item][2])
    for f, dc in docs.items():
        for g_ in dc.segs:
            if g_.edit is not None and g_.o is not None and g_.edit.item in states and g_.edit.item not in chosen:
                g_.c = g_.o

    # ---------------------------------------------------------------- write
    for o in outs:
        if os.path.exists(o):
            shutil.rmtree(o)
        shutil.copytree(paper, o, symlinks=True)
    for f in sorted(docs):
        for o, view in ((outs[0], 'ctext'), (outs[1], 'mtext')):
            with open(os.path.join(o, f), 'w', encoding='utf-8', errors='surrogateescape', newline='') as fh:
                fh.write(getattr(docs[f], view)())
    # \usepackage{r2changes} at the end of every main file's preamble, and the .sty next to it
    mains = []
    for root, dirs, files in os.walk(outs[1]):
        dirs.sort()
        for fn in sorted(files):
            if not fn.endswith('.tex'):
                continue
            p = os.path.join(root, fn)
            with open(p, encoding='utf-8', errors='surrogateescape', newline='') as fh:
                t = fh.read()
            if not re.search(r'^[^%\n]*\\documentclass', t, re.M):
                continue
            m = re.search(r'^([^%\n]*?)\\begin\{document\}', t, re.M)
            if not m:
                continue
            k = m.start() + len(m.group(1))
            if not re.search(r'^[^%\n]*\\usepackage\{r2changes\}', t[:k], re.M):
                t = t[:k] + ('\n' if m.group(1).strip() else '') + '\\usepackage{r2changes}\n' + t[k:]
                with open(p, 'w', encoding='utf-8', errors='surrogateescape', newline='') as fh:
                    fh.write(t)
            shutil.copyfile(STY, os.path.join(root, 'r2changes.sty'))
            if os.path.isfile(LOGO):   # the logo of the front pages (front_pages.py)
                shutil.copyfile(LOGO, os.path.join(root, 'r2logo.png'))
            with open(os.path.join(root, 'r2states.tex'), 'w', encoding='utf-8') as fh:
                fh.write('% check boxes of the items (apply_edits.py): item, ticked, read-only, reason\n')
                for n in sorted(states):
                    tick, ro, why = states[n]
                    if how != 'default' and not ro:
                        tick = n in chosen
                        why = ('your choice: do' if tick else "your choice: don't") if tick != states[n][0] \
                            else why
                    fh.write('\\rritemstate{%d}{%d}{%d}{%s}\n' % (n, int(tick and not ro), int(ro), why))
            mains.append(os.path.relpath(p, outs[1]))
    if not mains:
        warnings.append('no main file (\\documentclass and \\begin{document}) found: add \\usepackage{r2changes}')

    rows = []
    for e in edits:
        line = ''
        if e.seg is not None:
            dc = docs[e.seg_file]
            cp = dc.pos_of(e.seg, 'c')
            line = dc.ctext().count('\n', 0, cp) + 1
        q = e.d.get('question') or '' if isinstance(e.d, dict) else ''
        what = (e.d.get('what') or e.d.get('new') or '') if isinstance(e.d, dict) and e.kind == 'missing' else ''
        rows.append((str(e.item), e.kind, e.file, str(line), e.status, ' '.join(q.split()), ' '.join(what.split())))
    if args.log:
        with open(args.log, 'w', encoding='utf-8') as fh:
            fh.write('item\tkind\tfile\tline\tstatus\tquestion\twhat\n')
            for r in rows:
                fh.write('\t'.join(x.replace('\t', ' ').replace('\n', ' ') for x in r) + '\n')
    counts = {}
    for e in edits:
        counts[e.kind] = counts.get(e.kind, 0) + 1
    print('edits: %d (%s); notes: %d; files changed: %d; r2changes added to: %s' % (
        len(edits), ', '.join('%s %d' % kv for kv in sorted(counts.items())), len(notes), len(docs),
        ', '.join(mains) or '-'))
    ro = sum(1 for st in states.values() if st[1])
    print('check boxes: %d items; corrected copy (%s): %d applied, %d not, %d waiting for facts' % (
        len(states), how, len(chosen), len(states) - len(chosen) - ro, ro))
    for x in warnings:
        print('warning: ' + x)


if __name__ == '__main__':
    main()
