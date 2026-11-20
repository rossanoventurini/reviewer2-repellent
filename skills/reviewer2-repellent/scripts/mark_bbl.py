#!/usr/bin/env python3
"""Write a marked .bbl for the annotated PDF (step 6): the corrected bibliography with every change against the
original .bbl wrapped in r2changes marks (\\rrfix{n}{old}{new}), new entries in red, removed entries struck out next
to the entry that replaced them, and one \\rrnote per report item right after the \\bibitem of its first changed
entry.

Usage: python3 mark_bbl.py ORIG.bbl CORR.bbl OUT.bbl MAP.json [--bib FILE.bib [--bib-name NAME]]... [--whole-spans]

Marks are word-level by default: inside a changed stretch, words that print the same stay plain and only the
changed runs are marked, each old word in its own \\mbox so the struck-out text can break between words
(\\emph{a b} is spread over its words). --whole-spans marks each changed stretch as one \\rrfix instead.
--bib (repeatable) gives the corrected .bib files: each note then carries the location of its entry,
\\rrnote[NAME:line]{n}{text} (NAME defaults to the path as given).

MAP.json says which report item each change belongs to (all keys optional):
  {"default_item": 61,                                   item of a changed span when nothing else applies
   "default":  {"<key>": 21},                            item of the changed spans of one entry
   "rules":    {"<key>": [["<regex on old+new span>", 24]]},  tried first, per entry (every matching rule's
                                                         item gets its note at the entry)
   "case_item": 60,  "case_keys": ["<key>", ...],        a span that differs only in capitals gets case_item
                                                         (only in case_keys, if given; after "default")
   "items":    {"<key>": [21, 24]},                      every item that touches the entry: each gets its note at
                                                         this entry even if no span was assigned to it
   "new":      {"<key>": 17},                            entries added to the bibliography
   "removed":  {"<old key>": {"item": 20, "after": "<key>", "why": "duplicate, merged into"}},
   "replaces": {"<new key>": "<old key>"},               a renamed entry: compare it with its old key
   "notes":    {"21": "Published version replaces the arXiv preprint."},   one margin note per item
   "notes_short": {"21": "arXiv preprint replaced by the published version."}}  optional short notes (about 25
                                                         words), printed on crowded pages (\\rrnotepair)
Item of a changed span: rules (first regex that matches) > default[key] > case_item > default_item.
A note whose item has no changed span (a change the .bbl does not show, e.g. entries deleted from the .bib) goes at
the first entry listed for it in "items", else at the first entry whose rules or default name it, else right before
the first \\bibitem; each such placement is reported on stderr.
Both \\bibitem{key} and \\bibitem[label]{key} (natbib) are read, with spaces, line breaks and % comments allowed
between \\bibitem, [label] and {key} (acmart writes \\bibitem[label]%<newline>{key}); labels are kept. A changed
span that cuts through a {...} group is widened to the smallest balanced span. Differences that print the same (accent macros vs Unicode,
-- vs en dash, braces) are not marked. Note text is prose: _ % & # are escaped outside math unless already escaped.
Entries of the corrected .bbl with no original (and not in "new") are shown as new and reported; original entries
missing from the corrected .bbl and not in "removed" are reported. Exit status 0 (warnings on stderr).
Then compile the marked copy without BibTeX (e.g. latexmk with $bibtex_use = 0) so the marked .bbl is kept.
Python stdlib only.
"""
import argparse
import difflib
import os
import json
import re
import sys

# ---------------------------------------------------------------- parsing

def skip_space(s, i):
    """Index of the first character at or after i that is neither whitespace nor in a % comment (acmart writes
    \\bibitem[label]%<newline>{key})."""
    while i < len(s):
        if s[i].isspace():
            i += 1
        elif s[i] == '%':
            nl = s.find('\n', i)
            i = len(s) if nl < 0 else nl + 1
        else:
            break
    return i


