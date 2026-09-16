# Design: attest any target, from anywhere

**Status:** Implemented on branch `claude/joss-submission-prep-pmfto5`
(2026-09-16), in the slices of §5, after external review found no remaining
design blockers. Release gate before `verify-v1.5` is tagged: the Actions
fetch check in §2.13's pre-implementation list. Revised five times after
three review passes that reproduced failures against the code as it was;
the fixes those passes prompted (§2.12, §2.13) shipped first, the feature
slices after.
§2 holds positions settled in the first pass; §3 holds the items that were
open, each now carrying a decision and the reasoning, with the rejected
alternatives kept so a reviewer can disagree with something concrete.
The decision rule applied throughout §3: judge by the broadest set of
adopters (most often one researcher with an agent in one checkout), not
by any single team's habits; prefer the option that adds no protocol
surface; decide now when reversal is cheap. This document is the change
list for `gsa-core.md` 3.8.0, `SKILL.md`, `attest.py`, `init.py`, and
the verify workflow.

**Origin:** a reviewer who works from the integration branch (`dev`) tried
`/git-signoff` and found it hard to use. The skill assumes the reviewer has
the feature branch checked out, because the producer writes the attestation
commit at HEAD. Separately, the tool decides what "the integration branch"
is in three places that can disagree.

---

## 1. The problem, precisely

Two independent defects and one product question.

1. **Reviewer location is coupled to record location.** The attestation
   must end up as the last commit on the branch being merged (the PR-gate
   check reads it there). `attest.py` achieves that by committing at HEAD,
   so the interview can only run with the feature branch checked out. The
   protocol does not require this: trailers, notes, and the verifier all
   key on the reviewed commit and tree, not on where the reviewer sat.
2. **Three answers to "which branch is the integration branch".**
   `init.py` detects one (origin/HEAD, else a candidate list that includes
   `dev`) and writes it only into the workflow's `push:` filter. The
   shipped `ruleset.json` targets `~DEFAULT_BRANCH`, GitHub's notion,
   which is often `main` even when the team integrates on `dev`.
   `attest.py` falls back to `main`/`master` only, so on a `dev`-based
   repository with no usable upstream it silently diffs against the wrong
   base.
3. **Mixed teams.** Some people merge through pull requests, others push
   to the integration branch directly. The gate can block the first group
   and only warn the second. Whether and how to support both is a product
   decision, not a mechanics one.

## 2. Settled

### 2.1 Decouple the target from HEAD

`/git-signoff [<branch>]` attests the tip of `<branch>`. With no argument it
attests HEAD, exactly as today. Nothing changes for current users.

- **Interview range:** `merge-base(<integration>, <target>)..<target>`.
- **Record:** the same empty attestation commit, parented on the target
  tip, plus the same notes on the reviewed commit and tree. Created with
  plumbing (`git commit-tree`, which accepts `-S` for signing).
- **What the checkout is used for:** the reviewed code comes from the
  target ref, never from the working tree. The checkout supplies only
  the repository-level inputs: `.git-signoff/config.json` and
  `.git-signoff/profile.md` (the integration branch's policy, which is
  the right one to hold a feature branch to). Neither the worktree nor
  the index is modified, and the preparation record (§2.12) lives under
  the git dir, not in the tree.
- **Verifier:** the head-mode shape is unchanged — the attestation is
  still the last commit of the branch under review and passes as it does
  now. `verify-v1.5` adds the bounded cross-history lookup of §2.13, with
  its own conformance vectors.
- **Trailers and notes (gsa-core §2):** unchanged. §5.1 gains the
  sentence in §4 below about what a cross-history match establishes.

### 2.2 On the integration branch with no argument: list

When HEAD is the integration branch and no target is given, the producer
first applies §2.4: after a fetch, if the upstream is a strict ancestor of
HEAD, the range is the reviewer's own unpushed commits and the bare command
attests HEAD as today. If HEAD and its upstream have diverged, that is an
error naming both SHAs (the reviewer must reconcile before anything is
attested). Only when HEAD equals its upstream does the producer list: it
does not refuse and does not guess. Candidates are **fetched remote
branches** (`refs/remotes/origin/*`, including those with no local
branch, or the original reviewer-location problem returns), not merged
into the integration branch, excluding the integration branch itself and
branches whose tip is already an attestation, ordered by most recent
commit. An empty list is reported as such (§3.8).

