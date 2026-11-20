# b02-transposed
- A correct table (rows are different metrics; bold = best of its row, direction per metric). Wanted: no CHECK.
- Trap 1: check_trends sees three rows going "up" (80%) and Latency "down" -> false CHECK "row breaks the trend" (rows are different measures; Latency has its own direction).
- Trap 2: check_tables bold rule is per column: column A has one bold (1.5) which is not min/max of {10,30,60,1.5}... it is the min, passes by luck; column B bold 80 = max passes; column C bold 60 is not min/max of {30,60,75,3} -> false CHECK "bold value is not the best of its column"; column D 40 not extreme of {40,55,70,4} -> false CHECK.
- Fix: detect a transposed table (first column labels look like metrics: contain %, @, (ms), 'latency', 'recall'; or header cells are method names) and run bold/trend checks on rows instead of columns, or skip.
