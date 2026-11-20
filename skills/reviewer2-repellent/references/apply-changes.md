# Step 6 in detail: corrected copy and annotated PDF

Read this file when step 6 starts (SKILL.md keeps the summary and the table of kinds). `<out>` is the output folder,
`<work>` = `<out>/work`, and `<flags>` the line of `<work>/build-flags.txt` written in step 1 (`--root ... --engine ...`).

You (or one subagent per group of items, for a long report) write three or four files; one script builds everything
else. By default apply **every item** of the report, marked by how sure it is; the user can instead name items
("only 3, 7, 12") or exclude groups ("no appendix").

## 1. `work/edits.json`

Format in the header of `<skill>/scripts/apply_edits.py`: one entry per change, with its item number, file, the old
and new text and a context that occurs once in the file. The kind of each entry follows the table in SKILL.md.

**Nothing invented.** The `new` text of fix, check, style and raw entries may only contain numbers, terms and claims
that are in the paper or computed from it (put the computation in the note or question). Causal explanations and
mechanisms go in the `question`, never in `new`. `apply_edits.py` warns about each term, number or causal clause not
found in the paper: resolve every warning, or say why it stands.

**Placeholders** (`missing`) only for textual fixes; a submission file (highlights, declarations, cover letter,
supplementary material as separate files) is a `note` with a `question`. A question that only asks about a rounding
difference is not a question: make the item's edits `log` ("not applied: within rounding of the printed values");
`report_sync.py` drops such questions from section 9.

**Confidence.** Give every applied entry (`fix`, `check`, `style`, `raw`) a `confidence`: `high` for certain items,
`medium` for [to check] items, `low` when the report itself doubts the fix ("keep X if you prefer", an alternative
that is as good) and for optional wording. Each item gets one check box in `changes.pdf` ("do it" / "don't"),
pre-set from it: fix and raw ticked, check ticked unless low, style unticked, any low unticked; an item with any
`missing` entry ("your facts") gets a disabled box with its own glyph, never ticked, and none of its changes goes to
`corrected/` until the facts are given (its `% TODO #n` comments are written). `corrected/` holds exactly the ticked items (the defaults, or the author's
choices: section 9).

**Notes.** Give a `note` to every harder item (numbers and claims, [to check] items, cross-references, anything whose
fix is not obvious from the change itself) and use `plain: true` inside math, tables, captions and titles. A note
must be understood without the report: what was wrong, the evidence (the computation, the cells or sentences compared
with their location, the rule or the record), and what was changed; up to about 60 words, ending with "see report
#n" when the report says more. Give every note a `note_short` too: at most 25 words, what was wrong and the change, no
fact the note does not have. On a crowded page (a box pushed more than about 1.5 lines off its line) the build prints
the short text instead, followed by "See report #n" (and "To check." for items with a question; the decision sheet
keeps the question); `apply_edits.py` warns about notes over 60 words and notes over 30 words without `note_short`.
The note of a `raw` edit goes at the start of its text (the first sentence of its first paragraph, e.g. a moved
block): give `note_ctx` to put it elsewhere. The script adds the `file:line` of the change in `corrected/` to each
note. Notes, questions and `what` are prose: inline formatting (`\emph`, `\textbf`, `\texttt`), `\ref`, `\cite`,
`\url`, math in `$...$` and the paper's own macros are fine; structural commands (`\verb`, `\label`, `\footnote`,
`\item`, `\caption`, `\section`, environments) and commands the paper does not use are an error naming the item.
Text in a TikZ node works with every kind; when the `old` or `new` text holds a line break (`\\`, e.g. a multi-line
node), the script marks it line by line without the struck old text (a warning), so `raw` is not needed there.

**Rules.** Minimal edits in the author's style. Never invent a number, a result, a citation or a fact about the
method: the applied text of a `check` entry only restates what the paper already says (its numbers, its terms), and
any explanation goes in the margin question; what needs the authors' facts is `missing`. When an item offers
alternatives, apply the first and put the others in the question.

