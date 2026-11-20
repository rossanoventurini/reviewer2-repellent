# names-acronyms
Run: form_check.py main.tex --blind single
MUST report (CHECK):
- ANN used (line 3) before its definition (line 4)       -> missed: only "never defined" is reported
- Qlr-Hnsw x3 vs QLR-HNSW x2                              -> expected to pass
- MS MARCO x2 vs MSMARCO x2 (two-word name)                -> missed: tokens are single words
MUST NOT report:
- HTTP, NDCG, MRR, RAM, MIPS (defined in a footnote), CP (defined as "(CP, $\alpha$)"), EE ("(EE; ..."), PQ (acronym-first definition), HNSW (a \texttt code identifier)
  -> expected false positives: HTTP, NDCG, MRR, CP, EE, PQ, HNSW
- "Dpr x3 vs DPR x1" (Dpr exists only inside \textsc, which prints DPR)  -> expected false positive
