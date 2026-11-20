# log-refs: log parsing with wrapped lines, nested inputs, undefined refs/cites, duplicate labels, float too large
Run: form_check.py main.tex --blind single
MUST report:
- FAIL overfull \hbox in part-one.tex (paragraph, lines 1) and in part-one.tex (table, "detected at line")
- FAIL overfull \hbox in part-two.tex line 1   -> the stray ")" in part-one's overfull text pops file_at's stack: likely attributed to main.tex or "?"
- FAIL undefined reference eq:nope (log) and "??" in the PDF text, p.1
- FAIL undefined citation nokey (log) and "[?]" in the PDF
- FAIL label defined twice "dup" (main.tex:5 and :8)
- FAIL float too large (fig:huge)
- CHECK "h float specifier changed to ht" -> not in the regex list (only "No positions in optional float specifier")
MUST NOT report: overfull boxes attributed to the wrong file.
