# refs_check toy set (synthetic, network needed)

`python3 skills/reviewer2-repellent/scripts/refs_check.py evals/fixtures/refs_check/toy.bib`

R1-R5 are real works (R3 BERT cited as an arXiv preprint; R4 a 1999 tech report). C1-C5 are corrupted.
MUST report: C1 likely fabricated; C2 wrong authors; C3 DOI points to another work (FAIL); C4 year/venue
(2015, ICLR); C5 arXiv ID does not exist (FAIL); R3 published version exists (NAACL 2019).
MUST NOT report an error on R1, R2, R4, R5. With --no-refchecker only the FAIL lines and the published versions appear.
Result on 2026-11-07 (RefChecker 3.1.11 + local DBLP): all of the above, no error on R1-R5.
