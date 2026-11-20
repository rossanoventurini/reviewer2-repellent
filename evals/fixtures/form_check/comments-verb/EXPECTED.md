# comments-verb: comment splitting, \verb, \iffalse, comment env
Run: form_check.py main.tex --authors names.txt --blind double
MUST report:
- main.tex:4  "Jane Doe" in the compiled text (p.1)              -> FAIL author name in the text (the \verb must not swallow it)
- main.tex:5  comment "Jane Doe wrote this" after \url{...%7E...} -> INFO comment (author name)
- main.tex:7  "TODO inside verbatim" printed in the PDF           -> FAIL TODO marker, p.1
- main.tex:9-12 \iffalse block: name + LLM instruction           -> INFO comment (author name, LLM instruction); the "% \fi" on line 11 must not end the block early
- main.tex:13 comment environment                                 -> INFO comment environment
- main.tex:16 "% TODO: plain comment"                             -> INFO comment (TODO)
MUST NOT report:
- a FAIL "instruction to LLM" from the \iffalse text (it is not in the PDF)
- "100\%" as a comment start
