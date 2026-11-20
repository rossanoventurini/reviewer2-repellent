# Layout of changes.pdf

`changes.pdf` is the annotated copy of step 6: a few front pages, then the paper with every change marked. The front
pages are written by `scripts/front_pages.py` (LaTeX in `work/marked/rrfront.tex`, typeset with
`assets/r2changes.sty`) and built by `scripts/build_changes.py`. This file is the specification: the scripts follow
it and check it. Change the layout here first, then in the code and in `evals/tests/test_step6.py`.

## Page order

| Page | Id (log) | Title | When |
|---|---|---|---|
| i | `cover` | the paper's title (the summary) | always |
| ii | `venue` (`venue-2`) | Venue rules --- Avoid Desk Reject | `work/venue-status.json` has at least one rule |
| iii | `bib`, `bib-2`, ... | Bibliography --- Avoid Easy Reject for Wrong References | `work/bib-status.json` exists (build_changes.py writes it) |
| iv | `decisions-1`, `-2`, ... | Decisions for you | at least one item to confirm, check or complete |
| v | `checks` (`checks-2`) | What we checked | `work/checks.json` exists (build_changes.py writes it) |
| vi | `ai` | Traces of AI use --- Avoid 'written by ChatGPT' | `work/ai-traces.json` exists |
| 1 | | the paper | always; numbered from 1 again, colour legend in the margin of its first page |

