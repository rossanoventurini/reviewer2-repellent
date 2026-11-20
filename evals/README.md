# How the numbers in the README were measured

This page describes the three measurements behind the "How well does it work?" section of the [README](../README.md):
what was compared, how errors were counted, and the per-paper counts. The papers themselves, the reports and the
labels are not published: they contain other people's unpublished or under-review text. Papers are therefore called
A to E, and no title, identifier, author or quotation is given.

These are **development results**. The same papers were used to tune the checkers, so the numbers are optimistic;
the held-out evaluation is still to be run.

## 1. Combined checkers vs a single careful-reading agent

**Papers.** 5 conference papers submitted to an ICLR-style venue, with public reviews on OpenReview and LaTeX sources
on arXiv. A sixth paper was run but could not be scored (the scoring run failed on a network error) and is left out.

**Systems.** Both ran on the same LaTeX sources with the same model:

- *Single agent*: one agent asked to read the whole paper carefully and report every objective error.
- *Combined checkers*: the pipeline of the skill (a reader, a numbers-and-claims checker, a two-stage typos checker,
  the scripts' facts, and a merge step that produces one report). Only the main sections of the final report were
  counted; the appendix of "likely" typos was not.

**What counts as an objective error.** A defect that a reader can verify against the paper or an external record,
not an opinion: numbers that disagree with tables or with each other, claims that the results do not support, typos
and grammar slips, wrong references and bibliography entries, broken or wrong cross-references, leftovers (notes,
TODOs, commented text that leaks), violations of the venue's rules, and layout defects. Judgments on novelty,
significance, missing experiments or writing style are *subjective* and were counted apart.

**Pooling and labelling.** For each paper the items of the two reports were pooled and deduplicated by place and
problem, so that the same error found by both systems counts once. An independent model (a different model from the
one that produced the reports, run in a fresh context) labelled every item without knowing which system had found it
(the two reports were shown only as A and B): *objective* (a real objective error), *subjective* (an
opinion or a matter of taste) or *false* (the claimed error does not exist).

**Counts per paper.**

| paper | objective, single agent | objective, combined | found by both | only single agent | only combined | false (single / combined) | subjective (single / combined) |
|---|---:|---:|---:|---:|---:|:---:|:---:|
| A | 77 | 91 | 68 | 9 | 23 | 0 / 2 | 9 / 11 |
| B | 89 | 135 | 79 | 10 | 56 | 1 / 2 | 8 / 15 |
| C | 66 | 71 | 58 | 8 | 13 | 1 / 0 | 24 / 19 |
| D | 59 | 66 | 57 | 2 | 9 | 2 / 2 | 25 / 40 |
| E | 101 | 122 | 90 | 11 | 32 | 2 / 2 | 23 / 27 |
| **total** | **392** | **485** | **352** | **40** | **133** | **6 / 8** | **89 / 112** |

The union of the objective errors found by either system is 352 + 40 + 133 = 525. The combined checkers found
485 of them (92%), the single agent 392 (75%). The combined checkers found more on every paper. The 40 errors found
only by the single agent were analysed one by one: most (32) were simply not found in the combined run (run-to-run
variance: the combined pipeline contains a reader much like the single agent), a few were lost in the merge or rated
"likely" and moved to the appendix; the merge step was changed after this analysis.

## 2. Problems raised by the real reviewers

From the public reviews of the same 5 papers we kept the problems that are objective in the sense above (for
example an undefined symbol, inconsistent notation, a named typo or a wrong caption), and located each one in the
LaTeX source of the arXiv version that was run, dated before the reviews: 11 problems in total (1, 2, 3, 3 and 2 for papers A to E). A
problem counts as found when an item of the report points at the same place and the same defect (judged by the same
independent model).

| | found |
|---|---:|
| combined checkers | 11 / 11 |
| single agent | 10 / 11 |

The single agent missed one of the two problems of paper E. Eleven problems are few: this shows that the checkers
reach the kind of error reviewers complain about, not a precise recall figure.

## 3. Typos that authors fixed themselves

**Benchmark.** We took papers with two versions on arXiv, compared the LaTeX sources of v1 and v2 word by word, and
kept by hand the edits that fix an objective language error in v1 (agreement, a missing article, preposition or
verb, misspellings, wrong word forms), dropping style changes. This gives a recall measure only: v1 surely contains
other errors that the authors did not fix, so precision cannot be computed this way.

- *Development set*: 35 errors in 5 papers (3 to 11 per paper). The typos checker's checklist was written after
  looking at what earlier versions missed on these papers, so this set is not independent.
- *Held-out set*: 12 errors in 10 other papers, not used to write the checklist.

**Results** (number of author-fixed errors recovered):

| system | development (35) | held-out (12) |
|---|---:|---:|
| two-stage typos checker (high-recall finder, then a verifier) | 32-34, depending on the run | 11 |
| single typos agent (one pass, no verifier) | 26 | 7 |
| single careful-reading agent (whole review, as in section 1) | 19 | not run |

## Limits

- **Development set.** All papers in sections 1 and 2 and the 5 papers of the development typos set were used while
  designing and tuning the checkers. The held-out evaluation (separate OpenReview papers, opened once) is pending.
- **Small numbers.** 5 papers, 11 reviewer problems, 35 + 12 typos; one run per system and paper for sections 1 and
  2, and the typos results vary from run to run (32 to 34).
- **One model family.** The systems and the labelling model are all from one provider (Claude models); the labelling
  model differs from the one that produced the reports, but shares its family. Other agents and models are untested.
- **Labels by a model.** Objective / subjective / false labels were given by a model, not by people.
- **arXiv, not the submission.** The real-paper sets use the arXiv sources, which may differ from the PDF the
  reviewers read.
- **Venue type.** Machine-learning conference papers only; journals and other fields are untested.
- **Version.** Measured before the annotated `changes.pdf` existed; later changes to the prompts are not re-measured.
