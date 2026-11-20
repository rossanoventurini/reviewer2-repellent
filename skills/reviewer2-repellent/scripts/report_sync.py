#!/usr/bin/env python3
"""Make report.md say what step 6 established, where a script can: the counts of section 1 and the file names.

Usage: python3 report_sync.py OUT_DIR [--dry-run]

OUT_DIR is the output folder of the run. Reads report.md, work/edits.tsv (apply_edits.py) and, when present,
work/marked/r2states.tex (the pre-set check boxes). build_changes.py runs it after apply_edits.py, so the front pages,
edits.md and report.md give the same counts:
  - the sentence of section 1 that starts "In the corrected copy" is rewritten from work/edits.tsv, with the same
    classification as the front pages (front_pages.classify: fixed, to confirm, your facts, to check, optional,
    note only, not applied; an applied item with a question in section 9 is to confirm), and the pre-set boxes;
    the sentence is added after the "Total ..." line when the report has none;
  - names of earlier builds (changes-v3.pdf, changes_old.pdf) become changes.pdf;
  - an item whose "*In the copy:*" line disagrees with its kind is listed as a warning (the agent fixes the line:
    SKILL.md step 6, update the report).
  - with --build-id, a line "Build: `<id>` (...)" in section 1 (build_changes.py; the same id as changes.pdf,
    edits.md and corrected/);
  - questions of section 9 that only ask about a difference within rounding (within_rounding) are dropped, with a
    warning to make their edits `log`;
  - warnings: temporary paths in report.md, items without a "Severity:", numbers in the evidence of the numbers
    section without a source (provenance_gaps).
Prints what it changed; report.md is rewritten only when something changed. Python stdlib only.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import front_pages  # noqa: E402

PHRASE = [('fixed', '%d fixed'), ('confirm', '%d applied but to confirm'),
          ('facts', '%d need facts only the authors have (orange placeholders)'),
          ('check', '%d to check with nothing changed'), ('optional', '%d optional wording changes'),
          ('note', '%d with a margin note only'), ('notapplied', '%d not applied')]
# what an "*In the copy:*" line must say for each kind (any of the words)
EXPECT = {'fixed': r'applied|fixed', 'confirm': r'to confirm|to check|applied', 'facts': r'missing facts|placeholder|facts',
          'check': r'to check|nothing changed', 'optional': r'optional|applied', 'note': r'note|not applied',
          'notapplied': r'not applied'}
STALE = re.compile(r'\bchanges[-_](?:v\d+|old|new|\d+)\.pdf\b')
TEMP_PATH = re.compile(r'(?:/private)?/(?:tmp|var/folders)/\S+|\S*/scratchpad/\S*')
BUILD_LINE = re.compile(r'^Build: `?[0-9a-f]{6,}`?.*$', re.M)
ROUNDING = re.compile(r'\b(un)?round(ed|ing)?\b', re.I)
SOURCE = re.compile(r'\b(Table|Tab\.|Fig\.|Figure|Figs\.|cell|row|column|computed|recomputed|read from|plot|panel|'
                    r'Eq\.|Section|Sec\.)|`[^`]*\.(?:tex|pdf|csv|png)|[=/×÷]|\.tex:\d', re.I)


def decimals(text):
    return [(m.group(0), len(m.group(0).split('.')[1])) for m in re.finditer(r'(?<![\d.])\d+\.\d+(?![\d.])', text)]


def within_rounding(question, item_text=''):
    """True when a question only asks which of two values that differ by one unit in the last printed digit is right,
    about a rounded or recomputed value (references/merge-agent.md: such questions are dropped)."""
    both = (question or '') + ' ' + (item_text or '')
    if not ROUNDING.search(both):
        return False
    nums = decimals(both)
    for i, (a, da) in enumerate(nums):
        for b, db in nums[i + 1:]:
            if da == db and a != b and abs(float(a) - float(b)) <= 10 ** -da * 1.0001:
                return True
    return False


def provenance_gaps(report):
    """Items of the numbers section whose evidence has numbers but names no source (table cell, figure, computation)."""
    sec = next(((n, its) for n, t, its in report['sections'] if t.lower().startswith('numbers')), None)
    out = []
    for i in (sec[1] if sec else []):
        body = report['texts'].get(i, '')
        ev = re.split(r'\bFix:', body)[0]
        if len(decimals(ev)) + len(re.findall(r'(?<![\d.])\d{2,}(?![\d.])', ev)) >= 2 and not SOURCE.search(ev):
            out.append(i)
    return out


def sentence(counts, cls, items, states):
    parts = []
    for key, txt in PHRASE:
        n = counts.get(key, 0)
        if not n:
            continue
        t = txt % n
        if key in ('check', 'note', 'notapplied') and n <= 4:
            t += ' (%s)' % ', '.join('#%d' % i for i in sorted(items) if cls.get(i, ('notapplied',))[0] == key)
        parts.append(t)
    out = 'In the corrected copy: %s.' % ', '.join(parts)
    if states:
        tick = sum(1 for v in states.values() if v[0])
        ro = sum(1 for v in states.values() if v[1])
        out += (' Check boxes in changes.pdf: %d pre-set to apply, %d not%s; corrected/ follows them.' % (
            tick, len(states) - tick - ro, (', %d waiting for facts' % ro) if ro else ''))
    return out


def summary_end(lines):
    """The index of the last non-empty line of section 1 plus one (where a sentence goes when there is no "Total"
    line), or None without a section 1."""
    start = next((i for i, ln in enumerate(lines) if re.match(r'^##\s+1\.\s', ln)), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('## ')), len(lines))
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    return end


def sync(out_dir, build_id=None):
    rp = os.path.join(out_dir, 'report.md')
    with open(rp, encoding='utf-8') as fh:
        text = fh.read()
    report = front_pages.parse_report(rp)
    rows = front_pages.read_log(os.path.join(out_dir, 'work', 'edits.tsv'))
    cls = front_pages.classify(rows, report['questions'])
    counts = front_pages.item_counts(report['items'], cls)
    states = {}
    for dp, dns, fns in os.walk(os.path.join(out_dir, 'work', 'marked')):   # next to the root (maybe in a subfolder)
        dns.sort()
        if 'r2states.tex' in fns:
            states = front_pages.read_states(os.path.join(dp, 'r2states.tex'))
            break
    new_sent = sentence(counts, cls, report['items'], states)
    changes, warnings = [], []
    lines = text.split('\n')
    sec, done, total_at = None, False, None
    for i, ln in enumerate(lines):
        h = re.match(r'^##\s+(\d+)\.\s+(.*?)\s*$', ln)
        if h:
            sec = h.group(2).lower()
            continue
        if sec and sec.startswith('summary'):
            if re.match(r'^\s*In the corrected copy\b', ln):
                if ln.strip() != new_sent:
                    changes.append('section 1: "%s..." -> "%s"' % (ln.strip()[:60], new_sent))
                    lines[i] = new_sent
                done = True
            elif re.match(r'^\s*Total\b', ln):
                total_at = i
    if not done:
        at = total_at + 1 if total_at is not None else summary_end(lines)
        if at is not None:
            lines[at:at] = ['', new_sent] + ([''] if total_at is None else [])
            changes.append('section 1: added "%s"' % new_sent)
    # questions within rounding are not questions (merge-agent.md): out of section 9
    sec = None
    keep = []
    for ln in lines:
        h = re.match(r'^##\s+(\d+)\.\s+(.*?)\s*$', ln)
        if h:
            sec = h.group(2).lower()
        m = re.match(r'^\s*[-*]\s+\*\*#?(\d+)\*\*\s*:?\s*(.*)$', ln) if sec and sec.startswith('question') else None
        if m and within_rounding(m.group(2), report['texts'].get(int(m.group(1)), '')):
            changes.append('section 9: dropped the question of #%s (the two values differ only by rounding)' % m.group(1))
            warnings.append('item #%s asks about a difference within rounding: make its edits `log` ("not applied: '
                            'within rounding") and its *In the copy:* line say so' % m.group(1))
            continue
        keep.append(ln)
    lines = keep
    text2 = '\n'.join(lines)
    if build_id:
        bl = ('Build: `%s` (report.md, changes.pdf, edits.md and corrected/ of this folder come from this build).'
              % build_id)
        if BUILD_LINE.search(text2):
            if BUILD_LINE.search(text2).group(0) != bl:
                text2 = BUILD_LINE.sub(bl, text2, count=1)
                changes.append('build id %s' % build_id)
        else:
            text2 = text2.replace(new_sent, new_sent + '\n\n' + bl, 1)
            changes.append('build id %s' % build_id)
    stale = sorted(set(STALE.findall(text2)))
    if stale:
        text2 = STALE.sub('changes.pdf', text2)
        changes.append('file names %s -> changes.pdf' % ', '.join(stale))
    for p_ in sorted(set(TEMP_PATH.findall(text2))):
        warnings.append('report.md names a temporary path: %s (give the output folder instead)' % p_)
    miss = sorted(i for i in report['items'] if i not in report.get('severity_given', set())
                  and any(i in its for _, t, its in report['sections'] if not t.lower().startswith(('typos',
                                                                                                    'appendix'))))
    if miss:
        warnings.append('items without a "Severity:" (desk-reject / major / minor / optional), taken from their '
                        'section: %s' % ', '.join('#%d' % i for i in miss[:20]) + (' ...' if len(miss) > 20 else ''))
    gaps = provenance_gaps(report)
    if gaps:
        warnings.append('numbers without a source (table cell, figure and how read, computation) in the evidence of: '
                        '%s' % ', '.join('#%d' % i for i in gaps))
    for n, body in report['texts'].items():
        m = re.search(r'\*In the copy:\*\s*([^\n]*)', body)
        if not m:
            continue
        kind = cls.get(n, ('notapplied',))[0]
        if not re.search(EXPECT[kind], m.group(1), re.I):
            warnings.append('item #%d: "*In the copy:* %s" but work/edits.tsv makes it %s' % (
                n, m.group(1)[:60], front_pages.SHORT[kind]))
        elif kind == 'facts' and re.search(r'nothing changed', m.group(1), re.I):
            warnings.append('item #%d: "*In the copy:* %s" but the copy has a placeholder [#%d: ...]' % (
                n, m.group(1)[:60], n))
    return text, text2, changes, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('out')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--build-id', default=None, help='write "Build: <id>" in section 1 (build_changes.py)')
    a = ap.parse_args()
    text, text2, changes, warnings = sync(os.path.abspath(a.out), a.build_id)
    for c in changes:
        print('report.md: ' + c)
    for w in warnings:
        print('warning: ' + w)
    if text2 != text and not a.dry_run:
        with open(os.path.join(a.out, 'report.md'), 'w', encoding='utf-8') as fh:
            fh.write(text2)
    if not changes:
        print('report.md: counts already follow work/edits.tsv')
    return 0


if __name__ == '__main__':
    sys.exit(main())
