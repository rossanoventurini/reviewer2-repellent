# source-hygiene: Markdown, Unicode, invisible characters, comments that mention LLMs (invented text)

Must report (form_check.py --facts): `**very fast**`, the backtick code quote, `## Results`, the `[text](url)` link and
the two `- ` bullet lines (FAIL, Markdown in the text); `×` typed in text while `$n \times d$` is used in math (FAIL,
text font vs math font); the spaced Unicode em dashes next to unspaced `---` (FAIL, inconsistent); the zero-width
space (FAIL); the straight double quotes (FAIL, opening quote prints as a closing one); the non-breaking space and the
`≤` declared with `\DeclareUnicodeCharacter` (CHECK); the two comments naming ChatGPT / an LLM (CHECK).

Must not report: `\section*`, `$a * b$`, `$x \le y$`, `` `quoted text' ``, ``` ``double quotes'' ```, the authors'
apostrophe, unspaced `---` alone, `5--10`, a dash inside `\item`, verbatim and `\verb` content, `-` cells in a tabular.
The compile errors (the `#` heading, `_` and U+200B under pdfLaTeX) are intended: they are what such pastes do.
