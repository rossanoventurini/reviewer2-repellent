#!/usr/bin/env python3
"""Read the author's choices (the "do it" check boxes of each report item) and typed answers from a saved changes.pdf.

Usage: python3 read_choices.py CHANGES.pdf [--out PATH] [--defaults PATH] [--json]

CHANGES.pdf is the annotated copy of step 6, possibly ticked and re-saved by a PDF viewer (Preview, Acrobat, ...).
It has one AcroForm check box field per report item, named item-N: a parent field
  << /FT /Btn /T (item-12) /V /Yes|/Off /Ff flags /Kids [w1 0 R w2 0 R ...] >>
whose kids are the widgets (one next to every tag of the item) with /AS /Yes|/Off, or one merged field and widget
(/T and /AS in the same dictionary, no /Kids). Any state other than /Off counts as ticked (/Yes, /On, /1, ...);
without /V the kids' /AS decide (ticked if any is not /Off). Ff bit 1 (ReadOnly) marks the items that need the
authors' facts: they are always "dont" (nothing to apply until the facts are given).
The decision sheet also has one multi-line text field per question, named answer-N (/FT /Tx, merged field and
widget), where the author types the answer; its /V is a PDF text string (literal with escapes or hex; PDFDocEncoding,
UTF-16BE with BOM or UTF-8 with BOM). Line breaks (CR, CR LF) become LF; empty answers are left out.

The file is read without a PDF library: every object definition is collected in file order (top-level
"N G obj ... endobj" and the objects of every compressed object stream /Type /ObjStm, Flate), and a later
definition of an object number wins. This covers incremental updates (the way viewers save), object streams and
xref streams; the xref tables themselves are not needed.

--defaults (default: work/marked/r2states.tex next to the PDF, when it exists; written by apply_edits.py): one line
per item, \\rritemstate{12}{1}{0}{default: do -- certain fix} = item, default (1 do, 0 don't), read-only (1/0), the
reason of the default. Without it "default" is null and nothing counts as changed.
--out (default: work/choices.json next to the PDF when that folder exists, else ./choices.json):
  {"source": "changes.pdf",
   "items": {"12": {"choice": "do" | "dont", "default": "do" | "dont" | null, "changed": false,
                    "readonly": false, "reason": "default: do -- certain fix"}},
   "do": [3, 12], "dont": [5], "changed": [], "missing": [],      missing: items of the defaults with no field
   "answers": {"12": "42.1 is right: Table 3 is wrong"}}           the typed answers (non-empty only)
--json also prints the file. Exit status 1 when the PDF has neither an item-N nor an answer-N field. Python stdlib
only (zlib).
"""
import argparse
import json
import os
import re
import sys
import zlib

ITEM_T = re.compile(r'^item-(\d+)$')
ANSWER_T = re.compile(r'^answer-(\d+)$')
WS = b' \t\r\n\f\x00'
DELIM = b'()<>[]{}/%'


class Ref(tuple):
    """An indirect reference (num, gen)."""


class Name(str):
    """A PDF name, without the slash."""