def find_bibitems(txt):
    """Offsets of \\bibitem commands outside comments."""
    out = []
    for m in re.finditer(r'\\bibitem(?![A-Za-z@])', txt):
        line_start = txt.rfind('\n', 0, m.start()) + 1
        pre = txt[line_start:m.start()]
        if re.search(r'(?<!\\)%', pre):
            continue
        out.append(m.start())
    return out


def join_lines(body):
    """One line per entry; a line ending in an unescaped % joins the next without a space."""
    out = ''
    for ln in body.split('\n'):
        s = ln.strip()
        if s.endswith('%') and not s.endswith('\\%'):
            out += s[:-1]
        else:
            out += s + ' '
    return ' '.join(out.split())


def parse(path):
    with open(path, encoding='utf-8') as fh:
        txt = fh.read()
    starts = find_bibitems(txt)
    if not starts:
        sys.exit('no \\bibitem in %s' % path)
    end = txt.rfind('\\end{thebibliography}')
    if end < 0:
        sys.exit('no \\end{thebibliography} in %s' % path)
    head, tail = txt[:starts[0]], txt[end:]
    entries = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else end
        chunk = txt[s:e]
        i = skip_space(chunk, len('\\bibitem'))
        label = None
        if i < len(chunk) and chunk[i] == '[':
            d, bd, j = 0, 0, i
            while j < len(chunk):
                c = chunk[j]
                if c == '\\':
                    j += 2
                    continue
                if c == '{':
                    bd += 1
                elif c == '}':
                    bd -= 1
                elif c == '[' and bd == 0:
                    d += 1
                elif c == ']' and bd == 0:
                    d -= 1
                    if d == 0:
                        break
                j += 1
            label = ' '.join(chunk[i + 1:j].split())
            i = skip_space(chunk, j + 1)
        m = re.match(r'\{([^{}]*)\}', chunk[i:])
        if not m:
            sys.exit('cannot read the key of: %s' % chunk[:80])
        entries.append((m.group(1).strip(), label, join_lines(chunk[i + m.end():])))
    return head, entries, tail


# ---------------------------------------------------------------- normalisation (compare printed text)
ACC = {"\\'": {'e': 'é', 'a': 'á', 'E': 'É', 'i': 'í', 'o': 'ó', 'u': 'ú'},
       '\\"': {'o': 'ö', 'u': 'ü', 'a': 'ä', 'O': 'Ö', 'U': 'Ü', 'A': 'Ä'},
       '\\c': {'c': 'ç'}, '\\~': {'n': 'ñ'}, '\\`': {'e': 'è', 'a': 'à'}}


def norm(tok):
    t = tok
    for cmd, mp in ACC.items():
        for a, u in mp.items():
            for pat in (cmd + '{' + a + '}', cmd + a, cmd + ' ' + a):
                t = t.replace(pat, u)
    t = t.replace('\\textquotesingle', "'").replace('\\&', '&').replace('{-}', '-')
    t = t.replace('--', '–').replace('~', ' ')
    t = t.replace('{', '').replace('}', '')
    return t


def delta(tok):
    """(net brace depth change, minimum depth reached) of a token, ignoring \\{ and \\}."""
    d = mn = 0
    i = 0
    while i < len(tok):
        c = tok[i]
        if c == '\\':
            i += 2
            continue
        if c == '{':
            d += 1
        elif c == '}':
            d -= 1
            mn = min(mn, d)
        i += 1
    return d, mn


def depth_profile(toks):
    d = mn = 0
    for t in toks:
        td, tmn = delta(t)
        mn = min(mn, d + tmn)
        d += td
    return d, mn


def balanced(toks):
    d, mn = depth_profile(toks)
    return d == 0 and mn == 0


# ---------------------------------------------------------------- prose escaping for notes
REF_CMDS = {'ref', 'eqref', 'cref', 'Cref', 'autoref', 'pageref', 'label', 'url', 'href', 'cite', 'citep', 'citet',
            'citealp', 'nocite', 'doi'}


