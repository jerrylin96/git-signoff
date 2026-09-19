# Design: practice mode — the interview without the record

**Status:** Draft for external review (2026-09-19), branch
`claude/zealous-goodall-tnk50s`. Nothing here is implemented. §2 holds the
positions the author considers settled; §3 holds the decisions a reviewer is
most likely to disagree with, each with the rejected alternatives kept so
the disagreement can be concrete. The decision rule is the one used for
[`attest-any-target.md`](attest-any-target.md): judge by the broadest set of
adopters, prefer the option that adds no protocol surface, decide now where
reversal is cheap. This document is the change list for `SKILL.md`,
`attest.py`, `README.md`, `HARNESSES.md`, the contract tests, and one
informative sentence in `gsa-core.md`.

**Origin:** the question "can someone use this just for the interview —
questions, hints, answers — without PRs, CI, badges, rulesets?" The
honest answer today is "yes, but nothing tells them so, and the first
thing the tool does to them is refuse." The interview (SKILL.md §2) is
already a prompt that needs no CI; the obstacles are in the on-ramp and in
the helper's refusals, both of which exist to protect the *record*, which a
learner is not producing.

---

## 1. The problem, precisely

Four concrete frictions for a person who wants the interview and not the
attestation, and one design tension behind all of them.

1. **The on-ramp sells the gate.** `README.md` leads with the zero-touch
   initializer, which scaffolds a workflow, a config directory, a badge, a
   ruleset, and a branch. The "copy one folder" install is the second row of
   a table under *Installation*. A reader who only wants to be quizzed
   concludes they need all of it.
2. **The helper refuses a dirty tree.** SKILL.md §1 step 1 runs
   `attest.py prepare`, which calls `check_clean_tree` and exits 3 on any
   unstaged or staged change. That refusal is correct for an attestation
   (the interview must cover the committed state) and wrong for a learner
   who wants to be interviewed on the change they are *about* to commit.
   There is no flag around it.
3. **The prompt runs to the commit.** Nothing in SKILL.md tells the agent
   to stop after §2. The agent proposes an email, prints trailers, and asks
   for approval; the user's only exit is to say no at §3 step 2.