# ---------------------------------------------------------------- tokenizer / parser
class Parser:
    def __init__(self, data, pos=0):
        self.d, self.i = data, pos

    def ws(self):
        d, n = self.d, len(self.d)
        while self.i < n:
            c = d[self.i:self.i + 1]
            if c in (b' ', b'\t', b'\r', b'\n', b'\f', b'\x00'):
                self.i += 1
            elif c == b'%':
                while self.i < n and d[self.i:self.i + 1] not in (b'\r', b'\n'):
                    self.i += 1
            else:
                break

    def regular(self):
        j = self.i
        while j < len(self.d) and self.d[j] not in WS and self.d[j] not in DELIM:
            j += 1
        tok, self.i = self.d[self.i:j], j
        return tok

    def value(self):
        self.ws()
        d = self.d
        if self.i >= len(d):
            raise ValueError('end of data')
        c = d[self.i:self.i + 1]
        if c == b'<' and d[self.i:self.i + 2] == b'<<':
            self.i += 2
            out = {}
            while True:
                self.ws()
                if d[self.i:self.i + 2] == b'>>':
                    self.i += 2
                    return out
                k = self.value()
                out[str(k)] = self.value()
        if c == b'<':
            j = d.index(b'>', self.i)
            h = re.sub(rb'[^0-9A-Fa-f]', b'', d[self.i + 1:j])
            self.i = j + 1
            if len(h) % 2:
                h += b'0'
            return bytes.fromhex(h.decode())
        if c == b'(':
            return self.literal()
        if c == b'[':
            self.i += 1
            out = []
            while True:
                self.ws()
                if d[self.i:self.i + 1] == b']':
                    self.i += 1
                    return out
                out.append(self.value())
        if c == b'/':
            self.i += 1
            raw = self.regular()
            raw = re.sub(rb'#([0-9A-Fa-f]{2})', lambda m: bytes([int(m.group(1), 16)]), raw)
            return Name(raw.decode('latin-1'))
        tok = self.regular()
        if not tok:
            self.i += 1
            return None
        if re.fullmatch(rb'[+-]?\d+', tok):
            save = self.i
            self.ws()
            m = re.match(rb'(\d+)\s+R(?![^\s/\[\]<>()%])', d[self.i:self.i + 32])
            if m:
                self.i += m.end()
                return Ref((int(tok), int(m.group(1))))
            self.i = save
            return int(tok)
        if re.fullmatch(rb'[+-]?(\d+\.?\d*|\.\d+)', tok):
            return float(tok)
        return {b'true': True, b'false': False, b'null': None}.get(tok, tok)

    def literal(self):
        d, out, depth = self.d, bytearray(), 0
        self.i += 1
        esc = {ord('n'): b'\n', ord('r'): b'\r', ord('t'): b'\t', ord('b'): b'\b', ord('f'): b'\f'}
        while self.i < len(d):
            c = d[self.i]
            if c == 0x5c:   # backslash
                nx = d[self.i + 1]
                if nx in esc:
                    out += esc[nx]
                    self.i += 2
                elif 0x30 <= nx <= 0x37:
                    m = re.match(rb'[0-7]{1,3}', d[self.i + 1:self.i + 4])
                    out.append(int(m.group(0), 8) & 0xff)
                    self.i += 1 + m.end()
                elif nx in (0x0d, 0x0a):
                    self.i += 2
                    if nx == 0x0d and d[self.i:self.i + 1] == b'\n':
                        self.i += 1
                else:
                    out.append(nx)
                    self.i += 2
                continue
            if c == 0x28:
                depth += 1
            elif c == 0x29:
                if depth == 0:
                    self.i += 1
                    return bytes(out)
                depth -= 1
            out.append(c)
            self.i += 1
        return bytes(out)


# PDFDocEncoding where it differs from Latin-1 (PDF 32000, Annex D)
PDFDOC = {0x18: '\u02d8', 0x19: '\u02c7', 0x1a: '\u02c6', 0x1b: '\u02d9', 0x1c: '\u02dd', 0x1d: '\u02db',
          0x1e: '\u02da', 0x1f: '\u02dc', 0x80: '\u2022', 0x81: '\u2020', 0x82: '\u2021', 0x83: '\u2026',
          0x84: '\u2014', 0x85: '\u2013', 0x86: '\u0192', 0x87: '\u2044', 0x88: '\u2039', 0x89: '\u203a',
          0x8a: '\u2212', 0x8b: '\u2030', 0x8c: '\u201e', 0x8d: '\u201c', 0x8e: '\u201d', 0x8f: '\u2018',
          0x90: '\u2019', 0x91: '\u201a', 0x92: '\u2122', 0x93: '\ufb01', 0x94: '\ufb02', 0x95: '\u0141',
          0x96: '\u0152', 0x97: '\u0160', 0x98: '\u0178', 0x99: '\u017d', 0x9a: '\u0131', 0x9b: '\u0142',
          0x9c: '\u0153', 0x9d: '\u0161', 0x9e: '\u017e', 0xa0: '\u20ac'}


