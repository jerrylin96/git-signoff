# Changelog

All notable changes to git-signoff. Release tags are `vX.Y.Z`; pin tags for
the composite action (`verify-vX.Y`) and the initializer (`init-vN`) never
move and are listed with the release that introduced them. Dates are the tag
dates on `origin`.

## Unreleased

- **Added** `.git-signoff/config.json` with `integration_branch`, written by
  `init.py` (`--integration-branch`, else detected and confirmed). One
  choice read by the workflow's push filter, the rendered ruleset
  (`refs/heads/<name>` instead of `~DEFAULT_BRANCH`), the setup branch's
  base, and `attest.py`. The producer's reference precedence is now
  `--reference`, a usable upstream, the configured branch, `origin/HEAD`,
  then `main`/`master`; the `origin/HEAD` step is a behaviour change for
  repositories without a config whose default branch is neither. On the
  integration branch, an unpushed range is attested as the reviewer's own
  (direct-push case), a diverged upstream is exit 3, and nothing unpushed
  is exit 2. An installed GitHub ruleset targeting a different branch is
  reported with the manual step and never edited (`mismatch`).
- **Added** interview scaling for expansive ranges: `prepare` reports
  `components` and `skeptical_min_probes` (`max(8, 4 + 2 × components)`),
  and SKILL.md's Tier 2 floor uses it, with one probe per component.
- **Changed** `scripts/recover_notes.py` to attach a note only where the
  attestation commit object backs the trailer: one parent, empty commit,
  parent is the declared reviewed commit (else skipped), and the declared
  tree is the parent's tree (else the commit anchor only). A `[SIGNOFF]`
  commit on an unrelated tree naming a target's tree could otherwise mint a
  tree note and turn an unattested target green (constructed in external
  review, 2026-09-16). Eight attestations from 2026-08-01..05 in this
  repository's own history declare a tree no reviewed commit has; they now
  recover on their commit anchor only. Payload files remain trusted as
  committed fixtures.
- **Fixed** `attest.py commit` attesting a commit the interview never covered
  when no transcript was available. `commit` re-ran `prepare` and took
  whatever HEAD was; only the transcript's approval marker tied it to the
  reviewed commit, so with `--ack-no-transcript` a commit added after the
  interview was attested with exit 0 (reproduced; found in external review
  2026-09-16). `prepare` now writes `.git/git-signoff/prepared.json`
  (reviewed, base and tree SHAs, reference, timestamp, resolved profile) and
  `commit` attests exactly that record: no record, a moved HEAD or tree, or a
  changed interview profile is exit 3, with or without a transcript; a
  `--reference` at commit must resolve to the recorded one (else exit 2); the
  base in the trailers is the recorded one even if the reference moved during
  the interview. A successful commit removes the record; `marker` reprints the
  recorded marker and is read-only (a stale or missing record is exit 3, so it
  cannot restart a review the way a silent re-prepare would; caught in the
  second external review pass). Spec `gsa-core.md` 3.7.2 (informative §4.1).
- **Changed** the license of the three specification documents under
  `skills/git-signoff/specs/` from the Community Specification License 1.0
  to the Apache License 2.0 (`gsa-core.md` 3.7.1, since superseded by 3.7.2 above, `gsa-escrow.md` 1.0.1,
  `gsa-in-toto-predicate.md` 0.1.1; no normative change). `LICENSE-SPEC` is
  removed; the Apache text lives at `skills/git-signoff/specs/LICENSE` and a
  copy of the MIT `LICENSE` at `skills/git-signoff/LICENSE`, so the vendored
  folder carries both notices. Code was and remains MIT.
- **Changed** `LICENSE` copyright holder to the author's name; `CITATION.cff`
  gains the author's affiliation and lists both licenses.
- **Changed** README: "Who it's for" is now "Statement of need"; the
  License section names which files fall under which license.

## v0.5.0 — 2026-09-10 (`verify-v1.4`, `init-v7`, spec 3.7.0)

The deterministic-producer release: the agent conducts the interview, a
standard-library helper does every mechanical step.

- **Added** `skills/git-signoff/attest.py`: `prepare` (SHAs, range summary,
  profile resolution, science signals, intensity hints, approval marker),
  `commit` (one transcript snapshot, status derived from the bytes, trailer
  construction, empty signed commit, dual `refs/notes/signoff` notes,
  `cat_sort_uniq` merge before push, verifier self-check with rollback),
  `marker`, `--dry-run`, `--json`, documented exit codes 0/2/3/4/5/6/7. A
  rollback step that fails is reported as `ROLLBACK INCOMPLETE` rather than
  asserted as done, and `prepare` refuses a HEAD that is already an
  attestation commit, so a failed rollback cannot be followed by an
  attestation of the rejected attestation (both found during this branch's
  own signoff interview).
- **Added** the approval marker `GSA-APPROVAL <reviewed-sha> <timestamp>`:
  `commit` refuses a transcript that does not carry this conversation's marker
  for this commit, so a stale or foreign session file fails closed (exit 4)
  instead of being hashed. Recorded as a producer SHOULD in gsa-core §2.3.
- **Changed** `SKILL.md`: sections 1 and 3–5 invoke the helper; the bash
  heredoc, digest regexes, and trailer template are gone. The injection
  refused at the verifier since `verify-v1.3` is now refused at the producer
  (exit 2) as well.
