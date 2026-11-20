#!/usr/bin/env python3
"""Reference check of a LaTeX paper: do the cited works exist, and is their metadata right?

Usage (after compiling the paper, so that <root>.aux lists the cited keys):
  python3 refs_check.py <root>.tex [--dblp-db PATH] [--no-refchecker] [--json]
  python3 refs_check.py refs.bib   (checks every entry)

Three layers, each reported as one line per finding (SEV | kind | key | "quote" | hint), like form_check.py:
1. RefChecker (academic-refchecker), if installed, without any LLM key and with the local DBLP database: existence,
   authors, year, venue. Its findings are CHECK: about half of its alarms are false, the agent confirms them.
2. Our own deterministic checks: every arXiv ID and every DOI must exist and lead to the cited title. A different
   title with at least one matching author surname is a CHECK (translation, old title, renamed version); a different
   title by other authors is a FAIL. arXiv IDs are read from eprint/arxivid, volume={abs/...} (DBLP), journal(title),
   url, note and 10.48550 DOIs, old-style ids (cs/0112017) included; DOIs from doi= and from doi.org links.
   Crossref first, DataCite (Zenodo, datasets, software) when Crossref does not know the DOI.
3. Preprints (arXiv/CoRR, @online with an eprint) whose published version is in the local DBLP database or is
   declared in the arXiv record (journal_ref / DOI) (CHECK).
BibTeX handling: @string macros, # concatenation, crossref inheritance (parents that are only crossref targets are
not checked on their own), repeated keys (CHECK; the first definition wins, as in BibTeX).
Only reference metadata (titles, identifiers) leaves the machine, never the paper. RefChecker takes about 10 s per
reference: run this script in the background. Network calls retry on 429/5xx/timeouts with exponential backoff.
Python stdlib only; network: export.arxiv.org, arxiv.org, api.crossref.org, api.datacite.org, doi.org.
"""
import argparse
import html
import http.client
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from form_check import Report  # noqa: E402  (same folder)

UA = {"User-Agent": "reviewer2-repellent-refs-check/1.0 (reference verification; +https://github.com/rossanoventurini/reviewer2-repellent)"}
DEFAULT_DB = pathlib.Path.home() / ".cache" / "refchecker" / "dblp.db"
NETERR = (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, ValueError, ET.ParseError)
MONTHS = {m: n for m, n in zip("jan feb mar apr may jun jul aug sep oct nov dec".split(),
                               "January February March April May June July August September October November "
                               "December".split())}
# fields a crossref child does not inherit (identifiers of the parent volume, bookkeeping)
NO_INHERIT = {"title", "doi", "url", "eprint", "eprinttype", "archiveprefix", "primaryclass", "eprintclass", "arxivid",
              "arxiv", "biburl", "bibsource", "timestamp", "crossref", "ids", "urldate", "file", "pdf", "pages",
              "chapter", "abstract", "keywords"}
SERIES = re.compile(r"(?i)lecture notes in|communications in computer and information science|ceur workshop|"
                    r"proceedings of machine learning research|advances in intelligent systems|lipics|leibniz "
                    r"international proceedings|studies in computational intelligence|ifip advances|"
                    r"lecture notes of the institute")
CONTAINER_TYPES = {"proceedings", "book", "collection", "mvproceedings", "mvbook", "mvcollection", "reference",
                   "mvreference", "periodical"}


# ---------------------------------------------------------------- bib
def _match_close(text, i, close):
    """Index of the delimiter closing an entry that starts at text[i] (after its opening delimiter)."""
    depth = 0
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0 and close == "}":
                return i
            depth -= 1
        elif c == close and depth == 0:
            return i
        i += 1
    return len(text)


