---
name: reviewer2-repellent
description: Pre-submission check of a LaTeX research paper for the objective errors reviewers pounce on - venue rules (page limit, anonymity, template, required sections), numbers that disagree with tables or each other, unsupported claims, typos and grammar slips, broken references, wrong bibliography entries, leftovers, layout defects. Writes one numbered report with evidence and fixes, then a corrected copy of the sources and an annotated changes.pdf with every change marked by item number (red certain, orange to confirm, purple optional) and a do/don't box per change. Use when the paper is nearly ready to submit and the user says "reviewer 2", "check my paper before submission", "desk-reject check", "find errors / typos / inconsistencies in my paper", "proofread the paper", or "apply my choices in changes.pdf". Not for editing or polishing a draft still being written, judging the scientific merit, answering reviews already received, or reviewing others' papers. Heavy - several subagents read the whole paper.
license: MIT
compatibility: Works on LaTeX and BibTeX sources. Needs an agent that can launch subagents and fetch web pages, a LaTeX toolchain (latexmk), Python ≥ 3.9 and poppler-utils (pdfinfo, pdftotext, pdffonts, pdftoppm). Optional tools are listed in SETUP.md.
---

# reviewer2-repellent

Reviewer 2 decides in two minutes and then looks for pretexts: a page over the limit, a name in the PDF metadata, a
number in the abstract that no table contains, "the authors did not even proofread". This skill finds those
objective errors before submission and fixes them with the author.

It looks for errors that can be verified, not for opinions on the research. Several specialised checkers read the
paper independently (a general reader, a numbers-and-claims checker, a two-stage proofreader), scripts measure what
can be measured, and a merge step turns everything into one numbered report.

If the user asks to **apply their choices in changes.pdf**, go straight to "Apply the author's choices" below.

## Workflow

```
- [ ] 0. Paper, venue, output folder (root file, engine)
- [ ] 1. Venue rules (subagent, web) | copy and compile the paper, names.txt
- [ ] 2. Facts from the scripts
- [ ] 3. Three checkers in parallel: reader | numbers and claims | typos finder -> typos verifier
- [ ] 4. Merge into report.md
- [ ] 5. Show the report (counts, desk-reject risks, first fixes); do not ask the questions yet
- [ ] 6. changes.pdf built with the defaults and opened for the user ("report only" stops after 5)
```

## Paths and rules

- **`<skill>`** is this skill's absolute directory; **`<paper>`** is the folder with the paper's sources and
  **`<root>.tex`** its root file; **`<out>`** the output folder and **`<work>`** = `<out>/work`.
- **Output folder:** `<paper>/reviewer2-repellent/<YYYY-MM-DD>/` (a new run on a day that already has one goes to
  `-2`, `-3`), unless the user names another place. Say where it is at the start of the run. It holds `report.md`,
  `corrected/`, `changes.pdf`, `edits.md` and `work/`: `venue.md`, `names.txt`, `build-flags.txt`, `facts.txt`, the
  checkers' reports, `prompts/` (the filled prompts), `paper/` (a clean copy of the sources), `build/` (a second copy,
  compiled) and `tmp/` (every scratch file of the agents: nothing else goes outside these folders). Tell the user
  once: this folder must not be committed, synced to Overleaf or included in an arXiv upload (add
  `reviewer2-repellent/` to the paper's `.gitignore` if they want).
- **Never modify the original sources** unless the user explicitly asks; every edit goes to `corrected/`.
- **The manuscript never leaves the machine** except to the session's own model provider. Only reference metadata
  (titles, identifiers) goes to bibliographic services. Ask before using any tool or model that would send the paper
  elsewhere.
- **Setup:** on the first run, `python3 <skill>/scripts/check_setup.py`. Install nothing without the user's
  consent (SETUP.md), but ask once: list what is missing in two groups and do not make the user copy anything by
  hand. (1) Commands without sudo (uv, RefChecker, MCP servers, brew packages): ask one yes for the whole group
  and run them yourself. (2) Commands that need sudo (tlmgr/apt/dnf) and the DBLP database build (~20 min): give
  them as one block, one command per line, each prefixed with `! ` so the user runs them in the session (or
  pastes them); then rerun check_setup.py. A missing optional tool is not a reason to stop: the scripts report it as `SKIPPED`.
- **Subagents:** launch each checker as its own subagent with the prompt from its reference file. Fill it with
  `python3 <skill>/scripts/fill_prompt.py <skill>/references/<agent>.md KEY=VALUE ... > <work>/prompts/<agent>.txt`
  (it fails on an unfilled or unknown placeholder) and give the subagent that text. Use absolute paths in every
  value. If the agent cannot launch subagents (some CLIs), run the checkers one after another yourself, each from its
  prompt, without letting one checker's findings guide the next, and split the typos finder per chunk of `FILES`
  (`typos-finder.md` says how).
- **Files a subagent cannot write:** some environments stop subagents from writing report files. Each prompt asks
  the subagent to return its full text instead; save that text yourself, unchanged, to the expected path.
- **Background jobs:** start a slow script with the tool's background mode, not a shell `&` (it can die with the
  shell); a script is done when the last line of its output file starts with `COVERAGE |`.