- **Changed** every user-facing name to `git-signoff`: `skills/git-signoff/`,
  `.claude/skills/git-signoff`, `.agents/skills/git-signoff`, `/git-signoff`,
  `.git-signoff/profile.md`, `.git-signoff/ruleset.json`,
  `.github/workflows/git-signoff.yml`, `GIT_SIGNOFF_TRANSCRIPT_FILE`,
  `GIT_SIGNOFF_PROFILE_FILE`, `GIT_SIGNOFF_VERIFIED_BY`, branch
  `git-signoff/init`. Protocol identifiers are unchanged; existing
  attestations verify as before.
- **Changed** the verifier: moved into the skill folder
  (`skills/git-signoff/verify_signoff.py`, vendored into adopter repositories
  for a local `--audit`), `VERIFIER_PIN`, `--version`, and a stale-pin warning
  (`GIT_SIGNOFF_NO_UPDATE_CHECK=1` to skip). `verify/action.yml` runs the moved
  file.
- **Changed** `init.py`: vendors the renamed folder (skipping `__pycache__`),
  tolerates untracked OS metadata (`.DS_Store` and friends) in the repo-wide
  clean-tree guard as it already did inside skill destinations, logs why
  ruleset automation fell back to the manual URL, and gains `--verbose`.
- **Fixed** the unborn-repository bootstrap identity: `init.py` probed
  `git var GIT_AUTHOR_IDENT`, which succeeds on hosts whose hostname has a
  domain (macOS) because git synthesizes `<user>@<host>`, so the "Signoff Bot"
  fallback never fired there and the bootstrap author depended on the machine.
  It now probes `user.name` / `user.email`, the `GIT_*` variables, and `EMAIL`
  explicitly (pre-existing since v0.4.0; found by adversarial review).
- **Removed** the `git_signoff/` Python reference library; its tests now run
  against `attest.py`. `pyproject.toml` builds nothing (version and ruff
  configuration only).
- **Repository hygiene:** GitHub Actions pinned by commit SHA with Dependabot
  updates; `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, issue
  templates; `docs/reference.md` (flags, exit codes, environment variables) and
  `docs/walkthrough.md` (reproducible end-to-end run); CI fetches full history
  so the live-repo tests run there; ruff `target-version = "py310"` with the
  `B` and `I` rule sets.

## v0.4.0 — tagged 2026-09-08, released 2026-09-09 (`verify-v1.3`, `init-v6`, spec 3.6.0)

- **Security:** closed a PR-gate bypass in the verifier — a line break inside a
  trade-off could smuggle a second `Signoff-Reviewed-Tree-SHA` that anchored
  an unreviewed tree. One attestation now carries each single-valued trailer
  exactly once; notes are judged block by block; merged-note anchoring is
  scoped to the annotated object. New conformance vector
  `invalid-duplicate-reviewed-tree-sha.txt`.
- **Changed** the repository name to `jerrylin96/git-signoff` (old URLs
  redirect) and the import package to `git_signoff`.
- **Removed** the MCP server, the PyPI publish path, console scripts, the
  `mcp` dependency, and the duplicated `init.py`. Nothing is installed by name.
- **Fixed** five initializer defects (rollback ordering, symlink refusal,
  mutation boundary, staged-path guard, ruleset warning on rollback) and
  added Python-floor guards to `init.py` and the verifier.
- CI now runs on Python 3.10 and 3.13.

## init-v5, init-v4, init-v3, init-v2, init-v1 — 2026-08-25 to 2026-09-04

Initializer pins between releases: multi-harness destination resolution
(`--skill-target`), Policy A validation (symlinks, ignored destinations,
unrelated directories), atomic rollback of partial setups, the
`VENDORED-FROM` provenance stamp, and the single-destination hint.

## verify-v1.2 — 2026-08-21

- **Added** native verification of 2-parent merge commits: the merge tree
  must equal `git merge-tree --write-tree HEAD^1 HEAD^2` and the PR head must
  be attested.

## verify-v1.1 — 2026-08-20

- **Fixed** a bug that could destroy attestation notes created but not yet
  pushed: origin's notes were fetched straight into `refs/notes/signoff`. The
  verifier now fetches into its own mirror ref (`refs/notes/signoff-verify`).

## v0.3.0 — 2026-08-06 (`verify-v1` on 2026-08-18, spec 3.5.0)

- **Added** the badge and CI verifier check (`verify/`), the notes-recovery
  workflow, the project website, the transcript-escrow spec
  (`gsa-escrow.md`), the Community Specification License for spec documents,
  conformance vectors, and the in-toto predicate draft.
- **Added** `--audit` / `--export` to the verifier for the auditor–reviewer
  transcript loop.

## v0.2.0 — 2026-08-05

- **Added** repo-local interview profiles (`.signoff/profile.md`, now
  `.git-signoff/profile.md`), the default-on science-detection guard, and
  profile provenance digests in `Signoff-Agent`.

## v0.1.0 — 2026-08-05

- First tagged release: GSA v1.0 trailers, harness adapters (Antigravity,
  Claude Code with worktree fallback, generic file), signed empty attestation
  commits, `refs/notes/signoff` dual persistence, the `Signoff-Agent`
  provenance trailer, named interview intensity levels, and the MCP server
  (since removed).
