# floats: deferred floats, plural mentions, appendix figures
Run: form_check.py main.tex --blind single
MUST report:
- FAIL float printed after the references: Figures 1, 2, 3 (mentioned p.1, full-page [t] floats flushed after the bibliography)
MUST NOT report:
- "float never referenced" for Figure 2 or Table 2: they are mentioned as "Figures 1 and 2" / "Tables 1 and 2" (MENTION_RX captures only the first number)
- anything for Figure A.1 (appendix figure, mentioned in the appendix)
