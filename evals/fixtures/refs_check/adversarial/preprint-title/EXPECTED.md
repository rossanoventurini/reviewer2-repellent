# preprints with a published version
MUST report CHECK "published version exists": p2 (TPAMI 2020), p3 (NAACL 2019).
MUST NOT report: p4 (no published version known), p5 (already the published version).
Expected false negative: p1 (SPLADE v2 was published at SIGIR 2022 under another title): the DBLP lookup is by exact
normalized title. RefChecker or an arXiv "journal-ref"/DOI lookup (arXiv API returns <arxiv:doi> and <arxiv:journal_ref>
when the authors set them) would catch part of these at zero extra cost: the arXiv feed is already fetched.
