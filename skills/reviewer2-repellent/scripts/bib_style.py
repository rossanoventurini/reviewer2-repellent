#!/usr/bin/env python3
"""Uniformity of the bibliography style: for every feature (fields present, journal and proceedings names
abbreviated or full, author first names or initials, page ranges, arXiv citation form, months, DOI/URL...), the
majority form among the cited entries and the entries that differ from it.

It makes no judgement: it lists the minority entries per feature, for an agent to decide which differences are real
inconsistencies (a style that is uniform except for two entries) and which are legitimate (a book has a publisher,
an article does not).

Usage: bib_style.py <root>.tex|refs.bib [--min-share 0.6] [--json]
"""
import argparse
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from refs_check import parse_bib, split_and  # noqa: E402

ABBREV = re.compile(r"\b(?:[A-Z][a-z]{0,6}\.)(?:\s|$)")  # Trans. J. Proc. Conf. Int. Comput.
VENUE_FIELDS = {"article": "journal", "inproceedings": "booktitle", "incollection": "booktitle"}
PUBLISHER_ACRONYMS = {"ACM", "IEEE", "SIAM", "USENIX", "AAAI", "IFIP", "LNCS", "CEUR", "PMLR", "VLDB", "ACL"}
CHECK_FIELDS = ("editor", "publisher", "address", "pages", "doi", "url", "month", "volume", "number", "series",
                "isbn", "issn", "note", "urldate", "location", "organization")


def bib_files_and_cited(src):
    if src.suffix == ".bib":
        return [src], None
    code = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in [src] + sorted(src.parent.rglob("*.tex")))
    code = re.sub(r"(?<!\\)%.*", "", code)
    bibs = []
    for m in re.finditer(r"\\bibliography\s*\{([^}]+)\}|\\addbibresource\s*(?:\[[^\]]*\])?\{([^}]+)\}", code):
        for b in (m.group(1) or m.group(2)).split(","):
            p = src.parent / (b.strip() if b.strip().endswith(".bib") else b.strip() + ".bib")
            if p.is_file() and p not in bibs:
                bibs.append(p)
    cited = None
    aux = src.with_suffix(".aux")
    if aux.is_file():
        cited = set()
        for m in re.finditer(r"\\citation\{([^}]+)\}|\\abx@aux@cite\{\d*\}\{([^}]+)\}", aux.read_text(errors="replace")):
            cited.update(k.strip() for k in (m.group(1) or m.group(2)).split(","))
    return bibs, cited


def name_form(name):
    name = name.strip()
    if "," in name:
        first = name.split(",", 1)[1].strip()
    else:
        parts = name.split()
        first = " ".join(parts[:-1])
    if not first:
        return None
    toks = re.findall(r"[^\s~-]+", first)
    if all(re.fullmatch(r"[A-Z]\.?|\{?\\?[A-Za-z]\}?\.", t) for t in toks):
        return "initials"
    return "full first names"


