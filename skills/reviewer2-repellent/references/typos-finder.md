# Typos finder

Stage 1 of 2 of the typos check. Flags every place that might be a typo or a small grammar slip, with high recall;
it does not judge. Stage 2 (`typos-verifier.md`) sees only the flagged sentences and keeps the real errors.
Placeholders: {PAPER}, {FILES}, {CANDIDATES_OUT}.
English only: for a paper in another language, skip both typos stages and say so in the report. For a long paper
(or an agent without subagents), run one finder per chunk of {FILES} (a few files, or about 1500 source lines, each)
with its own {CANDIDATES_OUT} (`work/candidates-1.md`, ...), then concatenate the flag lines into `work/candidates.md`
and merge the `## Coverage` blocks (sum the counts, take the largest `chunk_lines_max`).

---

You are the first stage of a two-stage proofreading of a LaTeX paper. The sources are in {PAPER}; the body is in
{FILES}. Your job is RECALL: flag every place where a word may be misspelled, wrong, missing, extra or in the
wrong form. A second reviewer will check each flag against its sentence and discard the false alarms, so flag
whenever in doubt; a missed error cannot be recovered later, a false alarm costs nothing.

Read the prose in chunks of about 30 source lines, never more than 60: one Read call per chunk with `limit` 30
(offset advancing), never a whole file at once; long blocks make you skim and miss slips. File by file, in reading
order, including the abstract, captions, footnotes, table and figure text (including the text of TikZ nodes,
pgfplots axis labels, titles and legend entries written in the sources), section titles, appendices, related work
and acknowledgements. Skip
math, labels, citation keys, URLs, code and commented-out text. For each chunk, make one pass for each family
below, checking every sentence mechanically, not by reading for meaning.

1. Spelling. Every word that is not an English word or a correctly spelled technical term: swapped, doubled or
   dropped letters ("recieve", "perfomance", "achived"); a name or term spelled differently from elsewhere in the
   paper ("BERT"/"Bert", "pre-train"/"pretrain" is style, but "Transfomer" is a typo).
2. Real-word confusions. Every word that is spelled correctly but may not be the intended one: from/form,
   than/then, that/than, its/it's, their/there/they're, were/where/we're, to/too/two, of/off/or, on/one/in/is/it,
   the/they/then/these, and/an/any/as, with/which/wit, whether/weather, loss/lose/loose, lead/led,
   affect/effect, principal/principle, complement/compliment, quite/quiet, through/though/thorough/trough,
   few/view/new, same/some, now/no/not/know, form/from/for, cause/case, causal/casual, adapt/adopt,
   accept/except, latter/later, rate/rare, fitted/fitter, and any word that a one-letter change would make right.
3. Determiners. For every singular countable noun, check that it has a determiner (a, an, the, this, that, each,
   every, our, its, one, another, no, any) or a possessive. Look especially inside technical noun phrases and after
   prepositions ("we compute loss on validation set", "as shown in previous section", "results of proposed model",
   "when user submits query"). Check a versus an by sound ("a MLP", "an user", "a hour", "an unified"). Check
   "the" in front of names of methods or datasets only when the rest of the paper uses it.
4. Agreement. For every verb, find its subject, even when it is far away, compound, or behind a relative clause
   or a parenthesis ("the accuracy of the two models are", "the encoder and the decoder shares", "each of the
   queries have", "this approach, which the baselines lack, improve"). For every noun, check number against its
   determiner and its numeral ("those sample", "one of the result", "two dataset", "a indexes",
   "much experiments").
5. Verb forms and missing small words. Missing auxiliary ("the index currently rebuilt every hour"), missing or
   wrong preposition after a verb or adjective ("depends the threshold", "consists in two parts", "compared
   than", "focus at"), missing "to" or "that", missing subject ("and then improves the recall" with no subject), wrong form after a
   modal or "to" ("can achieves", "to evaluates", "is consist"), wrong participle ("has proved" is fine,
   "has prove" is not), tense switching inside one passage of the method or the results.
6. Word form. Adjective for adverb and the reverse ("significant faster", "a highly increase"), noun for verb
   ("we analysis", "to proof"), wrong derivation ("informations", "researches" as countable, "equipments",
   "an evidence", "the efficient of").
7. Repeated, extra and leftover words. Doubled words ("the the", "of of"), including across a line break or a
   LaTeX command; two words where one was meant ("a an", "to to"); half-edited sentences where an old and a new
   phrasing coexist; a sentence with no main verb; words left from search-and-replace; unclosed parentheses or
   quotes in prose.
8. Capitalisation and spacing in prose. A capital letter after a comma ("results, We"), a lowercase letter at a
   sentence start, a missing space before a citation or a reference (`word\cite`, `Section\ref`), a missing space
   after a full stop.

Write every flag to {CANDIDATES_OUT}, one per line:
`file:line | the full sentence, verbatim | the suspect words | family number | the suspected fix`.
Quote the whole sentence exactly as in the source (LaTeX commands included), because the second reviewer sees
only that. If two flags fall in the same sentence, write two lines. Do not use any skill named reviewer2-repellent.
Do not open files outside {PAPER}. If you use the web at all, send to the web only bibliographic metadata (titles, identifiers) and the venue's name, never text of the paper. Do not modify the sources. If you cannot write the file, put all the lines in
your reply. Reply with the number of flags.

End {CANDIDATES_OUT}, after the flag lines, with a block for the run statistics: a line `## Coverage` and then one `key: N` line per key below, each N a count of what you actually did in this run (write `key: not counted` when you did not keep count; never estimate). Keys: `chunks_read` (the pieces you read the files in), `chunk_lines_max` (source lines in the largest piece),
`sentences_read`, `flags` (lines written above). A run with `chunk_lines_max` over 60 is rerun.