## Time, stopping and resuming

Tell the user at the start: the scripts take a few minutes (`refs_check.py` about 10 s per reference), the three
checkers 10-30 min in parallel, the merge some minutes, the build of step 6 a few minutes. Each stage leaves a file
in `<work>`: `venue.md` (1), `build-flags.txt` and the compiled `build/` (1), `facts.txt` (2), `reader.md`,
`numbers.md`, `candidates.md`, `typos.md` (3, each complete when it ends with its `## Coverage` block), `merged.md`
and `report.md` (4), the answers in `report.md` (5), `edits.json` and `changes.pdf` (6). To resume an interrupted
run, reuse the newest output folder and start at the first stage whose file is missing or incomplete. A new run
after a finished one goes to a new `-2` folder. For a **quick re-check** after the author's own edits ("scripts
only"), run steps 0-2 into a new folder and report what changed in `facts.txt` against the earlier run (minutes, no
subagents).

## 0. Paper, venue, output folder

Find the root file (the `.tex` with `\documentclass` and `\begin{document}`), also in subfolders (a repository with
`paper/main.tex`, an Overleaf zip). `<paper>` is the root's folder, since TeX resolves `\input` from there; if the
root inputs files outside it (`../`), `<paper>` is the common parent and the root is `<subfolder>/<root>.tex`.
Find the engine: `xelatex` or `lualatex` when the sources load `fontspec`, `unicode-math`, `polyglossia`, `xeCJK` or
`luatexja`, have a `% !TEX program = xelatex|lualatex` line, or a `.latexmkrc`/`latexmkrc` sets `$pdf_mode = 5`
(xelatex) or `4` (lualatex) or names the engine; `lualatex` for Lua packages (`luacode`, `luatexja`), `xelatex`
otherwise; else `pdflatex`. Find the target venue (conference or journal, year, track) from the template, the
paper's notes or the conversation. Ask only if the venue is not clear: it sets the page limit, the review model and
the required sections. Create the output folder and `work/` with its subfolders, and tell the user where the report
will be and how long the run takes.

## 1. Venue rules | copy and compile

**Venue rules (subagent, in the background).** A web subagent follows `<skill>/references/venue-agent.md`
(`VENUE_ASKED`, `TEMPLATE` = the document class and options, `OUT` = `<work>/venue.md`). It reads the call or the
journal's guide for authors, falls back to archived copies when a site blocks automated access, quotes every rule
with its URL, and ends with the `FLAGS:` line for `form_check.py`. Its first line is the venue's short name.
**If it returns nothing usable** (no file, no `FLAGS:` line, every page blocked), do not stop: write a minimal
`venue.md` (line 1: the venue as asked followed by `(rules not retrieved)`; an empty `## Rules`; a `## Sources tried`
list with every URL it tried; last line `FLAGS: --blind unknown`) and `venue-status.json` as
`{"rules": [], "blocked": [{"url": ..., "note": ...}]}` with those URLs. The cover of `changes.pdf` then shows the
venue as "(rules not retrieved)"; say it to the user in step 5 and in the report.

