# arXiv identifiers in every form
MUST report FAIL: a6 (ID does not exist), a7 (ID is "Attention Is All You Need", not BERT).
MUST report CHECK "published version exists": a8 (TPAMI 2020), a9 (ICLR 2013 workshop, if DBLP lists it).
MUST NOT report: a1 (old-style id in eprint), a3, a4, a5, a9.
Expected bugs: a1 -> FAIL "does not exist" (arxiv_titles() keys the API answer by the last path component, "0112017v1",
so old-style ids never match); a2 old-style id in the journal field is not recognised (regex wants NNNN.NNNNN);
a9/a10 DBLP exports put the id in volume={abs/...}: not read, so a10's wrong id is missed and a9 is not even checked.