**Bibliography.** Edit the `.bib` in the same spec, one entry per changed bib entry with its item (`fix`, `check` or
`raw`, no `note`): both copies get the corrected `.bib`. The marks in `changes.pdf` come from the `.bbl` and need
BibTeX (a `thebibliography` list in the `.bbl`). With biblatex (biber) the corrected `.bib` still goes to
`corrected/`, but the printed bibliography of `changes.pdf` is not marked (the build warns): the bibliography
changes are listed in `edits.md` and shown by the `.bib` diff; tell the user so at the handover.

## 2. `work/tmp/bbl-map.json`

Only if the bibliography changes and the paper uses BibTeX (format in `<skill>/scripts/mark_bbl.py`): which item
each changed, new or removed entry belongs to, the `items` an entry carries, one note per item and one short note per
item (`notes_short`). A note whose item changes nothing the `.bbl` shows (e.g. uncited entries deleted) goes at an
entry listed for it in `items`, else before the first entry.

## 3. `work/venue-status.json`

Format in `<skill>/scripts/front_pages.py`: one row per rule of `venue.md` that you judged, with a verbatim `quote`
of it, its source status and URL as in `venue.md`, your status (`met`, `violated`, `confirm`, `unknown`: `unknown`
whenever the sources do not tell), the related items and one line on this paper; and the live pages that could not
be read (`blocked`, each URL as written in `venue.md`). The script checks quotes and URLs against `venue.md` and
judges nothing. When the venue research failed (SKILL.md, step 1) the file is `{"rules": [], "blocked": [...]}`.

## 4. `work/ai-traces.json` (the "Traces of AI use" page)

