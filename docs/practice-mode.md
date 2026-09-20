# Design: explanation and practice before signoff

**Status:** Implementation design, revised 2026-09-20 from the draft on
`claude/zealous-goodall-tnk50s`. The implementation branch is
`codex/learning-modes`. This replaces the original draft's raw transcript
search, unchanged reference-resolution rule, and practice-only hints rule.

The goal is to help someone understand a change, rehearse an interview, or
produce a real attestation without confusing those outcomes. Learning needs
no PR, workflow, badge, ruleset, email, or attestation. It still needs a Git
repository with an initial commit.

## 1. User-facing modes

| Invocation | Experience | Ending |
|---|---|---|
| `/git-signoff --explain [branch]` | Guided explanation and Q&A | Recap, open questions, coverage |
| `/git-signoff --practice [branch]` | Rehearsal using the real profiles and tier rules | Advisory scorecard |
| `/git-signoff [branch]` | Real interview and explicit approval | Existing attestation process |

`--explain` and `--practice` are mutually exclusive. `--quick` and
`--deep` retain their existing meaning and safety clamps for interviews,
including practice. Explanation has no interview tier or grade; the human
requests more or less detail conversationally. Reject intensity modifiers
with `--explain` rather than implying an assessment ran.

Use `--explain`, not `--prepare`, for the user-facing walkthrough:
`attest.py prepare` already names the helper's mechanical preparation.
The helper gains mutually exclusive `prepare --explain` and
`prepare --practice` flags. Real prepare's default behavior is unchanged.

## 2. Learning-state contract

Both learning modes share range inspection and return `mode` explicitly.
Neither writes or replaces `.git/git-signoff/prepared.json`, creates an
approval marker, asks for email, writes commits/notes, or publishes anything.
An existing preparation record remains byte-for-byte unchanged.
`write_record` itself rejects a learning state.
Inspection is read-only. Actually starting practice is a separate helper
command that writes a local session guard in shared Git metadata (§5).

Local learning compares the merge base to the current tracked working files.
An explicit `--reference` wins. Otherwise preserve the existing usable
upstream/integration-base precedence; on the integration branch with nothing
unpushed, or when there is no usable base in a local-only repository, use
HEAD as the base for uncommitted work. Decide emptiness from the resulting
diff, not solely from commit ancestry. A clean empty range produces an
actionable explanation and no empty quiz.

An already-attested tip is a warning, not a learning refusal. An unborn
branch is still an error: create the initial commit before inspecting a
range.

A named target fetches and inspects `origin/<branch>` as committed content;
the local working tree is not included. Learning may inspect the integration
branch with an explicit earlier reference, unlike attestation target mode.
Without a meaningful difference, report an empty learning scope. Target
inspection fetches objects and updates a tracking ref; the promise is no
attestation or working/index changes, not that every Git byte is untouched.

### 2.1 Working files are not necessarily the next commit

`git diff <base>` describes current tracked files, including unstaged
changes, rather than the staged snapshot. A staged change followed by an
unstaged reversal can disappear from this diff while still appearing in the
next commit. Report when staged and working scopes differ; do not silently
claim to review what the next `git commit` will record.

Untracked files are excluded and named/count-reported. The helper may
suggest `git add -N -- <path>`, but never runs it. Ignored files remain
excluded under Git's normal rules. Read operations disable optional Git
locks and external diff/textconv helpers.

### 2.2 Captured scope and drift

Learning JSON contains the captured `diff`, statistics, profile, hints,
`state_kind` (`working-tree` or `commit`), and `snapshot_id`.
For a local working-tree inspection, `context_head_sha` identifies context;
`reviewed_commit_sha` and `tree_sha` are null because HEAD does not
identify the uncommitted content. Target inspection has real commit/tree
identities. `diff_command` is explanatory; the captured patch is what the
agent reads.

Capture the patch before and after collecting statistics, refusing an
observed change. The snapshot fingerprint includes base, context commit,
target, patch, staged comparison, excluded untracked names, and profile.
This is a best-effort consistency check, not an atomic filesystem snapshot.

Save large learning JSON output in an ephemeral scratch file and read it in
bounded chunks. Do not interpret terminal truncation as end-of-diff. Do not
persist diffs, answers, or scores in the repository. The small session guard
records only that practice started, separately from learning content.

Before issuing a recap/scorecard, rerun the same learning command with
`--check-snapshot <snapshot_id>`. Drift exits 3: inspect again, explain
what changed, and revisit affected material. Only clear the open gaps after
covering the new state. Real prepare does not accept this flag.