def venue_form(v):
    v = re.sub(r"[{}]", "", v)
    feats = {}
    feats["abbreviated"] = "abbreviated" if ABBREV.search(v + " ") else "full words"
    if re.search(r"(?i)\bproc(?:eedings|\.)", v):
        feats["proceedings"] = "starts 'Proceedings/Proc.'" if re.match(r"(?i)\s*(the\s+)?proc", v) else "contains 'Proceedings'"
    else:
        feats["proceedings"] = "no 'Proceedings'"
    feats["acronym"] = "with acronym in parentheses" if re.search(r"\([A-Z][A-Za-z\-']{1,12}\s*('?\d{2,4})?\)", v) \
        else "no acronym"
    feats["year in name"] = "year in venue name" if re.search(r"\b(19|20)\d\d\b|'\d\d\b", v) else "no year"
    return feats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--min-share", type=float, default=0.6,
                    help="report a feature when its majority form covers at least this share (default 0.6)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    src = pathlib.Path(a.input).resolve()
    bibs, cited = bib_files_and_cited(src)
    if not bibs:
        print("SKIPPED | no .bib file found")
        return
    entries = {}
    for b in bibs:
        for key, typ, f in parse_bib(b.read_text(encoding="utf-8", errors="replace")):
            if cited is None or key in cited or "*" in cited:
                entries.setdefault(key, (typ, f))

    obs = defaultdict(lambda: defaultdict(list))  # feature -> form -> keys

    by_type = defaultdict(list)
    for k, (typ, f) in entries.items():
        by_type[typ].append(k)
    for typ, keys in by_type.items():
        if len(keys) < 4:
            continue
        for fld in CHECK_FIELDS:
            for k in keys:
                obs[f"@{typ}: field '{fld}'"]["present" if entries[k][1].get(fld) else "absent"].append(k)

    for k, (typ, f) in entries.items():
        vf = VENUE_FIELDS.get(typ)
        if vf and f.get(vf) and not re.search(r"(?i)arxiv|corr\b|preprint", f[vf]):
            for feat, form in venue_form(f[vf]).items():
                obs[f"{vf} ({typ}): {feat}"][form].append(k)
        for role in ("author", "editor"):
            if f.get(role) and not re.search(r"\band others\b", f[role]):
                forms = {name_form(n) for n in split_and(f[role])} - {None}
                if forms:
                    obs[f"{role} first names"]["mixed within entry" if len(forms) > 1 else forms.pop()].append(k)
            if f.get(role):
                obs[f"{role} list truncated"]["'and others'" if re.search(r"\band others\b", f[role]) else "full list"].append(k)
        if f.get("pages"):
            p = f["pages"]
            form = "en dash '--'" if "--" in p else ("single hyphen '-'" if re.search(r"\d\s*-\s*\d", p) else
                                                     ("en dash char" if "–" in p else "single page/article no."))
            obs["page range"][form].append(k)
        if f.get("month"):
            m = f["month"]
            obs["month"]["number" if re.fullmatch(r"\s*\d{1,2}\s*", m) else
                          ("abbreviated" if re.fullmatch(r"(?i)\s*[a-z]{3}\.?\s*", m) else "full name")].append(k)
        txt = " ".join(f.get(x, "") for x in ("journal", "booktitle", "eprint", "archiveprefix", "note", "howpublished",
                                             "publisher", "url"))
        if re.search(r"(?i)arxiv|\bcorr\b", txt) or f.get("eprint"):
            if f.get("eprint"):
                form = "eprint field"
            elif re.search(r"(?i)\bcorr\b", txt):
                form = "CoRR journal + volume abs/..."
            elif re.search(r"(?i)arxiv preprint arxiv:", txt):
                form = "'arXiv preprint arXiv:NNNN' in journal"
            else:
                form = "other arXiv form"
            obs["arXiv citation form"][form].append(k)
            obs[f"arXiv entries: entry type"][f"@{typ}"].append(k)
        if f.get("doi") and f.get("url"):
            obs["DOI and URL"]["both"].append(k)
        elif f.get("doi"):
            obs["DOI and URL"]["DOI only"].append(k)
        elif f.get("url"):
            obs["DOI and URL"]["URL only"].append(k)
        else:
            obs["DOI and URL"]["neither"].append(k)

    # the same venue written in different ways (by acronym in parentheses or by normalised name)
    venue_names = defaultdict(set)
    for k, (typ, f) in entries.items():
        vf = VENUE_FIELDS.get(typ)
        if vf and f.get(vf):
            v = re.sub(r"[{}]", "", f[vf])
            acr = re.search(r"\(([A-Z][A-Za-z\-]{1,12})\s*('?\d{2,4})?\)", v) or re.search(r"\b([A-Z]{3,}[a-z]?)\b", v)
            if acr and acr.group(1) not in PUBLISHER_ACRONYMS:
                venue_names[acr.group(1)].add(re.sub(r"\b(19|20)\d\d\b|'\d\d|\d+(st|nd|rd|th)\b", "", v).strip(" ,"))

    rows = []
    for feat, forms in sorted(obs.items()):
        total = sum(len(v) for v in forms.values())
        if total < 4 or len(forms) < 2:
            continue
        major, mkeys = max(forms.items(), key=lambda kv: len(kv[1]))
        share = len(mkeys) / total
        if share < a.min_share:
            rows.append(dict(sev="INFO", feature=feat, majority=None,
                             forms={f: len(v) for f, v in forms.items()}, minority={}))
            continue
        minority = {f: sorted(v) for f, v in forms.items() if f != major}
        rows.append(dict(sev="CHECK", feature=feat, majority=f"{major} ({len(mkeys)}/{total})",
                         forms={f: len(v) for f, v in forms.items()}, minority=minority))
    for acr, names in sorted(venue_names.items()):
        if len(names) > 1:
            rows.append(dict(sev="CHECK", feature=f"venue {acr} written in {len(names)} ways", majority=None,
                             forms={n: 1 for n in sorted(names)}, minority={}))

    coverage = {"entries_compared": len(entries), "features": len(obs) + len(venue_names),
                "venues_compared": len(venue_names), "differences": sum(1 for r in rows if r["sev"] == "CHECK")}
    if a.json:
        print(json.dumps(dict(entries=len(entries), rows=rows, coverage=coverage), indent=1, ensure_ascii=False))
        return
    print(f"INFO | bibliography style | {len(entries)} cited entries from {', '.join(b.name for b in bibs)}")
    for r in rows:
        if r["sev"] == "CHECK" and r["majority"]:
            mins = "; ".join(f"{f}: {', '.join(ks[:12])}{' …' if len(ks) > 12 else ''}" for f, ks in r["minority"].items())
            print(f"CHECK | style differs | {r['feature']} | majority {r['majority']} | {mins}")
        elif r["sev"] == "CHECK":
            print(f"CHECK | style differs | {r['feature']} | " + " / ".join(f'"{n}"' for n in r["forms"]))
        else:
            print(f"INFO | no dominant style | {r['feature']} | " + ", ".join(f"{f}: {n}" for f, n in r["forms"].items()))
    print("COVERAGE | " + " | ".join(f"{k}={v}" for k, v in coverage.items()))


if __name__ == "__main__":
    main()
