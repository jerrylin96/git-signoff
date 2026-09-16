# Design: attest any target, from anywhere

**Status:** Decided, pending one external review before implementation.
Revised 2026-09-16 after two review passes. Nothing here is implemented.
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
  plumbing (`git commit-tree`, which accepts `-S` for signing), so the
  reviewer's working tree is never read or modified.
- **Verifier:** unchanged. The attestation is still the last commit of
  the branch under review; head mode passes as it does now.
- **Trailers, notes, lookup order (gsa-core §2, §5):** unchanged. No new
  conformance vectors.

### 2.2 On the integration branch with no argument: list

When HEAD is the integration branch and no target is given, the producer
does not refuse and does not guess. It lists candidate branches and the
skill presents them for the human to pick. Candidates: branches with a
remote counterpart, not merged into the integration branch, excluding the
integration branch itself and branches whose tip is already an
attestation, ordered by most recent commit. An empty list is reported as
such.

### 2.3 One integration branch, chosen once, read everywhere

`init.py` confirms a single branch name (default: what it detects today)
and persists it in `.git-signoff/config.json`. Three consumers read it:
the scaffolded workflow's `push:` filter, `ruleset.json`'s `ref_name`
include (an explicit `refs/heads/<name>` instead of `~DEFAULT_BRANCH`),
and `attest.py` as its fallback reference. An adopter repository with no
config file keeps today's behaviour exactly, so re-running the
initializer is optional.

JSON rather than TOML because the documented Python floor is 3.10 and
`tomllib` arrived in 3.11.

### 2.4 The integration branch is not a target, except for your own pushes

Attesting the tip of the integration branch is refused, with one
exception: when HEAD is the integration branch and its upstream is behind
HEAD, the range is the reviewer's own unpushed commits and the attestation
is the last thing pushed. That is the direct-push workflow of §3.2, and
the producer already resolves this reference today. `SKILL.md`'s
"Worktree Target Mandate" is rewritten to say exactly this instead of
"strictly prohibited".

### 2.5 Stale-state check and commit ordering, translated

Today's circuit breaker protects one property: the interview covered the
committed state. In target mode the equivalent is a fetch immediately
before commit, then `origin/<target> == reviewed SHA`. The reviewer's own
working tree is irrelevant and is not checked.

The producer then works in an order that makes rollback of a pushed
attestation unnecessary:

1. Build the attestation commit object with `git commit-tree` (`-S` when a
   signing key is configured). No ref points at it yet.
2. Run the verifier self-check against that object.
3. Push it to `refs/heads/<target>` with
   `--force-with-lease=refs/heads/<target>:<reviewed SHA>`, last. The
   lease is a compare-and-swap against the tip the interview covered: a
   concurrent push by the author, or a rewind of the branch, rejects it.
4. Write the notes, merge with `cat_sort_uniq`, push them. A refused notes
   push is reported and tolerated, as today.

If anything before step 3 fails, nothing has to be undone: an unreferenced
object is garbage. Only a failed notes push after a successful branch push
leaves partial state, and that is the state the recovery workflow already
handles. This is the same failure shape as today's exit 3 for the race and
strictly less to clean up than today's local rollback path.

### 2.6 Enforcement strength is a GitHub fact, not a design choice

A pull request can be blocked: the ruleset makes `verify-signoff` required
and the merge button stays grey. A direct push cannot be blocked by CI:
GitHub exposes no pre-receive hook, so the most a direct pusher gets is a
failed run and a red badge after the fact. Every option in §3.2 lives
inside this constraint.

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
behaviour is generalised, no trailer changes. If §3.3 resolves as
decided in §3.3, the composite action's default changes and ships as
`verify-v1.5`.

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
and `origin/HEAD` are new, and a repository without a config file resolves
exactly as it does now.

### 2.11 Local state is untouched in target mode

The producer never updates `refs/heads/<target>` locally. The reviewer's
local copy of that branch, if any, fast-forwards on their next pull.
Reason: the branch may be checked out in another worktree, and moving its
HEAD from outside is what `git branch -f` refuses to do. The empty commit
would not corrupt files there, but it would move a HEAD nobody asked to
move. The bare command with HEAD as the target keeps updating the local
branch, since that is today's behaviour and the reviewer is on it.

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

**Decision: head mode as the new default, shipped as `verify-v1.5`.**
For a strictly enforced repository every push to the integration branch
is an attested PR merge, so head mode is always green and costs nothing.
For an advisory or bypass repository it is the entire point. History mode
wins only during migration, when an adopter with unattested history is red
until the first attestation lands; the verifier's failure line should name
the command to run. History mode stays available as an explicit input;
`require` applies only to it.

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
into it; `init.py` rewrites it on re-run after confirming the value.

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

## 4. Spec deltas (gsa-core 3.7.1 → 3.8.0)

- **§1** "recorded as empty Git commits on feature branches" → "recorded
  as empty Git commits on the branch whose tip is the reviewed commit".
- **§4.1 `signoff_prepare(target_ref)`** already takes a target; make the
  description say the target may be any ref, not only HEAD, and describe
  the listing behaviour of §2.2 as informative.
- **§4.1 `signoff_commit` stale-state circuit breaker** → "the target ref
  still resolves to `reviewed_commit_sha`; when the target is HEAD, the
  working tree is also clean (`git diff --quiet`, `git diff --cached
  --quiet`)".
- **§2.5** unchanged. If §3.1 chooses option B, add the reviewer-owned
  ref as a second persistence location and extend §5.1 lookup accordingly.
- **SKILL.md Worktree Target Mandate** → the rule in §2.4 above.

No change to §2.1–§2.4 (schema, status, field rules, identity binding)
or §5 (lookup order) unless §3.1 chooses B.

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
- Verify action: only if §3.3 changes the default.
- Tests: target mode end to end against scratch repos (reviewer on `dev`,
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
