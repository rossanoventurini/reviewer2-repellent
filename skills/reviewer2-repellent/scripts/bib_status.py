#!/usr/bin/env python3
"""Status of every cited bibliography entry, from the files of a run: the data of the front page "Bibliography"
of changes.pdf (front_pages.py). Nothing is judged here and nothing is guessed: a count or a field that no file
gives is left out, and the missing inputs are listed in "notes".

Usage: python3 bib_status.py OUT_DIR [--out PATH]          (default OUT_DIR/work/bib-status.json)

Inputs (all optional):
  refs_check   work/refs_check.out (full lines), else its section of work/facts.txt (lines may be cut there):
               "bib differs from the database record" and "not found in the reference databases" lines (per key),
               the other FAIL/CHECK lines of a key (arXiv, DOI, published version), the RefChecker INFO line, the
               SKIPPED lines and the COVERAGE line (references, refchecker_checked, arxiv_ids, arxiv_looked_up, dois,
               dois_looked_up, preprints, preprints_dblp_db)
  bib_style    work/bib_style.out, else its section of work/facts.txt: each "style differs" line is attributed to
               the keys it names in full (a key cut by the end of a shortened line is dropped)
  cited keys   \\citation lines of work/build/<root>.aux (root of work/paper), else every entry of the .bib
  .bib         the .bib files of work/paper (the original): type, title, year, DOI, arXiv IDs, preprint
               (refs_check.parse_bib, dois_of, arxiv_ids, is_preprint)
  bbl-map      work/tmp/bbl-map.json (mark_bbl.py): the report items that change each entry in the copy
  .bbl         work/tmp/build-original/<root>.bbl and work/tmp/build-corrected/<root>.bbl: whether the printed
               entry changed in the copy
  report.md    items that name a key in backticks (`key`) are linked to that entry

work/bib-status.json:
  {"version": 1, "inputs": {"refs_check": "work/refs_check.out", ...}, "notes": ["..."],
   "counts": {"cited": 119, "bib_entries": 187, "refchecker_checked": 119, "refchecker_errors": 10,
              "refchecker_warnings": 17, "refchecker_unverified": 1, "differs": 19, "not_found": 1,
              "dois": 57, "dois_looked_up": 57, "arxiv_ids": 13, "arxiv_looked_up": 0, "preprints": 14,
              "preprints_checked": 14, "style_entries": 119, "style_features": 81, "style_differences": 37,
              "style_flagged_entries": 80, "changed_in_copy": 60, "with_items": 70},     only counts a file gives
   "skipped": ["arXiv ID check: arXiv API unreachable for 13 IDs (HTTPError)"],
   "entries": [{"key": "ivf_gpu", "type": "article", "title": "...", "year": "2019",
                "db": "matched" | "differs" | "not_found" | "not_checked",
                "db_detail": "year: cited 2019, database 2021",          (differs / not_found; "" otherwise)
                "findings": [{"sev": "CHECK", "kind": "...", "detail": "..."}],   other refs_check lines of the key
                "doi": "10.1109/..." | null, "doi_checked": true | false | null,
                "arxiv": ["1810.07355"], "arxiv_checked": true | false | null,
                "preprint": false, "preprint_checked": true | false | null,
                "style": ["@article: field 'doi': absent; majority present (22/35)"],
                "changed": true | false | null,                           (null: no .bbl pair)
                "items": [31, 97]}]}                                       sorted by key, case-insensitive
"db_artefact": true when RefChecker's only difference is a parsing artefact (parse_artefact: braces, an escaped _, a
title cut at its colon): db is then "matched" (db_detail keeps the line) and counts.parse_artefacts counts them.
"matched": RefChecker checked every cited entry (refchecker_checked = cited) and no line names the key.
"not_checked": RefChecker did not run, or checked only some entries and the key is not named.
*_checked: from COVERAGE (all looked up: true; none: false; some: true unless the ID is listed in a SKIPPED line).
Python stdlib only.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from check_stats import coverage_of, facts_sections, read, report_items  # noqa: E402
from ai_traces import find_root  # noqa: E402
import refs_check  # noqa: E402

DIFFERS = re.compile(r"bib differs from the database record", re.I)
NOT_FOUND = re.compile(r"not found in the reference databases", re.I)
CUT = "\u2026"
BIB_ITEM = re.compile(r"\.bib\b|\bbib\b|bibliograph|referenc|\bentr(?:y|ies)\b|DBLP|\bDOI\b|citation|preprint", re.I)


def script_text(work, name, sections, inputs, notes):
    """The output of a script: work/<name>.out (full lines) if present, else its section of facts.txt."""
    out = read(os.path.join(work, name + ".out"))
    if out is not None:
        inputs[name] = "work/%s.out" % name
        return out
    if name in sections:
        inputs[name] = "work/facts.txt (## %s)" % name
        return sections[name]
    notes.append("no %s output (work/%s.out or its section of work/facts.txt)" % (name, name))
    return None


def lines_of(text):
    """[(sev, parts, cut)] of the FAIL/CHECK/INFO/SKIPPED/COVERAGE lines; cut: the line ends with an ellipsis."""
    out = []
    for ln in (text or "").split("\n"):
        ln = ln.rstrip()
        if not re.match(r"^(FAIL|CHECK|INFO|SKIPPED|COVERAGE) \| ", ln):
            continue
        cut = ln.endswith(CUT) or ln.endswith("...")
        out.append((ln.split(" | ")[0], ln.split(" | "), cut))
    return out


def unquote(s):
    s = s.strip()
    return s[1:-1] if len(s) >= 2 and s[0] == '"' and s[-1] == '"' else s.strip('"')


PART_MAX = 140   # refs_check.py keeps at most 140 characters of each RefChecker detail (and 400 of the line)
CUT_NOTE = " (cut short in the refs_check output)"


def trim_cut(rest, limit=PART_MAX):
    """A detail of refs_check at its length limit was cut: keep it up to the last complete item or word."""
    if len(rest) < limit - 2:
        return rest, False
    for sep in ("; ", ", ", " "):
        i = rest.rfind(sep)
        if i > len(rest) // 2:
            return rest[:i].rstrip(" ,;:"), True
    return rest, True


def short_detail(det):
    """'year: Year mismatch: cited: 2019 actual: 2021' -> 'year: cited 2019; database 2021' (each part); a part cut
    by refs_check ends at its last complete item, with a note."""
    parts = []
    for p in [x.strip() for x in re.split(r"\s+\|\s+", det) if x.strip()]:
        m = re.match(r"^([\w ]+?):\s*(.*)$", p)
        field, rest = (m.group(1), m.group(2)) if m else ("", p)
        rest, cut = trim_cut(rest)
        if cut:
            rest = re.sub(r"\s+actual:?$", "", rest)
        note = CUT_NOTE if cut else ""
        c = re.search(r"cited:\s*(.*?)\s+actual:\s*(.*)$", rest)
        if c:
            pre = rest[:rest.find("cited:")]
            pre = re.sub(r"^[\w ]*mismatch:?\s*", "", pre, flags=re.I).strip(" :")
            pre = re.sub(r"\bcorrect\b", "in the database", pre)
            txt = "%scited %s; database %s" % ((pre + ": ") if pre else "", c.group(1).strip(), c.group(2).strip())
        elif "cited:" in rest:
            txt = re.sub(r"^[\w ]*mismatch:?\s*", "", rest, flags=re.I).replace("cited:", "cited").strip()
            note = CUT_NOTE if cut else " (no database value in the refs_check output)"
        else:
            txt = rest
        parts.append(("%s: %s" % (field, txt) if field else txt) + note)
    return " | ".join(parts)


def _norm(x):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\\[a-zA-Z]+|[{}\\]", "", (x or "").lower()))


def parse_artefact(detail):
    """True when every part of a "differs" detail is a parsing artefact, not a real difference: the cited and the
    database value are equal once braces, backslashes, case and punctuation are dropped (C}ol{BERT} vs ColBERT,
    10.1007/x\\_28 vs 10.1007/x_28), or the database title is the cited title cut at its colon ({PLAID}: An
    Efficient ... vs PLAID)."""
    parts = [p for p in (detail or "").split(" | ") if p.strip()]
    if not parts:
        return False
    for p in parts:
        m = re.match(r"^\s*(\w[\w ]*?):\s*cited (.*?); database (.*?)(?: \(cut short in the refs_check output\))?$", p)
        if not m:
            return False
        field, cited, db = m.group(1).lower(), m.group(2), m.group(3)
        if _norm(cited) and _norm(cited) == _norm(db):
            continue
        if field == "title" and ":" in cited and _norm(cited.split(":")[0]) == _norm(db):
            continue
        return False
    return True


def drop_cut_word(s, cut):
    """When the line was shortened, the last word may be cut: drop it."""
    s = s.rstrip(CUT).rstrip(".").rstrip()
    return s.rsplit(" ", 1)[0] if cut and " " in s else s


def ids_in(text):
    return set(re.findall(r"\b(\d{4}\.\d{4,5}|[a-z\-]+/\d{7}|10\.\d{4,9}/\S+?)(?=[,;\s)]|$)", text or ""))


def bib_files(paper):
    out = []
    for dp, dns, fns in os.walk(paper):
        dns.sort()
        for fn in sorted(fns):
            if fn.endswith(".bib"):
                out.append(os.path.join(dp, fn))
    return out


def cited_keys(work, paper, inputs, notes):
    try:
        root = find_root(paper, None)
    except (SystemExit, OSError):
        root = None
    if root:
        stem = os.path.splitext(root)[0]
        for rel in ("build", os.path.join("tmp", "build-original")):
            aux = os.path.join(work, rel, stem + ".aux")
            t = read(aux)
            if t is not None:
                keys = []
                for m in re.finditer(r"\\citation\{([^}]*)\}|\\abx@aux@cite\{\d*\}\{([^}]+)\}", t):
                    for k in (m.group(1) or m.group(2)).split(","):
                        if k.strip():
                            keys.append(k.strip())
                inputs["cited"] = "work/%s/%s.aux" % (rel, stem)
                return list(dict.fromkeys(keys)), stem
    notes.append("no .aux of the original build: every .bib entry is treated as cited")
    return None, (os.path.splitext(root)[0] if root else None)


def bbl_entries(path):
    if not os.path.isfile(path):
        return None
    import mark_bbl
    try:
        _, entries, _ = mark_bbl.parse(path)
    except SystemExit:
        return None
    return {k: " ".join(body.split()) for k, _, body in entries}


def style_findings(text, keys_known):
    """{key: [label]}, number of style lines."""
    per, n = {}, 0
    for sev, parts, cut in lines_of(text):
        if sev != "CHECK" or len(parts) < 3 or "style differs" not in parts[1]:
            continue
        n += 1
        feature = parts[2].strip()
        majority = parts[3].strip() if len(parts) > 3 else ""
        groups = parts[4:] if len(parts) > 4 else []
        for gi, g in enumerate(groups):
            for seg in g.split("; "):
                m = re.match(r"^\s*([^:\"]+):\s*(.+)$", seg)
                if not m:
                    continue
                label = m.group(1).strip()
                toks = [t.strip() for t in m.group(2).split(",")]
                last_seg = gi == len(groups) - 1 and seg is g.split("; ")[-1]
                if cut and last_seg and toks:
                    toks = toks[:-1]      # the last key of a shortened line may be cut
                for t in toks:
                    t = t.rstrip(CUT).strip()
                    if t in keys_known:
                        txt = "%s: %s%s" % (feature, label, ("; " + majority) if majority else "")
                        per.setdefault(t, [])
                        if txt not in per[t]:
                            per[t].append(txt)
    return per, n


def map_items(mp, key, changed):
    its = []
    if not mp:
        return its
    if key in (mp.get("default") or {}):
        its.append(mp["default"][key])
    for _, it in (mp.get("rules") or {}).get(key, []):
        its.append(it)
    its += list((mp.get("items") or {}).get(key, []))
    if key in (mp.get("new") or {}):
        its.append(mp["new"][key])
    rem = (mp.get("removed") or {}).get(key)
    if isinstance(rem, dict) and rem.get("item") is not None:
        its.append(rem["item"])
    if changed and mp.get("case_item") is not None and key in (mp.get("case_keys") or []):
        its.append(mp["case_item"])
    if changed and not its and mp.get("default_item") is not None:
        its.append(mp["default_item"])
    return [int(i) for i in its if isinstance(i, int) or (isinstance(i, str) and i.isdigit())]


def build(out_dir):
    out_dir = os.path.abspath(out_dir)
    work = os.path.join(out_dir, "work")
    paper = os.path.join(work, "paper")
    inputs, notes, counts = {}, [], {}
    sections = facts_sections(os.path.join(work, "facts.txt"))

    # .bib entries (original sources)
    bib = {}
    files = bib_files(paper) if os.path.isdir(paper) else []
    for f in files:
        for key, typ, fields in refs_check.parse_bib(read(f) or ""):
            bib.setdefault(key, (typ, fields))
    if files:
        inputs["bib"] = ", ".join("work/paper/" + os.path.relpath(f, paper) for f in files)
        counts["bib_entries"] = len(bib)
    else:
        notes.append("no .bib file in work/paper")
    lower = {k.lower(): k for k in bib}
    cited, stem = cited_keys(work, paper, inputs, notes) if os.path.isdir(paper) else (None, None)
    if cited is None or "*" in (cited or []):
        cited = list(bib)
    else:
        missing = [k for k in cited if k not in bib and k.lower() not in lower]
        if missing and bib:
            notes.append("cited keys not in the .bib: %s" % ", ".join(missing))
        cited = [k if k in bib else lower.get(k.lower(), k) for k in cited]
    counts["cited"] = len(cited)

    # refs_check
    rtext = script_text(work, "refs_check", sections, inputs, notes)
    rc = coverage_of(rtext) or {}
    if rtext is not None and not rc:
        notes.append("refs_check output without a COVERAGE line: lookups per identifier are not known")
    for k in ("refchecker_checked", "dois", "dois_looked_up", "arxiv_ids", "arxiv_looked_up", "preprints"):
        if k in rc:
            counts[k] = rc[k]
    if "preprints_dblp_db" in rc:
        counts["preprints_checked"] = rc["preprints_dblp_db"]
    per_key, skipped, unchecked_ids, rc_ran = {}, [], set(), False
    for sev, parts, cut in lines_of(rtext):
        if sev == "SKIPPED":
            txt = " | ".join(parts[1:])
            m = re.match(r"^(.*?):\s*(?:[\w./\-]+,\s*)*[\w./\-]+\s*(?:,?\s*(?:\.\.\.|\u2026))?\s*$", txt)
            skipped.append(m.group(1) if m and ids_in(txt) else txt)
            unchecked_ids |= ids_in(txt)
            if re.search(r"refchecker", txt, re.I):
                rc_ran = False
            continue
        if sev == "COVERAGE" or len(parts) < 2:
            continue
        kind = parts[1].strip()
        if kind == "RefChecker":
            rc_ran = True
            m = re.search(r"(\d+) references?, (\d+) errors?, (\d+) warnings?, (\d+) unverified", " ".join(parts))
            if m:
                counts.update(refchecker_errors=int(m.group(2)), refchecker_warnings=int(m.group(3)),
                              refchecker_unverified=int(m.group(4)))
            continue
        if sev not in ("FAIL", "CHECK", "INFO") or len(parts) < 4:
            continue
        keys = [k.strip() for k in parts[2].split(" / ")]
        keys = [k if k in bib else lower.get(k.lower(), k) for k in keys]
        if not any(k in bib for k in keys):
            continue
        det = unquote(parts[3])
        if cut and len(parts) == 4:
            det = drop_cut_word(det, True)
        for k in keys:
            d = per_key.setdefault(k, {"db": None, "detail": "", "findings": [], "published": False})
            if DIFFERS.search(kind):
                d["db"], d["detail"] = "differs", short_detail(det)
            elif NOT_FOUND.search(kind):
                d["db"] = "not_found"
                d["detail"] = re.sub(r"^unverified:\s*", "", short_detail(det))
            else:
                d["findings"].append(dict(sev=sev, kind=kind, detail=det))
    if "refchecker_checked" in rc:
        rc_ran = rc_ran or rc["refchecker_checked"] > 0
    all_rc = rc_ran and rc.get("refchecker_checked", counts.get("cited")) >= counts["cited"]
    if rtext is not None and not rc_ran:
        notes.append("RefChecker did not run: no entry is marked matched")
    elif rc_ran and not all_rc:
        notes.append("RefChecker checked %s of %d cited entries: the others are not_checked unless a line names "
                     "them" % (rc.get("refchecker_checked"), counts["cited"]))

    def checked(total_key, done_key, ids):
        if total_key not in rc or done_key not in rc or not ids:
            return None
        if rc[done_key] >= rc[total_key]:
            return True
        if rc[done_key] == 0:
            return False
        return not any(i in unchecked_ids for i in ids)

    # bib_style
    stext = script_text(work, "bib_style", sections, inputs, notes)
    bs = coverage_of(stext) or {}
    for src, dst in (("entries_compared", "style_entries"), ("features", "style_features"),
                     ("differences", "style_differences")):
        if src in bs:
            counts[dst] = bs[src]
    style, _ = style_findings(stext, set(bib)) if stext is not None else ({}, 0)

    # the copy: bbl-map and the printed entries
    mp = None
    mp_text = read(os.path.join(work, "tmp", "bbl-map.json"))
    if mp_text is not None:
        try:
            mp = json.loads(mp_text)
            inputs["bbl_map"] = "work/tmp/bbl-map.json"
        except ValueError as ex:
            notes.append("work/tmp/bbl-map.json: %s" % ex)
    else:
        notes.append("no work/tmp/bbl-map.json: the items of the bibliography changes are not known")
    ob = cb = None
    if stem:
        ob = bbl_entries(os.path.join(work, "tmp", "build-original", stem + ".bbl"))
        cb = bbl_entries(os.path.join(work, "tmp", "build-corrected", stem + ".bbl"))
    if ob is not None and cb is not None:
        inputs["bbl"] = "work/tmp/build-original/%s.bbl, work/tmp/build-corrected/%s.bbl" % (stem, stem)
    else:
        notes.append("no original and corrected .bbl in work/tmp: whether an entry changed is not known")
        ob = cb = None

    # report.md: items naming a key in backticks
    rep_items = {}
    rp = os.path.join(out_dir, "report.md")
    if os.path.isfile(rp):
        inputs["report"] = "report.md"
        for n, _, text in report_items(rp)[0]:
            if not BIB_ITEM.search(text):
                continue      # a key named in an item about something else (a system, a dataset)
            for k in re.findall(r"`([^`\s]+)`", text):
                k = k if k in bib else lower.get(k.lower())
                if k:
                    rep_items.setdefault(k, set()).add(n)
    else:
        notes.append("no report.md")

    entries = []
    for key in cited:
        typ, f = bib.get(key, ("", {}))
        r = per_key.get(key, {})
        db = r.get("db") or ("matched" if all_rc else "not_checked")
        artefact = db == "differs" and parse_artefact(r.get("detail", ""))
        if artefact:
            db = "matched"
        dois = refs_check.dois_of(f) if f else []
        ax = refs_check.arxiv_ids(f) if f else []
        pre = refs_check.is_preprint(typ, f) if f else False
        changed = None
        if ob is not None:
            changed = ob.get(key) != cb.get(key)
        its = sorted(set(map_items(mp, key, changed)) | rep_items.get(key, set()))
        entries.append(dict(
            key=key, type=typ, title=" ".join(refs_check.detex(f.get("title", "")).split()) if f else "",
            year=f.get("year", "") if f else "", db=db, db_detail=r.get("detail", ""), findings=r.get("findings", []),
            doi=dois[0] if dois else None, doi_checked=checked("dois", "dois_looked_up", dois),
            arxiv=ax, arxiv_checked=checked("arxiv_ids", "arxiv_looked_up", ax),
            preprint=bool(pre), preprint_checked=(checked("preprints", "preprints_dblp_db", [key]) if pre else None),
            style=style.get(key, []), changed=changed, items=its, db_artefact=artefact))
    entries.sort(key=lambda e: e["key"].lower())
    if rtext is not None:
        counts["differs"] = sum(1 for e in entries if e["db"] == "differs")
        counts["not_found"] = sum(1 for e in entries if e["db"] == "not_found")
        counts["parse_artefacts"] = sum(1 for e in entries if e["db_artefact"])
    if stext is not None:
        counts["style_flagged_entries"] = sum(1 for e in entries if e["style"])
    if ob is not None:
        counts["changed_in_copy"] = sum(1 for e in entries if e["changed"])
    counts["with_items"] = sum(1 for e in entries if e["items"])
    return dict(version=1, inputs=inputs, notes=notes, counts=counts, skipped=skipped, entries=entries)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out_dir")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    res = build(a.out_dir)
    out = a.out or os.path.join(os.path.abspath(a.out_dir), "work", "bib-status.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, ensure_ascii=False)
    c = res["counts"]
    print("bib-status.json written: %s (%s)" % (out, ", ".join("%s %s" % kv for kv in c.items())))
    for n in res["notes"]:
        print("note: " + n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