### 2.3 One integration branch, chosen once, read everywhere

`init.py` confirms a single branch name (default: what it detects today)
and persists it in `.git-signoff/config.json`. Three consumers read it:
the scaffolded workflow's `push:` filter, `ruleset.json`'s `ref_name`
include (an explicit `refs/heads/<name>` instead of `~DEFAULT_BRANCH`),
and `attest.py` as its fallback reference. An adopter repository with no
config file resolves as §2.10 describes: today's behaviour plus the new
`origin/HEAD` step, which is a documented change for repositories whose
default branch is neither `main` nor `master`. Re-running the initializer
is optional; it is what writes the config file.

JSON rather than TOML because the documented Python floor is 3.10 and
`tomllib` arrived in 3.11.

**Migrating an installed ruleset.** Writing the config and rendering
`ruleset.json` does not touch a ruleset GitHub already has: today
`setup_ruleset()` returns as soon as one named "Signoff Enforcement"
exists. A team re-running the initializer to choose `dev` would get a
`dev` workflow and producer while GitHub still protects `main`, which is
the inconsistency this section exists to remove. First version: when the
installed ruleset's `ref_name` include does not match the configured
branch, the initializer reports the mismatch and prints the manual step
(the settings URL and the rendered JSON). Reconciling in place via the
API, preserving `bypass_actors` and any unrelated rules, is a later step
once there is an adopter who needs it; it is easy to get wrong silently.

### 2.4 The integration branch is not a target, except for your own pushes

Attesting the tip of the integration branch is refused, with one
exception: when HEAD is the integration branch and its upstream is behind
HEAD, the range is the reviewer's own unpushed commits and the attestation
is the last thing pushed. That is the direct-push workflow of §3.2, and
the producer already resolves this reference today. `SKILL.md`'s
"Worktree Target Mandate" is rewritten to say exactly this instead of
"strictly prohibited".

### 2.5 Stale-state check, commit sequence, and what survives a merge

Today's circuit breaker protects one property: the interview covered the
committed state. In target mode the equivalent is a fetch immediately
before commit, then `origin/<target> == reviewed SHA` from the preparation
record (§2.12). The reviewer's own working tree is irrelevant and is not
checked. Every input below comes from the record, never from a re-derived
HEAD or target.

**The sequence.** One order, in target mode:

1. Build the attestation commit object with `git commit-tree`, parented on
   the recorded reviewed SHA (`-S` when a signing key is configured). No ref
   points at it yet.
2. Run the verifier self-check against that object.
3. Append the message as a note on the reviewed commit and on its tree,
   merge with `cat_sort_uniq`, and push `refs/notes/signoff`. Both objects
   already exist on the remote, so this needs nothing from step 4.
4. Push the object to `refs/heads/<target>` with
   `--force-with-lease=refs/heads/<target>:<reviewed SHA>`. The lease is a
   compare-and-swap against the tip the interview covered: a concurrent
   push by the author, or a rewind of the branch, rejects it.

**The failure contract, step by step.**

- Steps 1 or 2 fail: nothing to undo. An unreferenced object is garbage.
- Step 3 refused (the cloud-session 403 this project tolerates today): the
  producer continues to step 4, because the PR check passes on the commit
  alone, and the report says in so many words that this attestation will
  survive a squash or rebase merge only through the recovery path below.
- Step 4 fails after step 3 succeeded: the branch is untouched and the
  object is garbage, but **the notes are published**. That outcome is
  accepted, not hidden: a note is a statement about a commit and a tree,
  and the human did attest exactly that commit and tree. If the author
  pushed a new tip, the note does not cover it and the check stays red for
  the right reason. If the branch was rewound, the note still describes a
  state that was reviewed. The producer names the published note SHAs in
  its report so an auditor can find them.

**Why the order is notes first.** Reversing it (branch, then notes) makes
the branch push the point of no return and turns a refused notes push into
partial state discovered too late. Notes first makes the branch push the
last and only irreversible step.

**What survives a merge, and who guarantees it.** After a squash merge the
attestation commit exists only on the PR branch; the squashed tip verifies
only through the tree-SHA note. GitHub's rebase-and-merge drops
intentionally empty commits (documented at
docs.github.com/en/pull-requests/reference/pull-request-merges), so a
rebase merge is in the same position: the tree note is the only path. If
step 3 was refused, that note does not exist on `origin`, and the recovery
workflow as it stands scans only the integration branch, where the
attestation commit never was.

