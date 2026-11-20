# b09-negatives
- True errors: tab:b row "w/o reg" lost its minus signs (3.2 vs -3.2) -> wanted CHECK "same row and column in two tables"; bold on -5.0 in tab:a column T1 is the worst, not the largest gain -> wanted CHECK bold.
- Trap: cell_value's regex has no sign: -3.2 and 3.2 are both 3.2. So the cross-table check sees equal values (missed); the Avg of row "w/o reg" is checked as mean(3.2,1.2,2.0)=2.13 vs 2.1 (passes by luck, but any correct signed average would be flagged as wrong); bold -5.0 reads as 5.0 = max -> passes.
- Text: "$-3.2$" is never matched against the table (lookbehind refuses a leading "-").
- Fix: parse the sign ("-", "$-$", "−", "--", "\minus"), in cells and in the text.
