# notes: note packages and colour-note macros
Run: form_check.py main.tex --blind double
MUST report:
- main.tex:6  \rv  = {{\color{red}#1}} used on line 11      -> FAIL coloured note macro used   (regex needs "\{\s*\\(textcolor|color)" right after the arg count; the extra brace defeats it)
- main.tex:7  \todoX = \textbf{\color{red}TODO: ...} used    -> FAIL                             (same regex; \textbf first)
- main.tex:12 \hl{...} (soul highlight) used                  -> at least CHECK; no rule
MUST NOT report:
- main.tex:3 todonotes with [disable]      -> expected to pass
- main.tex:4 fixme with [final]            -> expected to pass
- main.tex:8-9 \quokka defined red, then \renewcommand'ed to plain: at most INFO
