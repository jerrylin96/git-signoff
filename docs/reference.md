# Functionality reference

What the three scripts do, their flags, exit codes, and environment variables.
All three are standard-library Python 3.10+ and shell out to `git`. Behavior
is pinned by the tests named at the end of each section.

- [`init.py`](#initpy--repository-initializer) — sets a repository up once.
- [`attest.py`](#attestpy--producer) — writes an attestation (called by the
  agent running `/git-signoff`).
- [`verify_signoff.py`](#verify_signoffpy--verifier) — checks attestations
  (CI gate, badge, local audit).

The agent-facing workflow that ties them together is
[`skills/git-signoff/SKILL.md`](../skills/git-signoff/SKILL.md); a runnable
end-to-end example is [`walkthrough.md`](walkthrough.md).

---

## `init.py` — repository initializer

```bash
curl -fsSL https://raw.githubusercontent.com/jerrylin96/git-signoff/init-v7/init.py -o /tmp/signoff-init.py
python3 /tmp/signoff-init.py [options]
```

Run inside the repository to set up. Creates a branch, scaffolds the CI
workflow, an interview profile, the ruleset JSON, and a README badge, vendors
the skill folder, and commits — atomically: any failure rolls the repository
back to the state it found.

| Flag | Effect |
|---|---|
| `--profile {domain-science,software-general}` | Interview profile written to `.git-signoff/profile.md`. Default: recommended from the repository's manifests and notebooks, confirmed interactively. |
| `--branch NAME` | Setup branch (default `git-signoff/init`; a timestamp suffix is added if it exists). |
| `--integration-branch NAME` | The branch pull requests merge into. Written to `.git-signoff/config.json` and used for the workflow's push filter, the ruleset's target (`refs/heads/NAME`), the setup branch's base, and `attest.py`'s fallback reference. Default: detected (`origin/HEAD`, else a candidate list), confirmed interactively. An installed GitHub ruleset that targets a different branch is reported with the manual step, never edited. |
| `--skill-target {auto,claude,agents,both}` | Where to vendor the skill: `.claude/skills/git-signoff`, `.agents/skills/git-signoff`, or both. `auto` reads repository markers; a greenfield repo prompts (non-interactive: both). Existing installs are always re-vendored. |
| `--skill-source PATH` | Vendor from a local `skills/git-signoff/` folder instead of cloning the pin tag (offline installs). |
| `--skip-ruleset` | Do not write `.git-signoff/ruleset.json` or try `gh` to create the GitHub ruleset. |
| `--skip-badge` | Do not inject the README badge. |
| `--allow-dirty` | Permit unrelated unstaged/untracked work. Pre-staged changes and any state under managed paths are still refused. |
| `--non-interactive` | No prompts; defaults everywhere. |
| `--open-browser` | Open the GitHub rules settings page when ruleset automation falls back to manual. |
| `--verbose` | On error, print the exception type and traceback. |

Files written (all under the repository root): `.github/workflows/git-signoff.yml`,
`.git-signoff/profile.md`, `.git-signoff/config.json` (`{"integration_branch":
NAME}`), `.git-signoff/ruleset.json` (rendered for that branch; the portable
`verify/ruleset.json` template keeps `~DEFAULT_BRANCH`), `README.md` (badge),
and the skill folder(s) with a `VENDORED-FROM` stamp (source, ref, commit).

Exit status: `0` success, `1` any error (message on stderr; `--verbose` adds
the traceback). Untracked OS metadata (`.DS_Store`, `Thumbs.db`,
`desktop.ini`) does not count as a dirty tree.

Refusals (before any branch is created): not a git repository; staged
changes; dirty tree without `--allow-dirty`; a skill destination that is a
symlink, an ordinary file, git-ignored, holds ignored untracked files, or is
an unrelated non-empty directory; any scaffold path that passes through a
symlink.

Environment: none read by the initializer itself. `gh` is used when present
and authenticated; when it is not, the ruleset falls back to a manual import
URL and says why on stderr.

Tests: `tests/test_init.py`, `tests/test_ruleset.py`.

---

## `attest.py` — producer

Lives in the vendored folder (`.claude/skills/git-signoff/attest.py` or
`.agents/skills/git-signoff/attest.py`) next to `verify_signoff.py`, which it
imports by path. Run it from anywhere inside the repository; it uses
`git rev-parse --show-toplevel`.

```
attest.py prepare  [--target BRANCH] [--reference REF] [--json]
attest.py targets  [--reference REF] [--limit N] [--all] [--json]
attest.py commit   --email EMAIL --level {cursory,standard,skeptical}
                   [--tradeoff T]... [--risk R]... [--summary TEXT] [--model ID]
                   [--reference REF] [--ack-no-transcript] [--no-sign]
                   [--dry-run] [--no-push] [--json]
attest.py marker   [--reference REF]
attest.py --version
```

### `prepare`

**Target mode** (`--target BRANCH`, spelled `feature`, `origin/feature`, or
`refs/heads/feature`): fetches `origin/BRANCH` and reviews its tip. The
working tree is not consulted and need not be clean; the checkout supplies
only `.git-signoff/config.json` and the interview profile. Refused (exit 2)
for the integration branch and for a branch not on `origin`; exit 3 when
the tip is already an attestation. The reference skips the upstream step
below and starts at the integration branch. Output gains `target` and
`target_ref`.

**HEAD mode** (no `--target`): refuses a dirty tree (exit 3). Resolves HEAD as the reviewed commit and the
reference, in this order: `--reference`; `HEAD@{upstream}` when it is a strict
ancestor of HEAD (after `git push -u origin <feature>` the upstream is the
branch's own remote counterpart and is skipped with a warning); the
integration branch from `.git-signoff/config.json` (`origin/<name>`, then
`<name>`); the branch `origin/HEAD` points at; `main`, `master`,
`origin/main`, `origin/master` — each fallback with a warning. An explicit
reference that already contains HEAD is honored with an empty-range warning.
On the integration branch itself: an upstream that is a strict ancestor of
HEAD is the reviewer's own unpushed range and is attested as such; a diverged
upstream is exit 3 (reconcile first); nothing unpushed is exit 2 (there is no
range here — attest the branch under review). A malformed `config.json` is
exit 2, never a silent fallback. Then the merge-base
and the tree. Writes the preparation record `.git/git-signoff/prepared.json`
(per worktree: reviewed, base and tree SHAs, reference, timestamp, resolved
profile), which is the only state `commit` will attest. Prints:

| Field | Meaning |
|---|---|
| `reviewed_commit_sha`, `base_sha`, `tree_sha`, `reference` | The SHAs the attestation will carry. |
| `integration_branch` | From `.git-signoff/config.json`, else `origin/HEAD`, else null. |
| `diff_command`, `name_status`, `shortstat` | How to read the range and its summary. |
| `profile` | `source` (`env-override`, `repo-local`, `embedded-default`), `path`, `id`, 12-hex `digest` (file-sourced only), `fallback_reason` when a file-sourced profile was malformed. |
| `science_signals` | Categories from the science-detection guard found in the diff. |
| `transcript` | `harness_id`, `conversation_id`, `available`, `path` — informative; the binding snapshot happens in `commit`. |
| `hints` | `changed_files`, `executable_files`, `executable_lines_changed` (excludes docs, tests, lockfiles, binaries), `components` (distinct directories with executable changes; a root file counts as its own), `skeptical_min_probes` (`max(8, 4 + 2 × components)`, the Tier 2 floor SKILL.md applies to expansive ranges), `tier2_triggers` (path/content matches: `security-auth`, `schemas-migrations`, `public-api-contracts`, `scientific-computation`, `executable-blast-radius`). Informative; the agent classifies. |
| `marker` | `GSA-APPROVAL <reviewed-sha> <utc-timestamp>` — the line the agent emits after approval. |
| `record` | Path of the preparation record just written. |
| `warnings` | Also printed to stderr. |

### `targets`

Branches awaiting review: after `git fetch --prune`, every `refs/remotes/origin/*`
not merged into the base (`--reference`, else the integration branch —
neither: exit 2), excluding the base itself and tips whose subject is an
attestation, ordered by most recent committer date, ten by default (`--limit`,
`--all`). Each row: branch, short SHA, date, commits ahead, subject. An empty
list prints why (merged / attested / base counts). `--json`: `base`,
`base_source`, `integration_branch`, `candidates`, `total`, `truncated`,
`skipped`.

### `marker`

Prints the recorded `GSA-APPROVAL` line and nothing else. Read-only: with no
preparation record, or one whose reviewed commit is no longer HEAD, it exits 3
with the same message `commit` would give, plus a pointer to `prepare`. It
never re-prepares — that would let a refused commit be retried against the
moved HEAD without an interview of the new range.

### `commit`

Validates arguments (exit 2): `--email` contains `@`; every `--tradeoff`,
`--risk`, `--email`, and `--model` is one line with no carriage return;
`--summary` may span lines but none may match `^Signoff-[A-Za-z0-9-]+:`;
`--model` matches `[A-Za-z0-9._:/-]+`. Reads the preparation record (none →
exit 3: run `prepare` first) and re-verifies it: HEAD is the recorded reviewed
commit and its tree matches (else exit 3, naming both SHAs), the tree is clean
(exit 3), a `--reference` given here resolves to the same commit as the
recorded one (else exit 2), and the interview profile resolves to the recorded
source, id, and digest (else exit 3). The base, reference, and tree in the
trailers come from the record, never re-derived, so the attestation describes
the range the human saw even if the reference moved during the interview.
Then resolves the transcript adapter and reads the bytes **once**; every later
check uses that snapshot.

Then, in order: requires the approval marker in the last 64 KiB of the
snapshot with a SHA equal to HEAD (missing or for an unrelated commit → exit 4;
for an ancestor of HEAD → exit 3, the branch moved after prepare; one retry
after one second covers a slow harness flush); derives the status
(`VERIFIED_BY_HUMAN` with `sha256:<64 hex>` and the byte count, or with
`--ack-no-transcript` and no bytes `VERIFIED_BY_HUMAN_NO_TRANSCRIPT_DIGEST`
with `unavailable`/`unavailable`; no bytes without the flag → exit 4); builds
`Signoff-Agent` (`harness=<id>/<CLAUDE_CODE_VERSION|N/A> model=<ANTHROPIC_MODEL
| last "model" in the snapshot | --model | unavailable> reasoning=<CLAUDE_EFFORT|N/A>
interview=<level>/<profile-id>[/sha256:<digest>]`); builds the message and
runs the verifier's structural check on it (a failure here is a bug in the
helper → exit 7).

`--dry-run` prints the message and stops here (exit 0, nothing written; the
marker is not required because the dry run precedes approval).

**Target mode** (the record names a target; `--no-push` is exit 2): re-fetches
`origin/<target>` and requires it at the recorded tip (exit 3); builds the
attestation object with `git commit-tree` parented on it (`-S` when signing;
nothing references the object), checks its tree and parent (exit 7), runs
`check_head` on the object (exit 7, nothing published), appends the notes on
the reviewed commit and tree and pushes them (a refusal is a warning naming
the recovery dependency), then pushes the object to `refs/heads/<target>` with
`--force-with-lease=refs/heads/<target>:<reviewed>`. A rejected push is exit 3:
the branch is untouched, the object is unreferenced, and the notes — already
published — stand and are named. No local branch is updated; the
remote-tracking ref is refreshed. Output gains `target` and `branch_pushed`.

**HEAD mode:**

Otherwise: re-checks HEAD and the clean tree (exit 3), runs
`git commit --allow-empty [-S]` (`-S` when `user.signingkey` is set and
`--no-sign` is absent; a failing commit → exit 6, nothing written), verifies
the new commit's tree and parent (else removes it, exit 7), appends the
message as a note on the reviewed commit and on its tree (failure → notes
restored, commit removed, exit 6), runs `check_head` from the sibling
verifier on HEAD (failure → notes restored, commit removed, exit 7), and
unless `--no-push` fetches `origin`'s notes into `refs/notes/signoff-remote`,
merges with `cat_sort_uniq`, and pushes `refs/notes/signoff`. A refused push
is reported (`notes_pushed: false`, reason) and the exit is still 0. The
branch is never pushed by the helper. A successful commit removes the preparation
record; a refusal keeps it, and the next `prepare` overwrites it.

Output (`--json`: one object; otherwise labeled lines): `attestation_sha`,
`status`, `transcript_digest`, `transcript_bytes`, `transcript_path`,
`marker_found`, `message`, `signed`, `noted_shas`, `notes_pushed`,
`notes_push_reason`, `notes_merged_remote`, `verifier` (the PASS lines),
`warnings`. On failure in `--json` mode: `{"ok": false, "exit_code": N,
"error": "..."}` on stdout and the message on stderr.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. A refused notes push is reported, not fatal. |
| 2 | Usage or argument error, including unsafe free text; `--reference` that does not resolve; no default reference; missing sibling `verify_signoff.py`. |
| 3 | Stale or dirty: no preparation record (`prepare` has not run); HEAD or its tree differs from the record; the interview profile changed since `prepare`; unstaged or staged changes; the marker names an ancestor of HEAD; HEAD (or the target's tip) is already an attestation commit; target mode: `origin/<target>` moved since `prepare`, or the lease push was rejected (notes already published stand). |
| 4 | Transcript problem: unavailable without `--ack-no-transcript`; marker not found; marker for an unrelated commit. |
| 5 | `GIT_SIGNOFF_PROFILE_FILE` set but unreadable. A malformed repo-local profile is *not* an error (falls back, reported). |
| 6 | git failure (rev-parse, commit, notes append). |
| 7 | Self-check failure; anything written has been removed. If a rollback step itself fails, the message says `ROLLBACK INCOMPLETE` and names the step instead of claiming a clean state. |

### Environment

| Variable | Read by | Effect |
|---|---|---|
| `GIT_SIGNOFF_TRANSCRIPT_FILE` | `attest.py`, `verify_signoff.py --audit` | Transcript file; takes precedence over every harness adapter (`generic-file`). |
| `ANTIGRAVITY_CONVERSATION_ID` | `attest.py` | `~/.gemini/antigravity-cli/brain/<id>/.system_generated/logs/transcript.jsonl` |
| `CLAUDE_CODE_SESSION_ID` | `attest.py` | `~/.claude/projects/<slug of repo root>/<id>.jsonl`, falling back to the primary root of a linked worktree via `git rev-parse --git-common-dir`. Also scopes `CLAUDE_CODE_VERSION` and `CLAUDE_EFFORT` into `Signoff-Agent`. |
| `CODEX_SESSION_ID`, `CODEX_HOME` | `attest.py` | Newest `$CODEX_HOME/sessions/**/rollout-*-<id>.jsonl` (default `~/.codex`). |
| `ANTHROPIC_MODEL` | `attest.py` | Model id for `Signoff-Agent`; else the last `"model"` field in the snapshot; else `--model`; else `unavailable`. |
| `GIT_SIGNOFF_PROFILE_FILE` | `attest.py` | Interview profile override; unreadable → exit 5. Otherwise `<root>/.git-signoff/profile.md`, else the embedded default. |
| `GIT_SIGNOFF_VERIFIED_BY` | the agent (SKILL.md) | First choice for the proposed `--email`; then `CLAUDE_CODE_USER_EMAIL`; then `git config user.email` on local harnesses. |

Tests: `scripts/tests/test_attest.py`, `test_attest_adapters.py`,
`test_attest_profile.py`, `test_attest_notes_merge.py`,
`test_production_vector.py`.

---

## `verify_signoff.py` — verifier

Same file at `skills/git-signoff/verify_signoff.py` (vendored) and behind the
composite action `jerrylin96/git-signoff/verify@verify-v1.5`.

```
verify_signoff.py [--repo PATH] [--mode {head,history}] [--target REV] [--require N] [--scan-refs REF ...]
verify_signoff.py --audit [COMMIT] [--export PATH] [--repo PATH]
verify_signoff.py --version
```

| Flag | Effect |
|---|---|
| `--repo PATH` | Repository to verify (default `.`). |
| `--mode head` | PR gate (default): `--target` (default `HEAD`) must be a valid **empty** attestation commit attesting its parent's commit and tree; or be covered by a note on its commit or tree, a *sound* `[SIGNOFF *]` commit in its history or under `--scan-refs` (one parent, empty, parent is the declared reviewed commit; the declared tree anchors only when it is the parent's tree), or (for a 2-parent merge) a clean `merge-tree` whose PR head is attested. |
| `--mode history` | Badge check: `--target` (a ref) must reach at least `--require` (default 1) valid attestations — notes, and attestation commits that corroborate their trailers (a rebased attestation commit does not) — deduplicated by reviewed commit. |
| `--scan-refs REF ...` | Head mode: also consider sound attestation commits reachable from these refs (patterns expand via `for-each-ref`); a tree match proves the same code state was attested, not that this PR, base, or interview was reviewed. The composite action passes the merged same-repository pull request's head for the target; the verifier trusts no ref it was not given. |
| `--audit [COMMIT]` | Re-hash the local transcript for the attestation covering `COMMIT` (default `HEAD`) against `Signoff-Transcript-Digest` over the first `Signoff-Transcript-Bytes` bytes. The transcript is resolved from the harness id and conversation id, or from `GIT_SIGNOFF_TRANSCRIPT_FILE`. |
| `--export PATH` | With `--audit`: write the audited byte snapshot to `PATH`. |
| `--version` | Prints the pin (`verify-v1.5`). |

Before checking, the verifier fetches `origin`'s notes into its own mirror
ref `refs/notes/signoff-verify` and never writes `refs/notes/signoff`, so an
unpushed local attestation survives verification. Then it lists this
repository's `verify-v*` tags and prints
`warning: verifier pin verify-v1.5 is behind verify-vX.Y; see verify/README.md`
on stderr when a newer pin exists (never changes the verdict; stdout carries
only the verdict; silent on network failure).

Exit status: `0` pass, `1` fail (the reason is on stdout; a failed notes
fetch is named so "attested but unreachable" is not mistaken for "never
attested").

| Variable | Effect |
|---|---|
| `GIT_SIGNOFF_TRANSCRIPT_FILE` | `--audit` reads this file instead of the harness path. |
| `GIT_SIGNOFF_NO_UPDATE_CHECK=1` | Skip the stale-pin warning. |
| `GIT_SIGNOFF_PIN_REMOTE` | Repository URL queried for `verify-v*` tags (tests point it at a local bare repo). |
| `CODEX_HOME`, `HOME` | Transcript resolution for `--audit`. |

Composite action inputs (`verify/action.yml`): `mode` (`auto` = `head` on
`pull_request`, else `history`), `target`, `require`.

Tests: `scripts/tests/test_verify_signoff.py`,
`scripts/tests/test_conformance_vectors.py`.

---

## `scripts/recover_notes.py` — notes recovery (this repository's CI)

Rebuilds `refs/notes/signoff` from the `[SIGNOFF *]` commits reachable from
`--ref` plus any `--payload-file` attestations whose objects no longer exist
locally. Run by `.github/workflows/notes-recovery.yml` on every push to
`main`, because cloud sessions cannot push notes refs. Idempotent.

A note is attached only where the commit object backs the trailer's claim.
A commit-sourced payload earns its reviewed-commit anchor when the
attestation commit has exactly one parent, is empty (its tree is the
parent's), and that parent is the declared reviewed commit; it earns its
tree anchor only if the declared tree is the parent's actual tree (else the
note goes on the commit alone, reported as `tree-only-skip`). Anything else
is skipped loudly. Without this, a `[SIGNOFF]` commit on an unrelated tree
whose trailer named some target's tree would mint a tree note and turn that
unattested target green in every verifier. Payload files are trusted as
given: they exist for attestations whose objects are gone and are committed
to this repository. Tests: `scripts/tests/test_recover_notes.py`.
