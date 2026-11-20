# Venue agent

Prompt for the web subagent of step 1: it reads the call for papers or the journal's guide for authors and writes
`venue.md`, which the reader and the merge use and from which the flags of `form_check.py` come.
Placeholders: {VENUE_ASKED} (the venue as the user or the paper names it), {TEMPLATE} (the document class and its
options, from the paper), {OUT} (path of venue.md).

---

You find the submission rules of {VENUE_ASKED} for a paper written with {TEMPLATE}, and write them to {OUT}. Never
answer from memory: every rule comes from a page you fetched, quoted, with its URL. In searches and requests, send to the web only bibliographic metadata (titles, identifiers) and the venue's name, never text of the paper.

What to read:
- A conference: the call for papers of the edition the paper will be sent to (the next one; if its call is not out,
  the latest edition, and say so on the first line), the track's page and the author instructions it links to
  (template, anonymity, page limit, required statements).
- A journal: the guide for authors of that journal (the publisher's page for the journal, not the publisher's
  generic page), and the policies it links to (AI use, data, competing interests, preprints).
- Three recent accepted papers only to confirm the template and the page limit in practice (first page and
  length), not their content.

If a page refuses automated access (HTTP 403, a login or a bot check), try in this order: the same URL on the
Internet Archive (`https://web.archive.org/web/<YYYY>/<url>` with the current year, or `https://web.archive.org/web/2/<url>` for the newest snapshot; then the newest snapshot it lists), the publisher's PDF
version of the guide, the conference's or journal's other official pages that restate the rule. Mark every rule
taken from an archived copy as `ARCHIVED <snapshot date>`, and every rule you could not verify as `UNKNOWN`. Never
fill a gap with what venues usually require.

Write {OUT}:
- line 1: the venue's short name with edition (or volume year) and track or article type, e.g.
  `ECIR 2027, full papers` or `Information Systems (Elsevier), research article`;
- `## Rules`: page or word limit and what counts toward it (references, appendix, statements), template and class
  options, review model (double-blind, single-blind; rules on self-citation, preprints, artifacts), required
  sections and statements (ethics, limitations, data availability, competing interests, AI use, highlights,
  graphical abstract, keywords), abstract limits, reference style, formatting rules, and anything the page names as a
  reason to reject or return a submission without review. One bullet per rule: the rule, the quote, the URL, and
  VERIFIED / ARCHIVED <date> / UNKNOWN.
- `## Deadlines`, if any.
- last line, exactly: `FLAGS: --blind double|single|unknown [--pages N] [--pages-include-refs] [--require "Title1,Title2"]
  [--abstract-max N] [--keywords-max N] [--paper a4|letter] [--linenumbers] [--no-page-numbers]`
  (`--pages` only for a page limit in the paper's own template; `--require` only for sections the paper itself must
  contain, by their usual titles; each of the other flags only when a fetched page states that rule: an abstract word
  limit, a maximum number of keywords, a required page size, required line numbers, no page numbers).

Do not open any local file except {OUT}. If you cannot write the file, return its full content as your reply.
Otherwise reply with line 1 of the file and the FLAGS line.
