# Contributing

Thanks for helping Reviewer 2 lose its pretexts. New checks, fixed false alarms, venue rules, documentation and
better jokes are all welcome.

## Layout

- `skills/reviewer2-repellent/SKILL.md`: the flow the agent follows; `references/` holds the instructions of each
  checker and the formats; `scripts/` holds the Python scripts (standard library only, Python ≥ 3.9).
- `evals/fixtures/`: small synthetic papers and bibliographies, each built to trigger (or not trigger) specific
  findings, with an `EXPECTED.md` or an `expectations.json` saying what must and must not be reported.
- `evals/tests/`: the tests that run the scripts on those fixtures.

## Run the tests

From the root of the repository:

```bash
for t in evals/tests/test_*.py; do python3 -I "$t" || break; done
python3 skills/reviewer2-repellent/scripts/self_test.py              # one-page synthetic paper, end to end
python3 skills/reviewer2-repellent/scripts/self_test.py --network    # also the bibliography lookup (needs internet)
```

You need the tools in [SETUP.md](skills/reviewer2-repellent/SETUP.md) (at least Python, `latexmk` and
poppler-utils). Tests that compile LaTeX are skipped when `latexmk`/`pdflatex` is missing; `test_refs_check.py`
needs the network and skips cleanly when offline. Run a single test file with `python3 -I evals/tests/<file>.py`.

## Add or fix a check

1. **Write the fixture first.** Add a folder under `evals/fixtures/<script>/` (for example
   `evals/fixtures/form_check/my-case/main.tex`) with the smallest paper that shows the problem, and an
   `EXPECTED.md` that says in words what must be reported and what must stay silent. Add a near miss too: a case that
   looks similar but is correct, so the check cannot pass by flagging everything.
2. **Write the expectation.** For `form_check.py` add an entry to `evals/fixtures/form_check/expectations.json`
   (`must` and `must_not` lists of `[severity, kind, quote]`); for `refs_check.py` use
   `evals/fixtures/refs_check/expectations.json`; for the other scripts add a test case to the matching file in
   `evals/tests/`.
3. **Check that the test fails**, then change the script until it passes, and run the whole suite again.
4. If the check is done by a reading agent rather than a script, change the matching file in
   `skills/reviewer2-repellent/references/` and keep `SKILL.md` within its limits (`test_skill_md.py` checks them).
5. If you add or change a tool the skill depends on, update
   [SETUP.md](skills/reviewer2-repellent/SETUP.md) and `scripts/check_setup.py`.

A false alarm you met in a real run is a perfect contribution: turn the quoted sentence into a fixture (rewritten so
it shows the same pattern without your content) and an expectation in `must_not`.

## Style

- **No private data in fixtures, tests or examples.** Write the text from scratch or anonymise it completely: no
  unpublished papers or results, no real reviews, no names, e-mails or affiliations of people who did not agree, no
  confidential venue material. Invented references must be clearly invented (or real, published ones).
- Scripts use the standard library only and must run with `python3 -I`, which does not put the script's folder on
  the import path: a script that imports a sibling adds its own folder to `sys.path` explicitly.
- Every finding carries its evidence and its location; a check that cannot show where and why should not report.
- Prefer missing a doubtful case to flagging a correct one: false alarms cost the author time and trust.
- Keep the wording plain and short, in the report and in the code comments.

## Pull requests

Open the PR against `main` and fill in the template: say what changes and which fixture and test cover it.
Documentation-only changes need no test.
