# Adversarial fixtures for form_check.py (round 2)

Each folder: `main.tex` (+ `refs.bib`, `names.txt`) and `EXPECTED.md` (what the script must / must not report). The
machine-checked expectations are in `expectations.json`; run `python3 evals/tests/test_form_check.py`. All compile with
`latexmk -pdf -interaction=nonstopmode main.tex` (log-refs and bib exit non-zero on purpose: undefined refs, BibTeX error).
`make_fixtures.sh` regenerates the sources (widows/ and log-refs/ were then edited by hand: see their EXPECTED.md).

The verdicts below are those of the critic's round 2 (2026-11-07), before the fixes; all fixtures pass now.

| fixture | kind | verdict (round 2) |
|---|---|---|
| hidden-fn | false negatives, hidden text | FAIL: named colour, \raisebox/-30cm \vspace off page, injection in pdfsubject missed; accsupp caught only via pdftotext (mislocated) |
| hidden-fp | false positives, hidden text | FAIL: white-on-dark table header, alignment \phantom with words, opacity 0.05/0.08 all reported as FAIL |
| notes | note macros/packages | FAIL: `{{\color{red}#1}}` and `\textbf{\color{red}...}` macros missed, \hl missed; macro switched off by \renewcommand still FAIL |
| comments-verb | comments, \verb, \iffalse | PASS (noise: "TODO" counted as an acronym from verbatim text) |
| log-refs | log wrapping, nested inputs, refs | PASS mostly: `!` LaTeX errors and "h float specifier changed" not reported; "label defined twice" located at a wrong line |
| floats | deferred floats, plural mentions | FAIL: "Figures 1 and 2" / "Tables 1 and 2" -> Figure 2 and Table 2 "never referenced", Figure 2's deferral missed |
| widows | widows-and-orphans build | PASS |
| layout | layout hacks | FAIL: fullpage, savetrees, titlesec/\titlespacing, \def\baselinestretch missed |
| tables | ratio cells, bold | FAIL: baseline's own 1.0x flagged; bold-not-best missed (row-highlight heuristic); ratio inside a cell missed |
| names-acronyms | acronyms, name variants | FAIL: 8 acronym FPs incl. "(CP, $\alpha$)", "PQ (product quantization)", code identifiers; Dpr/Hnsw small-caps FPs; used-before-defined and two-word names missed |
| bib | .bib hygiene | FAIL: repeated key / BibTeX errors invisible (7 undefined citations reported without the cause); uncited commented entry flagged |
| blind (1 page) | double-blind leaks | FAIL: everything on the references page is skipped; pdfauthor={Anonymous} is a FAIL. single-blind run: PASS (silent) |
| blind2 (3 pages) | acks/e-mail/link on the references page | FAIL: all missed (only INFO "name in the references") |
