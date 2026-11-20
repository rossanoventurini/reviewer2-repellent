# hidden-fp: legitimate LaTeX that must NOT be flagged as hidden text
Run: form_check.py main.tex --blind double
MUST NOT report as FAIL:
- line 12 \textcolor{white} on a \rowcolor{header} dark row (white-on-dark header)   -> expected FAIL "white or near-white text colour" x3 cells
- line 4/14 near-white table shading (definecolor gray 0.98 + \rowcolor)             -> expected to pass (only textcolor/color uses are flagged)
- line 20 \phantom{Baseline method} alignment phantom with words                       -> expected FAIL "\phantom with words"
- line 22-23 opacity=0.05 / fill opacity=0.08 light shading                            -> expected FAIL "zero opacity" (regex 0?\.0\d* matches .05 and .08)
- line 26 \scalebox{0.5}                                                               -> expected to pass
Acceptable: CHECK for the phantom / white-on-dark cases, never FAIL.
