#!/usr/bin/env python3
"""Build the corrected copy and the annotated PDF of step 6 in one go.

Usage: python3 build_changes.py OUT_DIR [--root main.tex] [--engine pdflatex|xelatex|lualatex] [--date YYYY-MM-DD]
                                [--max-runs 12] [--crowd-tol 18] [--no-png] [--open] [--choices choices.json]
                                [--final-dir DIR] [--strict]

One consistent build: report.md (synced), changes.pdf, edits.md and corrected/ are written in this one run, carry the
same build id (a hash of the spec, the choices, the sources and the report) and are checked against each other at
the end (verify(): ids, items and kinds, counts, ticked boxes = corrected/, legend, no stale or temporary names);
any disagreement fails the build. OUT_DIR must not be a temporary or scratch folder unless --final-dir gives the
folder where the user will find the files (the summary page names it). --root may name a root in a subfolder
(sub/main.tex): LaTeX runs in that folder (latexmk -cd). --strict passes --strict to apply_edits.py (applied text
with terms, numbers or explanations not in the paper is an error).

OUT_DIR is the output folder of the run (SKILL.md). Reads:
  work/paper/               clean copy of the sources
  work/edits.json           the edit spec (apply_edits.py; .bib edits included)
  work/tmp/bbl-map.json     which item each bibliography change belongs to (mark_bbl.py); needed only when the
                            bibliography changes
  work/venue.md, work/venue-status.json, report.md   for the front pages (front_pages.py)
  work/ai-traces.json       the "Traces of AI use" page (ai_traces.py + the agent's fields); no page without it
  work/checks.json          the "What we checked" page and the cover's statistics: rewritten here by check_stats.py
                            from the files of the run and the sources (scope_stats.py)
Steps: apply_edits.py -> corrected/ and work/marked/ (log work/edits.tsv); compile the original and corrected/ with
latexmk in work/tmp/ (corrected/ stays clean) and compare pages and overfull boxes; mark the .bbl (mark_bbl.py,
word level, notes with the .bib line) or copy it; add the front pages to the marked copy (\\usepackage[front]
{r2changes}, \\input{rrfront}); run LaTeX on the marked copy (no BibTeX) until the .aux records stop changing,
regenerating the front pages before each run and fitting each one to its page (references/pdf-layout.md: from the
fill that LaTeX writes to the log, a page that overflows goes one level down, one under 90% one level up; the fill
and the levels are printed at the end); crowded pages: on every page where a box sits more than --crowd-tol
pt (about 1.5 lines) off its line, the notes switch to their short text (note_short; work/marked/<root>.rrs) and
LaTeX runs again, at most twice, with a report per page; check the note placement (check_notes.py); write changes.pdf and
edits.md; render the front pages and the most crowded pages to work/tmp/pages/ (unless --no-png); with --open, open
changes.pdf in the system viewer (open / xdg-open / start; a failure only prints the path).
Exit status 1 with a clear message at the first failing step. Python stdlib only.
"""
import argparse
import datetime
import filecmp
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hashlib  # noqa: E402
import tempfile  # noqa: E402
import check_notes  # noqa: E402
import front_pages  # noqa: E402
import pdf_links  # noqa: E402
import read_choices  # noqa: E402
import report_sync  # noqa: E402

BUILD_EXT = ('.aux', '.log', '.out', '.toc', '.lof', '.lot', '.fls', '.fdb_latexmk', '.synctex.gz', '.blg', '.bbl',
             '.bcf', '.run.xml', '.nav', '.snm', '.vrb', '.pdf')


class Fail(Exception):
    pass


def say(msg):
    print(msg, flush=True)


def run(cmd, cwd=None, timeout=900):
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors='replace', timeout=timeout)
    except FileNotFoundError:
        raise Fail('command not found: %s (see SETUP.md)' % cmd[0])
    except subprocess.TimeoutExpired:
        raise Fail('timed out after %d s: %s' % (timeout, ' '.join(cmd)))


def find_root(paper, given):
    if given:
        given = os.path.normpath(given)
        if os.path.isabs(given) or given.startswith('..'):
            raise Fail('--root must be a path inside work/paper: %s' % given)
        if not os.path.isfile(os.path.join(paper, given)):
            raise Fail('root file not found in work/paper: %s' % given)
        return given
    roots = []
    for fn in sorted(os.listdir(paper)):
        if fn.endswith('.tex'):
            with open(os.path.join(paper, fn), encoding='utf-8', errors='replace') as fh:
                t = fh.read()
            if re.search(r'^[^%\n]*\\documentclass', t, re.M) and re.search(r'^[^%\n]*\\begin\{document\}', t, re.M):
                roots.append(fn)
    if len(roots) != 1:
        raise Fail('cannot tell the root file in work/paper (%s): give --root' % (', '.join(roots) or 'none found'))
    return roots[0]


