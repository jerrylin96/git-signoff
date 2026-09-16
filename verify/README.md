# attested by humans — GSA verifier check & badge

A GitHub Actions check that verifies **Git Signoff Attestations** — the
machine-parsable records `/git-signoff` writes after a human passes a Socratic
comprehension interview about a diff — against your repository's history,
plus a README badge that shows the check is green.

Attestations are verified per the
[GSA v1.0 spec](../skills/git-signoff/specs/gsa-core.md) §5.1 lookup order:
git notes (`refs/notes/signoff`) on the commit and its tree, `[SIGNOFF *]`
attestation commits in the log, and the tree-SHA fallback that survives
squash merges.

## Install (60 seconds)

### Option A: Zero-touch 1-line setup (Recommended)

Run inside your repository root:
```bash
curl -fsSL https://raw.githubusercontent.com/jerrylin96/git-signoff/init-v7/init.py -o /tmp/signoff-init.py && python3 /tmp/signoff-init.py
```

This automatically scaffolds the workflow, selects your domain interview profile, configures the README badge, configures GitHub ruleset protection, and creates a setup branch ready for `/git-signoff`.

---

### Option B: Manual Setup

**1.** Add `.github/workflows/git-signoff.yml` to your repository:

```yaml
name: attested by humans

on:
  pull_request:
  push:
    branches: [ main ]

jobs:
  verify-signoff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history — attestations live in it
      - uses: jerrylin96/git-signoff/verify@verify-v1.5
```

**2.** (Recommended) Enforce signoff before merge with the preconfigured GitHub Ruleset:
Download [`ruleset.json`](ruleset.json) and import it into your repository via **Settings → Rules → Rulesets → Import a ruleset**. The ruleset enforces strict status checks, requiring branches to be up to date with the default branch so the verified attestation state never goes stale.

**3.** Add the badge to your README:

```markdown
[![attested by humans](https://github.com/OWNER/REPO/actions/workflows/git-signoff.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/git-signoff.yml)
```

Done. Pull requests now fail the check until the branch ends in a valid
attestation (run `/git-signoff` before merging), and your default branch badge
reads **attested by humans: passing**.

Pin tags do not move. Backward-compatible fixes ship as new `verify-v1.x`
tags; a breaking change to the action's inputs or pass criteria would ship
as `verify-v2`. Tracking `@main` works but couples your CI to this
repository's development pace.

**Stale-pin warning.** Since `verify-v1.4` the verifier lists this
repository's `verify-v*` tags after fetching notes and prints one line on
stderr (visible in the CI log; stdout stays the verdict) when a newer pin exists:

```text
warning: verifier pin verify-v1.5 is behind verify-v1.6; see verify/README.md
```

It never changes the verdict, is skipped silently when the network is
unavailable, and can be turned off with `GIT_SIGNOFF_NO_UPDATE_CHECK=1`.

> **If you pinned `@verify-v1` through `@verify-v1.4`, move to `@verify-v1.5`.**
> `verify-v1.5` makes the log lookup judge attestation *commits* by their
> objects, not their trailers (an empty `[SIGNOFF]` commit naming a target's
> tree no longer passes that target; a rebased attestation commit no longer
> counts in history mode), adds `--scan-refs` so a squash or rebase merge
> passes head mode via the merged pull request's head, and makes `auto` mode
> `head` on every event, so an adopter with unattested history starts red
> until the first attestation lands (the failure line names the command).
> `verify-v1.4` moves the verifier into the skill folder
> (`skills/git-signoff/verify_signoff.py`, vendored into every adopter
> repository, so `--audit` runs locally without a download and the producer
> helper `attest.py` self-checks every attestation it writes), renames the
> `--audit` override to `GIT_SIGNOFF_TRANSCRIPT_FILE`, and adds the stale-pin
> warning described below. `verify-v1.3` closed a PR-gate bypass: earlier verifiers accepted an
> attestation whose single-valued trailers appeared twice, so a line break
> smuggled into a trade-off could carry a second `Signoff-Reviewed-Tree-SHA`
> that made a later, unreviewed commit pass as attested. One attestation now
> carries each single-valued trailer exactly once (gsa-core §2.3), notes are
> judged block by block (so re-attesting a commit first without and then with
> a transcript no longer fails the squash-merge check), and the verifier exits
> with a clear message below Python 3.10. Earlier history: `verify-v1`
> predates a fix for a bug that could destroy attestation notes you had
> created but not yet pushed (origin's notes were fetched directly into
> `refs/notes/signoff`); `verify-v1.2` added native 2-parent merge commit
> provenance verification. Because pins never move, earlier pins keep running
> older behavior until you re-pin.

