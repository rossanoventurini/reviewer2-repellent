# @string, @comment, @preamble, crossref inheritance, # concatenation
MUST NOT report anything on x1, x2, x4 (own checks). x3 is a @proceedings parent: if a .tex cites only x2, BibTeX pulls x3 in,
but refs_check's cited filter drops it, so RefChecker sees x2 with a dangling crossref (check what it says).
Also: form_check's "inproceedings without booktitle" fires on x2 (booktitle inherited through crossref).
Field parsing: x4's concatenated booktitle ({...} # " " # {...}) is read as the first piece only.