An earlier revision proposed fetching `refs/pull/*/head` in the verify job
and re-dispatching verification after recovery. Both were wrong in the
same way: they assume an execution order. Fetching alone changes nothing,
because the verifier's log lookup walks history reachable from the target
commit, and a PR head is not an ancestor of a squash tip (reproduced by the
reviewer). Re-dispatch adds a trigger, a permission, and the constraint
that `workflow_dispatch` only reaches workflows on GitHub's default branch,
which for a `dev`-based repository is exactly the branch the workflow may
not be on. The contract instead removes the ordering dependency:

1. **Verification does not depend on recovery having run.** The composite
   action determines the eligible pull-request head refs for the target
   (§2.13), fetches exactly those, and the verifier's tree-SHA fallback
   (gsa-core §5.1 step 3) considers attestation commits reachable from
   them, via an explicit `--scan-refs` input, subject to the object
   integrity rules of §2.13. A squash or rebase tip whose PR head carries
   a sound attestation of the same tree passes on the spot, whether or not
   any note was ever pushed. Verifier change: `verify-v1.5`, with the
   head-mode default of §3.3. Read-only, so §5.1's rule that verification
   never mutates notes stands.
2. **Recovery is the durable path, and adopters get it.** `recover_notes.py`
   scans `refs/pull/*/head` as well as the integration branch, so the tree
   note is eventually reconstructed on `origin` for anyone reading notes
   directly. The initializer scaffolds the recovery workflow for adopters
   (it does not today: only this repository has one), so the path exists
   outside this repository at all. No re-dispatch: item 1 makes it
   unnecessary.
3. **Pre-implementation check.** Confirm on a scratch GitHub repository
   that `refs/pull/N/head` is fetchable from Actions with the default token
   after the branch is deleted, since item 1 rests on it.

### 2.6 Enforcement strength follows the chosen workflow

A pull request can be blocked: the ruleset makes `verify-signoff` required
and the merge button stays grey. A workflow that runs *after* a push is
accepted cannot reject that push. GitHub can, however, reject a direct
push whose tip commit lacks a passing required check, and that check may
have run on another branch first. So a pre-checked direct-push workflow
(push to a scratch branch, let CI pass, fast-forward the integration
branch) is possible and stays out of scope here. The consequence for §3.2:
advisory direct pushes are a property of the PR-only policy this project
chooses and of any bypass list a team configures, not a platform limit.

### 2.7 Out of scope for this change

- **Attesting after merge on the integration branch** as a substitute for
  the PR gate. Code lands before anyone attests to understanding it. If
  it is ever built it is labelled an audit trail, not a gate.
- **Notes-only attestation for fork pull requests.** Head mode would
  accept it (a note on the PR head commit already passes), but
  `recover_notes.py` rebuilds notes from attestation commits and could
  not restore a note that has no commit. Forks remain the documented
  limitation they are today.
- **Octopus merges.** Already unsupported by the verifier.

### 2.8 Release shape

`init.py` changes ship as `init-v8`. `gsa-core.md` goes to 3.8.0: producer
behaviour is generalised, no trailer changes. Per §3.3, the composite
action's default changes and ships as `verify-v1.5`.

### 2.9 Target parsing

`<target>` accepts `feature`, `origin/feature`, or `refs/heads/feature`
and resolves to `refs/remotes/origin/feature` after a fetch. The remote is
`origin`, as it is for notes today. A target that does not exist on the
remote is an error, not a local fallback: the PR check reads the remote.

### 2.10 Reference precedence

For the bare command (target is HEAD), in order: `--reference`; a usable
upstream (`HEAD@{upstream}` when it is behind HEAD, which is the
direct-push case of §2.4 and what makes a stacked branch diff against its
own base); `integration_branch` from `.git-signoff/config.json`;
`origin/HEAD`; `main`, then `master`. For an explicit target the upstream
step is skipped, because a feature branch's upstream is its own remote
counterpart. The first two steps are today's behaviour; the config file
and `origin/HEAD` are new. **`origin/HEAD` is a behaviour change** for a
repository with no config file whose GitHub default branch is not `main`
or `master`: today the producer falls through to `main`/`master` and
either warns or fails; afterwards it uses the remote's default branch.
That is the better default and it is documented in the changelog as a
change, not hidden as a fallback.