def text(v):
    """A PDF text string (PDFDocEncoding, UTF-16BE with BOM or UTF-8 with BOM) as str."""
    if isinstance(v, bytes):
        if v.startswith(b'\xfe\xff'):
            return v[2:].decode('utf-16-be', 'replace')
        if v.startswith(b'\xef\xbb\xbf'):
            return v[3:].decode('utf-8', 'replace')
        return ''.join(PDFDOC.get(b, chr(b)) for b in v)
    return v if isinstance(v, str) else None


# ---------------------------------------------------------------- objects
OBJ = re.compile(rb'(?<![0-9])(\d+)\s+(\d+)\s+obj\b')


def decode_stream(dic, raw):
    f = dic.get('Filter')
    fs = f if isinstance(f, list) else ([f] if f else [])
    for x in fs:
        if x != 'FlateDecode':
            raise ValueError('unsupported stream filter %s' % x)
        raw = zlib.decompressobj().decompress(raw)
    return raw


def objects(data):
    """{num: value} of every object, later definitions winning (incremental updates, object streams)."""
    out = {}
    pos = 0
    while True:
        m = OBJ.search(data, pos)
        if not m:
            break
        num = int(m.group(1))
        p = Parser(data, m.end())
        try:
            val = p.value()
        except (ValueError, IndexError):
            pos = m.end()
            continue
        end = p.i
        p.ws()
        if isinstance(val, dict) and data[p.i:p.i + 6] == b'stream':
            s = p.i + 6
            if data[s:s + 2] == b'\r\n':
                s += 2
            elif data[s:s + 1] in (b'\n', b'\r'):
                s += 1
            ln = val.get('Length')
            if isinstance(ln, int) and data[s + ln:s + ln + 20].lstrip(b'\r\n ').startswith(b'endstream'):
                e = s + ln
            else:
                e = data.index(b'endstream', s)
            raw = data[s:e]
            end = e + len(b'endstream')
            if val.get('Type') == 'ObjStm':
                out[num] = val
                try:
                    inner = decode_stream(val, raw)
                except (ValueError, zlib.error):
                    inner = None
                if inner is not None:
                    first, n = int(val.get('First', 0)), int(val.get('N', 0))
                    hdr = [int(x) for x in inner[:first].split()]
                    pairs = list(zip(hdr[0::2], hdr[1::2]))[:n]
                    for k, (onum, off) in enumerate(pairs):
                        try:
                            out[onum] = Parser(inner, first + off).value()
                        except (ValueError, IndexError):
                            pass
            else:
                out[num] = val
        else:
            out[num] = val
        e2 = data.find(b'endobj', end)
        pos = (e2 + 6) if e2 != -1 else end
    return out


def deref(objs, v, depth=0):
    while isinstance(v, Ref) and depth < 32:
        v = objs.get(v[0])
        depth += 1
    return v


def is_on(state):
    return state is not None and str(state) != 'Off'


def read_fields(pdf_path):
    """{item: (ticked, readonly)} of the item-N check box fields of the PDF."""
    with open(pdf_path, 'rb') as fh:
        data = fh.read()
    objs = objects(data)
    found = {}
    for num in sorted(objs, key=lambda k: k):
        d = objs[num]
        if not isinstance(d, dict) or 'T' not in d:
            continue
        name = text(deref(objs, d['T']))
        m = ITEM_T.match(name or '')
        if not m:
            continue
        item = int(m.group(1))
        v = deref(objs, d.get('V'))
        if v is not None and isinstance(v, str):
            ticked = is_on(v)
        else:
            kids = deref(objs, d.get('Kids')) or []
            states = []
            for k in kids:
                kd = deref(objs, k)
                if isinstance(kd, dict) and 'AS' in kd:
                    states.append(deref(objs, kd['AS']))
            if 'AS' in d:
                states.append(deref(objs, d['AS']))
            ticked = any(is_on(s) for s in states)
        ff = deref(objs, d.get('Ff'))
        readonly = bool(int(ff) & 1) if isinstance(ff, (int, float)) else False
        found[item] = (ticked, readonly)
    return found


