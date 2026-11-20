<!-- Thanks for contributing! See CONTRIBUTING.md. -->

**What this changes**
<!-- A new check, a fixed false alarm or false negative, venue rules, documentation ... -->

**Fixture and test**
<!-- Changes to a script need a fixture in evals/fixtures/ and a test (or an expectation) in evals/tests/ that
     fails before the change and passes after it. Say which ones. -->
- [ ] Added or updated a fixture: `evals/fixtures/...`
- [ ] Added or updated a test or expectation: `evals/tests/...`
- [ ] `for t in evals/tests/test_*.py; do python3 -I "$t" || break; done` passes
- [ ] `python3 skills/reviewer2-repellent/scripts/self_test.py` passes
- [ ] Documentation-only change (no test needed)

**No private data**
- [ ] Fixtures and examples are written from scratch or fully anonymised: no unpublished text, no real reviews, no names of people who did not agree.