def fresh_copy(src, dst, stem):
    """Copy the sources without the build files of the root (figures, also PDF ones, are kept). stem may name a
    subfolder (sub/main): the build files of that folder are left out."""
    if os.path.exists(dst):
        shutil.rmtree(dst)
    top = os.path.abspath(os.path.join(src, os.path.dirname(stem)))
    base = os.path.basename(stem)
    shutil.copytree(src, dst, symlinks=True, ignore=lambda d, fs: [
        f for f in fs if os.path.abspath(d) == top and f.startswith(base + '.') and f.endswith(BUILD_EXT)
        and f != base + '.tex'])


def latexmk(folder, root, engine):
    flag = {'pdflatex': '-pdf', 'xelatex': '-xelatex', 'lualatex': '-lualatex'}[engine]
    # -cd: LaTeX runs in the root's folder (a root in a subfolder keeps its \input paths), the PDF, log and .bbl
    # land next to it
    # -no-shell-escape: no command in the paper is executed (it also overrides -shell-escape set in a latexmkrc)
    r = run(['latexmk', flag, '-no-shell-escape', '-cd', '-interaction=nonstopmode', '-f', root], cwd=folder)
    stem = os.path.splitext(root)[0]
    pdf = os.path.join(folder, stem + '.pdf')
    if not os.path.isfile(pdf):
        raise Fail('LaTeX produced no PDF in %s: see %s' % (folder, os.path.join(folder, stem + '.log')))
    return pdf


def log_text(folder, root):
    p = os.path.join(folder, os.path.splitext(root)[0] + '.log')
    with open(p, encoding='latin-1') as fh:
        return fh.read()


def errors_of(log):
    return [ln for ln in log.split('\n') if ln.startswith('! ')]


def overfull(log):
    return len(re.findall(r'^Overfull \\hbox', log, re.M))


def pages_of(pdf):
    r = run(['pdfinfo', pdf])
    m = re.search(r'^Pages:\s+(\d+)', r.stdout, re.M)
    return int(m.group(1)) if m else None


def aux_state(aux):
    t = check_notes.read_aux(aux)
    keep = re.findall(r'\\(?:rr@at|rr@markat|rr@placed|rr@boxat|rr@paperstart|newlabel)\{[^\n]*', t)
    return sorted(keep)


def mark_bibliography(work, corrected, marked, root, origb, corrb):
    stem = os.path.splitext(root)[0]
    ob, cb = os.path.join(origb, stem + '.bbl'), os.path.join(corrb, stem + '.bbl')
    mb = os.path.join(marked, stem + '.bbl')
    if not os.path.isfile(cb):
        return 'no .bbl (bibliography written in the sources, or none)'
    with open(cb, encoding='utf-8', errors='replace') as fh:
        ctext = fh.read()
    if '\\bibitem' not in ctext:
        shutil.copyfile(cb, mb)
        for ext in ('.bcf',):
            if os.path.isfile(os.path.join(corrb, stem + ext)):
                shutil.copyfile(os.path.join(corrb, stem + ext), os.path.join(marked, stem + ext))
        return 'WARNING: biblatex bibliography copied unmarked (mark_bbl.py reads thebibliography only)'
    if not os.path.isfile(ob) or filecmp.cmp(ob, cb, shallow=False):
        shutil.copyfile(cb, mb)
        return 'bibliography unchanged: .bbl copied'
    mp = os.path.join(work, 'tmp', 'bbl-map.json')
    if not os.path.isfile(mp):
        raise Fail('the bibliography changed but %s is missing: write it (format in mark_bbl.py)' % mp)
    cmd = [sys.executable, '-I', os.path.join(HERE, 'mark_bbl.py'), ob, cb, mb, mp]
    for dp, dns, fns in os.walk(corrected):
        dns.sort()
        for fn in sorted(fns):
            if fn.endswith('.bib'):
                rel = os.path.relpath(os.path.join(dp, fn), corrected)
                cmd += ['--bib', os.path.join(dp, fn), '--bib-name', 'corrected/' + rel]
    r = run(cmd)
    if r.returncode != 0:
        raise Fail('mark_bbl.py failed:\n' + r.stdout + r.stderr)
    return ('bibliography marked: ' + r.stdout.strip() + ('\n' + r.stderr.strip() if r.stderr.strip() else ''))


