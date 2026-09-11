# Design: attest any target, from anywhere

**Status:** Draft for discussion. Nothing here is implemented. Sections marked
*settled* are positions we are confident in; sections marked *open* list the
alternatives and what each costs. Decide the open items, then this document
becomes the change list for `gsa-core.md` (a minor version), `SKILL.md`,
`attest.py`, `init.py`, and the verify workflow.

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

### 2.5 Stale-state check, translated

Today's circuit breaker protects one property: the interview covered the
committed state. In target mode the equivalent is a fetch immediately
before commit, then `local <target> == origin/<target> == reviewed SHA`.
The reviewer's own working tree is irrelevant and is not checked. The push
is a plain fast-forward, so a concurrent push by the author rejects it and
the producer rolls back, which is the same failure shape as today's exit 3.

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

`init.py` changes ship as `init-v8`. If the verifier and composite action
are untouched, `verify-v1.4` stands; §3.3 is the one open item that would
force `verify-v1.5`. `gsa-core.md` goes to 3.8.0: producer behaviour is
generalised, no trailer changes.

---

## 3. Open

### 3.1 Whose branch gets advanced

In target mode the reviewer pushes a commit onto a branch they may not
own. Mechanically this is gentle: the commit is empty, so the author's next
pull fast-forwards, and every case where it interferes (author has
unpushed commits and rebases; author force-pushes) is a case where the
check *should* go red because the diff changed after the attestation.

| Option | How | Costs |
|---|---|---|
| **A. Advance the target branch** (proposed) | `commit-tree` parented on the tip; `update-ref`; fast-forward push of `refs/heads/<target>`. | Requires push rights to that branch. Writes to someone else's branch, under the reviewer's identity. |
| **B. Reviewer-owned ref** | Same commit, pushed to `refs/heads/signoff/<target>`; note attached to the reviewed commit. Head mode passes on the note. | Ref clutter needing cleanup on merge. `recover_notes.py` must learn to scan `signoff/*` refs. A second persistence shape to document, test, and explain. |

Decide A unless the branch-ownership concern is real for the team. If the
branches under review are the reviewer's own (or written by an agent in
their checkout), the concern does not arise and A is strictly simpler.

### 3.2 Enforce or advise, and what the initializer asks

| Option | Mechanism | Consequence |
|---|---|---|
| **Enforce** | Ruleset on, `verify-signoff` required, PR rule on. | Nobody pushes to the integration branch directly, including the lead. |
| **Advise** | Ruleset off; workflow runs on push. | Badge tells the truth; stops nobody. |
| **Enforce with bypass** | Ruleset on; named `bypass_actors`. | Named people may push directly; their unattested pushes still turn the badge red (if §3.3 chooses head mode). Everyone else must PR. |

Open questions: does `init.py` ask this as a question, or keep today's
"create the ruleset unless `--skip-ruleset`" and document bypass as a
manual step? Does the config file record the choice, and if so does
anything read it? A recorded-but-unread setting is a trap.

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

### 3.4 What the base is in target mode

Proposed: the configured integration branch. Alternative: the pull
request's base branch, which is more precise for stacked PRs but requires
a GitHub query (`gh`, not always installed) or a `--reference` flag the
human must remember. Proposal: integration branch by default,
`--reference` to override, as today. Stacked PRs are an existing
limitation, unchanged.

### 3.5 Commit identity in target mode

The attestation commit's author and committer come from the reviewer's
git identity; `Signoff-Verified-By` comes from the confirmed email. In
cloud sessions the git identity is the session's, not the human's, which
is already true today and already documented in HARNESSES.md. Target
mode does not change this, but it makes the gap more visible: a commit on
someone else's branch, authored by a session identity, attested by a
human email. Options: leave as is; or set author from the confirmed email
when the harness is a cloud session. The second is small but touches
provenance semantics and belongs in the spec if done.

### 3.6 Local state of the target branch

The reviewer may have no local branch for the target, or a stale one.
Proposed: operate on `refs/remotes/origin/<target>` after a fetch, push,
and then fast-forward the local branch only if it exists and pointed at
the old tip. Alternative: require a local branch. The first is
friendlier; the second is simpler to reason about and test. Lean first.

### 3.7 Config file schema and growth

Minimal: `{"integration_branch": "dev"}`. Tempting additions
(`enforcement`, `attest_from`) are each a setting that some code path must
honour or they become misleading. Rule proposed: a key is added only in
the same change as its first reader. Also decide the file's relationship
to `.git-signoff/profile.md` (sibling, not merged) and whether
`init.py` rewrites it on re-run (proposed: yes, after confirming).

### 3.8 The listing when nothing qualifies

If the candidate list is empty (all branches merged or unattestable), the
skill needs a next step for the human. Options: say so and stop; or fall
back to asking for a branch name; or offer `--reference` for the
direct-push case. Small, but it is the first thing a confused new user
sees.

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
  `_check_target_unmoved`); commit path uses `commit-tree` + `update-ref`
  + `push`; rollback deletes the pushed commit by pushing the old tip
  (fast-forward is impossible, so rollback of a *pushed* attestation is a
  `--force-with-lease` to the previous SHA, which needs its own decision:
  do we ever force-push someone else's branch, even back to where it was?).
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

## 6. Evidence to gather before deciding §3

- Whose branches does the reviewer attest: their own, an agent's in their
  own checkout, or other people's? (Decides §3.1.)
- Does code reach the integration branch through pull requests, direct
  pushes, or both, and for whom? Five minutes in `git log --merges` on the
  integration branch answers it. (Decides §3.2 and §3.3.)
- Is the repository's GitHub default branch the same as its integration
  branch? (Decides how much §2.3 matters for this adopter.)