def esc_prose(s):
    """Escape _ % & # (and -> < >) outside math, unless already escaped; \\ref/\\cite/\\url arguments untouched."""
    out = []
    i, n = 0, len(s)
    math = None
    while i < n:
        ch = s[i]
        if ch == '\\':
            m = re.match(r'\\([A-Za-z]+)\*?', s[i:])
            if m:
                out.append(m.group(0))
                i += m.end()
                if m.group(1) in REF_CMDS:
                    while i < n and s[i] in '[{':
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
            tok = '$$' if s[i:i + 2] == '$$' else '$'
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


# ---------------------------------------------------------------- old text inside \sout
def esc_url(s):
    out = []
    for ch in s:
        out.append({'\\': '\\textbackslash{}', '_': '\\_', '#': '\\#', '%': '\\%', '&': '\\&',
                    '~': '\\textasciitilde{}', '{': '', '}': ''}.get(ch, ch))
    return ''.join(out)


def url_boxes(u):
    # struck-out URL broken into boxes at '/', '.', '-' so it can wrap
    parts = re.findall(r'[^/.\-]*[/.\-]?', u)
    parts = [p for p in parts if p]
    return '\\allowbreak '.join('\\mbox{' + esc_url(p) + '}' for p in parts)


def old_tok(tok):
    m = re.match(r'^(.*?)\\(url|doi)\{([^{}]*)\}(.*)$', tok)
    if m and balanced([m.group(1)]) and balanced([m.group(4)]):
        pre, kind, arg, post = m.groups()
        u = arg if kind == 'url' else 'https://doi.org/' + arg
        s = ''
        if pre:
            s += old_tok(pre) + ' '
        s += url_boxes(u)
        if post:
            s += '\\mbox{' + post + '}'
        return s
    if '\\' in tok or '{' in tok or '~' in tok:
        return '\\mbox{' + tok + '}'
    return tok


TEXT_CMDS = {'emph', 'textit', 'textbf', 'textsc', 'textsl', 'textup', 'textrm', 'textsf', 'texttt', 'textnormal'}


def units(toks):
    """Split tokens into minimal runs whose braces balance."""
    out, cur, d = [], [], 0
    for t in toks:
        cur.append(t)
        d += delta(t)[0]
        if d == 0:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def group_end(s, i):
    """s[i] == '{': index of the matching '}' (or -1)."""
    d = 0
    while i < len(s):
        c = s[i]
        if c == '\\':
            i += 2
            continue
        if c == '{':
            d += 1
        elif c == '}':
            d -= 1
            if d == 0:
                return i
        i += 1
    return -1


def old_unit(u):
    """Struck-out form of a balanced run of tokens: a text command or brace group spanning several words keeps its
    words separate (so the line can break); anything else is one box."""
    if len(u) == 1:
        return old_tok(u[0])
    s = ' '.join(u)
    if '\\url' not in s and '\\doi' not in s:
        m = re.match(r'^([^\\{}\s]*)(?:\\([A-Za-z]+))?\{', s)
        if m and (m.group(2) is None or m.group(2) in TEXT_CMDS) and '\\' not in m.group(1):
            o = m.end() - 1
            c = group_end(s, o)
            post = s[c + 1:] if c >= 0 else ''
            if c >= 0 and '{' not in post and '}' not in post and ' ' not in post:
                inner = s[o + 1:c].split()
                return s[:o] + '{' + old_text(inner) + '}' + (('\\mbox{%s}' % post) if '\\' in post else post)
    return '\\mbox{' + s + '}'


def old_text(toks):
    return ' '.join(old_unit(u) for u in units(toks))


# ---------------------------------------------------------------- diff

