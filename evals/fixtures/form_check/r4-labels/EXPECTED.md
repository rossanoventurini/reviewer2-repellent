# labels: subcaptions, \label inside \caption, cleveref, \tag in align*, \nonumber in align, \section* proof
Run: form_check.py main.tex --blind single --offline --no-widows
MUST report: FAIL \label before \caption for fig:early (figure*); CHECK reference to its own section for sec:details (\cref) and sec:intro.
MUST NOT report: fig:a (a subfigure label before its subcaption), fig:pair (label inside \caption);
FAIL "\ref to a label in an unnumbered display" for eq:tagged (align* with \tag is numbered) -> expected false positive;
CHECK "unnumbered section" for "Proof of Theorem 1" -> expected false positive (add proof|abstract|keywords to UNNUMBERED_OK).
Expected false negative: eq:nonumber (a \nonumber line inside align: the reference prints the next equation's number).
