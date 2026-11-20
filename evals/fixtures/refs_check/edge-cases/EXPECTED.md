# edge cases added with the refs_check.py fixes (network needed)
MUST report: e1 CHECK published version (arXiv journal_ref/DOI, not in DBLP); e2 FAIL malformed arXiv id; e5 CHECK crossref
target not found; e8 CHECK title differs from the arXiv record (same authors, different title).
MUST NOT report: e3 (old-style id with subject class and version), e4 (DOI in a dx.doi.org link), e6 (eprint of
another type), e7 (@string macro + # concatenation, escaped underscore in the DOI).