### 2.11 Local state is untouched in target mode

The producer never updates `refs/heads/<target>` locally. The reviewer's
local copy of that branch, if any, fast-forwards on their next pull.
Reason: the branch may be checked out in another worktree, and moving its
HEAD from outside is what `git branch -f` refuses to do. The empty commit
would not corrupt files there, but it would move a HEAD nobody asked to
move. The bare command with HEAD as the target keeps updating the local
branch, since that is today's behaviour and the reviewer is on it.

### 2.12 The prepared state is an explicit input to commit — implemented

Found by the external review and reproduced against the current producer:
`commit` re-ran `prepare` and attested whatever HEAD was at that moment.
The approval marker tied the transcript to the reviewed commit, but with
`--ack-no-transcript` there was no transcript and therefore no tie. Prepare
on A, add B, commit with no transcript: B was attested with exit 0 and the
verifier's own PASS line.

Fixed on this branch, independent of the target-mode feature: `prepare`
writes `.git/git-signoff/prepared.json` (per worktree: reviewed, base and
tree SHAs, reference, timestamp, resolved profile source/id/digest), and
`commit` attests exactly that record. No record, a HEAD or tree that
differs from it, or a profile that resolves differently is exit 3, with or
without a transcript. A `--reference` given at commit must resolve to the
recorded one (exit 2 otherwise). The base in the trailers is the recorded
one even if the reference moved during the interview, so the attestation
describes the range the human saw. A successful commit removes the record.
`marker` reprints the recorded marker and is read-only: the second review
pass showed that a `marker` which silently re-prepared on a stale record
was the one command that could clear a refusal without an interview
(prepare A, add B, commit refuses, `marker`, commit attests B). Only
`prepare` writes the record. No new trailers; `gsa-core.md` 3.7.2 records
it as an informative §4.1 change.

Target mode builds on this: the record gains the target ref, and §2.5's
lease uses the recorded reviewed SHA, never a fresh resolution.

### 2.13 Evidence boundaries: object integrity and eligibility

The third review pass constructed a forgery that needs no hash collision:
an empty `[SIGNOFF]` commit on an unrelated tree whose trailers name a
target's commit and tree. Today's history fallback in the verifier accepts
it if it is reachable from the target (trailer syntax and value match only),
and today's recovery script attached a tree note on its say-so, after which
the unchanged verifier accepted the previously unattested target. Both
paths trusted the trailer where they should have checked the object. Two
boundaries follow, and any lookup that reaches beyond the target's own
history must sit inside both.

**Object integrity.** A commit-sourced candidate is evidence only if the
commit object itself corroborates the trailers, in the shape the producer
writes and head mode already demands at HEAD:

1. exactly one parent;
2. the commit is empty — its tree is its parent's tree;
3. its parent is the declared `Signoff-Reviewed-Commit-SHA`;
4. for the tree anchor only: the declared `Signoff-Reviewed-Tree-SHA` is
   that parent's actual tree.

A candidate failing 1–3 is not an attestation of anything and is skipped
loudly. One passing 1–3 but failing 4 attests its commit and nothing else.
Only then is the corroborated tree compared with the target's tree.
Payload files given to recovery are the explicit exception: they exist for
attestations whose objects are gone and are committed to this repository.

**Implemented now for recovery** (`scripts/recover_notes.py`, this branch),
with regression tests for the forged tree trailer (target stays
unattested), a non-empty candidate, a wrong-parent candidate, a two-parent
candidate, the declared-tree mismatch, and the positive squash case. This
repository's own history shows why rule 4 is separate from rules 1–3: eight
attestations from 2026-08-01..05, written by the first bash-heredoc skill,
declare a tree no reviewed commit has, and one from the same week sits on
the integration branch after its merge commit rather than on the commit it
names. They recover on the commit anchor only, or not at all, with the
reason printed. **At `verify-v1.5`** the verifier's own history fallback
applies the same rules, as does the `--scan-refs` lookup.

**Evidence eligibility.** `refs/pull/*/head` includes every pull request
GitHub has ever received, including unmerged ones and ones from forks. A
fork can reproduce a public target's exact tree and append a self-declared,
unsigned attestation that passes every integrity rule; scanning all PR refs
would let that contribution vouch for an unrelated integration tip. The
project already states that unsigned trailers do not authenticate their
author; this would additionally widen *who may supply evidence* for a
branch they cannot push to. So:

