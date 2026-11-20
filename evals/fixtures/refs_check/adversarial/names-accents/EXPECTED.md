# names-accents: LaTeX-escaped accents, braces, translated titles
MUST NOT report: n1 (escaped umlauts fold to the Crossref title), n3, n4, n5.
Expected false positive: n2 (the English translation of a German title) -> FAIL "DOI points to another work"; needs a
"title in another language" escape (e.g. CHECK when the Crossref title has no common words at all AND the DOI resolves).
