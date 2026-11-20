# hidden-fn: hidden-text variants the script should catch (false negatives)
Run: form_check.py main.tex --blind double
MUST report (FAIL hidden text / instruction):
- main.tex:3  instruction to an LLM in PDF metadata (pdfsubject)        -> check_anonymity reads only /Author; INJECTION never applied to metadata
- main.tex:4  \definecolor{ghost}{named}{white} + line 8 \textcolor{ghost} -> model "named" returns None
- main.tex:5  \hide macro (fontsize 1pt) and its use on line 9            -> expected to pass
- main.tex:6  \AddToShipoutPictureBG with white text                      -> CMD_END blocks the BG/FG suffix
- main.tex:10 \raisebox{-40cm} (off page)                                 -> no rule
- main.tex:11 accsupp ActualText injection (text layer differs from ink)  -> no rule; pdftotext shows the ActualText
- main.tex:13 \vspace*{-30cm} (off page): old script had "text pushed off the page", new one only says "negative vertical space"
MUST NOT report: nothing else.