- Default eligibility is the pull request **associated with the merged
  target**, discovered by the composite action from the API
  (`GET /repos/{owner}/{repo}/commits/{sha}/pulls`), filtered to merged
  PRs whose head repository is this repository. Exactly those
  `refs/pull/N/head` are fetched and passed to `--scan-refs`. No API, no
  eligible PR, or a fork head: nothing is scanned and verification behaves
  as today. Eligibility is an API fact about the PR, never a ref-name
  pattern.
- Recovery applies the same eligibility: it walks the integration branch,
  and PR head refs only for merged same-repository PRs.
- Anything broader (all same-repository PRs, all PR refs, another
  repository's notes) is a deliberate trust policy an adopter opts into by
  configuration, not a default. Authenticated reviewer identity (the
  deferred item in `docs/roadmap.md`) is the other route and is what would
  make fork evidence admissible.

**What a cross-history match means.** A sound, eligible attestation from
another history whose corroborated tree equals the target's establishes
that the same tracked code state was attested. It does not establish that
this pull request, this base, or this interview context was reviewed. That
is consistent with GSA's existing code-state semantics (the tree-SHA anchor
was always about the state, not the branch) and the spec says it in so many
words (§4).

**Regression cases required before `verify-v1.5`**, each for both the
lookup and recovery: forged tree trailer; non-empty candidate; wrong-parent
candidate; ineligible fork ref carrying an otherwise sound attestation;
valid squash recovery; changed-tree rejection after the squash. The
recovery half exists on this branch; the lookup half is the pin's gate.

---

## 3. Decided after review (alternatives kept)

### 3.1 Whose branch gets advanced

In target mode the reviewer pushes a commit onto a branch they may not
own. Mechanically this is gentle: the commit is empty, so the author's next
pull fast-forwards, and every case where it interferes (author has
unpushed commits and rebases; author force-pushes) is a case where the
check *should* go red because the diff changed after the attestation.

| Option | How | Costs |
|---|---|---|
| **A. Advance the target branch** (decided) | `commit-tree` parented on the tip; lease push of the object to `refs/heads/<target>` (§2.5); no local ref update (§2.11). | Requires push rights to that branch. Writes to someone else's branch, under the reviewer's identity. |
| **B. Reviewer-owned ref** | Same commit, pushed to `refs/heads/signoff/<target>`; note attached to the reviewed commit. Head mode passes on the note. | Ref clutter needing cleanup on merge. `recover_notes.py` must learn to scan `signoff/*` refs. A second persistence shape to document, test, and explain. |

**Decision: A.** Three reasons, none specific to any one team. The most
common adopter is one researcher with an agent in one checkout, for whom
"someone else's branch" never arises and B would be pure overhead. A
maintainer pushing to a pull-request branch is an existing GitHub norm,
so nothing new has to be learned. B adds a second persistence shape to
the protocol: every third-party verifier would have to implement it and
§5.1's lookup order would grow, and spec surface is the cost that
compounds for a protocol seeking implementers. The ownership concern is a
team norm a tool cannot settle; the approval step already names the
branch that will receive the commit, so the reviewer consents each time.
Reopen only on a concrete adopting team that objects; B is the harder
direction to reverse, so it is not chosen on a hypothetical.

### 3.2 Enforce or advise, and what the initializer asks

| Option | Mechanism | Consequence |
|---|---|---|
| **Enforce** | Ruleset on, `verify-signoff` required, PR rule on. | Nobody pushes to the integration branch directly, including the lead. |
| **Advise** | Ruleset off; workflow runs on push. | Badge tells the truth; stops nobody. |
| **Enforce with bypass** | Ruleset on; named `bypass_actors`. | Named people may push directly; their unattested pushes still turn the badge red (if §3.3 chooses head mode). Everyone else must PR. |

**Decision: change nothing in the initializer; document bypass.** The
initializer already enforces by default and `--skip-ruleset` already is
advisory mode. The bypass list is a GitHub setting about people, not a
property of the tool, so it is a documented manual step in
`verify/README.md`. The config file records nothing about enforcement,
because a recorded-but-unread setting is a trap. Enforcement stays the
default even though some teams dislike PR requirements: the gate is the
product, and the opt-out exists.

### 3.3 What the push-to-integration job checks

