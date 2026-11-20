#!/usr/bin/env python3
"""Check where the margin notes of the annotated PDF landed (step 6), from the records r2changes.sty writes to the
.aux of the last LaTeX run:
  \\rr@at{k}{n}{page}{y}               note k of item n, at the line y (sp from the page bottom) of that page
  \\rr@placed{k}{note page}{box page}{shift}   box k drawn on that page, shift = how far below its line (pt)
  \\rr@markat{m}{n}{page}              mark (tag #n) m of item n on that page
  \\rr@hasshort{k}                     note k has a short text (\\rrnotepair)
Pages are counted from the first page of the PDF (front pages included).

Usage: python3 check_notes.py MAIN.aux [--json OUT.json] [--line-tol 1.5]

Fails (exit 1) if a note has no box or its box is on another page than the note. Reports how many boxes sit on
their line (shift <= --line-tol pt), how many moved down or up and by how much, and the items whose box shares no
page with any tag of the item (a note placed at the end of a sentence that runs onto the next page, or a note given
its own place). Follows \\@input{...} to the .aux files of \\include'd chapters. Python stdlib only.
"""
import argparse
import json
import os
import re
import sys

AT = re.compile(r'\\rr@at\{(\d+)\}\{([^{}]*)\}\{(\d+)\}\{(-?\d+)\}')
PLACED = re.compile(r'\\rr@placed\{(\d+)\}\{(\d+)\}\{(\d+)\}\{(-?[\d.]+)pt\}')
MARKAT = re.compile(r'\\rr@markat\{(\d+)\}\{([^{}]*)\}\{(\d+)\}')
HASSHORT = re.compile(r'\\rr@hasshort\{(\d+)\}')
INPUT = re.compile(r'\\@input\{([^{}]+)\}')


def read_aux(path, seen=None):
    """Text of an .aux file and of the .aux files it \\@input's."""
    seen = set() if seen is None else seen
    path = os.path.abspath(path)
    if path in seen or not os.path.isfile(path):
        return ''
    seen.add(path)
    with open(path, encoding='utf-8', errors='replace') as fh:
        t = fh.read()
    parts = [t]
    for m in INPUT.finditer(t):
        parts.append(read_aux(os.path.join(os.path.dirname(path), m.group(1)), seen))
    return '\n'.join(parts)


def records(text):
    """(notes {k: (item, page, y)}, placed {k: (note page, box page, shift pt)}, marks {m: (item, page)})."""
    notes, placed, marks = {}, {}, {}
    for m in AT.finditer(text):
        notes.setdefault(int(m.group(1)), (m.group(2), int(m.group(3)), int(m.group(4))))
    for m in PLACED.finditer(text):
        placed[int(m.group(1))] = (int(m.group(2)), int(m.group(3)), float(m.group(4)))
    for m in MARKAT.finditer(text):
        marks.setdefault(int(m.group(1)), (m.group(2), int(m.group(3))))
    return notes, placed, marks


def with_short(text):
    """Numbers of the notes that have a short text."""
    return {int(m.group(1)) for m in HASSHORT.finditer(text)}


def page_shifts(text):
    """{page: [(note, item, shift pt)]} of the drawn boxes, in note order."""
    notes, placed, _ = records(text)
    out = {}
    for k in sorted(placed):
        if k in notes:
            out.setdefault(notes[k][1], []).append((k, notes[k][0], placed[k][2]))
    return out


def check(text, tol=1.5):
    notes, placed, marks = records(text)
    tags = {}
    for item, page in marks.values():
        tags.setdefault(item, set()).add(page)
    off_page = []
    for k, (item, page, _) in sorted(notes.items()):
        if k not in placed:
            off_page.append({'note': k, 'item': item, 'note_page': page, 'box_page': None})
        elif placed[k][1] != page:
            off_page.append({'note': k, 'item': item, 'note_page': page, 'box_page': placed[k][1]})
    shifts = {k: placed[k][2] for k in placed if k in notes}
    down = sorted((s for s in shifts.values() if s > tol), reverse=True)
    up = sorted((s for s in shifts.values() if s < -tol))
    no_tag = sorted({(notes[k][0], notes[k][1]) for k in notes
                     if notes[k][0] in tags and notes[k][1] not in tags[notes[k][0]]},
                    key=lambda x: (x[1], int(x[0]) if x[0].isdigit() else 0))
    return {
        'notes': len(notes), 'boxes': len(shifts), 'marks': len(marks),
        'off_page': off_page,
        'on_line': sum(1 for s in shifts.values() if abs(s) <= tol),
        'moved_down': len(down), 'max_down_pt': round(down[0], 1) if down else 0.0,
        'median_down_pt': round(down[len(down) // 2], 1) if down else 0.0,
        'moved_up': len(up), 'max_up_pt': round(-up[0], 1) if up else 0.0,
        'box_without_tag_on_page': [{'item': i, 'page': p} for i, p in no_tag],
        'pages_with_notes': len({p for _, p, _ in notes.values()}),
    }


def summary(r):
    lines = ['notes: %d, boxes drawn: %d, marks: %d, pages with notes: %d'
             % (r['notes'], r['boxes'], r['marks'], r['pages_with_notes']),
             'boxes on their line: %d; moved down: %d (max %.1fpt, median %.1fpt); moved up: %d (max %.1fpt)'
             % (r['on_line'], r['moved_down'], r['max_down_pt'], r['median_down_pt'], r['moved_up'], r['max_up_pt'])]
    if r['box_without_tag_on_page']:
        lines.append('info: boxes on a page with no tag of their item: ' + ', '.join(
            '#%s p.%d' % (x['item'], x['page']) for x in r['box_without_tag_on_page']))
    if r['off_page']:
        lines.append('FAIL: %d boxes not on the page of their note: ' % len(r['off_page']) + ', '.join(
            '#%s (note p.%s, box %s)' % (x['item'], x['note_page'],
                                          'missing' if x['box_page'] is None else 'p.%d' % x['box_page'])
            for x in r['off_page']))
    elif r['notes'] == 0:
        lines.append('no notes recorded (is r2changes.sty loaded, and has LaTeX run twice?)')
    else:
        lines.append('OK: every box is on the page of its note')
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('aux')
    ap.add_argument('--json', default=None, help='write the full result here')
    ap.add_argument('--line-tol', type=float, default=1.5, help='shift (pt) still counted as on the line')
    args = ap.parse_args()
    if not os.path.isfile(args.aux):
        sys.exit('no such .aux file: %s' % args.aux)
    r = check(read_aux(args.aux), args.line_tol)
    print(summary(r))
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as fh:
            json.dump(r, fh, indent=1)
    return 1 if r['off_page'] else 0


if __name__ == '__main__':
    sys.exit(main())