## What it checks

| Event | Mode | Passes when |
|---|---|---|
| every event (default `mode: auto`, since `verify-v1.5`) | `head` | The target commit is (or carries) a valid attestation: an **empty** attestation commit attesting its own parent's commit and tree — the normal shape of a branch ending in `/git-signoff`; a non-empty attestation commit fails, so trailers cannot smuggle unreviewed changes — a note on the commit or its tree, a *sound* attestation commit in its history or under `scan-refs` whose earned anchor matches (see below), or (for a 2-parent PR merge commit) a clean 3-way merge (`git merge-tree --write-tree HEAD^1 HEAD^2`) where the merged PR branch head `HEAD^2` is validly attested. On `push`, the badge therefore means "the current tip of this branch is attested", not "this repository has used the tool". |
| explicit `mode: history` | `history` | The ref's history carries at least `require` (default 1) valid attestations — notes, and attestation commits that corroborate their trailers. |

**Evidence, not trailers (`verify-v1.5`).** An attestation *commit* found by the
log lookup counts only if the commit object corroborates its trailers: exactly
one parent, empty (its tree is the parent's), and that parent is the declared
reviewed commit; its declared tree anchors only when it is the parent's actual
tree. Without this, an empty `[SIGNOFF]` commit on an unrelated tree whose
trailer named some target's tree passed that target. A consequence for
history mode: a rebased attestation commit (parent rewritten) is reported,
not counted — re-run `/git-signoff` after a rebase, as head mode always
required.

**`scan-refs` (`verify-v1.5`).** On `push`, `auto` asks the API for the merged
pull request from *this* repository whose merge commit is the target, fetches
exactly its `refs/pull/N/head`, and lets a sound attestation there anchor the
target by tree. That is what makes a squash or rebase merge pass head mode
even when the interview ran in a cloud session whose notes push was refused.
A match by tree establishes that the same tracked code state was attested,
not that this pull request, base, or interview context was reviewed. Fork
pull requests are never fetched by `auto`; broader evidence is an explicit
`scan-refs` value you choose. Requires the `gh` CLI (present on GitHub
runners) and the workflow token; without them nothing is scanned.

### Supported Merge Strategies

`verify_signoff.py` supports standard Git / GitHub merge workflows:

- **Standard PR Merge (2-parent merge commit)**: When merging via GitHub's "Create a merge commit" button (or `git merge --no-ff`), `mode: head` verifies that `HEAD^{tree}` cleanly matches `git merge-tree --write-tree HEAD^1 HEAD^2` and that `HEAD^2` was validly attested. Any manual conflict resolution or unreviewed changes introduced during merge cause verification to fail.
- **Fast-Forward Merge**: Preserves the attestation commit directly at the branch tip, passing `mode: head`.
- **Squash Merge**: In `mode: head`, the squashed tip passes when its tree was attested — via the note on the reviewed **tree** (gsa-core §2.5) or, since `verify-v1.5`, via the merged pull request's head under `scan-refs` — which holds when the base branch has not advanced. If the base has advanced, the squashed tree combines base and branch changes (a new code state), requiring `/git-signoff` to be re-run on the updated branch before merge.
- **Rebase Merge**: GitHub drops intentionally empty commits during rebase-and-merge, so the attestation commit itself does not land; the rebased tip passes `mode: head` only via the reviewed tree (note or `scan-refs`), which holds when the base has not advanced. Rebasing onto an advanced base rewrites the code state, requiring `/git-signoff` to be re-run on the rebased branch before merge.

Override with inputs:

```yaml
      - uses: jerrylin96/git-signoff/verify@verify-v1.5
        with:
          mode: history      # or: head (the default on every event)
          target: main       # commit (head) or ref (history)
          require: '1'       # history mode: minimum valid attestations
          scan-refs: auto    # head mode: auto | none | explicit refs (see above)
```

The verifier is a single stdlib-only Python file
([`skills/git-signoff/verify_signoff.py`](../skills/git-signoff/verify_signoff.py))
— no dependencies beyond git and Python 3.10+. It ships inside the skill
folder, so every repository that vendored `/git-signoff` already has it at
`.claude/skills/git-signoff/verify_signoff.py` (or `.agents/…`) for local
`--mode head` and `--audit` runs; the composite action in this directory runs
that same file. Copy it into any CI system; GitHub Actions is just the
packaged path.

Running it is non-destructive to your signoff notes: it fetches origin's
notes into an isolated mirror (`refs/notes/signoff-verify`) and never writes
to `refs/notes/signoff` — ensuring any unpushed local attestations remain
intact and verifiable (gsa-core §5.1).

## Auditing & retrieving interview transcripts

Git signoff attestations bind the interview transcript's SHA-256 digest (`Signoff-Transcript-Digest`) into immutable git history and notes. Transcripts remain locally on the reviewer's laptop for privacy and security. Anyone — leads, reviewers, compliance auditors — can verify or audit the transcript at any time using the verifier CLI.

### The 3-Step Verification Loop (Auditor $\leftrightarrow$ Reviewer)

```text
Auditor (Lead / Compliance)                  Reviewer (Employee)
           │                                          │
           │  1. Request transcript snapshot          │
           │  (quotes commit or PR)                   │
           ├─────────────────────────────────────────>│
           │                                          │  2. Export snapshot:
           │                                          │     verify_signoff.py --audit HEAD
           │                                          │       --export transcript.jsonl
           │  3. Send transcript.jsonl                │
           │<─────────────────────────────────────────┤
           │                                          │
           │  4. Verify against git trailers:         │
           │     GIT_SIGNOFF_TRANSCRIPT_FILE=transcript.jsonl
           │     python3 verify_signoff.py --audit HEAD
           │                                          │
           │  Output: ✅ VALID MATCH                   │
```

#### Step 1: Auditor requests transcript
The auditor identifies the attestation on the commit or PR (e.g. `[SIGNOFF 979cb45]`) and asks the reviewer to export the session transcript.

#### Step 2: Reviewer exports transcript
On the machine where the signoff interview occurred, the reviewer runs the verifier CLI with `--audit` and `--export`:
```bash
python3 .claude/skills/git-signoff/verify_signoff.py --audit HEAD --export /tmp/transcript.jsonl
```
The verifier resolves the local transcript for the harness (`claude-code`, `antigravity-cli`, `codex-cli`, etc.), checks that the first $N$ bytes match the `Signoff-Transcript-Digest` trailer, and writes the snapshot to the specified path:
```text
✅ VALID MATCH: Transcript SHA-256 matches sha256:1675b6...
  Harness: claude-code
  Conversation ID: 979cb45-session
  Bytes verified: 8432
  Exported snapshot to: /tmp/transcript.jsonl
```
The reviewer sends `/tmp/transcript.jsonl` to the auditor.

#### Step 3: Auditor verifies snapshot against git trailers
The auditor points `GIT_SIGNOFF_TRANSCRIPT_FILE` at the received file and audits the target commit:
```bash
GIT_SIGNOFF_TRANSCRIPT_FILE=/tmp/transcript.jsonl python3 .claude/skills/git-signoff/verify_signoff.py --audit HEAD
```
The verifier recomputes the SHA-256 digest and confirms it matches the git attestation byte-for-byte.

## What a green badge means — and doesn't

Green means: a human answered a Socratic interview about this code in their
own words, acknowledged its named trade-offs and risks, and accepted
accountability — and the record of that survives in git, tamper-evident.
It does **not** mean the code is correct; it means a named human
understands it. That is exactly the claim, no more.

Two enforcement caveats. First, the check is advisory until you enforce
it on your default branch via branch protection or by importing
[`ruleset.json`](ruleset.json) (**Settings → Rules → Rulesets → Import a
ruleset**) — without that, a red check does not block the merge button.
Second, unsigned trailers are self-attested: they verify that a
structurally valid GSA record binds to this exact code state, not who wrote
it. Where independent identity assurance matters, combine the gate with
signed attestation commits (`git commit -S`, GSA §2.4) and your platform's
signature verification.
