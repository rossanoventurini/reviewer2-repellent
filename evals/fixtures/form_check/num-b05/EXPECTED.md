# b05-fraction-pct
- True error: nDCG 1.23 in a [0,1] column -> wanted CHECK "value above 1 in a column of fractions" (research §6.2). Not implemented: nothing fires.
- Trap: abstract "95%" vs table 0.95 -> reported as INFO "not found in any table" (noise); should be matched by ×100 when the table column lies in [0,1] and the text uses %.
