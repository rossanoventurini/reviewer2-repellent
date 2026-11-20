#!/usr/bin/env python3
"""Check the links of changes.pdf: every link resolves, no two links overlap, item links land in the paper.

Usage: python3 pdf_links.py CHANGES.pdf --front N [--json]

N is the number of front pages (the paper starts on page N+1). Reads the PDF without a library (read_choices.py's
object reader: incremental updates and object streams included), follows the page tree, the named destinations
(/Names /Dests tree or /Dests dictionary) and every /Link annotation (/A GoTo or /Dest). Reports:
  - unresolved: links whose named destination does not exist (they jump nowhere, or to page 1);
  - overlaps: two link rectangles on one page that overlap (a link nested in another: one click, two targets);
  - item links of the front pages (destinations rrmark-*, rr-<n>) that land on a front page instead of the paper;
  - the number of links per kind of destination.
build_changes.py runs it on the marked PDF and prints the summary; exit status 1 when something is wrong.
Python stdlib only.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from read_choices import Ref, deref, objects, text  # noqa: E402


def pages_of(objs):
    cat = next((v for v in objs.values() if isinstance(v, dict) and v.get('Type') == 'Catalog'), None)
    if cat is None:
        raise ValueError('no catalog')
    out = []

    def walk(ref, depth=0):
        node = deref(objs, ref)
        if not isinstance(node, dict) or depth > 64:
            return
        if node.get('Type') == 'Page' or ('Kids' not in node and 'Contents' in node):
            out.append(ref[0] if isinstance(ref, Ref) else None)
            return
        for k in deref(objs, node.get('Kids')) or []:
            walk(k, depth + 1)
    walk(cat.get('Pages'))
    return cat, out


def dests_of(objs, cat):
    """{name: page object number}"""
    out = {}

    def page_of(d):
        d = deref(objs, d)
        if isinstance(d, dict):
            d = deref(objs, d.get('D'))
        if isinstance(d, list) and d and isinstance(d[0], Ref):
            return d[0][0]
        return None

    def tree(node, depth=0):
        node = deref(objs, node)
        if not isinstance(node, dict) or depth > 64:
            return
        names = deref(objs, node.get('Names'))
        if isinstance(names, list):
            for k in range(0, len(names) - 1, 2):
                out[text(names[k])] = page_of(names[k + 1])
        for kid in deref(objs, node.get('Kids')) or []:
            tree(kid, depth + 1)
    nm = deref(objs, cat.get('Names'))
    if isinstance(nm, dict) and nm.get('Dests') is not None:
        tree(nm['Dests'])
    old = deref(objs, cat.get('Dests'))
    if isinstance(old, dict):
        for k, v in old.items():
            out[k] = page_of(v)
    return out


def overlap(a, b):
    ax0, ay0, ax1, ay1 = min(a[0], a[2]), min(a[1], a[3]), max(a[0], a[2]), max(a[1], a[3])
    bx0, by0, bx1, by1 = min(b[0], b[2]), min(b[1], b[3]), max(b[0], b[2]), max(b[1], b[3])
    w, h = min(ax1, bx1) - max(ax0, bx0), min(ay1, by1) - max(ay0, by0)
    if w <= 0.5 or h <= 0.5:
        return False
    small = min((ax1 - ax0) * (ay1 - ay0), (bx1 - bx0) * (by1 - by0)) or 1
    return w * h > 0.3 * small


ITEM_DEST = re.compile(r'^(?:rrmark-\d+|rr-\d+)$')


def check(pdf, front):
    with open(pdf, 'rb') as fh:
        objs = objects(fh.read())
    cat, pages = pages_of(objs)
    index = {num: i + 1 for i, num in enumerate(pages)}
    dests = dests_of(objs, cat)
    res = dict(pages=len(pages), links=0, by_kind={}, unresolved=[], overlaps=[], item_on_front=[])
    for pno, num in enumerate(pages, 1):
        page = objs.get(num)
        annots = deref(objs, page.get('Annots')) if isinstance(page, dict) else None
        rects = []
        for a in annots or []:
            ad = deref(objs, a)
            if not isinstance(ad, dict) or ad.get('Subtype') != 'Link':
                continue
            act = deref(objs, ad.get('A'))
            dest = ad.get('Dest')
            if isinstance(act, dict):
                if act.get('S') != 'GoTo':
                    res['by_kind']['uri'] = res['by_kind'].get('uri', 0) + 1
                    rects.append((deref(objs, ad.get('Rect')), 'uri'))
                    res['links'] += 1
                    continue
                dest = act.get('D')
            dest = deref(objs, dest)
            res['links'] += 1
            name = text(dest) if isinstance(dest, (bytes, str)) else None
            kind = re.sub(r'[-.].*$', '', name) if name else 'explicit'
            res['by_kind'][kind] = res['by_kind'].get(kind, 0) + 1
            rects.append((deref(objs, ad.get('Rect')), name))
            if name is not None:
                target = dests.get(name)
                if target is None or target not in index:
                    res['unresolved'].append((pno, name))
                elif pno <= front and ITEM_DEST.match(name) and index[target] <= front:
                    res['item_on_front'].append((pno, name, index[target]))
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                ra, rb = rects[i][0], rects[j][0]
                if isinstance(ra, list) and isinstance(rb, list) and len(ra) == 4 and len(rb) == 4 and \
                        overlap([float(x) for x in ra], [float(x) for x in rb]):
                    res['overlaps'].append((pno, rects[i][1], rects[j][1]))
    return res


def summary(res):
    bad = len(res['unresolved']) + len(res['overlaps']) + len(res['item_on_front'])
    lines = ['links: %d on %d pages (%s)' % (res['links'], res['pages'], ', '.join(
        '%s %d' % kv for kv in sorted(res['by_kind'].items())))]
    if res['unresolved']:
        lines.append('unresolved destinations: ' + ', '.join('p.%d %s' % x for x in res['unresolved'][:12]))
    if res['overlaps']:
        lines.append('overlapping links: ' + ', '.join('p.%d %s/%s' % x for x in res['overlaps'][:12]))
    if res['item_on_front']:
        lines.append('item links landing on a front page: ' + ', '.join(
            'p.%d %s -> p.%d' % x for x in res['item_on_front'][:12]))
    if not bad:
        lines.append('OK: every link resolves, none overlaps, every item link lands in the paper')
    return '\n'.join(lines), bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('pdf')
    ap.add_argument('--front', type=int, required=True)
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    res = check(a.pdf, a.front)
    text_, bad = summary(res)
    print(json.dumps(res, indent=1) if a.json else text_)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
