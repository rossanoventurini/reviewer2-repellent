# b04-units-cells
- True errors: text 1.6M params vs table 1.5M (digit error) -> wanted CHECK; text \SI{640}{\milli\second} vs table in µs -> wanted CHECK "unit differs"; text 1e-4 vs table 1e-3 for Ours -> wanted CHECK/INFO.
- Trap: "1.6M" and "800k" are never matched (the text regex refuses a number followed by a letter; the cell gives 1.5, not 1.5e6); \SI{640}{\milli\second} loses its unit (norm_tex_numbers does not know siunitx); 1e-3, $10^{-3}$ and $3\times10^{-4}$ give None in cells and are skipped in the text (two-numbers rule / lookbehind on "-").
- \num{1.5e3} -> None; \qty{900}{\micro\second} parses as 900 but the unit is lost.
- Fix: parse K/M/B/G suffixes (×1e3/1e6/1e9), e-notation and 10^{n}, \num/\SI/\qty/\si units -> canonical unit in the table index and in the text.