4. **Remediation never reveals.** The vague-answer rule ("pause signoff,
   explain the mechanics, re-probe with a scenario") is a gate's rule: it
   explains the *mechanics* and demands the *answer* again, because an
   attestation whose answers came from the agent is worthless. A learner
   wants the opposite half of the time: a hint, then the answer, then the
   next question.

The tension: every one of these behaviours is a load-bearing part of the
accountability record. Relaxing them *in the attesting path* would weaken
what the project exists to produce. So the design has to add a path where
they do not apply and make it impossible for that path to leak into a real
attestation.

## 2. Settled

### 2.1 One skill, one modifier: `/git-signoff --practice`

Practice mode is a modifier of the existing skill, not a second skill.
`--practice` runs §1 (range resolution, profile, hints) and §2 (the
interview) and then stops with a scorecard (§2.5). It never enters §3: no
email, no dry run, no marker, no commit.

Why not a separate `/git-interview` skill: SKILL.md §2 is the ~60 lines the
learner actually wants, and the contract test
(`test_skill_references.py::test_signoff_phase3f_adaptive_intensity_contract`)
pins that text in one file. A second copy drifts, and the point of the
adaptive-intensity matrix is that practice shows the learner *exactly* what
a real signoff would ask. Same text, same tiering, same probes.

`--practice` combines with `--quick` and `--deep` (they select the tier as
today) and with a `<branch>` argument (target mode, §2.3).

### 2.2 `attest.py prepare --practice`

One new flag on `prepare`. Differences from a real prepare, all of them
"less", none of them new capability:

- **No clean-tree check.** `check_clean_tree` is skipped.
- **The working tree is the reviewed state** (HEAD mode only). The range is
  `merge-base(<reference>, HEAD)` against the working tree:
  `git diff <base>` with no second endpoint, and the same for
  `--name-status`, `--shortstat`, `--numstat`. Untracked files are not in a
  `git diff` and are reported by count in `warnings` ("N untracked files
  are not part of this diff; `git add -N` to include them") rather than
  silently omitted. The index is never touched.
- **No preparation record.** `write_record` is not called, and an existing
  `.git/git-signoff/prepared.json` from an earlier real prepare is left
  alone (it still describes what it described; §2.4 is what stops it being
  abused).
- **No approval marker.** The `marker` field is absent from the JSON and the
  human output does not end with a `GSA-APPROVAL` line. `attest.py marker`
  is unaffected: it reprints the *recorded* marker, and practice records
  nothing.
- **A practice marker instead** (§2.4): the output carries
  `practice_marker: "GSA-PRACTICE <utc-timestamp-of-prepare>"`, and the
  human output ends with that line, exactly as a real prepare ends with the
  approval marker. The agent emits it verbatim as its own paragraph
  *before the first probe*.
- **"HEAD is already an attestation" is not a refusal.** A learner may
  legitimately practise on a branch that has already been attested; the
  diff is still there. The condition is reported as a warning.
- **Everything else is identical:** reference precedence, profile
  resolution (including the `fallback_reason` announcement and the exit-5
  unreadable-override rule), science signals, intensity hints,
  `skeptical_min_probes`, transcript-adapter detection (informative only,
  as today).

The JSON gains `"mode": "practice"` (real prepares gain `"mode": "attest"`,
so an agent reading the output never has to infer the mode from an absent
field).

### 2.3 Target mode under practice

`prepare --practice --target <branch>` reviews `origin/<branch>`'s tip after
a fetch, as today. The working-tree rule of §2.2 does not apply (there is no
working tree in target mode by construction). The integration-branch
refusal (§2.4 of the target design) still applies: practising "the
integration branch against itself" is an empty range, and the existing
message already says what to do. `targets` is unchanged.

### 2.4 A practice run can never become an attestation

This is the invariant the rest of the design exists to protect, and it has
two layers.

**Prompt layer (SKILL.md).** In practice mode the agent never emits a
`GSA-APPROVAL` line, never runs `attest.py commit`, and never proposes an
email. If the human asks, mid-practice, to "just attest it now", the agent
declines and says why: the answers in this conversation were partly the
agent's (§2.6), so a record of *this* conversation would not be a record of
the human's understanding. The way to attest is to commit, open a new
conversation, and run `/git-signoff` without `--practice`.

**Helper layer (attest.py).** `commit` already snapshots the transcript and
searches its last 64 KiB for the approval marker. It additionally searches
the *whole* snapshot for `GSA-PRACTICE` (the line §2.2 makes the agent
emit) and refuses with exit 3 if one is present, naming the byte offset:

> stale: this conversation contains a practice run (`GSA-PRACTICE
> 2026-09-19T14:02:11Z` at byte 18344 of <path>). An attestation is never
> written from a conversation in which practice mode ran; start a new
> conversation and run `/git-signoff` there.

A real `prepare` in the same conversation warns about the same condition
early (it already reads the transcript to report availability), so the
human learns before the interview, not after it, that this conversation
cannot produce a record.

What this layer does *not* cover: the `--ack-no-transcript` path, where
there is no snapshot to search. There the prompt layer stands alone, as it
already does for everything the approval marker protects. That is the same
trust boundary the project already accepts for the downgraded status
(gsa-core §2.3, last sentence of the marker paragraph), not a new one.

Why the whole snapshot and not the last 64 KiB: the approval marker is
searched in a window because only the *last* approval matters and a stale
one is a separate refusal. A practice marker anywhere in the conversation
contaminates everything after it, so the search has no natural window.
Cost: one linear scan of a file that is already read in full for the
digest.

### 2.5 What practice ends with: the scorecard

After the last probe the agent prints a fixed-shape summary and stops.
Shape, so the contract test can pin it and a learner can compare two runs:

```text
Practice scorecard — <level> / <profile-id>  (range <base7>..<HEAD7 or "working tree">)

Axis                              Probes  Unaided  Hinted  Revealed
1 Mechanics & intent                 2       2       0        0
2 Trade-offs & edge cases            2       1       1        0
3 Boundary & failure loudness        2       0       1        1
4 Ownership                          1       1       0        0

Trade-offs a signoff would record:   <one line each, or "none">
Risks a signoff would record:        <one line each, or "none">
Silent failures found:               <one line each, or "none">
Would a real signoff have passed:    no — axis 3 had a revealed answer
To attest for real: commit, open a new conversation, run /git-signoff
```

"Would a real signoff have passed" applies §2's pass criteria for the tier
that ran (a revealed answer is an unresolved axis; a hinted answer that then
passed is a pass). It is advisory: nothing is gated, and the line exists so
the learner knows the distance to the bar.

### 2.6 Hints and answers, and only here

Practice mode replaces the remediation rule of §2 ("pause signoff, explain
the mechanics, re-probe with a scenario") with a two-step ladder per probe:

1. **Vague, wrong, or "not sure" → hint.** A pointer, not an answer: the
   hunk or symbol to look at, or a concrete input to trace by hand. One
   hint per probe. The probe is then re-asked.
2. **Still vague or wrong → reveal.** The agent gives the answer with the
   mechanics behind it (what `@skill:explain-diff` does in harnesses that
   ship it; inline otherwise, per HARNESSES.md portability rule 3) and
   moves to the next probe. The axis is marked *revealed* in the scorecard.

Prediction challenges (Tier 2) keep their shape: the learner predicts, the
agent reveals the actual behaviour either way, and a wrong prediction gets
one fresh scenario before the reveal counts against the axis.

Hints and reveals are practice-only by construction, and the prompt says
so in one sentence in the §2 remediation rule, so that a human asking for
"a hint" during a real signoff is told that hints exist in `--practice` and
that a real interview cannot give one. That sentence is the only change to
the attesting path's interview text.

Escalation is unchanged: Tier 0 vagueness still escalates to Tier 1 and
Tier 1 unresolved edge cases still escalate to Tier 2, so the learner sees
the tier a real run would have ended at. The scorecard records the
post-escalation level, as `Signoff-Agent` would.

### 2.7 Install path for the interview-only user

`README.md` gains a short section directly under *Quickstart*, before the
initializer:

> **Just want the interview?** Copy `skills/git-signoff/` into
> `<your-repo>/.claude/skills/git-signoff/` (or `.agents/skills/git-signoff/`
> for other harnesses), commit it, and run `/git-signoff --practice` on any
> branch, dirty tree included. No workflow, badge, ruleset, or PR is
> involved; nothing is written to git. When you want the record, the
> initializer below sets up the gate.

No change to `init.py`. §3.4 records why.

### 2.8 Out of scope

- Any change to the verifier, the action, the recovery workflow, the
  conformance vectors, or the trailer schema. Practice writes nothing a
  verifier could see.
- A practice log or history ("how did I do last week"). Nothing persists;
  the scorecard is in the conversation. Revisit only on a request with a
  use in it.
- Profiles that differ between practice and attest. The profile is the
  sole customization point and it customizes emphases, not mode.
- Teaching content beyond the diff (general software-engineering lessons).
  The interview is about *this* change; the scorecard's "silent failures
  found" is as far as generic advice goes.

## 3. Decided, alternatives kept

### 3.1 Name: `--practice`

Rejected: `--learn` (says what the user wants, not what the tool does),
`--explain` (collides with `@skill:explain-diff`, which is a step inside the
interview), `--no-attest` (accurate but names the absence; a learner does
not know what an attestation is yet), `--dry-run` (already means "print the
trailers, commit nothing" on `commit`, and a practice run is not a dry run
of anything). `--practice` says both that it is not the real thing and what
it is for.

### 3.2 The working tree is the reviewed state in practice

Alternative: diff `base..HEAD` as today, skipping only the clean-tree check,
so uncommitted changes are simply not interviewed. Rejected because the
common learner case is "interview me on what I am about to commit", and a
run that silently ignores the uncommitted half of that answers a question
nobody asked. The untracked-files warning exists because `git diff` omits
them and a learner should not discover that from the questions.

Alternative: include untracked files by staging them with intent-to-add.
Rejected: `prepare` has never modified the index and should not start in
the mode that is supposed to be the safe one.

### 3.3 Contamination rule: any practice marker in the conversation refuses commit

Alternative A — a state file `.git/git-signoff/practiced.json` keyed by the
transcript's conversation id, checked by `commit`. Rejected: it lives in
one checkout (a learner who practises in a worktree and attests in
another is not caught), it needs a conversation id (the generic-file
adapter has none), and it is a second piece of state next to the
preparation record with its own staleness rules. The transcript marker
reuses a mechanism that already exists, is checked where the digest is
already computed, and is stateless.

Alternative B — scope the refusal to the same range (`GSA-PRACTICE
<tree-sha> <ts>`, refuse only when the reviewed tree matches). Rejected for
now: the common practice run is on a dirty tree, which has no tree SHA, so
the scoped rule would degrade to the unscoped one in exactly the case that
matters, and the unscoped rule has a two-second workaround (a new
conversation). Reopen if adopters report the workaround as a real cost;
the marker format can grow a tree field without changing the refusal.

Alternative C — prompt rule only, no helper check. Rejected on the
project's own principle: the helper exists because the agent's "never do
X" is not a guarantee, and a practice transcript is the easiest imaginable
way to produce a well-formed attestation of answers the human did not
give.

### 3.4 `init.py` gets no `--skill-only` flag

The interview-only install is `cp -r`, which is what the manual row of the
installation table already says. The initializer's value is precisely the
parts practice does not need (workflow, config, badge, ruleset, branch,
Policy A boundary checks around all of them). Adding a mode that makes a
1,600-line script do less than a copy is surface without payoff.
`productionization.md`'s simplification backlog already records the
opposite direction ("ruleset/badge/branch automation could become
flags-off-by-default"); if that lands, `--skill-only` is a natural
consequence of it, not a separate feature. Trigger to reopen: an adopter
who wants the vendoring step's version-pin and update behaviour without
the gate.

### 3.5 Practice does not lower the tier

Alternative: practice always runs `standard`, or lets the learner pick any
tier freely. Rejected: the learner's question is "what would the real
thing ask me", and the answer depends on the tier the diff earns. `--quick`
under practice is still clamped by the four-row table, so a learner sees
the clamp fire and learns why. The cost is that a Tier 2 practice run on a
large range is long; that is information too.

### 3.6 One informative sentence in gsa-core, no version bump beyond patch

The practice marker is, like the approval marker, not a trailer; verifiers
never see it. gsa-core §2.3's marker paragraph gains one sentence (§4) so
the two markers are documented side by side and a second producer knows the
convention. Spec 3.8.0 → 3.8.1: informative only, no conformance vector,
no verifier change. Alternative: leave the spec silent. Rejected because
the approval marker's rationale lives there, and a reader of that paragraph
would otherwise not learn why a producer might refuse a snapshot that
*contains* the approval marker.

## 4. Spec deltas (gsa-core 3.8.0 → 3.8.1)

§2.3, marker paragraph, appended:

> A producer MAY also refuse a snapshot that carries evidence the interview
> was not solely the human's — the shipped producer emits
> `GSA-PRACTICE <utc-timestamp>` at the start of a practice interview
> (answers may be revealed) and `commit` refuses any snapshot containing
> it, anywhere. Like the approval marker, it is not a trailer and a
> verifier MUST NOT require or reject it.

No other spec text changes. Trailer schema, status derivation, notes
persistence, and the verifier's rules are untouched.

## 5. Implementation sketch

Slices, each independently testable and shippable in order.

1. **`attest.py`** (`0.5.0` → `0.6.0`):
   - `prepare --practice`: branch in `prepare()` after the unborn-HEAD
     check; skip `check_clean_tree` and the attestation-at-HEAD refusal
     (warn instead); `_prepare_range` takes a `working_tree: bool` that
     drops the second diff endpoint and adds the untracked-file warning;
     `PrepareState` gains `mode` and `practice_marker`; `write_record` is
     not called; `_print_prepare` ends with the practice marker.
   - `commit`: after the snapshot, `find_practice_marker(data)` over the
     full bytes; refusal is exit 3 with path, offset, and the marker text.
     Runs before the approval-marker check so the message names the real
     cause.
   - `prepare` (real): if the adapter resolves a readable transcript that
     contains a practice marker, append the warning of §2.4.
   - Docstring: the `prepare` entry, the exit-3 line, and a new
     `GSA-PRACTICE` line under the marker description.
2. **`SKILL.md`**:
   - §1 step 1: the practice command line beside the two existing ones;
     "practice mode never writes the preparation record and prints a
     practice marker instead of the approval marker".
   - §2, remediation: the one-sentence "hints exist only in `--practice`"
     rule; a new *Practice mode* subsection with the hint/reveal ladder
     (§2.6) and the scorecard (§2.5).
   - §3: opening sentence "not run in practice mode"; the invariant of
     §2.4's prompt layer.
   - *Modifiers*: the `--practice` row.
3. **Docs**: README §2.7 section and the *Modifiers* mention in *How to
   use it* step 3; HARNESSES.md modifier paragraph (line ~244) and
   portability rule on inline explanation; `docs/reference.md` `prepare`
   usage and exit-code table; `site/index.html` modifier sentence (line
   ~456); CHANGELOG under *Unreleased*; gsa-core §2.3 and its version line.
4. **Tests** (§6).

Estimated size: ~80 lines of `attest.py`, ~40 lines of `SKILL.md`, ~30
lines of docs, ~150 lines of tests. No new files outside `docs/`.

## 6. Test plan

`scripts/tests/test_attest.py`, following the `scratch_repo` fixtures:

- `test_prepare_practice_allows_dirty_tree` — unstaged and staged changes;
  exit 0; `mode == "practice"`.
- `test_prepare_practice_diffs_the_working_tree` — an uncommitted hunk
  appears in `diff` and `name_status`; a committed-only run does not
  differ from a real prepare's range.
- `test_prepare_practice_reports_untracked_files_by_count` — the warning
  names N and the `git add -N` remedy; the files are absent from the diff.
- `test_prepare_practice_writes_no_record_and_no_approval_marker` — no
  `prepared.json`; JSON has `practice_marker` and no `marker`; human output
  ends with the `GSA-PRACTICE` line; `attest.py marker` exits 3 afterwards.
- `test_prepare_practice_leaves_an_existing_record_alone` — real prepare,
  then practice; the record's bytes are unchanged.
- `test_prepare_practice_does_not_refuse_an_attestation_at_head` — warning,
  not exit 3.
- `test_prepare_practice_target_mode` — reviews `origin/<branch>`; the
  working-tree rule does not apply; integration branch still refused.
- `test_commit_refuses_a_transcript_containing_a_practice_marker` — a
  transcript with `GSA-PRACTICE` early and a valid `GSA-APPROVAL` at the
  end; exit 3; message names the offset; nothing committed, no notes.
- `test_commit_practice_marker_outside_the_approval_window_still_refuses`
  — marker more than 64 KiB before the end.
- `test_prepare_warns_when_the_conversation_already_practised` — real
  prepare with a readable transcript containing the practice marker.
- `test_commit_ack_no_transcript_cannot_see_a_practice_marker` — documents
  the accepted gap of §2.4 (passes today, pinned so a later change is
  deliberate).

`scripts/tests/test_skill_references.py`, in the Phase 3f contract test or
a sibling:

- `--practice` present in SKILL.md *Modifiers*, README, HARNESSES.md,
  `site/index.html`.
- The scorecard header line and the four axis rows are present verbatim.
- The sentence restricting hints to practice mode is present in the §2
  remediation rule.
- §3 states it is not run in practice mode.
- The self-containment test (`test_skill_folder_is_self_contained`) still
  passes: no new file in the skill folder.

`scripts/tests/test_conformance_vectors.py`, `test_verify_*`: unchanged
and must stay green, which is the evidence that the verifier did not move.

## 7. Questions for the reviewer

Ordered by how much a "no" would change.

1. **§3.3, the contamination rule.** Is "any practice marker anywhere in the
   conversation refuses commit" the right strength, or is it an
   over-correction that will be worked around by deleting the line from a
   transcript (which is possible on every harness and would also defeat the
   approval marker)? The author's position: the rule is for honest
   mistakes, forgery is already out of scope (roadmap, "authenticity
   beyond structure"), and strict-with-a-cheap-workaround beats
   scoped-with-a-hole.
2. **§2.2, working tree as the reviewed state.** A practice run has no
   tree SHA and no reviewed commit in the usual sense. Is anything in the
   hints (`components`, `skeptical_min_probes`) or the science guard
   assuming a committed range in a way that matters?
3. **§2.6, hints at Tier 2.** Prediction challenges reveal the actual
   behaviour by design. Does a practice hint before the prediction make the
   challenge meaningless, and should hints be withheld on prediction
   probes?
4. **§3.4.** Is "no initializer change" right, or is the initializer's
   vendoring (version pin, update path, Policy A checks on the destination)
   worth exposing without the gate now rather than on request?
5. **§2.5.** Is the scorecard the right terminal artifact, or should
   practice end the way a real interview does (a summary paragraph) so the
   two modes feel like one tool?
