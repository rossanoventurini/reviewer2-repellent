---
name: Bug report
about: A script fails, a step crashes, or the output is wrong or missing
title: "[bug] "
labels: bug
---

<!-- Please do not attach your paper or its sources. Quote only the few lines needed to show the problem,
     and replace anything confidential (names, numbers, unpublished results) with placeholders. -->

**What happened**
<!-- What you asked the agent, what you expected, what you got. -->

**Where**
- Step or script: <!-- e.g. form_check.py, refs_check.py, build_changes.py, step 6, read_choices.py -->
- Error message or log excerpt:

```
paste here
```

**Setup**
- Venue: <!-- e.g. SIGIR 2027, or "none" -->
- Document class: <!-- e.g. acmart sigconf, llncs, IEEEtran, article -->
- Engine: <!-- pdflatex, xelatex, lualatex; bibtex or biber -->
- Agent CLI and version: <!-- e.g. Claude Code 2.1.x, Codex, Gemini CLI -->
- Operating system:
- Output of `python3 skills/reviewer2-repellent/scripts/check_setup.py` (from the folder where the skill lives):

```
paste here
```

**Minimal example (optional, very welcome)**
<!-- A tiny .tex/.bib written from scratch that reproduces the problem. -->