def _parse_value(body, i, macros):
    """Parse 'part # part # ...' starting at body[i]; returns (value, next index)."""
    parts = []
    n = len(body)
    while True:
        while i < n and body[i].isspace():
            i += 1
        if i >= n:
            break
        c = body[i]
        if c == "{":
            depth, j = 0, i
            while j < n:
                if body[j] == "{":
                    depth += 1
                elif body[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            parts.append(body[i + 1:j])
            i = j + 1
        elif c == '"':
            depth, j = 0, i + 1
            while j < n and not (body[j] == '"' and depth == 0):
                depth += body[j] == "{"
                depth -= body[j] == "}"
                j += 1
            parts.append(body[i + 1:j])
            i = j + 1
        else:
            m = re.match(r"[^\s,#}]+", body[i:])
            if not m:
                break
            tok = m.group(0)
            parts.append(tok if tok.isdigit() else macros.get(tok.lower(), tok))
            i += len(tok)
        while i < n and body[i].isspace():
            i += 1
        if i < n and body[i] == "#":
            i += 1
            continue
        break
    return re.sub(r"\s+", " ", "".join(parts)).strip(), i


def _parse_fields(body, macros):
    fields, i, n = {}, 0, len(body)
    while i < n:
        m = re.compile(r"[\s,]*([^\s=,{}\"#]+)\s*=").match(body, i)
        if not m:
            break
        val, i = _parse_value(body, m.end(), macros)
        name = m.group(1).lower()
        if name not in fields:  # BibTeX keeps the first occurrence of a repeated field
            fields[name] = val
    return fields


def parse_bib(text):
    """[(key, type, fields)] in file order, with @string macros and # concatenation resolved. Entries commented with
    a leading '%' are read too, as BibTeX does (it has no comment character outside entries)."""
    out, macros, pos = [], dict(MONTHS), 0
    at = re.compile(r"@\s*(\w+)\s*([{(])")
    while True:
        m = at.search(text, pos)
        if not m:
            break
        typ = m.group(1).lower()
        end = _match_close(text, m.end(), "}" if m.group(2) == "{" else ")")
        body = text[m.end():end]
        pos = end + 1
        if typ in ("comment", "preamble"):
            continue
        if typ == "string":
            for name, val in _parse_fields(body, macros).items():
                macros[name] = val
            continue
        km = re.match(r"\s*([^,\s]+)\s*,", body)
        if not km:
            continue
        out.append((km.group(1), typ, _parse_fields(body[km.end():], macros)))
    return out


def split_and(s):
    """Split a BibTeX name list on ' and ' outside braces."""
    out, depth, cur, i = [], 0, "", 0
    while i < len(s):
        c = s[i]
        depth += c == "{"
        depth -= c == "}"
        if depth == 0 and re.match(r"\s+and\s+", s[i:], re.I) and cur:
            m = re.match(r"\s+and\s+", s[i:], re.I)
            out.append(cur)
            cur = ""
            i += m.end()
            continue
        cur += c
        i += 1
    if cur.strip():
        out.append(cur)
    return [x.strip() for x in out if x.strip()]


FOLD = str.maketrans({"ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
                      "đ": "d", "Đ": "D", "ı": "i", "þ": "th"})


def detex(s):
    s = re.sub(r"\\[`'^\"~=.]\s*\{?\s*\\?([A-Za-z])\}?", r"\1", s)  # accents: {\"o}, \'\i, \'{e}
    s = re.sub(r"\\[uvHtcdbkr](?:\s*\{\s*\\?([A-Za-z])\s*\}|\s+([A-Za-z]))",
               lambda m: m.group(1) or m.group(2), s)  # \v{s}, \c c (not \textbf, \ref)
    s = re.sub(r"\\(ss|ae|AE|oe|OE|aa|AA|o|O|l|L|i|j)(?![A-Za-z])\s*", lambda m: {"o": "o", "O": "O", "l": "l", "L": "L",
               "i": "i", "j": "j", "aa": "a", "AA": "A"}.get(m.group(1), m.group(1)), s)
    s = re.sub(r"\\[a-zA-Z]+\s*", " ", s)
    s = re.sub(r"\\.", "", s)
    s = re.sub(r"<[^>]+>", "", html.unescape(s))  # JATS/HTML tags in Crossref titles
    return re.sub(r"[{}$]", "", s)


def fold(s):
    s = unicodedata.normalize("NFKD", detex(s).translate(FOLD))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def norm_words(t):
    return [w for w in re.findall(r"[a-z0-9]+", fold(t)) if len(w) >= 3]


def main_title(t):
    return re.split(r"[:?!]|\s[-\u2013\u2014]{1,2}\s", detex(t), maxsplit=1)[0]


def similar(a, b):
    """Similarity of two titles (0..1): the larger of token Jaccard; containment of the shorter title in the longer
    one when the shorter has at least 4 words; 0.9 when one title is the other's main title (subtitle dropped)."""
    A, B = set(norm_words(a)), set(norm_words(b))
    if not A or not B:
        return 0.0
    inter = len(A & B)
    s = inter / len(A | B)
    if min(len(A), len(B)) >= 4:
        s = max(s, 0.9 * inter / min(len(A), len(B)))
    MA, MB = set(norm_words(main_title(a))), set(norm_words(main_title(b)))
    if (MA and MA == B) or (MB and MB == A):
        s = max(s, 0.9)
    return s


def show(t, n=80):
    return " ".join(detex(t).split())[:n]


GENERIC = {"the", "of", "and", "team", "group", "inc", "ltd", "et", "al"}


def cited_surnames(fields):
    """Folded surname tokens of the cited authors (editors if there are no authors)."""
    out = set()
    for name in split_and(fields.get("author") or fields.get("editor") or ""):
        if name.lower() == "others":
            continue
        if name.startswith("{") and name.endswith("}"):  # corporate author
            last = name
        else:
            depth, cut = 0, None
            for i, c in enumerate(name):
                depth += c == "{"
                depth -= c == "}"
                if c == "," and depth == 0:
                    cut = i
                    break
            last = name[:cut] if cut is not None else (name.split() or [""])[-1]
        out |= {w for w in re.findall(r"[a-z0-9]+", fold(last)) if len(w) >= 2 and w not in GENERIC}
    return out


def name_tokens(names):
    out = set()
    for n in names:
        out |= {w for w in re.findall(r"[a-z0-9]+", fold(n or "")) if len(w) >= 2}
    return out


def dblp_keys(title):
    """The two normalized forms RefChecker's DBLP database may use (with and without a 'Name:' prefix)."""
    t = fold(title)
    full = re.sub(r"[^a-z0-9]", "", t)
    rest = re.sub(r"[^a-z0-9]", "", t.split(":", 1)[1]) if ":" in t else full
    return [k for k in dict.fromkeys([full, rest]) if k]


AXID = r"(\d{4}\.\d{4,5}|[a-z][a-z\-]*(?:\.[A-Za-z\-]{2,})?/\d{7})(?:v\d+)?"


def norm_axid(i):
    """Canonical arXiv id: no version, no subject class in old-style ids (cs.DL/0112017 -> cs/0112017)."""
    i = re.sub(r"v\d+$", "", i.strip())
    m = re.match(r"([A-Za-z\-]+)(?:\.[A-Za-z\-]+)?/(\d{7})$", i)
    return f"{m.group(1).lower()}/{m.group(2)}" if m else i


def arxiv_ids(fields):
    """All distinct arXiv ids the entry prints, from every field where they appear."""
    out = []
    etype = (fields.get("eprinttype") or fields.get("archiveprefix") or "arxiv").lower()
    for f in ("eprint", "arxivid", "arxiv"):
        v = fields.get(f, "")
        if f == "eprint" and "arxiv" not in etype:
            continue
        m = re.search(r"(?<![\w.])" + AXID, v)
        if m:
            out.append(m.group(1))
    m = re.match(r"\s*abs/" + AXID + r"\s*$", fields.get("volume", ""))
    if m:
        out.append(m.group(1))
    blob = " ".join(fields.get(f, "") for f in ("journal", "journaltitle", "url", "howpublished", "note", "booktitle",
                                                 "doi", "pdf", "publisher", "number"))
    for m in re.finditer(r"arxiv\b[^0-9]{0,25}?(?<![\w])" + AXID, blob, re.I):
        out.append(m.group(1))
    return list(dict.fromkeys(norm_axid(i) for i in out))


def clean_doi(d):
    d = re.sub(r"\\url\s*\{([^}]*)\}", r"\1", d.strip()).replace("\\_", "_").replace("\\%", "%").replace("\\#", "#")
    d = re.sub(r"(?i)^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)", "", d.strip())
    return d.strip()


def dois_of(fields):
    """DOIs printed by the entry: the doi field, plus doi.org links in url/howpublished/note (not arXiv DOIs)."""
    out = []
    if fields.get("doi"):
        out.append(clean_doi(fields["doi"]))
    blob = " ".join(fields.get(f, "") for f in ("url", "howpublished", "note"))
    for m in re.finditer(r"(?i)(?:https?://)?(?:dx\.)?doi\.org/(10\.\d{4,9}/[^\s\"<>{}]+)", blob.replace("\\_", "_")):
        out.append(urllib.parse.unquote(m.group(1)).rstrip(".,;)"))
    seen, res = set(), []
    for d in out:
        if d and d.lower() not in seen and not d.lower().startswith("10.48550/arxiv"):
            seen.add(d.lower())
            res.append(d)
    return res


def is_preprint(typ, fields):
    blob = " ".join(fields.get(f, "") for f in ("journal", "journaltitle", "booktitle", "publisher", "howpublished",
                                                 "note", "institution")).lower()
    if re.search(r"\barxiv\b|\bcorr\b|preprint", blob):
        return True
    has_id = bool(arxiv_ids(fields)) or bool(fields.get("eprint"))
    venue = any(fields.get(f) for f in ("journal", "journaltitle", "booktitle"))
    return has_id and (typ in ("misc", "unpublished", "online", "electronic", "www") or (typ == "article" and not venue))


# ---------------------------------------------------------------- network
def get(url, timeout=30, tries=4):
    """GET with retries on 429/5xx/timeouts (exponential backoff, Retry-After respected); raises on final failure."""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or i == tries - 1:
                raise
            ra = (e.headers or {}).get("Retry-After", "")
            wait = int(ra) if ra.strip().isdigit() else 2 ** i
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException):
            if i == tries - 1:
                raise
            wait = 2 ** i
        time.sleep(min(wait, 60))