def widen(spans, o, n):
    """spans: change spans [i1, i2, j1, j2] in order, separated by equal runs (same length on both sides).
    Widen each, token by token, until both sides balance; spans that meet are merged."""
    k = 0
    while k < len(spans):
        sp = spans[k]
        guard = 0
        while not (balanced(o[sp[0]:sp[1]]) and balanced(n[sp[2]:sp[3]])):
            guard += 1
            if guard > len(o) + len(n) + 5:
                break
            need_left = need_right = False
            for toks in (o[sp[0]:sp[1]], n[sp[2]:sp[3]]):
                d, mn = depth_profile(toks)
                if mn < 0:
                    need_left = True
                if d - mn > 0:
                    need_right = True
            moved = False
            if need_left:
                if k > 0 and spans[k - 1][1] == sp[0] and spans[k - 1][3] == sp[2]:
                    prev = spans.pop(k - 1)
                    k -= 1
                    sp[0], sp[2] = prev[0], prev[2]
                    moved = True
                elif sp[0] > 0 and sp[2] > 0:
                    sp[0] -= 1
                    sp[2] -= 1
                    moved = True
            if need_right or not moved:
                if k + 1 < len(spans) and spans[k + 1][0] == sp[1] and spans[k + 1][2] == sp[3]:
                    nxt = spans.pop(k + 1)
                    sp[1], sp[3] = nxt[1], nxt[3]
                    moved = True
                elif sp[1] < len(o) and sp[3] < len(n):
                    sp[1] += 1
                    sp[3] += 1
                    moved = True
            if not moved:   # cannot widen within the entry: take all of it
                sp[:] = [0, len(o), 0, len(n)]
                spans[:] = [sp]
                k = 0
                break
            while k > 0 and spans[k - 1][1] >= sp[0]:
                prev = spans.pop(k - 1)
                k -= 1
                sp[0], sp[2] = min(prev[0], sp[0]), min(prev[2], sp[2])
            while k + 1 < len(spans) and spans[k + 1][0] <= sp[1]:
                nxt = spans.pop(k + 1)
                sp[1], sp[3] = max(nxt[1], sp[1]), max(nxt[3], sp[3])
        k += 1
    return spans


# ---------------------------------------------------------------- word-level marks
def close_brace(s, i):
    """s[i] == '{': index of the matching '}' (or len(s) - 1 if unbalanced)."""
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
                return j
        j += 1
    return len(s) - 1


def split_top(c):
    """Split at spaces outside braces."""
    out, cur, d, i = [], '', 0, 0
    while i < len(c):
        ch = c[i]
        if ch == '\\':
            cur += c[i:i + 2]
            i += 2
            continue
        if ch == '{':
            d += 1
        elif ch == '}':
            d -= 1
        if ch in ' \n' and d == 0:
            if cur:
                out.append(cur)
            cur = ''
        else:
            cur += ch
        i += 1
    if cur:
        out.append(cur)
    return out


WRAP = re.compile(r'^\\(mbox|emph)\{')


def expand(tok):
    """\\mbox{a b} -> a b ; \\emph{a b}x -> \\emph{a} \\emph{b}x (recursively)."""
    m = WRAP.match(tok)
    if not m:
        return [tok]
    j = close_brace(tok, m.end() - 1)
    inner, tail = tok[m.end():j], tok[j + 1:]
    parts = []
    for w in split_top(inner):
        parts.extend(expand(w))
    if not parts:
        return [tail] if tail else []
    if m.group(1) == 'emph':
        parts = ['\\emph{%s}' % p if not p.startswith('\\emph{') else p for p in parts]
    parts[-1] += tail
    return parts


def word_tokens(s):
    out = []
    for t in split_top(s):
        out.extend(expand(t))
    return out


def word_key(t):
    t = t.replace('\\allowbreak', '').replace('\\newblock', 'NB')
    t = re.sub(r'\\(mbox|emph)\{', '{', t)
    return norm(t.replace('{', '').replace('}', ''))


def old_word(t):
    """One struck-out word in its own \\mbox (a URL piece keeps its \\allowbreak after the box)."""
    if t.endswith('\\allowbreak'):
        return old_word(t[:-len('\\allowbreak')]) + '\\allowbreak' if t[:-len('\\allowbreak')] else t
    if t.startswith('\\mbox{') and close_brace(t, 5) == len(t) - 1:
        return t
    return '\\mbox{%s}' % t


