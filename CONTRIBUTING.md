# Contributing to git-signoff

Thanks for looking. This page covers how to set up, test, and propose changes,
and how the project's own gate applies to its own branches.

## What lives where

| Path | What it is |
|---|---|
| `skills/git-signoff/` | The vendored skill folder adopters copy: `SKILL.md` (interview prompt), `attest.py` (deterministic producer), `verify_signoff.py` (verifier), `HARNESSES.md`, `profiles/`, `specs/`. Everything an adopter runs is in here, standard library only. |
| `init.py` | Zero-touch initializer (curl-run, standard library). |
| `verify/` | Composite GitHub Action wrapping the verifier, plus its README and `ruleset.json`. |
| `conformance/` | Test vectors third-party implementations run against. |
| `scripts/tests/`, `tests/` | The test suite (see below). |
| `docs/` | Roadmap, productionization record, functionality reference, walkthrough. |
| `site/` | The static project website. |

Functionality reference (flags, exit codes, environment variables):
[`docs/reference.md`](docs/reference.md). Reproducible end-to-end run:
[`docs/walkthrough.md`](docs/walkthrough.md).

## Development setup

Python 3.10+ and git. Nothing from this repository is installed; the only
development dependencies are the test runner and the linter:

```bash
pip install pytest ruff
ruff check . && pytest
```

CI runs exactly that on Python 3.10 and 3.13 (the floor and ceiling of the
documented "Python 3.10+" promise).

### Tests that skip without full history

Two tests exercise this repository's own attestation history rather than a
scratch repository: `test_end_to_end_against_this_repo` in
`scripts/tests/test_verify_signoff.py` and in
`scripts/tests/test_recover_notes.py`. They need a `main` (or `origin/main`)
that reaches the 2026-08 attestation commits, so they **skip on shallow
clones** and on checkouts without `main`, with the reason
`shallow clone or stale local main`. CI checks out with `fetch-depth: 0` so
they run there. Locally, `git fetch --unshallow origin main` (or a normal
clone) makes them run. A skip is not a failure; a failure is.

### Test layout

- `scripts/tests/test_attest.py` — the producer, end to end against scratch
  repositories, including the approval-marker protocol, rollback paths, notes
  push, and an `init.py` → `attest.py` → verifier run through a vendored copy.
- `scripts/tests/test_attest_*.py` — adapters, profile resolution, notes merge.
- `scripts/tests/test_verify_signoff.py` — the verifier (head, history, audit,
  stale-pin warning).
- `scripts/tests/test_skill_references.py` — contract tests on `SKILL.md`,
  `HARNESSES.md`, and the spec (these pin wording deliberately; if you change
  the prose they guard, change the test in the same commit and say why).
- `scripts/tests/test_conformance_vectors.py` — the reference verifier against
  `conformance/`.
- `tests/test_init.py`, `tests/test_ruleset.py` — the initializer and ruleset.

Tests load `attest.py` and `verify_signoff.py` by path (`_attest_loader.py`),
the way the vendored folder is used; there is no package to import.

## Making a change

1. Branch from `main`.
2. Keep the skill folder self-contained: no imports outside the standard
   library and the sibling file, no relative links out of the folder
   (`test_skill_folder_is_self_contained` enforces both).
3. Protocol identifiers (`Signoff-*` trailers, `refs/notes/signoff`,
   `[SIGNOFF <sha>]`) are governed by `specs/gsa-core.md`. A change to what an
   attestation *means* is a spec change first: bump the document version,
   add or update a conformance vector, then change code.
4. Pin tags never move. A change to the verifier's behavior ships as a new
   `verify-vX.Y` tag: bump `VERIFIER_PIN` in `verify_signoff.py`, add the tag
   to `PINS` in `.github/workflows/tag.yml`, and update the install snippets
   (tests pin all three to each other). Initializer changes ship as `init-vN`
   the same way (`SKILL_SOURCE_REF` in `init.py`).
5. Run `ruff check . && pytest`.
6. Open a pull request. The `verify-signoff` check runs red until the branch
   ends in a valid attestation — see the next section.

## Signing off your own branch

This repository uses its own gate. Before a pull request can merge, the last
commit on the branch must be an attestation written by `/git-signoff`: an
agent reads the diff, interviews the author, and `attest.py` writes the
record. Run it from the branch, after the diff is final; pushing anything
after the attestation turns the check red again (re-run `/git-signoff`).
The interview intensity is adaptive; a change to `attest.py` or the verifier
is Tier 2 (`skeptical`).

Cloud sessions cannot push `refs/notes/signoff` (the proxy returns 403);
`attest.py` reports that and exits 0, and the `notes-recovery` workflow
rebuilds the notes ref from the attestation commits on merge.

## Reporting issues and getting help

- Bugs and feature requests: open an issue using the templates under
  `.github/ISSUE_TEMPLATE/`.
- Security problems (a way to make the verifier pass an attestation it
  should reject, or the producer write one it should refuse): see
  [`SECURITY.md`](SECURITY.md) — please do not open a public issue first.
- Questions and adoption help: open an issue with the "Support" template.
  Interviews with prospective users follow
  [`docs/discovery-interview.md`](docs/discovery-interview.md).

## Licensing of contributions

Code (everything except the documents under `skills/git-signoff/specs/`) is
MIT (`LICENSE`). The specification documents are under the Apache License
2.0 (`skills/git-signoff/specs/LICENSE`); a contribution to them is
licensed under Apache-2.0 per its section 5, including the patent grant.
Neither license covers the other set of files.