ATOM = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}


def _arxiv_query(ids):
    """({id: record}, [malformed ids]) for one API call."""
    q = urllib.parse.urlencode({"id_list": ",".join(ids), "max_results": len(ids)})
    root = ET.fromstring(get("https://export.arxiv.org/api/query?" + q))
    got, bad = {}, []
    for e in root.findall("a:entry", ATOM):
        eid = e.findtext("a:id", "", ATOM) or ""
        title = " ".join((e.findtext("a:title", "", ATOM) or "").split())
        if "/api/errors" in eid or title.lower() == "error":
            m = re.search(r"incorrect_id_format_for_(.+)$", eid)
            bad.append(m.group(1) if m else None)
            continue
        if "/abs/" not in eid or not title:
            continue
        got[norm_axid(eid.split("/abs/", 1)[1])] = dict(
            title=title, authors=[a.findtext("a:name", "", ATOM) for a in e.findall("a:author", ATOM)],
            doi=(e.findtext("x:doi", "", ATOM) or "").strip(), jref=" ".join((e.findtext("x:journal_ref", "", ATOM) or "").split()))
    return got, bad


def _arxiv_abs_page(i):
    """Record from the arxiv.org/abs page (fallback when the API omits an id); None if the page is 404."""
    try:
        page = get("https://arxiv.org/abs/" + i).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    meta = lambda n: [html.unescape(x) for x in re.findall(rf'<meta name="{n}" content="([^"]*)"', page)]  # noqa: E731
    t = meta("citation_title")
    if not t:
        raise ValueError("no citation_title")
    return dict(title=" ".join(t[0].split()), authors=meta("citation_author"), doi=(meta("citation_doi") or [""])[0],
                jref="")


