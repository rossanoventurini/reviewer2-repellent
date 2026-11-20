# b08-labels
- True error: NQ/SPLADE R@10 60.0 (tab:a) vs 61.0 (tab:b) -> wanted CHECK "same row and column in two tables".
- Trap 1: the method is in the second column of tab:a (first is a \multirow dataset); row keys come from column 1 only -> no common labels -> missed.
- Trap 2: cell_value("SPLADE~\cite{formal2021}") = 2021 (digits inside \cite), so even in tab:b the row is excluded from keyed() ("not cell_value(r[0])[0]").
- Trap 3: "GPT-4 reranker" in a label column yields 4 as a number; in trend/arith checks over r[1:] it enters the series.
- Fix: strip \cite/\ref/\multirow{n}{*}{} before counting numbers; key rows by (group label from the multirow or \multicolumn group row, method label); when column 1 is empty or a multirow, use the first non-numeric cell as the label.
