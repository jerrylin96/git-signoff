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
| `--skill-target {auto,claude,agents,both}` | Where to vendor the skill: `.claude/skills/git-signoff`, `.agents/skills/git-signoff`, or both. `auto` reads repository markers; a greenfield repo prompts (non-interactive: both). Existing installs are always re-vendored. |
| `--skill-source PATH` | Vendor from a local `skills/git-signoff/` folder instead of cloning the pin tag (offline installs). |
| `--skip-ruleset` | Do not write `.git-signoff/ruleset.json` or try `gh` to create the GitHub ruleset. |
| `--skip-badge` | Do not inject the README badge. |
| `--allow-dirty` | Permit unrelated unstaged/untracked work. Pre-staged changes and any state under managed paths are still refused. |
| `--non-interactive` | No prompts; defaults everywhere. |
| `--open-browser` | Open the GitHub rules settings page when ruleset automation falls back to manual. |
| `--verbose` | On error, print the exception type and traceback. |

Files written (all under the repository root): `.github/workflows/git-signoff.yml`,
`.git-signoff/profile.md`, `.git-signoff/ruleset.json`, `README.md` (badge),
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
attest.py prepare  [--reference REF] [--json]
attest.py commit   --email EMAIL --level {cursory,standard,skeptical}
                   [--tradeoff T]... [--risk R]... [--summary TEXT] [--model ID]
                   [--reference REF] [--ack-no-transcript] [--no-sign]
                   [--dry-run] [--no-push] [--json]
attest.py marker   [--reference REF]
attest.py --version
```

### `prepare`

Refuses a dirty tree (exit 3). Resolves HEAD as the reviewed commit, the
reference (`--reference`, else `HEAD@{upstream}` when it is behind HEAD — after
`git push -u origin <feature>` the upstream is the branch's own remote
counterpart and is skipped with a warning — else `main`/`master`/`origin/main`/
`origin/master` with a warning; an explicit reference that already contains
HEAD is honored with an empty-range warning; on `main`/`master` itself with no
usable base, exit 2), the merge-base,
and the tree. Prints:

| Field | Meaning |
|---|---|
| `reviewed_commit_sha`, `base_sha`, `tree_sha`, `reference` | The SHAs the attestation will carry. |
| `diff_command`, `name_status`, `shortstat` | How to read the range and its summary. |
| `profile` | `source` (`env-override`, `repo-local`, `embedded-default`), `path`, `id`, 12-hex `digest` (file-sourced only), `fallback_reason` when a file-sourced profile was malformed. |
| `science_signals` | Categories from the science-detection guard found in the diff. |
| `transcript` | `harness_id`, `conversation_id`, `available`, `path` — informative; the binding snapshot happens in `commit`. |
| `hints` | `changed_files`, `executable_files`, `executable_lines_changed` (excludes docs, tests, lockfiles, binaries), `tier2_triggers` (path/content matches: `security-auth`, `schemas-migrations`, `public-api-contracts`, `scientific-computation`, `executable-blast-radius`). Informative; the agent classifies. |
| `marker` | `GSA-APPROVAL <reviewed-sha> <utc-timestamp>` — the line the agent emits after approval. |
| `warnings` | Also printed to stderr. |

### `commit`

Validates arguments (exit 2): `--email` contains `@`; every `--tradeoff`,
`--risk`, `--email`, and `--model` is one line with no carriage return;
`--summary` may span lines but none may match `^Signoff-[A-Za-z0-9-]+:`;
`--model` matches `[A-Za-z0-9._:/-]+`. Re-runs `prepare`. Resolves the
transcript adapter and reads the bytes **once**; every later check uses that
snapshot.

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
branch is never pushed by the helper.

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
| 3 | Stale or dirty: unstaged or staged changes; HEAD moved since prepare (marker names an ancestor). |
| 4 | Transcript problem: unavailable without `--ack-no-transcript`; marker not found; marker for an unrelated commit. |
| 5 | `GIT_SIGNOFF_PROFILE_FILE` set but unreadable. A malformed repo-local profile is *not* an error (falls back, reported). |
| 6 | git failure (rev-parse, commit, notes append). |
| 7 | Self-check failure; anything written has been removed. |

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
composite action `jerrylin96/git-signoff/verify@verify-v1.4`.

```
verify_signoff.py [--repo PATH] [--mode {head,history}] [--target REV] [--require N]
verify_signoff.py --audit [COMMIT] [--export PATH] [--repo PATH]
verify_signoff.py --version
```

| Flag | Effect |
|---|---|
| `--repo PATH` | Repository to verify (default `.`). |
| `--mode head` | PR gate (default): `--target` (default `HEAD`) must be a valid **empty** attestation commit attesting its parent's commit and tree; or be covered by a note on its commit or tree, a `[SIGNOFF *]` commit in its history, or (for a 2-parent merge) a clean `merge-tree` whose PR head is attested. |
| `--mode history` | Badge check: `--target` (a ref) must reach at least `--require` (default 1) structurally valid attestations, counting notes and commits, deduplicated by reviewed commit. |
| `--audit [COMMIT]` | Re-hash the local transcript for the attestation covering `COMMIT` (default `HEAD`) against `Signoff-Transcript-Digest` over the first `Signoff-Transcript-Bytes` bytes. The transcript is resolved from the harness id and conversation id, or from `GIT_SIGNOFF_TRANSCRIPT_FILE`. |
| `--export PATH` | With `--audit`: write the audited byte snapshot to `PATH`. |
| `--version` | Prints the pin (`verify-v1.4`). |

Before checking, the verifier fetches `origin`'s notes into its own mirror
ref `refs/notes/signoff-verify` and never writes `refs/notes/signoff`, so an
unpushed local attestation survives verification. Then it lists this
repository's `verify-v*` tags and prints
`warning: verifier pin verify-v1.4 is behind verify-vX.Y; see verify/README.md`
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
`main`, because cloud sessions cannot push notes refs. Idempotent. Tests:
`scripts/tests/test_recover_notes.py`.