def add_front(marked, root):
    p = os.path.join(marked, root)
    with open(p, encoding='utf-8', errors='surrogateescape', newline='') as fh:
        t = fh.read()
    t2 = re.sub(r'^(\s*)\\usepackage\{r2changes\}', r'\1\\usepackage[front]{r2changes}', t, count=1, flags=re.M)
    if t2 == t:
        raise Fail('no \\usepackage{r2changes} in work/marked/%s' % root)
    m = re.search(r'^[^%\n]*\\begin\{document\}[^\n]*\n?', t2, re.M)
    t2 = t2[:m.end()] + ('' if t2[m.end() - 1:m.end()] == '\n' else '\n') + '\\input{rrfront}\n' + t2[m.end():]
    with open(p, 'w', encoding='utf-8', errors='surrogateescape', newline='') as fh:
        fh.write(t2)
    with open(os.path.join(marked, os.path.dirname(root), 'latexmkrc'), 'w') as fh:
        fh.write('$bibtex_use = 0;  # keep the marked .bbl\n')


# the colour of each kind in changes.pdf, in words (front_pages.KINDS gives the LaTeX colour of each kind)
COLOUR_WORDS = {'rrred': 'red', 'rrorange': 'orange', 'rrorange!60!white': 'orange placeholder [#n: ...]',
                'rrorange!60!black': 'orange tag', 'rrpurple': 'purple', 'rrblueframe': 'blue margin note only',
                'rrnotapplied': 'grey, nothing in the paper'}


def legend_lines():
    """The legend of edits.md, one line per kind, from the same table as the summary page of changes.pdf."""
    return ['- **%s**: %s in changes.pdf (%s)' % (front_pages.SHORT[k], COLOUR_WORDS[col], sub.replace(r'[\#n: \dots]',
                                                                                                    '[#n: ...]'))
            for k, _, sub, col in front_pages.KINDS]