Why this order (the user's): the summary; the venue rules first because a violation is a desk reject; the
bibliography next because wrong references are the easiest reject; then the author's to-do list; then the evidence of
depth; then the traces of AI use.

Front pages are numbered i, ii, ...; a page that has no data is left out and the next one moves up. Every front
page is one page, except "Venue rules" and "What we checked" (two pages when one overflows even at level 0), the
bibliography (as many pages as its rows need, each filled in turn) and "Decisions for you" (30 rows per page at most,
balanced). A second page repeats the frame and continues under "<Title> (continued)", "page k of n".

**Avoid subtitles.** Every check title says the reviewer pretext it prevents (`AVOID` in front_pages.py), the same
on the page titles, in the categories of "What we checked" and in the summary: Venue rules --- Avoid Desk Reject;
Bibliography --- Avoid Easy Reject for Wrong References; Build and layout --- Avoid 'formatting violations'; References
and citations --- Avoid 'broken references and citations'; Numbers and claims --- Avoid 'the results do not support
the claims'; Figures and tables --- Avoid 'unreadable figures'; Language --- Avoid 'the paper needs careful
proofreading'; Notation --- Avoid 'undefined notation, hard to follow'; Leftovers --- Avoid 'the authors did not even
reread it'; Traces of AI use --- Avoid 'written by ChatGPT'.

## Pages

Every page has the same frame: the dark top band; the navigation line (every front page by its short name, the
current one in ink, the others links, then PAPER, a link to page 1 of the paper) with the build date, the build id
(the same in report.md, edits.md and corrected/.reviewer2-build) and "prepared by reviewer2-repellent" on the right;
the title (18pt) and one intro line saying what the page is, in plain words: no script, file or tool names
(`work/...`, `.py`, "pdftocairo copy", "the verifier kept ..."), no internals of the run. Each page carries the anchor `rr-<page>` and the label `rrF-rr-<page>` (its page number for the links of
the summary). Sections are listed top to bottom; a section whose data is empty is left out. Body text of the table
pages is at least 8pt.

### i. Summary (`cover`)
Purpose: the page the author reads first. The apply box with its strip is on every level and for every paper; the
rest shrinks around it.
1. "PRE-SUBMISSION CHECK · ANNOTATED COPY", the title, authors, target venue; the logo (`assets/r2logo.png`, 74bp)
   at the top right, beside them.
2. **Readiness**: one line from the data: "Not ready yet: N desk-reject risks open in the copy (#items); M
   decisions for you (p.)", or "Ready once you review the ticked changes". Only real desk-reject risks count: items
   of severity desk-reject not fixed in the copy (and violated rules with no item). When `venue-status.json` has no
   rules, a caveat line: "Venue rules not retrieved: check the page limit, anonymity and template in the call
   yourself."
3. **Headline tiles**, one row: need you and desk-reject risks (items of severity desk-reject) large (orange, red);
   problems found, numbers and claims, fixed in the copy (+ to confirm), boxes pre-set to apply small.
4. **How deep we looked**: one row of six statistics of `work/checks.json` chosen by id (`COVER_STATS`: pages of the
   original PDF, references checked against databases, numbers, sentences, venue rules, independent checkers), the
   link to "What we checked".
5. **Kind bar**: every item once, a segment per kind; the one-line legend (counts add up to the items; "your facts
   (placeholders [#n: ...])"; the items not applied by number).
6. **How to apply the changes** (always): the four cards of the README's "How it works" drawn in TikZ
   (`\rrFcards` in r2changes.sty: 1 Install, 2 Run, 3 Choose --- "this file", changes.pdf --- 4 Apply; no fifth
   step). With the `animate` package one card is lit at a time (about 4.5 s each, looping) in Acrobat and Reader;
   the poster frame, shown by every other viewer and in print, has all four lit. Then two lines: "1. Mark: in this
   PDF, every change has a box: [x] will be applied, [ ] will not. We pre-set them by how sure we are; click to
   change. Save the PDF." and "2. Ask your agent: 'Apply my choices in <absolute path of changes.pdf>'", and the small
   line "The folder corrected/ next to this PDF already holds the pre-set choices". The path is the output folder
   where the user finds the files, never a temporary or scratch folder: `front_pages.py` refuses one, and
   `build_changes.py --final-dir` names the real folder when the build runs in a temporary copy.
7. **Most Important Errors**: every desk-reject and major item, and the minor items of the desk-reject, numbers and
   other reviewer-visible sections, ranked by severity (desk-reject, major, minor; numbers and claims before the
   other sections; then report order; never by item number; optional items left out), as many as the level allows
   ("N of M"; the rest: decision sheet and report.md): box state, linked #n, severity, one line (its section-9
   question, else the first sentence of its text that is not a quotation, LaTeX made readable, never cut), linked
   copy page, kind.
8. **Changes per page of the paper** (from 8 errors on): a strip of the paper's pages coloured by the number of marks
   (from the .aux), each cell a link.

### ii. Venue rules (`venue`)
Purpose: every rule of the call and the guide for authors that applies, judged on this paper.
1. Title and one line on what the table is (venue name, the file it comes from).
2. Counts line; the **source caveat** banner when a live page could not be read or a rule comes from an archived
   copy or is unverified (`blocked`, `source` in `work/venue-status.json`).
3. The table, violated first, then to confirm, cannot tell, met: icon, rule (a rule judged violated whose items are
   all minor or optional is shown as to confirm: only a desk-reject item makes a rule violated) (and, at levels 4-5, its verbatim
   quote), this paper (items, page, one line), **in the copy** (the kind of its items), source.
4. Icon legend; the numbered source URLs; blocked live pages (on the last page when split).

### iii. Bibliography (`bib`)
Purpose: every cited entry, verified against which record, what the copy changed (`work/bib-status.json` of
`bib_status.py`: refs_check and bib_style outputs, the .bib, the .aux citations, bbl-map.json, report.md).
1. Counts: entries cited (of the .bib), checked against the databases (match / differ / not found), DOIs resolved,
   arXiv IDs looked up (with the skip reason), preprints searched, style differences, entries changed in this copy,
   entries to check by you.
2. One row per entry that the databases flagged or that an item changes for its content: icon, entry (link to its
   place in the marked bibliography, year), databases (the difference), identifiers, in the copy (items and kinds).
   Icons: changed in the copy (red circle, arrow), problem found by a report item but not changed (red cross),
   flagged with no item (orange !), matches. A difference that is only a parsing artefact (braces, an escaped `_`, a
   title cut at its colon; `db_artefact` of `bib_status.py`) is no flag: such an entry joins the compact list.
3. A compact list of the other entries (they match the record; changed only for a uniform style, or not at all;
   orange: arXiv ID not looked up).
4. Legend.

### iv. Decisions for you (`decisions-n`)
Purpose: the author's to-do list. The intro gives the count by kind (the same as the summary's "need you"). One
row per item to confirm, to check or needing facts, in page order: the item's check box (the same field as next to
its change; a "your facts" item has the disabled box with its own glyph, never ticked), item (link), page (link),
kind with the item's severity under it, one question, and under it a "your answer" text field (`answer-N`). The
intro says where answers in words go: typed in the field, then save the PDF; or a reply to the agent in the chat,
or under the item in section 9 of report.md, then a rebuild.

### v. What we checked (`checks`)
Purpose: every check of the run, also those that found nothing, with how much it covered.
1. Title and the summary line of the table (rows, categories, rows by result, report items raised).
2. All statistics of `work/checks.json`, four per row, with their footnote.
3. The table by category, each with its Avoid subtitle: icon, check (and who ran it), how much, result (nothing
   found / n items, linked / flagged by a script with no item, orange, e.g. Type 3 fonts / flags passed to the next
   checker, blue / not checked). Checks of one checker that found nothing are merged. A reason is printed in full.
4. **Items with no mark in the paper** (applied by another item, not applied, preamble changes): their state; the
   links of these items land here.
5. Icon legend; when an item belongs to several categories, the number of mentions and of distinct items.

### vi. Traces of AI use (`ai`)
Purpose: verifiable artifacts versus style perception, what venues do, the paper's disclosure. Content and rules in
the header of `scripts/front_pages.py` and `scripts/ai_traces.py` (`work/ai-traces.json`,
`references/ai-venue-actions.md`).

## Rules

- **Every number comes from a file of the run**: `report.md`, `work/edits.tsv`, `work/venue-status.json`,
  `work/checks.json` (written by `check_stats.py` from the scripts' COVERAGE lines, the checkers' Coverage blocks
  and `scope_stats.py` on the sources), `work/ai-traces.json`, the `.aux` of the previous LaTeX run (pages).
  Nothing is typed by hand.
- **No empty or "not counted" cell.** A statistic exists only with a value; a check row always says how much it
  covered (or, when not run, why). Drop a statistic or a row rather than print "not counted", "--", "?" or
  nothing. `front_pages.py` fails on a statistic without a value, a row without an amount, or the words "not
  counted" anywhere in the pages.
- **Statistics and their basis** (`basis` in `checks.json`):
  - *measured*: counted by a script while checking (COVERAGE line) or by a checker in its Coverage block.
  - *in scope*: counted on the sources by `scope_stats.py`: what the checker reads by design (every number for the
    numbers checker, every sentence for the proofreader). The text says "in scope of the ... checker". Once the
    checker writes a Coverage block, its own count replaces the scope ("1,100 numbers checked, of 2,149").
  - *estimate* (marked `*`): counted by a stated pattern (comparative statements, numbers cited from tables and
    figures). The footnote gives the method (`method`, from `scope_stats.METHOD`).
  - *counted from outputs* (marked †): counted in a checker's output file (e.g. the flag lines of candidates.md).
- **Numbers reconcile**: a count shown on two pages is computed once (the summary's tiles and kind bar from
  `report.md` and `work/edits.tsv`, its venue counts from `work/venue-status.json`, its checks line by the same
  function as the checks page); the kinds add up to the items, "need you" equals the rows of the decision sheet.
- **Item check boxes**: one AcroForm field `item-n` per item with something to apply, its widgets next to every tag
  of the item, in the header of its margin box (with the reason of the default) and in its decision row; ticking one
  ticks all. Defaults from `apply_edits.py` (kind and `confidence`; `r2states.tex`); `read_choices.py` reads them
  back from a saved PDF; `--choices` applies them. An item with any missing facts ("your facts") gets a disabled,
  read-only box with its own glyph (a dashed orange square with three dots, `\rrboxsym{2}`), never ticked; none of
  its changes is in `corrected/` until the facts are given.
- **One severity per item**: `Severity: desk-reject | major | minor | optional` of each item of report.md (merge
  agent; older words are mapped: reviewer-visible = major, low/cosmetic = minor; without one, the section's
  default). The cover, the venue page, the decision sheet and edits.md all use it.
- **One build**: `build_changes.py` writes report.md (synced), changes.pdf, edits.md and corrected/ in one run and
  checks at the end that they agree: the same build id in all four (page 1 of the PDF, `Build:` in report.md and
  edits.md, `corrected/.reviewer2-build`), the same items and kinds, the counts of report.md and of the summary page,
  the ticked boxes of the PDF = the pre-set (or chosen) items = corrected/ (rebuilt with `apply_edits.py --only`
  and compared file by file), edits.md's legend = the kinds and colours of the summary, no earlier or temporary
  file names. Any disagreement fails the build.
- **Links**: one link per reference, never nested. An item's links land on its first mark in page order (the
  `\rr@markat` records of the .aux; the page is the copy page of that mark), else on its note, else on its row in
  "Items with no mark in the paper". `pdf_links.py` checks the PDF at every build (unresolved destinations,
  overlapping link rectangles, item links landing on a front page).
