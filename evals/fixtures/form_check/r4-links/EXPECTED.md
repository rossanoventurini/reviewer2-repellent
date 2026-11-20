# links: URL forms, dead pages, commented-out URLs, a third-party page naming an author
Run (online): form_check.py main.tex --authors names.txt --blind double --no-widows
MUST report: CHECK broken link for .../this-page-does-not-exist-404 (example.org answers 404).
MUST NOT report: mailto:, ftp://, ./relative (skipped by design), the two commented-out URLs (dead on purpose),
"linked page names an author" for the Faiss repository (a third-party page that happens to mention Douze) -> expected false positive;
Expected false negative: the plain \texttt URL is never checked.
