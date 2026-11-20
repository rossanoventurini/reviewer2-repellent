# b01-multicol
- Table b repeats D2 of table a. True error: Ours/QPS 2,500 (a) vs 2,600 (b). Wanted: CHECK "same row and column in two tables" on Ours/QPS 2,500 vs 2,600.
- Trap 1: header[-1] has R@10 twice; c2.index(col) picks D1's column -> false CHECK "Base / r@10: 80.1 vs 70.5" and "Ours / r@10: 85.2 vs 75.0", and the D1 QPS (1,000) is compared with the D2 QPS of table b (2,000): false CHECK; the true 2,500 vs 2,600 is never compared.
- Trap 2: row Third has \multicolumn{2}{c}{OOM}: its 2,100 is in source column 4 but printed column 5. Column indices should be expanded by the multicolumn span.
