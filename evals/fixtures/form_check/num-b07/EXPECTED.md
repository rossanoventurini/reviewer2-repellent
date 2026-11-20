# b07-headers
- True error: Ours/Memory 14.0 (tab:a) vs 14.5 (tab:b) -> wanted CHECK "same row and column in two tables".
- Trap 1: \makecell{Latency\\(ms)} contains \\, so table_index splits the header into fragments; header[-1] of tab:a is "(ms)} & \makecell{Memory" -> column labels never match "memory (gb)" -> the error is missed (only INFO "tables report the same systems").
- Trap 2: third table: non-booktabs and the header row is mostly numeric (90, 95, 99) -> taken as a data row "system: 90, 95, 99"; header empty. Check whether it leaks into trend/arith checks.
