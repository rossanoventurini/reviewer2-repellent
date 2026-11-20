# layout: layout hacks
Run: form_check.py main.tex --blind single
MUST report (CHECK layout hack):
- main.tex:3 fullpage, :4 savetrees, :5 titlesec compact, :7 \titlespacing   -> no rule for these packages/commands
- main.tex:6 \def\baselinestretch{0.95}                                      -> regex only matches \renewcommand{\baselinestretch}
- main.tex:8 \setlength{\textfloatsep}, :14 \enlargethispage, :11 negative vspace -> expected to pass
MUST NOT report:
- main.tex:2 lmodern on article (font package on a class that does not fix the font)