def rewrite_words(n, old, new):
    """One \\rrfix{n}{old}{new} as word-level marks."""
    a, b = word_tokens(old), word_tokens(new)
    ka, kb = [word_key(t) for t in a], [word_key(t) for t in b]
    ops = difflib.SequenceMatcher(None, ka, kb, autojunk=False).get_opcodes()
    merged = []   # changed runs separated by one short equal word are merged (no #n every other word)
    for op in ops:
        if (op[0] != 'equal' and len(merged) >= 2 and merged[-1][0] == 'equal'
                and merged[-1][2] - merged[-1][1] == 1 and len(ka[merged[-1][1]]) <= 3 and merged[-2][0] != 'equal'):
            merged.pop()
            prev = merged.pop()
            merged.append(('replace', prev[1], op[2], prev[3], op[4]))
        elif merged and op[0] != 'equal' and merged[-1][0] != 'equal':
            prev = merged.pop()
            merged.append(('replace', prev[1], op[2], prev[3], op[4]))
        else:
            merged.append(op)
    out = []
    for tag, i1, i2, j1, j2 in merged:
        if tag == 'equal':
            out.append(' '.join(b[j1:j2]))
        else:
            out.append('\\rrfix{%s}{%s}{%s}' % (n, ' '.join(old_word(t) for t in a[i1:i2]), ' '.join(b[j1:j2])))
    return ' '.join(x for x in out if x)


def word_level(s):
    """Rewrite every \\rrfix{n}{old}{new} of s as word-level marks."""
    res, pos = [], 0
    for m in re.finditer(r'\\rrfix\{(\d+)\}\{', s):
        if m.start() < pos:
            continue
        i = m.end() - 1
        j = close_brace(s, i)
        if j + 1 >= len(s) or s[j + 1] != '{':
            continue
        k = close_brace(s, j + 1)
        res.append(s[pos:m.start()])
        res.append(rewrite_words(m.group(1), s[i + 1:j], s[j + 2:k]))
        pos = k + 1
    res.append(s[pos:])
    return ''.join(res)


def bib_lines(paths):
    """key -> 'NAME:line' of its @type{key, in the given .bib files."""
    out = {}
    for path, name in paths:
        with open(path, encoding='utf-8', errors='replace') as fh:
            for i, ln in enumerate(fh, 1):
                m = re.match(r'\s*@\w+\s*[{(]\s*([^,\s]+)\s*,', ln)
                if m and m.group(1) not in out:
                    out[m.group(1)] = '%s:%d' % (name, i)
    return out


