# widows: a hyphen in the last line of a page (widows-and-orphans warns "Hyphen in last line of page 2"); blind2 also has a genuine "Widow on page 2"
Run: form_check.py main.tex --blind single
MUST report: CHECK widow/orphan/page-break hyphen p.2
Missed by design (no rule): a \section heading as the last line of a page; a page whose last line is a displayed equation or a single table row.