Today the composite action's `auto` mode runs **history** mode on push,
requiring one valid attestation anywhere in history. For an advisory badge
that is close to meaningless: a single attestation from months ago keeps
the badge green forever.

| Option | Behaviour | Costs |
|---|---|---|
| **Keep history mode** | Badge means "this repo has used the tool". | Direct pushers are never flagged. |
| **Head mode on push** | Badge means "the current tip is an attestation, or an attested PR merge, or a squash whose tree is attested". | Adopters with unattested history start red until the first attestation lands. Behaviour change to the action's default: `verify-v1.5` and a changelog entry. |
| **Head mode, opt-in** | New action input; default unchanged. | Nobody gets the honest badge unless they read the docs. |

Head mode on push is the only option under which §3.2's bypass path means
anything. If §3.2 chooses plain Enforce, this item matters less.

**Decision: head mode as the new default, shipped as `verify-v1.5`
together with the `--scan-refs` lookup of §2.5.** For a strictly enforced
repository a push to the integration branch is an attested PR merge, which
head mode passes directly for merge commits and, for squash and rebase
merges, via the tree note or via the PR head's attestation commit under
`refs/pull/*/head`. Without the second path, a refused notes push in a
cloud-session interview would turn a squash merge red; with it, head mode
is honest for everyone, and for an advisory or bypass repository it is the
entire point. History mode wins only during migration, when an
adopter with unattested history is red until the first attestation lands;
the verifier's failure line names the command to run. History mode stays
available as an explicit input; `require` applies only to it.

### 3.4 What the base is in target mode

Proposed: the configured integration branch. Alternative: the pull
request's base branch, which is more precise for stacked PRs but requires
a GitHub query (`gh`, not always installed) or a `--reference` flag the
human must remember. **Decision:** integration branch by default,
`--reference` to override, per the precedence in §2.10. Stacked PRs are
an existing limitation, unchanged.

### 3.5 Commit identity in target mode

The attestation commit's author and committer come from the reviewer's
git identity; `Signoff-Verified-By` comes from the confirmed email. In
cloud sessions the git identity is the session's, not the human's, which
is already true today and already documented in HARNESSES.md. Target
mode does not change this, but it makes the gap more visible: a commit on
someone else's branch, authored by a session identity, attested by a
human email. Options: leave as is; or set author from the confirmed email
when the harness is a cloud session. **Decision: leave as is, explicitly
deferred.** It is documented behaviour today and target mode does not
change what is recorded, only where. Revisit on a report of confusion;
the change is small but touches provenance semantics and would need a
spec sentence in §2.4.

### 3.6 Local state of the target branch — settled, see §2.11

Resolved 2026-09-16 as remote-only. Kept here so the numbering of earlier
discussion still resolves.

### 3.7 Config file schema and growth

Minimal: `{"integration_branch": "dev"}`. Tempting additions
(`enforcement`, `attest_from`) are each a setting that some code path must
honour or they become misleading. Rule proposed: a key is added only in
the same change as its first reader. **Decision:** the minimal schema and
that rule; the file is a sibling of `.git-signoff/profile.md`, not merged
into it; `init.py` rewrites it on re-run after confirming the value, and
reports (does not yet reconcile) an installed ruleset that disagrees
with it (§2.3).

### 3.8 Listing heuristic, and the empty list

How many candidates, and chosen how?

| Option | Behaviour | Costs |
|---|---|---|
| **Count cap** (decided) | The ten most recent by commit date, each shown with its date; `--all` lists every candidate. | A very active repository may push the wanted branch off the list; the date column and `--all` cover it. |
| **Time window** | Branches touched in the last N days. | Fails in the setting this feature is for: a lab branch last touched six weeks ago is often the one the lead reviews late, and it would be hidden with no hint that anything was hidden. |

If the list is empty (everything merged, or nothing has a remote
counterpart), the skill needs a next step for the human. Options: say so
and stop; fall back to asking for a branch name; offer `--reference` for
the direct-push case of §2.4. Small, but it is the first thing a confused
new user sees. **Decision:** state the reason the list is empty, then
ask for a name.

---

## 4. Spec deltas (gsa-core 3.7.2 → 3.8.0)

Already shipped on this branch as 3.7.2 (informative): §4.1's stale-state
circuit breaker verifies against the recorded prepared state (§2.12).
The target-mode deltas below build on that wording.

- **§1** "recorded as empty Git commits on feature branches" → "recorded
  as empty Git commits on the branch whose tip is the reviewed commit".