def write_edits_md(out, log_path, report_path, build_id=None):
    rows = front_pages.read_log(log_path)
    report = front_pages.parse_report(report_path) if os.path.isfile(report_path) else {'items': set()}
    cls = front_pages.classify(rows, report.get('questions', {}))
    sev = report.get('severity', {})
    by = {}
    for r in rows:
        try:
            by.setdefault(int(r['item']), []).append(r)
        except ValueError:
            continue
    lines = ['# Edits in corrected/ (report items)', '']
    if build_id:
        lines += ['Build: `%s` (the same build as report.md, changes.pdf and corrected/ of this folder).' % build_id, '']
    lines += ['Each item: its status in corrected/, the `file:line` of the change in corrected/, then [kind in '
              'changes.pdf; severity]. Kinds and colours, as on the summary page of changes.pdf:', '']
    lines += legend_lines() + ['', '`% TODO #n` comments in corrected/ mark the facts only the authors have.', '']
    for it in sorted(set(by) | report['items']):
        rs = by.get(it, [])
        st = list(dict.fromkeys(r['status'] for r in rs if r['status'])) or ['not applied (no edit)']
        locs = list(dict.fromkeys('%s:%s' % (r['file'], r['line']) for r in rs if r['file'] and r['line']))
        kind = front_pages.SHORT[cls.get(it, ('notapplied',))[0]]
        lines.append('- **%d** %s%s [%s; %s]' % (it, ' + '.join(st), (' — ' + ', '.join(locs)) if locs else '',
                                                 kind, sev.get(it, 'minor')))
    with open(os.path.join(out, 'edits.md'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')


BUILD_FILE = '.reviewer2-build'   # in corrected/: the build id and the items applied there


def build_id_of(work, out, choices, date):
    """A short hash of what decides the four outputs: the edit spec, the author's choices, the sources and the
    report (without its derived lines: counts, build id)."""
    h = hashlib.sha256()
    for p in (os.path.join(work, 'edits.json'), choices, os.path.join(work, 'tmp', 'bbl-map.json'),
              os.path.join(work, 'venue-status.json')):
        if p and os.path.isfile(p):
            with open(p, 'rb') as fh:
                h.update(fh.read())
    paper = os.path.join(work, 'paper')
    for dp, dns, fns in os.walk(paper):
        dns.sort()
        for fn in sorted(fns):
            if fn.endswith(('.tex', '.bib', '.sty', '.cls', '.bst')):
                with open(os.path.join(dp, fn), 'rb') as fh:
                    h.update(os.path.relpath(os.path.join(dp, fn), paper).encode() + fh.read())
    with open(os.path.join(out, 'report.md'), encoding='utf-8') as fh:
        rep = fh.read()
    rep = report_sync.BUILD_LINE.sub('', rep)
    rep = re.sub(r'(?m)^\s*In the corrected copy\b.*$', '', rep)
    h.update(rep.encode('utf-8'))
    h.update(date.encode())
    return h.hexdigest()[:12]


def verify(out, work, root, build_id, choices_used, strict_cmd):
    """The four outputs agree (B1): the same build id in report.md, edits.md, corrected/ and changes.pdf; the same
    items and kinds in report.md, edits.md and the log; the counts of report.md and of the summary page; the boxes
    of changes.pdf = the pre-set or chosen items = what corrected/ holds (rebuilt independently with apply_edits.py
    --only and compared file by file); edits.md's legend is the one of changes.pdf; no stale or temporary file names
    in report.md and edits.md. Returns the list of problems (empty: consistent)."""
    bad = []
    rp, ep, pdf = os.path.join(out, 'report.md'), os.path.join(out, 'edits.md'), os.path.join(out, 'changes.pdf')
    corrected = os.path.join(out, 'corrected')
    with open(rp, encoding='utf-8') as fh:
        rtext = fh.read()
    with open(ep, encoding='utf-8') as fh:
        etext = fh.read()
    # 1. build id
    if '`%s`' % build_id not in rtext:
        bad.append('report.md does not carry build %s' % build_id)
    if '`%s`' % build_id not in etext:
        bad.append('edits.md does not carry build %s' % build_id)
    bf = os.path.join(corrected, BUILD_FILE)
    ctext = open(bf, encoding='utf-8').read() if os.path.isfile(bf) else ''
    if build_id not in ctext:
        bad.append('corrected/%s does not carry build %s' % (BUILD_FILE, build_id))
    r = run(['pdftotext', '-f', '1', '-l', '1', '-layout', pdf, '-'])
    p1 = ' '.join(r.stdout.split())
    if build_id not in p1:
        bad.append('page 1 of changes.pdf does not carry build %s' % build_id)
    # 2. items and kinds
    report = front_pages.parse_report(rp)
    rows = front_pages.read_log(os.path.join(work, 'edits.tsv'))
    cls = front_pages.classify(rows, report['questions'])
    emd = {int(m.group(1)): m.group(2) for m in re.finditer(r'^- \*\*(\d+)\*\* .*\[([^;\]]+);', etext, re.M)}
    if report['items'] - set(emd):
        bad.append('items of report.md missing in edits.md: %s' % sorted(report['items'] - set(emd)))
    for it, k in emd.items():
        want = front_pages.SHORT[cls.get(it, ('notapplied',))[0]]
        if k != want:
            bad.append('edits.md says #%d is %s, changes.pdf %s' % (it, k, want))
    # 3. counts: report.md section 1 and the summary page
    counts = front_pages.item_counts(report['items'], cls)
    states = front_pages.read_states(os.path.join(work, 'marked', os.path.dirname(root), 'r2states.tex'))
    sent = report_sync.sentence(counts, cls, report['items'], states)
    if sent not in rtext:
        bad.append('report.md section 1 does not say: %s' % sent)
    for k, n in counts.items():
        if '%d %s' % (n, front_pages.SHORT[k]) not in p1:
            bad.append('page 1 of changes.pdf does not show "%d %s"' % (n, front_pages.SHORT[k]))
    # 4. legend of edits.md = the kinds and colours of changes.pdf
    for ln in legend_lines():
        if ln not in etext:
            bad.append('edits.md legend line missing or different: %s' % ln)
    # 5. boxes of changes.pdf = the ticked set = corrected/
    try:
        fields = read_choices.read_fields(pdf)
    except (OSError, ValueError) as ex:
        fields = None
        bad.append('the boxes of changes.pdf cannot be read: %s' % ex)
    ticked = sorted(n for n, st in states.items() if st[0] and not st[1])
    if fields is not None:
        pdf_ticked = sorted(n for n, (t, ro) in fields.items() if t and not ro)
        if pdf_ticked != ticked:
            bad.append('boxes ticked in changes.pdf %s differ from the build %s' % (pdf_ticked, ticked))
        ro_pdf = sorted(n for n, (t, ro) in fields.items() if ro)
        ro_st = sorted(n for n, st in states.items() if st[1])
        if ro_pdf != ro_st:
            bad.append('disabled boxes in changes.pdf %s differ from the "your facts" items %s' % (ro_pdf, ro_st))
        if any(t for n, (t, ro) in fields.items() if ro):
            bad.append('a disabled ("your facts") box is ticked in changes.pdf')
    m = re.search(r'^applied: (.*)$', ctext, re.M)
    if m is None or sorted(int(x) for x in re.findall(r'\d+', m.group(1))) != ticked:
        bad.append('corrected/%s does not list the ticked items' % BUILD_FILE)
    chk = tempfile.mkdtemp(prefix='r2verify-')
    try:
        c2, m2 = os.path.join(chk, 'c'), os.path.join(chk, 'm')
        r = run([sys.executable, '-I', os.path.join(HERE, 'apply_edits.py'), os.path.join(work, 'edits.json'),
                 os.path.join(work, 'paper'), c2, m2, '--only', ','.join(map(str, ticked)) or '0'] + strict_cmd)
        if r.returncode != 0:
            bad.append('apply_edits.py --only (check of corrected/) failed: %s' % (r.stderr or r.stdout)[-300:])
        else:
            diff = tree_diff(corrected, c2, skip={BUILD_FILE})
            if diff:
                bad.append('corrected/ is not exactly the ticked items %s: %s differ' % (ticked, ', '.join(diff[:8])))
    finally:
        shutil.rmtree(chk, ignore_errors=True)
    # 6. names
    for name, t in (('report.md', rtext), ('edits.md', etext)):
        st = sorted(set(report_sync.STALE.findall(t)))
        if st:
            bad.append('%s names earlier builds: %s' % (name, ', '.join(st)))
        tp = sorted(set(report_sync.TEMP_PATH.findall(t)))
        if tp:
            bad.append('%s names temporary paths: %s' % (name, ', '.join(tp[:3])))
    return bad


def tree_diff(a, b, skip=()):
    """Relative paths whose content differs between two folders (files only in one count)."""
    def files(top):
        out = {}
        for dp, dns, fns in os.walk(top):
            for fn in fns:
                rel = os.path.relpath(os.path.join(dp, fn), top)
                if rel not in skip:
                    out[rel] = os.path.join(dp, fn)
        return out
    fa, fb = files(a), files(b)
    return sorted(k for k in set(fa) | set(fb)
                  if k not in fa or k not in fb or not filecmp.cmp(fa[k], fb[k], shallow=False))


def render(pdf, notes_json, nfront, dest):
    if not shutil.which('pdftoppm'):
        return []
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    per = {}
    for _, page, _ in notes_json.values():
        per[page] = per.get(page, 0) + 1
    crowded = [p for p, _ in sorted(per.items(), key=lambda x: (-x[1], x[0]))[:3]]
    want = sorted(set(range(1, nfront + 2)) | set(crowded))
    for p in want:
        run(['pdftoppm', '-r', '70', '-png', '-f', str(p), '-l', str(p), pdf, os.path.join(dest, 'p%03d' % p)])
    return sorted(os.listdir(dest))


def open_viewer(path):
    """Open a file with the system viewer; True if the command started."""
    if sys.platform == 'darwin':
        cmd = ['open', path]
    elif os.name == 'nt':
        cmd = ['cmd', '/c', 'start', '', path]
    else:
        cmd = ['xdg-open', path]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=30)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('out')
    ap.add_argument('--root', default=None)
    ap.add_argument('--engine', default='pdflatex', choices=('pdflatex', 'xelatex', 'lualatex'))
    ap.add_argument('--date', default=datetime.date.today().isoformat())
    ap.add_argument('--max-runs', type=int, default=12)
    ap.add_argument('--crowd-tol', type=float, default=18.0,
                    help='a box further than this (pt) from its line makes its page crowded (default 18, ~1.5 lines)')
    ap.add_argument('--no-png', action='store_true')
    ap.add_argument('--open', action='store_true', help='open changes.pdf in the system PDF viewer at the end')
    ap.add_argument('--final-dir', default=None,
                    help='where the user will find the output folder, when OUT is a temporary copy of it (the summary '
                         'page names it); a temporary OUT without it is an error')
    ap.add_argument('--strict', action='store_true',
                    help='applied text with terms, numbers or explanations not in the paper is an error (apply_edits.py)')
    ap.add_argument('--choices', default=None,
                    help="work/choices.json of read_choices.py: corrected/ and the boxes follow the author's choices")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    out = os.path.abspath(args.out)
    work = os.path.join(out, 'work')
    paper, marked, corrected = os.path.join(work, 'paper'), os.path.join(work, 'marked'), os.path.join(out, 'corrected')
    tmp = os.path.join(work, 'tmp')
    final = os.path.abspath(args.final_dir) if args.final_dir else out
    strict = ['--strict'] if args.strict else []
    try:
        if front_pages.is_temporary(final):
            raise Fail('the output folder %s is a temporary folder: the summary page would tell the user to look '
                       'there. Build in the output folder, or give --final-dir <where the files will be>' % final)
        need = [paper, os.path.join(work, 'edits.json'), os.path.join(out, 'report.md'),
                os.path.join(work, 'venue.md'), os.path.join(work, 'venue-status.json')]
        miss = [p for p in need if not os.path.exists(p)]
        if miss:
            raise Fail('missing input(s):\n  ' + '\n  '.join(miss))
        for tool in ('latexmk', args.engine, 'pdfinfo'):
            if not shutil.which(tool):
                raise Fail('%s not found (see SETUP.md)' % tool)
        os.makedirs(tmp, exist_ok=True)
        root = find_root(paper, args.root)
        stem = os.path.splitext(root)[0]
        log_path = os.path.join(work, 'edits.tsv')

        say('1/9 apply_edits.py')
        cmd = [sys.executable, '-I', os.path.join(HERE, 'apply_edits.py'), os.path.join(work, 'edits.json'), paper,
               corrected, marked, '--log', log_path, '--force'] + strict
        if args.choices:
            cmd += ['--choices', os.path.abspath(args.choices)]
        r = run(cmd)
        if r.returncode != 0:
            raise Fail('apply_edits.py found problems in work/edits.json (nothing written):\n' + r.stderr + r.stdout)
        say('    ' + r.stdout.strip().replace('\n', '\n    '))
        bid = build_id_of(work, out, os.path.abspath(args.choices) if args.choices else None, args.date)
        say('    build %s' % bid)
        r = run([sys.executable, '-I', os.path.join(HERE, 'report_sync.py'), out, '--build-id', bid])
        say('    ' + r.stdout.strip().replace('\n', '\n    '))
        st0 = front_pages.read_states(os.path.join(marked, os.path.dirname(root), 'r2states.tex'))
        with open(os.path.join(corrected, BUILD_FILE), 'w', encoding='utf-8') as fh:
            fh.write('reviewer2-repellent build %s (%s)\napplied: %s\n' % (
                bid, args.date, ' '.join(str(n) for n in sorted(st0) if st0[n][0] and not st0[n][1])))

        say('2/9 compile the original and corrected/ (latexmk, in work/tmp/)')
        origb, corrb = os.path.join(tmp, 'build-original'), os.path.join(tmp, 'build-corrected')
        fresh_copy(paper, origb, stem)
        fresh_copy(corrected, corrb, stem)
        opdf = latexmk(origb, root, args.engine)
        cpdf = latexmk(corrb, root, args.engine)
        olog, clog = log_text(origb, root), log_text(corrb, root)
        op, cp = pages_of(opdf), pages_of(cpdf)
        new_err = [e for e in errors_of(clog) if e not in errors_of(olog)]
        if new_err:
            raise Fail('corrected/ has LaTeX errors the original does not have (see %s):\n  %s' % (
                os.path.join(corrb, stem + '.log'), '\n  '.join(new_err[:10])))
        side = 'pages %s -> %s, overfull boxes %d -> %d' % (op, cp, overfull(olog), overfull(clog))
        say('    original vs corrected: ' + side + ('   <-- CHECK: the page count changed' if op != cp else ''))

        say('3/9 bibliography')
        say('    ' + mark_bibliography(work, corrected, marked, root, origb, corrb).replace('\n', '\n    '))

        say('4/9 front pages')
        r = run([sys.executable, '-I', os.path.join(HERE, 'check_stats.py'), out])
        if r.returncode != 0:
            raise Fail('check_stats.py failed:\n' + r.stdout + r.stderr)
        say('    ' + r.stdout.strip().replace('\n', '\n    '))
        r = run([sys.executable, '-I', os.path.join(HERE, 'bib_status.py'), out])
        if r.returncode != 0:
            say('    WARNING: bib_status.py failed, no bibliography page:\n' + r.stdout + r.stderr)
            bs = os.path.join(work, 'bib-status.json')
            if os.path.isfile(bs):
                os.remove(bs)
        else:
            say('    ' + r.stdout.strip().replace('\n', '\n    '))
        if not os.path.isfile(os.path.join(work, 'ai-traces.json')):
            say('    no work/ai-traces.json: no "Traces of AI use" page (run ai_traces.py first, SKILL.md step 6)')
        add_front(marked, root)
        rdir = os.path.join(marked, os.path.dirname(root))
        for f in os.listdir(rdir):
            if f.startswith(os.path.basename(stem) + '.') and f.endswith(('.aux', '.out', '.toc')):
                os.remove(os.path.join(rdir, f))
        mroot = os.path.join(marked, root)

        say('5/9 LaTeX on the marked copy until the note positions are stable')
        aux = os.path.join(marked, stem + '.aux')
        state = {'levels': dict(front_pages.DEFAULT_LEVELS), 'frozen': set(), 'split': set(), 'fills': []}

        def adapt(fills):
            """Fit every front page (pdf-layout.md): a page that overflows goes one level down (and stays there; the
            checks and venue tables split over two pages at level 0); a page under FILL_TARGET goes one level up while it can."""
            moved = False
            by = {}
            for f in fills:
                by.setdefault(f['key'], []).append(f['ratio'])
            for key, ratios in by.items():
                lv = state['levels'].get(key)
                if lv is None:
                    continue
                if max(ratios) > 1.0:
                    state['frozen'].add(key)
                    if lv > 0:
                        state['levels'][key], moved = lv - 1, True
                        say('    %s overflows (%.0f%%): level %d -> %d' % (key, 100 * max(ratios), lv, lv - 1))
                    elif key in ('checks', 'venue') and key not in state['split']:
                        state['split'].add(key)
                        state['frozen'].discard(key)   # two pages: the level may rise again to fill them
                        moved = True
                        say('    %s overflows at level 0: spread over two pages' % key)
                elif min(ratios) < front_pages.FILL_TARGET and key not in state['frozen'] and \
                        lv < front_pages.MAX_LEVELS.get(key, 0):
                    state['levels'][key], moved = lv + 1, True
                    say('    %s is %.0f%% full: level %d -> %d' % (key, 100 * min(ratios), lv, lv + 1))
            return moved

        def settle(min_runs):
            prev, runs = None, 0
            for runs in range(1, args.max_runs + 1):
                fp = argparse.Namespace(run_dir=out, root=mroot, out=None, date=args.date, title=None, authors=None,
                                        final_dir=final, build_id=bid,
                                        report=None, venue=None, status=None, log=None, ai=None, checks=None, bib=None,
                                        levels=dict(state['levels']), checks_split='checks' in state['split'],
                                        venue_split='venue' in state['split'])
                tex, msgs = front_pages.build(fp)
                if tex is None:
                    raise Fail('front_pages.py:\n  ' + '\n  '.join(msgs))
                with open(os.path.join(rdir, 'rrfront.tex'), 'w', encoding='utf-8') as fh:
                    fh.write(tex)
                run([args.engine, '-interaction=nonstopmode', os.path.basename(root)], cwd=rdir)
                if not os.path.isfile(aux):
                    raise Fail('no .aux after LaTeX: see %s' % os.path.join(marked, stem + '.log'))
                cur = aux_state(aux)
                state['fills'] = front_pages.fill_of(log_text(marked, root))
                if adapt(state['fills']):
                    prev = None
                    continue
                if runs >= min_runs and cur == prev:
                    break
                prev = cur
            else:
                say('    WARNING: still changing after %d runs (positions may be off by one run)' % args.max_runs)
            return runs, tex, msgs

        runs, tex, msgs = settle(3)
        say('    %d LaTeX runs' % runs)

        say('6/9 crowded pages (boxes more than %.0fpt off their line): short notes' % args.crowd_tol)
        short, done, first = set(), {}, None
        for rnd in (1, 2):
            text = check_notes.read_aux(aux)
            pages = check_notes.page_shifts(text)
            if first is None:
                first = pages
                say('    first build: ' + check_notes.summary(check_notes.check(text)).split('\n')[1])
            has = check_notes.with_short(text)
            todo = {}
            for pg, boxes in sorted(pages.items()):
                if max(abs(s) for _, _, s in boxes) > args.crowd_tol:
                    ks = [k for k, _, _ in boxes if k in has and k not in short]
                    if ks:
                        todo[pg] = ks
            if not todo:
                break
            for pg, ks in todo.items():
                short.update(ks)
                done.setdefault(pg, []).extend(ks)
            with open(os.path.join(marked, stem + '.rrs'), 'w', encoding='utf-8') as fh:
                fh.write(''.join('\\rrshortnote{%d}\n' % k for k in sorted(short)))
            runs2, tex, msgs = settle(2)
            say('    round %d: %d notes on %d pages switched to their short text (%d LaTeX runs)'
                % (rnd, sum(len(v) for v in todo.values()), len(todo), runs2))
        last = check_notes.page_shifts(check_notes.read_aux(aux))
        has = check_notes.with_short(check_notes.read_aux(aux))
        worst = lambda bs: max(abs(s) for _, _, s in bs) if bs else 0.0
        for pg in sorted(set(first) | set(last)):
            b0, b1 = first.get(pg, []), last.get(pg, [])
            if worst(b0) <= args.crowd_tol and pg not in done:
                continue
            items = {k: it for k, it, _ in b0 + b1}
            sh = ', '.join('#%s' % items[k] for k in done.get(pg, []))
            nos = ', '.join('#%s' % it for k, it, _ in b1 if k not in has)
            say('    PDF page %d: %s; max offset %.1fpt -> %.1fpt%s' % (
                pg, ('shortened ' + sh) if sh else 'nothing to shorten', worst(b0), worst(b1),
                ('; no note_short: ' + nos) if nos else ''))
        if not done:
            say('    none' if not any(worst(b) > args.crowd_tol for b in first.values()) else
                '    crowded pages have no note_short to switch to')
        mlog = log_text(marked, root)
        new_err = [e for e in errors_of(mlog) if e not in errors_of(clog)]
        if new_err:
            raise Fail('the marked copy has LaTeX errors (see %s):\n  %s' % (
                os.path.join(marked, stem + '.log'), '\n  '.join(new_err[:10])))
        mpdf = os.path.join(marked, stem + '.pdf')
        mp = pages_of(mpdf)
        say('    %s pages' % mp)
        for m in msgs:
            say('    warning: ' + m)
        fills = state['fills']
        if fills:
            say('    front pages filled: ' + ', '.join('%s (p. %s) %.0f%%' % (f['id'], f['page'], 100 * f['ratio'])
                                                       for f in fills))
            say('    levels: ' + ', '.join('%s %d' % kv for kv in sorted(state['levels'].items())))
        for m in front_pages.fill_warnings(fills):
            say('    WARNING: ' + m)
        if 'Front page too tall' in mlog and not any(f['ratio'] > 1 for f in fills):
            say('    WARNING: a front page overflows (see the log): shorten the venue notes or questions')
        undef = sorted(set(re.findall(r"Reference `(rr-[^']*)' on page \d+ undefined", mlog)))
        if undef:
            say('    WARNING: undefined item anchors: ' + ', '.join(undef))

        say('7/9 note placement and links')
        res = check_notes.check(check_notes.read_aux(aux))
        say('    ' + check_notes.summary(res).replace('\n', '\n    '))
        if res['off_page']:
            raise Fail('margin boxes are not on the page of their note (see above)')
        nfront = len(re.findall(r'\\begin\{rrfullpage\}', tex))
        try:
            lres = pdf_links.check(mpdf, nfront)
            ltext, lbad = pdf_links.summary(lres)
            say('    ' + ltext.replace('\n', '\n    '))
            if lbad:
                say('    WARNING: links to fix (see above)')
        except (ValueError, OSError) as ex:
            say('    WARNING: links not checked (%s)' % ex)

        say('8/9 changes.pdf, edits.md')
        shutil.copyfile(mpdf, os.path.join(out, 'changes.pdf'))
        write_edits_md(out, log_path, os.path.join(out, 'report.md'), bid)
        if not args.no_png:
            notes = check_notes.records(check_notes.read_aux(aux))[0]
            pngs = render(mpdf, notes, nfront, os.path.join(tmp, 'pages'))
            if pngs:
                say('    pages to look at: %s/{%s}' % (os.path.join(tmp, 'pages'), ','.join(pngs)))
        say('9/9 consistency of report.md, changes.pdf, edits.md and corrected/')
        bad = verify(out, work, root, bid, args.choices, strict)
        if bad:
            raise Fail('the outputs disagree (build %s):\n  %s' % (bid, '\n  '.join(bad)))
        say('    OK: build %s in all four; same items, kinds and counts; corrected/ = the %d ticked items' % (
            bid, sum(1 for v in front_pages.read_states(os.path.join(marked, os.path.dirname(root),
                                                                         'r2states.tex')).values() if v[0] and not v[1])))
        say('DONE: %s (%s pages: %d front + paper), %s, %s' % (
            os.path.join(out, 'changes.pdf'), mp, nfront, os.path.join(out, 'edits.md'), corrected))
        say('original vs corrected: ' + side)
        if args.open:
            pdf = os.path.join(out, 'changes.pdf')
            say(('opened: %s' if open_viewer(pdf) else 'could not open a viewer; the file is at %s') % pdf)
        return 0
    except Fail as ex:
        print('FAILED: %s' % ex, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
