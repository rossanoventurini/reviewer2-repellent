# Pre-submission report: main.tex (WOMCON 2027, full papers)

## 1. Summary

| Section | Items |
|---|---|
| 2. Desk-reject risks | 1 (21) |
| 3. Numbers and claims | 4 (3, 8, 14, 20) |

Fix first:
1. **Item 21**: the PDF author field names a person; anonymous review.
2. **Item 3**: the memory saving is 2.4× in Table 1, not 2.3×.
3. **Item 14**: the figure shows only the small collection.

## 2. Desk-reject risks

**21.** `main.tex:3`: PDF metadata. **[to check]** Severity: desk-reject. Checkers: facts.

## 3. Numbers and claims

**3.** `sections/intro.tex:6`: "$2.3\times$ less memory"; Table 1 gives 2.4. **[to check]** Checkers: numbers.

**8.** `sections/results.tex:21`: 1200/1100 = 1.09, not 1.10. **[to check]** Checkers: numbers.

**14.** `sections/results.tex:28`: caption names one collection. **[to check]** Checkers: reader.

**20.** `sections/results.tex:23`: the speedup is rounded. **[to check]** Checkers: numbers.

## 4. Other reviewer-visible problems

**2.** `sections/intro.tex:4`: "Many system solve". Checkers: reader.

**5.** `sections/intro.tex:11`: number of threads not given. Checkers: reader.

**6.** `sections/intro.tex:10`: QPS defined loosely. Checkers: reader.

**7.** `sections/results.tex:10`: caption does not say what is bold. Checkers: reader.

**9.** `sections/intro.tex:9`: version 1.2 vs 1.3. Checkers: reader.

**10.** `main.tex:8`: title noun number. Checkers: reader.

**11.** `sections/results.tex:8`: floats only at the top. Checkers: reader.

**12.** `main.tex:13`: repetition. **[to check]** Checkers: reader.

**17.** experiment on the large collection missing. Checkers: reader.

**18.** `references.bib:16`: year 2017 for quokka2019. Checkers: reader.

**19.** `references.bib:4`: booktitle without acronym. Checkers: reader.

## 5. Typos and grammar

1. `sections/intro.tex:4 | a old | an old` (typos)
13. `sections/results.tex:5 | and the gap grows with the collection size | delete` (numbers)
16. `sections/results.tex:33 | 0.9 | $0.9$` (typos)

## 7. Appendix: possible language improvements

4. `sections/intro.tex:10 | three encoder | three encoders`
15. `sections/results.tex:23 | resident set size | resident set size (RSS)`

## 9. Questions for the author

- **3**: Is the memory saving 2.3× or 2.4×?
- **8**: Is 1.10 a rounding of an unrounded value?
- **12**: Keep the repetition for emphasis?
- **14**: Does the figure show both collections?
- **20**: Recompute 1.10 from the unrounded data?
- **21**: Should the PDF author field stay empty?