- **§4.1 `signoff_prepare(target_ref)`** already takes a target; make the
  description say the target may be any ref, not only HEAD, and describe
  the listing behaviour of §2.2 as informative.
- **§4.1 `signoff_commit` stale-state circuit breaker** → "the recorded
  target ref still resolves to the recorded `reviewed_commit_sha` (after a
  fetch, for a remote target); when the target is HEAD, the working tree is
  also clean (`git diff --quiet`, `git diff --cached --quiet`)".
- **§2.5** gains the target-mode ordering: notes pushed before the branch,
  and the producer's report on a refused notes push and on notes published
  by a commit whose branch push then failed.
- **§5.1 step 3** (tree-SHA fallback): a verifier MAY consult attestation
  commits outside the target's history only when (a) the commit object
  corroborates the trailers — one parent, empty, parent is the declared
  reviewed commit, declared tree is the parent's tree — and (b) the
  commits come from refs the repository's write authority controls, by
  default the merged pull request associated with the target. A match
  found this way establishes that the same tracked code state was
  attested, not that this pull request, base, or interview context was
  reviewed. The same integrity rule applies to the log lookup of step 2.
  Still read-only; the MUST NOT mutate rule stands.
- **SKILL.md Worktree Target Mandate** → the rule in §2.4 above.

No change to §2.1–§2.4 (schema, status, field rules, identity binding).
§5.1's lookup order is amended only as stated above: the same three
steps, with the integrity and eligibility conditions on what steps 2 and 3
may consult, and the sentence on what a cross-history match establishes.

## 5. Implementation sketch

- `attest.py`: `prepare`/`commit`/`marker` gain `--target <branch>`;
  `prepare` gains `--list-targets`; a `TargetRef` abstraction replaces
  the HEAD assumptions (`_check_clean_tree` becomes
  `_check_target_unmoved`); commit path uses `commit-tree`, verifier
  self-check, then a lease push of the object to the remote branch, in
  the order of §2.5, with no local ref update (§2.11), so a pushed
  attestation never needs rolling back; `--list-targets` implements
  §2.2 and §3.8.
- `init.py`: integration-branch confirmation, config write, ruleset
  `ref_name` from config, `init-v8`.
- `SKILL.md`: Section 1 gains the on-integration-branch listing step;
  Section 3 mandate rewritten.
- Verify action and verifier (`verify-v1.5`): head mode on push as the
  default; the action resolves the merged same-repository PR for the
  target via the API, fetches exactly its `refs/pull/N/head`, and passes
  it to `--scan-refs`; the verifier applies §2.13's object-integrity
  rules to both the scan and its existing history fallback. Conformance
  vectors for the forged-trailer and wrong-parent cases.
- `recover_notes.py` and `notes-recovery.yml`: integrity rules shipped on
  this branch; add eligible PR head refs (merged, same repository) to the
  scan; no re-dispatch. `init.py` scaffolds the recovery workflow for
  adopters alongside `git-signoff.yml`.
- `init.py`: report an installed ruleset whose branch disagrees with the
  configured one, with the manual step.
- Pre-implementation check: `refs/pull/N/head` fetchable from Actions with
  the default token after branch deletion, on a scratch repository.
- Tests: the §2.13 regression matrix for the lookup (the recovery half
  exists); target mode end to end against scratch repos (reviewer on `dev`,
  target pushed by another clone); race (author pushes mid-interview);
  no-local-branch; integration-branch refusal and the own-push exception;
  config precedence; ruleset rendering; listing order and exclusions.
- Docs: `reference.md`, `walkthrough.md` (a second walkthrough from the
  integration branch), `HARNESSES.md`, README quickstart.

## 6. Evidence still worth gathering from the originating adopter

None of it changes the design above; it tells us whether the feature
helps the reviewer who prompted it, and what to write in the docs.

- Does code reach the integration branch through pull requests, direct
  pushes, or both, and for whom? Five minutes in `git log --merges` on the
  integration branch answers it. If there are no pull requests, the gate
  cannot help this repository regardless, and that is a workflow
  conversation, not a spec change.
- Whose branches does the reviewer attest? If other people's, §3.1's
  consent line in the approval step should be worded with that reader
  in mind.
- Is the repository's GitHub default branch the same as its integration
  branch? Tells us how much §2.3 matters for this adopter.
