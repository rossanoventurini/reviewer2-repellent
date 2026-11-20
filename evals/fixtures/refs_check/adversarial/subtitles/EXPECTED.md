# subtitles: title similarity against Crossref
MUST NOT report: s1, s2 (subtitle added: containment 0.9 passes).
MUST report FAIL "DOI points to another work": s5 (the book title with a chapter DOI).
Expected weaknesses: s3 "Data Banks" and s4 "Deep Learning" pass, because any two words contained in the real title give 0.9
(similar(): containment is computed on min(|A|,|B|) >= 2). A wrong-but-overlapping title is never caught.
