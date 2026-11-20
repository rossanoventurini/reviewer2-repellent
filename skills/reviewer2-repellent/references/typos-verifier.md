# Typos verifier

Stage 2 of 2 of the typos check. Judges each flag of `typos-finder.md` against its sentence (and the source line if
needed), keeps the objective errors and marks each one `certain` or `likely`. Placeholders: {PAPER},
{CANDIDATES_IN}, {REPORT}. English only, like the finder. When the finder ran in chunks, give the verifier the
concatenated `work/candidates.md` (or one verifier per chunk, concatenating their reports into `work/typos.md`).

---

You are the second stage of a two-stage proofreading of a LaTeX paper. The first stage flagged, with high recall,
every place that might be a typo or a small grammar slip; many flags are false alarms. {CANDIDATES_IN} lists them,
one per line: `file:line | sentence | suspect words | family | suspected fix`.

For each flag, decide whether the flagged words contain an error that a careful native-speaker copy editor of a
research paper would correct. Judge each flag on its own: a sentence can contain several errors, and a flag is not
answered by another flag in the same sentence. Judge the sentence as written; the suspected fix is only a hint,
and the real error may be a different word in the same place. When the sentence alone is not enough (a subject in
the previous sentence, a term defined elsewhere, a LaTeX macro whose text you need), open the source file in
{PAPER} and read the lines around the flagged one; do not read the rest of the paper.

Keep:
- misspellings, wrong real words (including e.g./i.e., affect/effect and similar), doubled or leftover words,
  missing words that make the sentence ungrammatical (a missing verb, auxiliary, preposition, "to", "that",
  subject);
- a missing determiner before a singular countable noun used without any determiner, possessive or numeral. This
  includes technical terms used as common nouns ("such as CNN or RNN", "the threat model of white-box attacker",
  "we fine-tune encoder", "reduces to single-vector model") and nouns followed by an of-phrase or a relative clause that
  makes them specific ("estimating variance of the estimator", "size of index"); and fixed phrases that require the
  article ("on the other hand", "the state of the art", "at the same time", "in the long run");
- a/an against the sound of the next word;
- subject–verb and determiner–noun disagreement, a noun whose number disagrees with its determiner or numeral,
  a wrong verb form after a modal, "to" or an auxiliary;
- a wrong word form: adjective for adverb, noun for adjective ("high-dimension vectors"), noun for verb, an
  uncountable noun made plural ("informations", "researches", "softwares");
- a preposition that the verb or adjective does not take, when the standard one is clear ("lies on a subspace" for "in",
  "robust against changes of" vs "to", "consists in" for parts, "depends the");
- a capital after a comma, a lowercase sentence start, a missing space that shows in print.

Drop only what is clearly acceptable as written:
- style and wording preferences, register, sentence length, passive voice, word choice that is merely unusual,
  prepositions where both choices are standard ("replace by/with", "correlated to/with");
- articles that are truly optional: before plural or mass nouns used generically, before proper names of specific
  methods, datasets, metrics or systems (D2D-FR, MS MARCO, NDCG), in headings, table cells, captions written as
  noun phrases, and list items;
- British versus American spelling and hyphenation variants used consistently; hyphenation of compound modifiers;
- punctuation choices (serial comma, comma before "which"); mathematical notation; anything inside math or source
  code. Text in verbatim or lstlisting blocks that is prose printed in the paper (a prompt, an example message) is
  checked like any other prose, and so is the text of TikZ nodes and pgfplots labels and legends;
- meaning or content problems that are not language errors (a wrong figure reference, a wrong number): drop them
  here, another check covers them.

When in doubt, keep: a kept false alarm costs the author a few seconds, a dropped error stays in the paper.

For every kept error, give a confidence:
- `certain`: any copy editor would change it and you can name the rule. This includes:
  misspellings; wrong real words; doubled or leftover words; subject–verb and determiner–noun disagreement; a wrong
  verb form; a/an; a missing word that breaks the grammar (a missing verb, auxiliary, subject, "of", "with", "to");
  an uncountable noun made plural; a capital after a comma; punctuation that shows in print (two full stops, a
  missing final full stop, a missing space);
  a missing determiner before a singular countable noun, also when the noun is a technical term or the name of a
  specific set, component, dataset split or tool used as a common noun ("Encoder architecture has", "on the test
  set" written "on test set", "with Adam optimizer", "the size of hidden layer", "at highest level");
  a bare singular acronym or term used as a countable noun ("behaves like CNN", "compared to GNN", "unlike
  transformer model");
  a wrong word form or derivation ("the evaluated metric" for "evaluation metric", "the overlapping between" for
  "the overlap between", "a sorting list" for "a sorted list");
  a standard idiom used with the wrong word ("in inference time" for "at inference time", "on the other side" for
  "on the other hand"); a finite verb where a label or description needs a participle or relative clause
  ("Dataset A: contains 10K users" is fine as a fragment, "Two datasets contain reviews" introducing a list of
  descriptions is not);
- `likely`: a correction is reasonable but a careful writer could defend the original: an optional article before
  a mass or abstract noun or a symbol-named object ("loss $L$ is", "input sequence $x$"), a preposition where both
  choices are used, a noun number that both readings allow, a dangling modifier, a comma splice, tense choice in
  related work, "such as" versus "like", a spelling or name used inconsistently, word choice at the border of style.

Write the kept errors to {REPORT}, one per line: `file:line | wrong text (a few words around it) | fix | rule |
certain|likely`, all `certain` lines first, then the `likely` lines grouped by rule.
If you use the web at all, send to the web only bibliographic metadata (titles, identifiers) and the venue's name, never text of the paper. Do not use any skill named reviewer2-repellent. Do not modify the sources. If you cannot write the file, put the
lines in your reply. Reply with the number of flags read and the number kept, certain and likely.

End {REPORT}, after the error lines, with a block for the run statistics: a line `## Coverage` and then one `key: N` line per key below, each N a count of what you actually did in this run (write `key: not counted` when you did not keep count; never estimate). Keys: `flags_judged` (flag lines of {CANDIDATES_IN}; its own Coverage block is not a flag), `kept_certain`, `kept_likely`, `dropped`.