`python3 <skill>/scripts/ai_traces.py <out> [--root <root>]` gathers the objective artifacts from `facts.txt`,
`report.md` and `venue.md` (each linked to its items), measures the style signals and finds the paper's LLM-use
statement (format, and the definition of strong evidence, in its header; `--json PATH` writes elsewhere). Then add to
the file: `assessment` (at most 80 words), `disclosure.venue_rule` (one sentence) with `venue_quote` (verbatim from
`venue.md`) and `advice`, and a `note` on any artifact whose automatic line misleads. Write `suggestion` (a statement
in the venue's place and wording, e.g. "We used <tool> to edit the language of Sections X-Y; the authors reviewed
and take full responsibility for the content.") only when `evidence.strong` is true, as the authors' choice if it
matches what they did. You may lower `evidence.strong` with a `why`, never raise it. Never call the paper
AI-written, never count a style signal as evidence, never suggest hiding, softening or removing AI use or its
disclosure. The venue panel comes from `<skill>/references/ai-venue-actions.md` (dated: update it there).

## 5. Build

`python3 <skill>/scripts/build_changes.py <out> <flags> --open` (a few minutes; longer for a long paper). The output
folder must be where the user will find the files: a temporary or scratch folder fails the build unless
`--final-dir <the real output folder>` names it (the summary's "Apply my choices in <path>" uses it). `--strict`
makes the "nothing invented" warnings errors. It runs
`apply_edits.py` (or lists every problem in the spec and writes nothing: fix and rerun), compiles the original and
`corrected/` in `work/tmp/`, marks the `.bbl` word by word, rewrites the counts of section 1 of `report.md` from the
log (`report_sync.py`), adds the front pages (summary, venue rules, bibliography, decisions for you, what we checked,
traces of AI use: page order, content, data files and rules in `<skill>/references/pdf-layout.md`; it rewrites
`work/checks.json` with `check_stats.py` and `work/bib-status.json` with `bib_status.py`, every count from a file of
the run or the sources), fits each front page to its height, compiles `work/marked/` until the note positions are
stable, switches the notes of crowded pages to their short text and rebuilds (at most twice), fails if a margin box
is off the page of its note, checks every link of the PDF (`pdf_links.py`), and writes `changes.pdf` and `edits.md`. Its last step prints "9/9 consistency ... OK: build <id> in all four":
`report.md`, `changes.pdf`, `edits.md` and `corrected/` come from that one run and carry the same build id (`Build:`
line in `report.md` and `edits.md`, page 1 of `changes.pdf`, `corrected/.reviewer2-build`). Never hand over outputs of
different runs; if the build fails at 9/9, fix what it lists and rerun.
Read its output: a page-count change or new overfull boxes between the original and `corrected/` are side effects of
a fix (a class or font switch, a longer caption): fix what you caused, or say it.

## 6. Look

Open the images it lists in `work/tmp/pages/` (front pages and the most crowded pages): every note readable next to
its line, every front page full (the build prints each page's fill; under 80% or overflowing is a warning) and as
`pdf-layout.md` describes it. A page that stays crowded after the short notes usually has several notes at one
place: spread them with `note_ctx` and rebuild.

## 7. Update the report

Keep the first version as `work/report-before-fixes.md` (copy it once). Then make every item of `report.md` say what
step 6 established, in an `*In the copy:*` line (applied / to confirm / missing facts / not applied and why), move
answered questions out of section 9, and rerun `ai_traces.py` and `build_changes.py` so the front pages and
`edits.md` follow the report. The build rewrites the "In the corrected copy" counts of section 1 from the log and
replaces names of earlier builds (`changes-v3.pdf`) with `changes.pdf`; it warns about every `*In the copy:*` line
that disagrees with the log: fix those lines.

## 8. Handover

`--open` opened `changes.pdf` in the system viewer (`open` on macOS, `xdg-open` on Linux, `start ""` on Windows; in a
headless or remote session it only prints the path). Tell the user where it is, what the colours mean, how many
items fall in each group (the summary page), and where `corrected/`, `changes.pdf` and `edits.md` are (with biblatex:
that the bibliography changes are in `edits.md`, not marked in the PDF). The author ticks or unticks the box of each
change in `changes.pdf` (the summary's "How to apply the changes"), saves the PDF, and asks for the choices to be
applied, in this session or a new one. Answers in words (the questions of section 9) are typed in the text box under
each question on the "Decisions for you" page and saved with the PDF; the chat works too.

## 9. Apply the author's choices ("apply my choices in changes.pdf")

This works in a new session too: nothing but the output folder is needed.

1. **Find the output folder.** If the user gives the path of the saved PDF, its folder is `<out>` when it holds
   `work/`. Otherwise look for `reviewer2-repellent/<YYYY-MM-DD>[-n]/changes.pdf` under the paper's folder (the
   current directory or the one the user names) and take the newest; ask when several papers or folders qualify.
   A PDF saved elsewhere (e.g. Downloads) is read from there, with `<out>` found as above.
2. `python3 <skill>/scripts/read_choices.py <saved changes.pdf> --out <work>/choices.json --defaults
   <work>/marked/r2states.tex` writes each item's choice (do or don't, and whether it differs from the pre-set) and
   the typed answers (`"answers"`, item -> text). Viewer saves with incremental updates and object streams are read.
   **Answered questions** (typed or in the chat): copy each answer verbatim under its item in `report.md`
   (`*Author:* ...`), move the question out of section 9, then apply what it settles in `work/edits.json` and drop
   the entries' `question` (the rebuilt PDF asks no more):
   - confirms the applied text: the `check` entry becomes `fix` (confidence `high`);
   - picks the other alternative or gives the right value: the entry becomes `fix` (confidence `high`) with that
     `new` (the author's fact: a "not in the paper" warning is expected);
   - gives the facts of a `missing` entry: it becomes a `fix` with them;
   - "keep as is" / "no": the item's edits become `log` ("not applied: author's answer");
   - unclear: leave the item as it is and quote the answer to the user.
   Set `items["n"].choice` in `choices.json` to match (`do` for a new fix, also a former facts item; `dont` for a
   log), since the build follows it; tell the user what each answer changed.
3. `python3 <skill>/scripts/build_changes.py <out> <flags> --choices <work>/choices.json --open` rebuilds
   `corrected/` with exactly the chosen items (all edits of an item together; `% TODO #n` comments always kept) and
   `changes.pdf` with the boxes as chosen. Without `work/build-flags.txt` (an older run), detect the engine and root
   again as in step 1 of SKILL.md.
4. Tell the user which items changed from the pre-set and that `corrected/` now holds exactly the ticked set; they
   copy it over their sources (it never includes the output folder).