def arxiv_records(ids, R):
    """{id: record | None (does not exist) | 'malformed'}; ids that could not be looked up are absent."""
    res = {}
    for i in set(ids):  # new-style ids have 4 digits after the dot up to 1412, 5 from 1501
        m = re.fullmatch(r"(\d{2})(\d{2})\.(\d+)", i)
        if m and (int(m.group(2)) not in range(1, 13) or len(m.group(3)) != (5 if m.group(1) + m.group(2) >= "1501" else 4)):
            res[i] = "malformed"
    ids = sorted(set(ids) - set(res))
    for s in range(0, len(ids), 50):
        chunk = ids[s:s + 50]
        for _ in range(3):  # malformed ids make the API answer with an error only: drop them and ask again
            try:
                got, bad = _arxiv_query(chunk)
            except NETERR as e:
                R.skip(f"arXiv ID check: arXiv API unreachable for {len(chunk)} IDs ({e.__class__.__name__}): "
                       + ", ".join(chunk[:10]))
                chunk = []
                break
            if bad:
                for b in bad:
                    if b in chunk:
                        res[b] = "malformed"
                chunk = [c for c in chunk if c not in res]
                if None in bad or not chunk:
                    break
                time.sleep(3)
                continue
            for c in chunk:
                if c in got:
                    res[c] = got[c]
            break
        for c in chunk:
            if c not in res:  # missing from the API answer: confirm on the abs page before calling it non-existent
                try:
                    res[c] = _arxiv_abs_page(c)
                except NETERR as e:
                    R.skip(f"arXiv ID check: arXiv:{c} not in the API answer and its abs page unreachable "
                           f"({e.__class__.__name__})")
        time.sleep(3)  # arXiv API etiquette
    return res


