# bib: bibliography hygiene
Run: form_check.py main.tex --blind single
MUST report:
- CHECK same title under different keys: dup1, dup2 (braces differ only)
- CHECK '%' does not comment out: commented (cited, printed)
- CHECK bib entry without year: noyear
- FAIL/CHECK repeated key "repeated" (BibTeX: "Repeated entry" error in .blg; the second is skipped) -> missed: .blg errors are not "Warning--" lines and parse_bib silently overwrites
MUST NOT report:
- capitals lost for HNSW / DiskANN (protected with braces)
- "article without journal" for strjournal (journal=jair is a @string)
- '%' commented entry "uncommented": it is not cited, so harmless  -> expected false positive (flagged before the cited filter)