def esc_loc(s):
    return ''.join({'_': '\\_', '#': '\\#', '%': '\\%', '&': '\\&', '$': '\\$', '~': '\\textasciitilde{}',
                    '{': '', '}': ''}.get(ch, ch) for ch in s)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('orig')
    ap.add_argument('corr')
    ap.add_argument('out')
    ap.add_argument('map')
    ap.add_argument('--bib', action='append', default=[], help='corrected .bib file (repeatable)')
    ap.add_argument('--bib-name', action='append', default=[], help='name printed for the --bib of the same rank')
    ap.add_argument('--whole-spans', action='store_true', help='one mark per changed stretch, not per word run')
    args = ap.parse_args()
    ORIG, CORR, OUT, MAP = args.orig, args.corr, args.out, args.map
    names = args.bib_name + args.bib[len(args.bib_name):]
    BIBLOC = bib_lines(list(zip(args.bib, names)))
    CFG = json.load(open(MAP, encoding="utf-8"))
    ohead, oents, _ = parse(ORIG)
    chead, cents, ctail = parse(CORR)
    odict = {k: body for k, _, body in oents}
    ckeys = [k for k, _, _ in cents]
    onum = {k: i + 1 for i, (k, _, _) in enumerate(oents)}

    REPLACES = CFG.get("replaces", {})
    REMOVED = {k: (v["item"], v["after"], v.get("why", "removed")) for k, v in CFG.get("removed", {}).items()}
    NEW = CFG.get("new", {})
    DEFAULT = CFG.get("default", {})
    DEFAULT_ITEM = CFG.get("default_item", 0)
    RULES = {k: [(rx, it) for rx, it in v] for k, v in CFG.get("rules", {}).items()}
    CASE_ITEM = CFG.get("case_item")
    CASE_KEYS = set(CFG.get("case_keys", []))
    ITEMS = {k: [int(x) for x in v] for k, v in CFG.get("items", {}).items()}
    NOTES = {int(k): esc_prose(v) for k, v in CFG.get("notes", {}).items()}
    SHORT = {int(k): esc_prose(v) for k, v in CFG.get("notes_short", {}).items()}
    warnings = []

    def item_for(key, old, new):
        s = ' '.join(old + new)
        for rx, it in RULES.get(key, []):
            if re.search(rx, s):
                return it
        if key in DEFAULT:
            return DEFAULT[key]
        if CASE_ITEM and (not CASE_KEYS or key in CASE_KEYS):
            a, b = norm(' '.join(old)), norm(' '.join(new))
            if a != b and a.lower() == b.lower():
                return CASE_ITEM
        return DEFAULT_ITEM

    def mark_diff(key, otext, ntext):
        o, n = otext.split(), ntext.split()
        sm = difflib.SequenceMatcher(a=[norm(t) for t in o], b=[norm(t) for t in n], autojunk=False)
        spans = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                continue
            # merge changes separated by at most one equal token, so marks are readable
            if spans and i1 - spans[-1][1] <= 1 and i1 - spans[-1][1] == j1 - spans[-1][3]:
                spans[-1][1], spans[-1][3] = i2, j2
            else:
                spans.append([i1, i2, j1, j2])
        spans = widen(spans, o, n)
        out, items, pos = [], [], 0
        for i1, i2, j1, j2 in spans:
            out.extend(n[pos:j1])
            ot, nt = o[i1:i2], n[j1:j2]
            it = item_for(key, ot, nt)
            items.append(it)
            # a widened span can hold changes of several items: every rule that matches gets its note here
            sp = ' '.join(ot + nt)
            items.extend(r_it for rx, r_it in RULES.get(key, []) if re.search(rx, sp) and r_it != it)
            out.append('\\rrfix{%d}{%s}{%s}' % (it, old_text(ot), ' '.join(nt)))
            pos = j2
        out.extend(n[pos:])
        return ' '.join(out), items

    noted = set()
    lines = [chead.rstrip() + '\n']
    stats = {'changed': 0, 'unchanged': 0, 'added': 0, 'removed': 0}

    def note_cmd(it, loc):
        o = '[%s]' % loc if loc else ''
        if it in SHORT:
            short = SHORT[it] + ('' if re.search(r'report\s*\\?#\s*%d\b' % it, SHORT[it]) else ' See report \\#%d.' % it)
            return '\\rrnotepair%s{%d}{%s}{%s}' % (o, it, NOTES[it], short)
        return '\\rrnote%s{%d}{%s}' % (o, it, NOTES[it])

    def notes_for(items, key):
        s = ''
        loc = esc_loc(BIBLOC[key]) if key in BIBLOC else ''
        for it in dict.fromkeys(items):
            if it not in noted and it in NOTES:
                noted.add(it)
                s += note_cmd(it, loc)
        return s

    def bibitem(key, label):
        return '\\bibitem[%s]{%s}' % (label, key) if label is not None else '\\bibitem{%s}' % key

    after = {}
    for ok, (it, ck, why) in sorted(REMOVED.items()):
        if ok not in odict:
            warnings.append('removed %s: not in the original .bbl' % ok)
            continue
        if ck not in ckeys:
            warnings.append('removed %s: "after" entry %s is not in the corrected .bbl (shown at the end)' % (ok, ck))
            ck = ckeys[-1]
        after.setdefault(ck, []).append((ok, it, why))

    unmatched_new = []
    heads = {}
    for ck, clabel, ctext in cents:
        ok = REPLACES.get(ck, ck)
        if ck in NEW or ok not in odict:
            it = NEW.get(ck)
            if it is None:
                it = DEFAULT.get(ck, DEFAULT_ITEM)
                unmatched_new.append((ck, it))
            body = '\\rrfix{%d}{}{%s}' % (it, ctext)
            items = [it]
            stats['added'] += 1
        else:
            body, items = mark_diff(ck, odict[ok], ctext)
            stats['changed' if items else 'unchanged'] += 1
        heads[ck] = (len(lines), bibitem(ck, clabel))
        lines.append('%s%s\n%s\n' % (bibitem(ck, clabel), notes_for(items + ITEMS.get(ck, []), ck), body))
        for okey, it, why in after.get(ck, []):
            ref = '~\\cite{%s}' % ck if 'merged' in why else ''
            whyb = ' '.join('\\mbox{%s}' % esc_prose(w) for w in why.split())
            lines.append('\\item[\\rrold{[%d]}]%s\\rrfix{%d}{%s}{}~{\\color{rrred}\\sffamily\\scriptsize\\mbox{(}%s%s)}\n'
                         % (onum[okey], notes_for([it], ck), it, old_text(odict[okey].split()), whyb, ref))
            stats['removed'] += 1

    # notes of items with no changed span: at an entry the map links to the item, else before the first \\bibitem
    for it in sorted(set(NOTES) - noted):
        listed = [k for k in ckeys if it in ITEMS.get(k, [])]
        named = [k for k in ckeys if DEFAULT.get(k) == it or any(r_it == it for _, r_it in RULES.get(k, []))]
        key = (listed or named or [None])[0]
        if key is None:
            lines[0] = lines[0] + notes_for([it], None)
            warnings.append('item %d: no changed span and no entry names it: note placed before the first \\bibitem'
                            % it)
        else:
            i, b = heads[key]
            lines[i] = b + notes_for([it], key) + lines[i][len(b):]
            warnings.append('item %d: no changed span: note placed at entry %s (%s)'
                            % (it, key, 'listed in "items"' if listed else 'named by its rules/default'))

    lines.append(ctail)
    text = '\n'.join(lines)
    if not args.whole_spans:
        text = word_level(text)
    with open(OUT, 'w', encoding='utf-8') as fh:
        fh.write(text)

    replaced_from = set(REPLACES.values())
    missing = [k for k, _, _ in oents if k not in ckeys and k not in REMOVED and k not in replaced_from]
    for k in sorted(set(ckeys) - set(BIBLOC)) if args.bib else []:
        warnings.append('entry %s not found in the --bib files (note without location)' % k)
    for k in list(DEFAULT) + list(RULES) + list(ITEMS):
        if k not in ckeys:
            warnings.append('map key %s is not in the corrected .bbl' % k)
    for k, its in ITEMS.items():
        for it in its:
            if it not in NOTES:
                warnings.append('item %d listed for %s has no note' % (it, k))
    unnoted = sorted(set(NOTES) - noted)
    print(stats, 'notes:', sorted(noted))
    if unmatched_new:
        print('UNMATCHED corrected entries (no original entry, not in "new"; shown as new): ' +
              ', '.join('%s (item %d)' % x for x in unmatched_new), file=sys.stderr)
    if missing:
        print('UNMATCHED original entries (not in the corrected .bbl, not in "removed"; not shown): ' +
              ', '.join(missing), file=sys.stderr)
    if unnoted:
        print('notes never placed (no entry carries these items; list them under "items"): %s' % unnoted,
              file=sys.stderr)
    for w in dict.fromkeys(warnings):
        print('warning: ' + w, file=sys.stderr)


if __name__ == '__main__':
    main()