**Meanwhile:** copy the sources twice, to `<work>/paper/` (kept clean: no build files ever go there) and to
`<work>/build/`, leaving out the output folder itself and any build files. Compile in place in `<work>/build/` (in the
root's subfolder if any): `latexmk -pdf|-xelatex|-lualatex -no-shell-escape -interaction=nonstopmode <root>.tex`, and
fix nothing. If no PDF comes out, stop and tell the user with the first `! ` error of the log. A paper that needs
shell escape (`minted`, `\write18`, some `svg` or `gnuplot` set-ups) fails here safely, without running anything: say
so and ask the user whether to compile with `-shell-escape`, which runs the commands written in the paper; never add
it on your own. Write `<work>/build-flags.txt`, one line: `--root <root>.tex --engine <engine>` (the root relative
to `work/paper/`).
Write `<work>/names.txt`, one per line: every author name, affiliation, e-mail and handle (GitHub, ORCID, personal
URL) found in `\author`, `\affil`, `\affiliation`, `\institute`, `\email`, `\thanks`, `\orcid` and the metadata
(`\hypersetup`, `pdfauthor`), also in commented-out lines; if the sources are already anonymised and the venue is
double-blind, ask the user for the names (the anonymity check needs them).

## 2. Facts from the scripts

From the root's folder in `<work>/build/` (it has the `.aux`, `.log` and PDF the scripts need), with the flags from
the `FLAGS:` line of `venue.md` (`--blind unknown` and no `--pages` when the venue research failed):

```
python3 <skill>/scripts/refs_check.py <root>.tex > <work>/refs_check.out 2>&1   # background mode, about 10 s per reference: start it first
python3 <skill>/scripts/form_check.py <root>.tex --facts --authors <work>/names.txt <flags> > <work>/form_check.out 2>&1
python3 <skill>/scripts/bib_style.py <root>.tex > <work>/bib_style.out 2>&1
```

Add `--offline` to `form_check.py` when there is no network or the user does not want the paper's links fetched;
pass `--engine` from `work/build-flags.txt` (otherwise it is detected). If the author has supplementary material or a
code archive, pass each with `--supp PATH` (folder or .zip, repeatable): with `--blind double` it reports names,
e-mails, home paths, `.git` identities, notebook outputs, document metadata and author/licence lines; with any review
model, credentials and tokens (masked). Ask the user for these files at step 0 for a double-blind venue. When all three
are done, write `<work>/facts.txt`: each output under its heading, exactly `## form_check`, `## refs_check` and
`## bib_style` (the script name without `.py`; the step-6 scripts read these sections). FAIL lines are measured violations,
CHECK lines are candidates to verify, INFO lines are context; the final `COVERAGE |` line counts what the script read
and tested. `form_check.py` also reports source hygiene (visible Markdown, Unicode that prints wrongly or
inconsistently, invisible characters, comments naming LLMs or prompts): defects whoever wrote them; the report never
calls them "AI".

## 3. Three checkers in parallel

Launch the three in parallel; they do not see each other's work. Each writes its report into `work/` and replies
with counts only. Every prompt ends its file with a `## Coverage` block (`key: N` lines: what the checker actually
read, recomputed, looked up or judged; keys in each prompt); keep these blocks when you save a returned text.

| Checker | Prompt | Placeholders |
|---|---|---|
| Reader: venue compliance, layout, figures and tables, references, leftovers, notation, numbers, bibliography | `<skill>/references/reader-agent.md` | `PAPER`=`work/paper`, `ROOT`, `VENUE` (the short name, first line of `venue.md`), `VENUE_RULES`=`work/venue.md`, `BLIND_NOTE` (one sentence on the review model), `RUN`=`work`, `REPORT`=`work/reader.md` |
| Numbers and claims | `<skill>/references/numbers-agent.md` | `PAPER`, `ROOT`, `BUILD`=`work/build`, `REPORT`=`work/numbers.md` |
| Typos, stage 1 (high recall) | `<skill>/references/typos-finder.md` | `PAPER`, `FILES` (the root file and every file it actually inputs, in reading order, TikZ/pgfplots files included; a commented-out `\input` is not part of the paper), `CANDIDATES_OUT`=`work/candidates.md` |
| Typos, stage 2 (after stage 1) | `<skill>/references/typos-verifier.md` | `PAPER`, `CANDIDATES_IN`=`work/candidates.md`, `REPORT`=`work/typos.md` |

Use absolute paths. The reader starts only when `venue.md` exists (the other checkers do not need it). The typos
verifier starts when the finder has finished, and only if the `## Coverage` block of `candidates.md` has
`chunk_lines_max` of 60 or less: otherwise (or `not counted`) the finder skimmed; run it again once, telling it to
read 30 lines per Read call.

## 4. Merge

One subagent follows `<skill>/references/merge-agent.md` with `PAPER`, `FACTS`=`work/facts.txt`, `READER`,
`NUMBERS`, `TYPOS` (the three reports), `VENUE` (short name), `VENUE_RULES`=`work/venue.md` and
`REPORT`=`work/merged.md` (some environments stop subagents from writing a file named like a final report). Copy
`work/merged.md` to `report.md` in the output folder; if the subagent returned the report as text instead, save that
text, unchanged. It merges duplicates, resolves conflicts against the sources, checks every quote, turns the
measured violations into items, numbers the items and lists the questions the author must answer.

## 5. Show the report

Read `report.md` and give the user: the counts per section, the desk-reject risks if any (the items of severity
`desk-reject`: every item carries `Severity: desk-reject | major | minor | optional`), the three items to fix
first, and the path of the report (and, if the venue research failed, that the venue rules were not retrieved and
must be checked by hand). **Do not ask the questions for the author here and do not offer a choice between
answering first and "using the defaults"**: go straight to step 6, which builds `changes.pdf` with the defaults (the
[to check] items in orange with their question) and opens it. The PDF is where the author reads, ticks and saves
the choices. Mention `corrected/` only as a by-product, never as something to wait for.

## 6. Corrected copy and annotated PDF

By default apply **every item** of the report, marked by how sure it is, so the author sees the whole corrected
paper and decides in one pass; the user can instead name items ("only 3, 7, 12") or exclude groups ("no appendix").
**Read `<skill>/references/apply-changes.md` first**: it has the rules for notes, confidence, the bibliography, the
venue status, the AI-traces page, the build and the handover. Each entry of `work/edits.json` has one kind:

| Kind | For | In `changes.pdf` |
|---|---|---|
| `fix` | items of sections 2-6 with one right fix (typos, references, a miscomputed number) | new text red, old struck out, `#n` |
| `check` | [to check] items: the report's first proposed fix, with its question | new text orange, `#n`; the margin note starts "To check:" and asks the question |
| `style` | the appendix (possible language improvements) | new text purple, `#n` |
| `missing` | a fix that needs facts only the authors have (measurements, runs, variance, a new section) | an orange `[#n: what is needed]`; in `corrected/` a `% TODO #n:` comment |
| `note` | an item whose change is not visible on the page (preamble, class options, float placement, macro definitions, verbatim code, supplementary files) or a check-only item | only the margin note (with a `question`: an orange `#n` too) |
| `raw` | changes the marks cannot wrap (a table cell set in bold, a moved block, a class switch): give the marked text yourself, e.g. `{\color{rrred}\textbf{0.93}}\rrtag{rrred}{83}` | your `mark` text |
| `log` | an item not applied, or applied by another item | nothing; a line in the log |

In short: write `work/edits.json` (format in `apply_edits.py`), `work/tmp/bbl-map.json` if the bibliography changes
(BibTeX only: with biblatex the bibliography is not marked in the PDF, and its changes are listed in `edits.md` and
the `.bib` diff), `work/venue-status.json`, then

```
python3 <skill>/scripts/ai_traces.py <out> --root <root>.tex      # then complete work/ai-traces.json
python3 <skill>/scripts/build_changes.py <out> $(cat <work>/build-flags.txt) --open
```

look at the page images it lists, update `report.md` with an `*In the copy:*` line per item and rebuild, and hand
over: `changes.pdf` is open; what the colours mean; the author ticks the boxes, types answers in the box under each
question ("Decisions for you" page), saves the PDF and says "apply my choices in changes.pdf" (that reads both and
regenerates `corrected/` with exactly the ticked set). Only now list the questions for the author (section 9 of the
report) in one message, each with its item number and evidence, as optional: answering in the chat works too;
unanswered ones stay as they are in the PDF.

## Apply the author's choices ("apply my choices in changes.pdf")

Works in a new session. Find the output folder: the folder of the saved PDF when it holds `work/`, else the newest
`reviewer2-repellent/<date>[-n]/` with a `changes.pdf` under the paper's folder (ask if several qualify). Then:

```
python3 <skill>/scripts/read_choices.py <saved changes.pdf> --out <work>/choices.json --defaults <work>/marked/r2states.tex
```

`choices.json` holds the boxes and the typed answers (`"answers": {"12": "..."}`; answers given in the chat count
the same). Record each answer verbatim in `report.md` under its item, apply what it settles to `work/edits.json` and
move the question out of section 9 (rules: section 9 of `apply-changes.md`). Then

```
python3 <skill>/scripts/build_changes.py <out> $(cat <work>/build-flags.txt) --choices <work>/choices.json --open
```

Tell the user which items changed from the pre-set, what each answer changed, and that `corrected/` now holds
exactly the ticked set.

## Special cases

- **Overleaf zip:** unzip into a new empty folder next to it; that folder (or the root's subfolder) is `<paper>`.
- **Not in English:** the typos checkers are English-only: skip them, write `work/typos.md` with one line saying
  why, and say so in the report; the other checks run.
- **TikZ/pgfplots:** text written in the sources (node text, axis labels, legends) is prose for the typos finder;
  text inside included images is seen only by the reader on the rendered pages.
- **Very long papers** (over ~40 pages, theses): split the typos finder per chunk of `FILES`, tell the user the run
  takes longer, and offer to check the appendices in a second run.

## Gotchas

- A finding with a quote that is not in the sources is suspect: the merge drops it unless the location is right.
- Numbers: when the text and a table disagree, which one is wrong is the author's call, not yours.
- The bibliography is checked on the `.bib` source, not on the printed list: the style can hide differences.
- When DBLP and the publisher's record disagree, the publisher's record wins.
- Comments in the source never reach the PDF, but they are public if the source is posted on arXiv.
- Metadata and comments can name people who are not authors: in the report write "a name", never the name.
- Do not soften true results or add hedges to please a reviewer; fix errors, not the author's voice.