def read_answers(pdf_path, objs=None, keep_empty=False):
    """{item: text} of the non-empty answer-N text fields of the PDF (keep_empty: every answer field)."""
    if objs is None:
        with open(pdf_path, 'rb') as fh:
            objs = objects(fh.read())
    out = {}
    for num in sorted(objs):
        d = objs[num]
        if not isinstance(d, dict) or 'T' not in d:
            continue
        m = ANSWER_T.match(text(deref(objs, d['T'])) or '')
        if not m:
            continue
        v = deref(objs, d.get('V'))
        t = text(v).replace('\r\n', '\n').replace('\r', '\n').strip() if isinstance(v, bytes) else ''
        if t or keep_empty:   # (a /V that is a stream or a dict, rich text, is not read)
            out[int(m.group(1))] = t
    return out


# ---------------------------------------------------------------- defaults and choices
STATE = re.compile(r'\\rritemstate\{(\d+)\}\{([01])\}\{([01])\}\{(.*)\}\s*$')


def load_defaults(path):
    """{item: {"default": "do" | "dont", "readonly": bool, "reason": str}} of r2states.tex."""
    out = {}
    with open(path, encoding='utf-8') as fh:
        for ln in fh:
            m = STATE.match(ln.strip())
            if m:
                reason = m.group(4)
                for a, b in (('\\%', '%'), ('\\&', '&'), ('\\_', '_'), ('\\#', '#'), ('---', '\u2014'),
                             ('--', '\u2013')):
                    reason = reason.replace(a, b)
                out[int(m.group(1))] = {'default': 'do' if m.group(2) == '1' else 'dont',
                                        'readonly': m.group(3) == '1', 'reason': reason}
    return out


def choices(pdf, defaults=None):
    """The choices of the PDF as in the JSON file. defaults: a dict of load_defaults, a path, or None."""
    if isinstance(defaults, str):
        defaults = load_defaults(defaults)
    defaults = defaults or {}
    fields = read_fields(pdf)
    answers = read_answers(pdf, keep_empty=True)
    if not fields and not answers:   # (XeLaTeX builds have no item boxes, only the answer fields)
        raise ValueError('%s has no item-N check box fields: is it a changes.pdf built with the choice boxes?' % pdf)
    items = {}
    for n in sorted(fields):
        ticked, ro = fields[n]
        df = defaults.get(n)
        ro = ro or bool(df and df['readonly'])
        choice = 'do' if ticked and not ro else 'dont'
        dflt = df['default'] if df else None
        items[str(n)] = {'choice': choice, 'default': dflt, 'changed': dflt is not None and choice != dflt,
                         'readonly': ro, 'reason': df['reason'] if df else ''}
    ints = lambda pred: sorted(int(k) for k, v in items.items() if pred(v))
    return {'source': pdf, 'items': items, 'do': ints(lambda v: v['choice'] == 'do'),
            'dont': ints(lambda v: v['choice'] == 'dont'), 'changed': ints(lambda v: v['changed']),
            'missing': sorted(n for n in defaults if n not in fields),
            'answers': {str(n): answers[n] for n in sorted(answers) if answers[n]}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('pdf')
    ap.add_argument('--out', default=None)
    ap.add_argument('--defaults', default=None)
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    here = os.path.dirname(os.path.abspath(a.pdf))
    work = os.path.join(here, 'work')
    dflt = a.defaults
    if dflt is None and os.path.isfile(os.path.join(work, 'marked', 'r2states.tex')):
        dflt = os.path.join(work, 'marked', 'r2states.tex')
    if dflt is not None and not os.path.isfile(dflt):
        print('defaults file not found: %s' % dflt, file=sys.stderr)
        return 1
    try:
        res = choices(a.pdf, dflt)
    except (OSError, ValueError) as ex:
        print('ERROR: %s' % ex, file=sys.stderr)
        return 1
    out = a.out or (os.path.join(work, 'choices.json') if os.path.isdir(work) else 'choices.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, indent=1)
        fh.write('\n')
    n = len(res['items'])
    print("%d items: %d do, %d don't, %d changed from the default, %d answer%s%s -> %s" % (
        n, len(res['do']), len(res['dont']), len(res['changed']), len(res['answers']),
        '' if len(res['answers']) == 1 else 's',
        ('; %d items of the defaults have no box: %s' % (len(res['missing']), res['missing'][:10]))
        if res['missing'] else '', out))
    if a.json:
        print(json.dumps(res, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