- **Links**: every `#n` links to the change in the paper, every page number to its page; the navigation line of
  every front page links the others and page 1 of the paper; the summary gives the page number of every front page;
  the decision sheet's check boxes are PDF form fields.
- **Fill**: every front page is full but never overflows. `r2changes.sty` sets each page at its natural height and
  writes `rrfront fill: id=<id> page=<p> natural=<pt> full=<pt>` to the log; a page that fits is stretched to the
  full height at its `\rrFgap[share]{space}` gaps (between sections, never inside a table; the gap under a page's
  intro takes a quarter share, so the slack goes mostly above the footer legend). `build_changes.py` adapts each page
  through its **level** until it fits:
  - overflow: one level down, and the page stays there (`venue`, `checks` at level 0: two pages);
  - under 90% full: one level up, while the page has a higher level (under 80% at the end is a warning).

  | Page | Levels (low to high) |
  |---|---|
  | cover | the number of Most Important Errors: 3, 4, 6, 8 (+ page strip), 10, ... 28 (start: 10) |
  | venue | 0: compact (start; two pages when it overflows); 1-3: larger type and rows; 4-5: + the verbatim quote of each rule |
  | checks | 0 (8pt) to 4: larger type and rows; 1 (start); two pages when level 0 overflows, then the level may rise again |
  | bib | rows per page: 0 fewest to 4 most (start: 2) |
  | decisions | 0: tightest; 1 (start) to 4: larger type and rows |
  | ai | fixed |

  `front_pages.py` prints the fill of the last LaTeX run and warns about a page under 80%; `build_changes.py`
  prints the fill and the level of every page. When a page stays under 80% at its highest level, say so; when one
  still overflows at level 0, shorten its text (venue notes, questions).

## Visual conventions

- Type: sans serif; page titles 18pt (continued pages 13pt, cover title 21pt), section heads 8pt bold small
  capitals in grey (`rrmuted`),
  body 7-9pt; ink `rrink` (28,36,52), grey `rrmuted` (95,105,120), rules `rrrule` (215,222,232), table bands
  `rrband` (243,246,250), alternating rows.
- Change colours (as in the paper): red `rrred` = certain fix applied (old text struck out); orange `rrorange` = fix
  applied, to confirm, and `[#n: ...]` placeholders for facts only the authors have; purple `rrpurple` = optional
  wording; light blue `rrbluebg` / `rrblueframe` = margin notes and their `#n` tags; grey = not applied.
- Status icons: green check = met / nothing found; red cross = violated / problems (report items); orange ! = to
  confirm / flagged by a script with no item; grey ? = cannot tell / not checked; red circle with an arrow =
  changed in the copy (bibliography page).
- Margin notes in the paper: one box per item at the height of its line (an item to check also gets a one-line box
  with its question at each orange mark far from its note: another file, or more than 1,500 characters away), `#n` linked both ways, the `file:line` of
  the change in `corrected/`; on a crowded page the short note (`note_short`).