Intensity and science helpers consume the captured diff and numstat; they
need no committed-range-specific alternative.

## 3. Explanation

Inspired by the read-only, summary-first walkthrough in
[explain-diff](https://github.com/jerrylin96/dotgemini/tree/gemini/explain-diff-anti-hallucination-765133/skills/explain-diff).
The implementation is self-contained skill instructions and shared range
inspection, with no dependency on that repository, its tools, or resolver.

First explain the selected scope, before/after behavior, main components,
and how they interact. Distinguish observed code, author claims in commit
messages/docs, and inferred rationale. If why is unknown, say so.

Offer topic exploration, with file and commit views when useful, and
follow-up Q&A. Ground claims in inspected code/context, cite locations, and
quote displayed excerpts faithfully. Never invent execution or test results.
Report resolution/read failures separately from a genuinely empty diff.
Mention relevant non-text changes and material not inspected.

The walkthrough is not an automatic bug hunt or code-editing phase. Mention
concrete issues encountered; do not hide them or fix them without a separate
request. Do not run tests as part of learning. End with a recap, unresolved
questions, and coverage; there is no score or pass claim.

Finishing explanation is not consent to begin an interview. On an explicit
request, explanation can lead to practice or a real interview in the same
conversation. For real signoff, first commit outstanding work as appropriate,
run a fresh real prepare, and test understanding using new scenarios rather
than repeating worked examples. The full approval process still applies.

## 4. Practice and remediation

Use the same profiles, science guard, tier selection, escalation, and
coverage requirements as the real interview. Learning does not lower rigor;
an unfinished run is simply incomplete. The learner can stop or skip.

Obtain an initial answer/prediction before assistance. On difficulty, give a
hint and retry; if needed or requested, reveal the answer and its mechanics,
then continue. The learner need not demonstrate mastery before moving on.
A correct prediction followed by explanation of its result is still unaided.

Real interviews continue to allow hints/explanations as remediation. They
require independent understanding on a fresh scenario afterward. There is
no blanket ban on teaching during a real interview.

### 4.1 Scorecard

Track assistance and demonstrated understanding separately:

```text
Practice scorecard — <level> / <profile-id>
Scope: <base> -> <working-tree snapshot or target commit>

Axis                         Probes  Unaided  Hinted  Revealed  Open gaps
Mechanics & intent
Trade-offs & edge cases
Boundary & failure loudness
Ownership

Coverage: <complete for the selected tier, or incomplete; omissions>
Trade-offs discussed: <items or none>
Risks and concrete silent failures found: <items or none>
Readiness for a fresh signoff interview: <ready / needs practice / incomplete>
Next steps: <specific gaps; a fresh conversation is required to attest>
```

Count each completed scenario once under its highest assistance level.
Skipped/unanswered material is an open gap, not an unaided success.
Unasked axes are "not assessed" (including axes outside Tier 0's required
coverage). Fresh successful scenarios may resolve earlier gaps without
erasing the assistance used. Preserve component coverage and Tier 2's
minimum probes and prediction requirements. Readiness is advisory, never a
claim that an attestation was earned. Finding an unresolved silent failure
also prevents a "ready" assessment.

## 5. Practice-session separation

An actual practice run requires a fresh conversation before real signoff.
Practice never requests approval or invokes `commit`. This prevents an
accidental promotion of a rehearsal; it is not proof against forgery or
proof that a person has never been taught the material.

### 5.1 Local session record: the primary guard

Inspect the nonempty scope first. Immediately before the first probe, run
`attest.py practice-start --json`. It writes
`<git-common-dir>/git-signoff/practice-sessions/<session-key>.json` and
returns `guard: local-record`, `practice_record`, `created`, and a backup
`practice_marker`. The file contains a format version, hashed session key,
and start timestamp; no answers, transcript contents, or raw conversation id.

The key hashes the current conversation id, or the canonical transcript path
when a generic export has no conversation id. The same repository's linked
worktrees share the Git common directory, so switching worktrees or branches
does not clear the guard. A new conversation id has a different key. A generic
path must identify one session; use a new path for a new session.

Practice-start never overwrites an existing record. File presence blocks
signoff even if a failed write left it empty/partial. A write error exits 6
and stops practice before the first probe. A guard lookup error exits 3;
unknown state is not treated as absence. There is no in-session reset or
expiry. New sessions do not remove the old session's record.

Real prepare and `marker` refuse the recorded session (exit 3). Commit checks
before loading preparation state and again after transcript snapshot/retries,
before any writes, including target mode and dry-run. Missing or unrecognized
transcripts and `--ack-no-transcript` do not bypass this check. Learning
inspection and explanation remain available after practice.

If neither an id nor a transcript path is available, practice-start returns
`guard: instruction-only`, null record/marker fields, and a warning. That
unidentified case still relies on the fresh-conversation instruction.

### 5.2 Dedicated assistant event: transcript backup

When identity is available, practice-start returns
`GSA-PRACTICE <session-key-24hex> <utc-timestamp>`.
Before the first probe, the agent emits a separate assistant message whose
entire text is that line: no prose, code fence, quotation, or tool call.

Use the event from practice-start's result. Inspection alone does not start
practice, even though practice prepare also exposes the marker format. The
key is not secret; this event provides a backup if the local record is absent.

The helper parses top-level JSONL message envelopes and checks the entire
assistant text, not arbitrary transcript substrings. Supported forms:
- Claude `type: assistant` / `message.role: assistant`, text content.
- Codex `type: response_item` / `payload.type: message` /
  `payload.role: assistant`, output-text content.
- Normalized `{"role":"assistant","content":"<exact control line>"}`.
  Generic/Antigravity exports can use this form.

Nested JSON in user/tool messages, quoted examples, code blocks, and markers
for another session are not events. Native events with an explicit different
session id are also ignored. A generic file should contain one session;
reusing its path as a different session is not a supported identity scheme.

Real prepare warns early when it recognizes practice. Both dry-run and real
commit refuse with exit 3, naming the event's byte offset and transcript
path. Check the final bytes used for the digest, including a snapshot retry.
Search the whole snapshot, not only the final approval-marker window.

### 5.3 Limits

Opaque text, unrecognized transcript schemas, and unavailable transcripts
prevent only backup detection; the local record still enforces separation.
No identity/path means the helper cannot bind either guard to a session.

The record is local to this repository and its linked worktrees. Pushes,
clones, other repositories, and copied working files do not carry it; those
contexts rely on the transcript backup or the skill instructions. Explicit
practice-start is required; inspection alone never writes it. Changing the
identity/path, deleting records, or modifying/discarding transcript events
can defeat the guards. They prevent accidental promotion, not deliberate
forgery, and do not claim transaction locking against concurrent interviews.

No-transcript attestation in a fresh session keeps its existing explicit
acknowledgment and downgraded status. There is no new trailer, attestation
status, verifier rule, or claim of stronger transcript authenticity.

Explanation alone does not emit a practice event or poison the conversation.
Simply reading this design or the implementation's tests must not refuse a
real signoff.

## 6. Installation and release

Show a manual copy-the-skill learning path before the initializer in README.
Install on the base before starting a feature when possible, so vendoring
does not dominate the practice diff. No workflow or PR is required.

There is no new initializer flag. There are new immutable delivery pins:
`init-v10` for the updated skill, and `verify-v1.7` for the bundled
missing-gh recovery fix. Update templates, snippets, pin workflow, and tests.
Project/helper version 0.5.0 stays synchronized with release metadata until
the next project release. Core spec 3.8.1 adds an informative producer note
only; wire spec 1.0, evidence rules, and existing attestations are unchanged.

## 7. Validation

Test real and learning paths separately:
- dirty integration branch, local-only repo, feature and explicit reference;
- staged/working disagreement, excluded untracked files, empty ranges;
- existing attestation tips and remote target scope;
- learning JSON/CLI identity, captured diff, drift refusal, profile/science;
- no index/ref/notes/preparation-record writes in local learning;
- explicit practice-start records, missing/opaque transcripts, no-transcript
  acknowledgment refusal, linked worktrees, fresh sessions, generic-path
  identity, idempotence, write/read errors, and partial records;
- practice events versus quotes, fixtures, tool output, foreign sessions,
  native/normalized envelopes, old events, and the final retried snapshot;
- explanation followed by fresh real prepare/commit; no-transcript limits;
- missing-gh recovery: auto reports incomplete, none stays intentional;
- unchanged existing producer/verifier/conformance tests, lint and pin tests.

Keep the recovery fix independently reviewable from the learning feature.
No implementation step conducts an interview, creates an attestation,
merges a branch, or publishes release tags.