def doi_record(doi):
    """{'ra': 'crossref'|'datacite'|'other'|'missing', 'titles', 'authors', 'containers'} or None on network failure.
    'other' = registered with another agency (mEDRA, JaLC, ...): existence only."""
    q = urllib.parse.quote(doi, safe="/:;()<>[]")
    try:
        m = json.loads(get("https://api.crossref.org/works/" + q)).get("message", {})
        titles = [t for t in m.get("title") or [] if t]
        subs = [t for t in m.get("subtitle") or [] if t]
        titles += [f"{t}: {s}" for t in titles[:1] for s in subs] + (m.get("original-title") or []) + \
            (m.get("short-title") or [])
        people = [a.get("family") or a.get("name") or "" for a in (m.get("author") or []) + (m.get("editor") or [])]
        return dict(ra="crossref", titles=titles, authors=name_tokens(people), containers=m.get("container-title") or [])
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return None
    except NETERR:
        return None
    try:
        a = json.loads(get("https://api.datacite.org/dois/" + q)).get("data", {}).get("attributes", {})
        titles = [t.get("title") or "" for t in a.get("titles") or []]
        titles = [t for t in titles if t]
        people = [c.get("familyName") or (c.get("name") or "").split(",")[0] for c in (a.get("creators") or [])]
        return dict(ra="datacite", titles=titles, authors=name_tokens(people), containers=[])
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return None
    except NETERR:
        return None
    try:
        h = json.loads(get("https://doi.org/api/handles/" + q))
        return dict(ra="other" if h.get("responseCode") == 1 else "missing", titles=[], authors=set(), containers=[])
    except urllib.error.HTTPError as e:
        return dict(ra="missing", titles=[], authors=set(), containers=[]) if e.code == 404 else None
    except NETERR:
        return None


def compare(cited_t, cited_auth, titles, rec_auth, containers=()):
    """None if the record's title matches the cited one; else ('container'|'same-authors'|'other', best title)."""
    titles = [t for t in titles if t and t.strip()]
    if not cited_t or not titles:
        return None
    if max(similar(cited_t, t) for t in titles) >= 0.5:
        return None
    if any(similar(cited_t, c) >= 0.8 for c in containers):
        return ("container", titles[0])
    shared = cited_auth & rec_auth
    # a translation or a renamed paper keeps its authors: one common surname ("Sun") is not enough
    strong = len(shared) >= 2
    overlap = any(set(norm_words(cited_t)) & set(norm_words(t)) for t in titles)
    foreign = looks_foreign(cited_t) or any(looks_foreign(t) for t in titles)
    every = bool(cited_auth) and shared == cited_auth  # all cited authors are on the record
    if strong or (every and (overlap or foreign)):
        return ("same-authors", titles[0])
    return ("other", titles[0])


FOREIGN = re.compile(r"[^\x00-\x7f]|\b(der|die|das|und|über|eine?|le|la|les|des|une?|et|pour|sur|dans|il|lo|gli|della|"
                     r"delle|per|una|el|los|las|para|con|em|do|da|uma|het|een|voor|och|för|och)\b", re.I)


def looks_foreign(title):
    return bool(FOREIGN.search(title or ""))


# ---------------------------------------------------------------- layers
def bib_text(entries):
    out = []
    for k, (typ, f, bf) in entries.items():
        body = ",\n".join(f"  {n} = {{{v}}}" for n, v in f.items() if n != "crossref")
        out.append(f"@{typ}{{{k},\n{body}\n}}")
    return "\n\n".join(out) + "\n"


def run_refchecker(bib, db, R, timeout):
    exe = shutil.which("academic-refchecker")
    if not exe:
        R.skip("RefChecker not installed (see SETUP.md): existence/author/venue checks rely on the agent")
        return []
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "cited.bib"
        p.write_text(bib, encoding="utf-8")
        rep = pathlib.Path(td) / "rc.json"
        cmd = [exe, "--paper", str(p), "--report-file", str(rep), "--report-format", "json"]
        if db and db.is_file():
            cmd += ["--dblp-db", str(db)]
        else:
            R.skip("local DBLP database missing: RefChecker uses online sources only (weaker year/venue diagnosis)")
        env = {k: v for k, v in os.environ.items()
               if k not in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY")}
        try:
            subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout, cwd=td)
        except subprocess.TimeoutExpired:
            R.skip(f"RefChecker timed out after {timeout} s")
            return []
        if not rep.is_file():
            R.skip("RefChecker produced no report")
            return []
        data = json.loads(rep.read_text())
        s = data.get("summary", {})
        if isinstance(s.get("total_references_processed"), int):
            R.coverage["refchecker_checked"] = s["total_references_processed"]
        R.add("INFO", "RefChecker", quote=f"{s.get('total_references_processed', '?')} references, "
              f"{s.get('total_errors_found', 0)} errors, {s.get('total_warnings_found', 0)} warnings, "
              f"{s.get('total_unverified_refs', 0)} unverified", key="rcsum")
        return data.get("records", [])


