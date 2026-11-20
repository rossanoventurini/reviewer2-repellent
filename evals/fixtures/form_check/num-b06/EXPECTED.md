# b06-avg-traps
- Both tables are correct. Wanted: no CHECK (at most INFO "mean column is a geometric mean per caption").
- Trap 1: Avg column: parts = every numeric cell left of Avg, including Params -> false CHECK on every row (mean of 110,70,80,60 = 80 ≠ 70).
- Trap 2: second Average row averages all rows above, including the first group and the first Average row -> false CHECK.
- Trap 3: the caption says geometric mean; rows A and C are flagged as "average column does not match" (arith mean 7 vs 4). Should try the geometric and harmonic means (and a weighted mean if a count column exists) before flagging, and honour "geometric|harmonic|weighted|macro|micro" in the caption or header.
