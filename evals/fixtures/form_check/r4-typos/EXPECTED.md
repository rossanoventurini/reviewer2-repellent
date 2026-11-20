# typos: legit words in CLASSIC_TYPOS, doubled-word traps, compounds, citation usage, leftover words
Run: form_check.py main.tex --blind single --offline --no-widows
MUST report: CHECK doubled word "in in 2020"; CHECK compound pre-trained/pretrained; CHECK \citet inside parentheses; CHECK \citep as subject.
MUST NOT report: doubled word for "in in-memory", "on on-device", "data data-driven" (hyphenated compounds) -> expected false positives (regex \b stops before the hyphen);
"probable misspelling" for therefor, wether, supercede, publically (real words) -> expected, acceptable only as CHECK;
"submission-status text" for "confidential data" and "under review in our corpus" -> expected false positives;
INFO "numeric citation as subject" for "\cite{c} shows" in an author-year paper (\cite = \citet there) -> expected noise.
Expected false negatives: "multi vector" vs "multi-vector" (space form not covered); re-rank/rerank (length < 8).