def venue_abbreviates(det):
    m = re.search(r"cited:\s*(.*?)\s*actual:\s*(.*)$", det, re.S)
    if not m:
        return False
    cited, actual = (re.sub(r"[^a-z]", "", x.lower()) for x in m.groups())
    if not actual or not cited:
        return False
    if actual in cited or cited in actual:
        return True
    it = iter(cited)
    return len(actual) <= 12 and all(ch in it for ch in actual)  # acronym letters appear in order in the full name


NON_INDEXED_TYPES = {"book", "misc", "techreport", "manual", "online", "electronic", "www", "booklet", "unpublished", "phdthesis", "mastersthesis"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="<root>.tex (cited keys from <root>.aux) or a .bib file")
    ap.add_argument("--dblp-db", default=str(DEFAULT_DB), help=f"RefChecker's local DBLP database (default {DEFAULT_DB})")
    ap.add_argument("--no-refchecker", action="store_true", help="skip RefChecker (fast, own checks only)")
    ap.add_argument("--timeout", type=int, default=3600, help="RefChecker timeout in seconds")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    R = Report()
    src = pathlib.Path(a.input).resolve()
    bibs, cited = [], None
    if src.suffix == ".bib":
        bibs = [src]
    else:
        code = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in [src] + sorted(src.parent.rglob("*.tex")))
        code = re.sub(r"(?<!\\)%.*", "", code)
        for m in re.finditer(r"\\bibliography\s*\{([^}]+)\}|\\addbibresource\s*(?:\[[^\]]*\])?\{([^}]+)\}", code):
            for b in (m.group(1) or m.group(2)).split(","):
                p = src.parent / (b.strip() if b.strip().endswith(".bib") else b.strip() + ".bib")
                if p.is_file() and p not in bibs:
                    bibs.append(p)
        aux = src.with_suffix(".aux")
        if aux.is_file():
            cited = set()
            for m in re.finditer(r"\\citation\{([^}]+)\}|\\abx@aux@cite\{\d*\}\{([^}]+)\}", aux.read_text(errors="replace")):
                cited.update(k.strip() for k in (m.group(1) or m.group(2)).split(","))
        else:
            R.skip(f"{aux.name} not found: checking every .bib entry, cited or not (compile first)")
    if not bibs:
        bbl = src.with_suffix(".bbl") if src.suffix == ".tex" else None
        print("SKIPPED | no .bib file found" + (f" (only {bbl.name}: check the references in it by hand or with the "
              "DBLP MCP server)" if bbl and bbl.is_file() else ""))
        return
    every, lower = {}, {}
    for b in bibs:
        for key, typ, fields in parse_bib(b.read_text(encoding="utf-8", errors="replace")):
            if key.lower() in lower:  # BibTeX keys are case-insensitive; the first definition wins
                if cited is None or key in cited or "*" in cited or lower[key.lower()] in cited:
                    R.add("CHECK", "repeated BibTeX key", key, "", f"defined again in {b.name}: the later definition "
                          "is ignored by BibTeX", key=f"dup{key}", hint="delete or rename one of the two entries")
                continue
            lower[key.lower()] = key
            every[key] = (typ, fields, b.name)
    # crossref inheritance: the child gets the parent's missing fields (the parent's title becomes its booktitle)
    targets = set()
    for k, (typ, f, bf) in every.items():
        x = f.get("crossref")
        if not x:
            continue
        pk = lower.get(x.lower())
        if pk is None:
            if cited is None or k in cited or "*" in cited:
                R.add("CHECK", "crossref target not found", k, "", f"crossref={x}", key=f"xref{k}",
                      hint="add the parent entry or inline its fields")
            continue
        targets.add(pk)
        ptyp, pf, _ = every[pk]
        for n, v in pf.items():
            if n not in NO_INHERIT and n not in f:
                f[n] = v
        if pf.get("title") and "booktitle" not in f and typ in ("inproceedings", "incollection", "inbook",
                                                                 "inreference", "conference"):
            f["booktitle"] = pf["title"]
    entries = {k: v for k, v in every.items() if cited is None or k in cited or "*" in cited}
    if not entries:
        raise SystemExit("no cited entries found")

    # 1. RefChecker (not on parents that are only crossref targets: they are volumes, not cited works)
    if not a.no_refchecker:
        to_check = {k: v for k, v in entries.items()
                    if not (k in targets and (cited is None or "*" in cited) and v[0] in CONTAINER_TYPES)}
        recs = run_refchecker(bib_text(to_check), pathlib.Path(a.dblp_db), R, a.timeout)
        by_title = {}
        for k, (typ, f, bf) in to_check.items():
            by_title.setdefault(" ".join(norm_words(f.get("title", ""))), []).append(k)
        per_key = {}
        for r in recs:
            orig = r.get("original_reference")
            orig = orig if isinstance(orig, dict) else {}
            m = re.match(r"@\w+\{([^,\s]+)", r.get("ref_raw_text") or orig.get("raw_text") or "")
            key = orig.get("bibtex_key") or (m.group(1) if m else None)
            if key not in to_check:
                ks = by_title.get(" ".join(norm_words(r.get("ref_title") or "")))
                key = " / ".join(ks) if ks else (r.get("ref_title") or "?")
            for err in r.get("_original_errors") or [r]:
                kind = err.get("error_type") or err.get("warning_type") or err.get("info_type") or "issue"
                det = err.get("error_details") or err.get("warning_details") or err.get("info_details") or ""
                if "info_type" in err and "error_type" not in err:
                    continue  # suggestions such as "could include arXiv URL"
                if "venue" in kind.lower() and SERIES.search(str(det).split("actual:")[-1]):
                    continue  # the "actual venue" is a book series (LNCS, CEUR, PMLR...), not a mismatch
                if "venue" in kind.lower() and venue_abbreviates(str(det)):
                    continue  # full name in the bib, acronym in the database (EMNLP, AISTATS, EuroS&P)
                if "year" in kind.lower():
                    ys = [int(y) for y in re.findall(r"\b(?:19|20)\d\d\b", str(det))]
                    if len(ys) >= 2 and abs(ys[0] - ys[1]) <= 1:
                        continue  # arXiv year vs venue year
                hall = "hallucinat" in json.dumps(err).lower() or kind == "unverified"
                d = per_key.setdefault(key, {"hall": False, "items": []})
                d["hall"] |= hall
                d["items"].append(f"{kind}: " + " ".join(str(det).split())[:140])
        for key, d in per_key.items():  # one line per reference, all its problems
            typ = to_check.get(key, ("",))[0].lower()
            if d["hall"]:
                # absence from the databases is not fabrication: books, reports, manuals and web pages are often absent
                R.add("INFO" if typ in NON_INDEXED_TYPES else "CHECK", "not found in the reference databases", key, "",
                      " | ".join(d["items"])[:400], key=f"rc{key}",
                      hint="look the title up on the web; report it only if no such work exists or its authors differ")
            else:
                R.add("CHECK", "bib differs from the database record", key, "", " | ".join(d["items"])[:400],
                      key=f"rc{key}", hint="quote both (bib says / database says) after checking the record")

    # 2. arXiv IDs and DOIs
    auth = {k: cited_surnames(f) for k, (t, f, b) in entries.items()}
    ax = {k: arxiv_ids(f) for k, (t, f, b) in entries.items()}
    ax = {k: v for k, v in ax.items() if v}
    recs_ax, ok_ax = {}, {}  # ok_ax: key -> arXiv record whose title matches the cited work
    if ax:
        recs_ax = arxiv_records([i for v in ax.values() for i in v], R)
        for k, ids in ax.items():
            cited_t = entries[k][1].get("title", "")
            for i in ids:
                if i not in recs_ax:
                    continue  # lookup failed: already in SKIPPED
                rec = recs_ax[i]
                if rec == "malformed":
                    R.add("FAIL", "arXiv ID is malformed", k, "", f"arXiv:{i} — cited title: {show(cited_t, 90)}")
                    continue
                if rec is None:
                    R.add("FAIL", "arXiv ID does not exist", k, "", f"arXiv:{i} — cited title: {show(cited_t, 90)}")
                    continue
                c = compare(cited_t, auth[k], [rec["title"]], name_tokens(rec["authors"]))
                if c is None:
                    ok_ax.setdefault(k, rec)
                elif c[0] == "same-authors":
                    ok_ax.setdefault(k, rec)
                    R.add("CHECK", "title differs from the arXiv record (old version title or renamed?)", k, "",
                          f"arXiv:{i} is \"{show(c[1])}\"; cited: \"{show(cited_t)}\"", key=f"axt{k}{i}",
                          hint="same authors: cite the current title, or confirm the old one is intended")
                else:
                    R.add("FAIL", "arXiv ID points to another paper", k, "",
                          f"arXiv:{i} is \"{show(c[1])}\" by other authors; cited: \"{show(cited_t)}\"")
    dois = {k: dois_of(f) for k, (t, f, b) in entries.items()}
    dois = {k: v for k, v in dois.items() if v}
    failed, ndoi = [], 0
    for k, ds in dois.items():
        cited_t = entries[k][1].get("title", "")
        for d in ds:
            ndoi += 1
            rec = doi_record(d)
            time.sleep(0.2)
            if rec is None:
                failed.append(f"{k} ({d})")
                continue
            if rec["ra"] == "missing":
                R.add("FAIL", "DOI does not resolve", k, "", d, hint="check the DOI at https://doi.org (typo, "
                      "trailing punctuation?)")
                continue
            c = compare(cited_t, auth[k], rec["titles"], rec["authors"], rec["containers"])
            if c is None:
                continue
            if c[0] == "container":
                R.add("FAIL", "DOI points to another work", k, "", f"{d} is \"{show(c[1])}\", a part of the cited "
                      f"\"{show(cited_t)}\"", hint="cite the chapter/article title, or use the volume's DOI")
            elif c[0] == "same-authors":
                R.add("CHECK", "title differs from the DOI record (translation or old title?)", k, "",
                      f"{d} is \"{show(c[1])}\"; cited: \"{show(cited_t)}\"", key=f"doit{k}{d}",
                      hint="same authors: fine for a translation, otherwise fix the title or the DOI")
            else:
                R.add("FAIL", "DOI points to another work", k, "",
                      f"{d} is \"{show(c[1])}\" by other authors; cited: \"{show(cited_t)}\"")
    if failed:
        R.skip(f"DOI check: {len(failed)} of {ndoi} DOIs could not be looked up (network/rate limit): "
               + ", ".join(failed[:12]) + (" ..." if len(failed) > 12 else ""))

    # 3. published versions of preprints (local DBLP, then the arXiv record's journal_ref/DOI)
    db = pathlib.Path(a.dblp_db)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True) if db.is_file() else None
    if con is None:
        R.skip("published-version check: local DBLP database not found (see SETUP.md); arXiv journal_ref only")
    npre = 0
    for k, (typ, f, bf) in entries.items():
        if not f.get("title") or not is_preprint(typ, f):
            continue
        npre += 1
        rec = ok_ax.get(k)
        found = False
        if con is not None:
            rows = []
            for t in [f["title"]] + ([rec["title"]] if rec else []):
                for nk in dblp_keys(t):
                    rows += con.execute("select title, venue, year, externalIds_DOI from papers "
                                        "where normalized_paper_title=?", (nk,)).fetchall()
            try:
                py = int(f.get("year", "")[:4])
            except ValueError:
                py = None
            pub = [r for r in rows if r[1] and not re.match(r"(?i)corr|arxiv", r[1])
                   and (py is None or (r[2] and int(r[2]) >= py - 1))]  # never a work older than the preprint
            if pub:
                t, v, y, d = sorted(pub, key=lambda r: r[2] or 0)[0]
                R.add("CHECK", "preprint cited, published version exists", k, "",
                      f"{v} {y}" + (f", doi {d}" if d else ""), key=f"pub{k}",
                      hint="cite the published version (reviewers notice)")
                found = True
        if not found and rec and (rec["doi"] or rec["jref"]):
            R.add("CHECK", "preprint cited, published version exists", k, "",
                  "arXiv record: " + "; ".join(x for x in (rec["jref"], f"doi {rec['doi']}" if rec["doi"] else "") if x),
                  key=f"pub{k}", hint="cite the published version (reviewers notice); its title may differ")

    R.add("INFO", "references checked", quote=f"{len(entries)} cited entries from {', '.join(b.name for b in bibs)}; "
          f"{sum(len(v) for v in ax.values())} arXiv IDs, {ndoi} DOIs", key="count")
    nax = sum(len(v) for v in ax.values())
    with_id = set(ax) | set(dois)
    not_looked = {k for k, v in ax.items() for i in v if i not in recs_ax} | {x.split(" (")[0] for x in failed}
    cov = {"references": len(entries)}
    cov.update(R.coverage)
    cov.update(arxiv_ids=nax, arxiv_looked_up=sum(1 for v in ax.values() for i in v if i in recs_ax),
               dois=ndoi, dois_looked_up=ndoi - len(failed), refs_with_identifier=len(with_id),
               refs_identifier_looked_up=len(with_id - not_looked), preprints=npre,
               preprints_dblp_db=npre if con is not None else 0)
    R.coverage = cov
    if a.json:
        print(json.dumps(dict(findings=R.rows(), skipped=R.skipped, coverage=R.coverage), indent=1, ensure_ascii=False))
    else:
        print(R.text())


if __name__ == "__main__":
    main()
