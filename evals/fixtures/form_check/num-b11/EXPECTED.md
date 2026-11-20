# b11-precision
- Both tables agree after rounding. Wanted: INFO/CHECK "same value printed with different precision in two tables" (research K), not CHECK "different values" with the same wording as a real inconsistency.
- Trap: 92.34 vs 92.3 and 80.12 vs 80.1 are reported as "same row and column in two tables, different values" (two CHECK lines) with the hint "the same experiment must have the same number; explain or fix".
- Trap 2: "Gain (%)" is a relative improvement; 150 is legitimate -> false CHECK "percentage above 100". Exclude headers with gain|improvement|increase|Δ|rel|speedup|overhead.
