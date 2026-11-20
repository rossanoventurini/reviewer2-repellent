# refs-r4: biblatex @online, doi+eprint disagreeing, SICI DOI, old-style ids with categories, parent cited directly, @string title, math title, scheme-less DOI, same-surname wrong DOI
Run: refs_check.py refs.bib --no-refchecker
MUST report: FAIL q2 (eprint is the Transformer paper); FAIL q14 (DOI points to Gödel, authors differ); CHECK published version for q1, q6?, q13.
MUST NOT report: q3, q4 (SICI characters), q5, q6, q7, q8, q9, q10.
Expected: q11 "doi.org/..." without scheme -> FAIL "does not resolve" (clean_doi strips only doi: and http(s)://...doi.org/);
q12 same surname (Sun) with a wrong DOI -> only CHECK "translation or old title?" (severity too low for a wrong DOI).
