# What computer science venues do about AI use

Data for the "What venues do now" panel of the "Traces of AI use" page (front_pages.py reads it; edit this file, not
the code). Every line is a published venue decision or policy, with its source URL. Update the date below whenever a
line changes.

As of: 2026-11-10

## Actions

One line per action: `- <when> | <venue> | <what it did, one sentence> | <source URL>`. At most six lines.

- 2025-11 | ICLR 2026 | Desk-rejects extensive undisclosed LLM use, but only when an AC or SAC finds concrete evidence, because detection tools give false positives. | https://blog.iclr.cc/2025/11/19/iclr-2026-response-to-llm-generated-papers-and-reviews/
- 2026-03 | ICLR 2026 | Desk-rejected every paper with confirmed hallucinated references, with an appeal channel for checker false positives. | https://blog.iclr.cc/2026/03/31/a-retrospective-on-the-iclr-2026-review-process/
- 2026-03 | ICML 2026 | Desk-rejected 497 papers (about 2%) of reciprocal reviewers caught by hidden watermark instructions; every case was verified by hand and no generic AI detector was used. | https://blog.icml.cc/2026/03/18/on-violations-of-llm-review-policies/
- 2027 | CVPR 2027 | Rejects papers that lack an LLM Usage Statement. | https://cvpr.thecvf.com/Conferences/2027/AuthorGuidelines
- current | ARR (ACL) | Submissions with hidden prompts "should be desk rejected". | https://aclrollingreview.org/reviewerguidelines
- 2025 | NeurIPS 2025 | Authors answer for every reference: unverified LLM-generated references are a violation that can revoke publication. | https://neurips.cc/Conferences/2025/LLM

## Closing line

- No venue policy found mentions bullets, em dashes, bold or layout.

## Baselines

Reference points for the style signals, one line per signal: `- <signal id> | <text> | calibrated: yes|no | <URL>`.
Signal ids: em_dash, excess_words, participle_tails, bold_runins, items, boxes, checkmark_tables. "calibrated: no"
means the numbers do not come from computer science papers measured before and after 2022, so the page still says that
no calibrated baseline exists.

- em_dash | human essays 0.33-17.12 per 1,000 words (Freeburg, 8 essays, not papers) | calibrated: no | https://arxiv.org/html/2603.27006v1
