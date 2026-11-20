# tables: ratio cells and bold
Run: form_check.py main.tex --blind single
MUST report (CHECK):
- Table 1: "1.4x next to 300" not reproducible (true)
- Table 1: bold 100 in Latency is not min/max (80 is min) (true)
- Table 4: 1.5x in "8 (1.5$\times$)" wrong             -> missed: a cell with two numbers is skipped
- Table 1: \bfseries 0.99 bold                           -> missed: only \textbf/\mathbf/\bf are recognised (0.99 IS the max, so no finding either way here)
MUST NOT report:
- Table 1: "1.0x next to 200" (a baseline's own 1.0x: left/left = 1 should be accepted)
- Table 2: ratios against FAISS, not in the table -> flagged by design; acceptable only as CHECK, better: skip when the column header says "vs."
- Table 3: percentages
