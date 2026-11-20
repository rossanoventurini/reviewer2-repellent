# biblatex field names (date, journaltitle, eprinttype, @online/@software/@dataset/@thesis)
MUST report FAIL: b6 (arXiv ID points to another paper).
MUST report CHECK "published version exists": b2 (HNSW, TPAMI 2020).
MUST NOT report: b1, b3, b5.
Expected bugs: b2 is not seen as a preprint (is_preprint() reads journal, not journaltitle) and its id sits in volume;
b4 wrong title on a DataCite DOI is missed (see corporate-datasets).
