# blind: double-blind leaks, and silence in single-blind
Run A: form_check.py main.tex --authors names.txt --blind double
MUST report:
- FAIL author name in the text: "Doe and Roe" running head (every page), "Jane Doe" p.1
- CHECK first-person ownership: "our previous work", "our library Foo ["
- FAIL identifying repository link: github.com/janedoe, github.com/acme-lab (acme-lab is in names.txt)
- INFO repository link: facebookresearch; nothing for anonymous.4open.science
- FAIL acknowledgements section
- CHECK grant number 123456
- Appendix after the references: "jane@doe.org" and "Jane Doe" on the last page -> missed/mislabelled: e-mails are skipped after ref_page, the name is labelled "in the references"
MUST NOT report:
- FAIL "author metadata in the source" / "PDF Author metadata" for pdfauthor={Anonymous}  -> expected false positive (any /Author or pdfauthor is a FAIL)
Run B: same with --blind single
MUST NOT report any of the anonymity kinds; names in bibitem/running head are fine.
