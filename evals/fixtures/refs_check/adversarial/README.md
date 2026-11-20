# refs_check.py fixtures (round 3)

Each folder: `refs.bib`, `EXPECTED.md`, `RESULT.txt` (run of 2026-11-07, `--no-refchecker` except refchecker-small).
Real identifiers on purpose; network needed. `make.sh` regenerates the .bib files.

| fixture | verdict |
|---|---|
| subtitles | s5 caught; s3/s4 (two-word titles with a wrong DOI) pass: containment too lenient |
| names-accents | accents fold correctly; n2 translated title -> FAIL (false positive) |
| corporate-datasets | no FP on corporate authors; c4 wrong title on a Zenodo DOI missed (DataCite never queried) |
| reports-books | silent, as expected |
| arxiv-ids | a6/a7 caught; a1 old-style id -> FAIL "does not exist" (false positive); a2, a9, a10 (id in journal/volume) not read |
| biblatex | b6 caught; b2 (journaltitle=CoRR, volume=abs/...) and b1 (@online) get no published-version CHECK; b4 missed |
| doi-forms | d8 caught, d5 trailing dot caught; d4 "doi:" prefix is fine (Crossref tolerates it); d7 DOI only in url= never checked |
| strings-crossref | silent (own checks); see refchecker-small for the crossref problem |
| preprint-title | p2/p3 caught; p1 (title changed at publication) missed: exact-title DBLP lookup; the arXiv feed's journal_ref/doi are discarded |
| duplicates | u2 caught; second u3 (same key) silently dropped; RefChecker findings on u2 would land on u1 |
| refchecker-small | RefChecker: k2 wrong authors caught; k3 corporate and k4 accents clean; k5/k6 crossref child/parent -> 2 false positives |
