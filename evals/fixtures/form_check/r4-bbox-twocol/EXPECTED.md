# bbox-twocol: two columns, figure*, overflowing equation, landscape page, lineno, \small paragraph, appendix in \small, headers, rotated text, subscripts
Run: form_check.py main.tex --blind single --offline --no-widows ; and again with --no-page-numbers
MUST report: CHECK content outside the text block on the page with the overflowing equation (p.1 or 2).
MUST NOT report: content outside the text block on the figure* page; "very small text" on the math page (subscripts);
"page numbers printed" from the footnote "1 of 1" (run with --no-page-numbers: the real page numbers ARE printed, so one FAIL is right, but the key is the footnote).
Expected weaknesses: the landscape page (rotated page, pdflscape) -> content outside the text block (false positive);
the \small paragraph mid-paper is not detected (median per page); appendix pages in \small -> font drift (documented).
