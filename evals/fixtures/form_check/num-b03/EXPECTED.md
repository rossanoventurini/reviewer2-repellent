# b03-pm
- True errors: Ours Avg 80.0 vs mean(92.3,85.0,72.0,63.0)=78.1 -> CHECK average column; bold 92.3 in T1 is not the best (Worse has 92.9) -> CHECK bold; abstract "average of 90.0" is in no table -> INFO.
- Trap: every mean±std cell has two numbers so cell_value returns None: the Avg check sees <2 parts and stays silent, the bold check sees no numeric column, and the abstract's 92.3 is reported as "not found in any table" (false INFO). Four spellings of ±: $\pm$, ± (unicode), \textsubscript{0.3}, $_{\pm 0.4}$.
- Fix: in cell_value, strip "\pm|±" and what follows, \textsubscript{...}, _{...}, ^{...}, \scriptsize... trailing groups, and "(...)" deltas, then take the first number as the value.
