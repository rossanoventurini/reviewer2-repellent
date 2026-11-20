# DOI spellings
MUST report FAIL "does not resolve": d8. d5 (trailing dot) may be reported as not resolving: acceptable, the printed DOI is broken.
MUST NOT report: d1, d2, d3, d6, d9, d10.
Expected bugs: d4 "doi:" prefix is not stripped -> FAIL "does not resolve" (false positive);
d7 a DOI that only appears in url= is never checked, so its wrong target (ResNet, cited as BERT) is missed.
