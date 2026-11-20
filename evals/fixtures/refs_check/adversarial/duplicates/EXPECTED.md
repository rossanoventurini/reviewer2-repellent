# duplicate entries
MUST report FAIL: u2 (its eprint is the Transformer paper, not BERT).
MUST report CHECK published version: u1.
Expected weaknesses: the second u3 (same key, bad DOI) is ignored because the first key wins, which matches BibTeX, but no
"repeated key" finding is produced here or in form_check (BibTeX only warns in the .blg). With RefChecker, u1 and u2 have
the same normalized title, so by_title maps both records to u1: any RefChecker finding about u2 is attributed to u1.
