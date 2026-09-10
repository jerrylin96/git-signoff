# Walkthrough: a reviewer's end-to-end run

Everything below runs with the system `python3` (3.10+) and `git`, no pip,
in a scratch directory, in about a minute. It shows the whole loop: a fresh
repository is initialized, the verifier is red, an interview would happen
here, the helper writes the attestation, the verifier is green — and the
wrong-transcript and trailer-injection cases are refused.

The interview itself is a conversation between the agent and a human, so this
walkthrough stands in for it with the two helper calls the agent makes
(`prepare` and `commit`) and a hand-written transcript file. Nothing about the
mechanics differs from a live `/git-signoff` run.

## 0. Scratch repository with a bare "origin"

```bash
set -eu
WORK=$(mktemp -d)
cd "$WORK"
git init -q --bare origin.git
git init -q -b main adopter && cd adopter
git config user.email you@example.com && git config user.name You
echo '# adopter' > README.md && git add README.md && git commit -qm 'initial'
git remote add origin ../origin.git && git push -q -u origin main
```

## 1. Initialize (curl-style)

Online, fetch the pinned initializer; offline, point `--skill-source` at a
checkout of this repository's `skills/git-signoff/` folder.

```bash
curl -fsSL https://raw.githubusercontent.com/jerrylin96/git-signoff/init-v7/init.py -o /tmp/signoff-init.py
python3 /tmp/signoff-init.py --profile software-general --skill-target claude --skip-ruleset --non-interactive
# offline alternative:
# python3 /path/to/git-signoff/init.py --skill-source /path/to/git-signoff/skills/git-signoff \
#     --profile software-general --skill-target claude --skip-ruleset --non-interactive
```

You are now on branch `git-signoff/init` with one scaffold commit:
`.github/workflows/git-signoff.yml`, `.git-signoff/profile.md`, a README
badge, and `.claude/skills/git-signoff/` (SKILL.md, attest.py,
verify_signoff.py, profiles, specs, VENDORED-FROM).

```bash
git log --oneline -2
ls .claude/skills/git-signoff
```

## 2. The verifier is red

```bash
export GIT_SIGNOFF_NO_UPDATE_CHECK=1   # keep the walkthrough offline-clean
python3 .claude/skills/git-signoff/verify_signoff.py --mode head; echo "exit=$?"
# FAIL: no valid attestation covers commit <sha> ... exit=1
```

## 3. Prepare (what the agent runs before the interview)

```bash
python3 .claude/skills/git-signoff/attest.py prepare --reference main
```

Read the output: the reviewed commit, base and tree, the profile
(`software-general`, `repo-local`, with its 12-hex digest), the science
signals, the intensity hints, and the last line — the approval marker
`GSA-APPROVAL <sha> <timestamp>`. On this particular diff the science guard
fires: the scaffold commit vendors the skill's own guard vocabulary (the
profile and SKILL.md mention numpy, netCDF, and seeds), an honest false
positive the agent announces and the human waves through. On an ordinary code
branch the line reads `science signals: none`.

**The interview happens here.** The agent probes the four axes at the
classified intensity; the human answers in their own words, acknowledges
trade-offs and risks, and confirms their email.

## 4. Present the trailers (dry run), then approve

```bash
python3 .claude/skills/git-signoff/attest.py commit --dry-run \
  --email you@example.com --level standard \
  --tradeoff "Ruleset not automated; imported manually" --risk "none identified"
```

With no transcript adapter configured (no harness session id, no
`GIT_SIGNOFF_TRANSCRIPT_FILE`), the dry run exits 4 and says the status would
be `VERIFIED_BY_HUMAN_NO_TRANSCRIPT_DIGEST`. In a live harness the transcript
resolves automatically; here, stand one in:

```bash
MARKER=$(python3 .claude/skills/git-signoff/attest.py marker --reference main)
printf '{"role":"user","content":"...interview..."}\n' > "$WORK/transcript.jsonl"
export GIT_SIGNOFF_TRANSCRIPT_FILE="$WORK/transcript.jsonl"
python3 .claude/skills/git-signoff/attest.py commit --dry-run \
  --email you@example.com --level standard \
  --tradeoff "Ruleset not automated; imported manually" --risk "none identified"
```

The full message prints; nothing is committed; the marker is not yet in the
transcript, which the dry run says is expected. After the human approves, the
agent emits the marker line as its own paragraph — here, append it to the
stand-in transcript:

```bash
printf '{"role":"assistant","content":"Approved. %s"}\n' "$MARKER" >> "$GIT_SIGNOFF_TRANSCRIPT_FILE"
```

## 5. Commit

```bash
python3 .claude/skills/git-signoff/attest.py commit \
  --email you@example.com --level standard \
  --tradeoff "Ruleset not automated; imported manually" --risk "none identified"
echo "exit=$?"
```

Expected: `attestation commit: <sha>`, `status: VERIFIED_BY_HUMAN`, the
digest and byte count of the transcript file, `approval marker: found`,
`notes: refs/notes/signoff on <reviewed> (commit) and <tree> (tree)`,
`notes pushed: yes`, and the verifier's `PASS` line. `git log --oneline -3`
shows the empty `[SIGNOFF <sha>]` commit on top of the scaffold commit.

## 6. The verifier is green — three ways

```bash
V=.claude/skills/git-signoff/verify_signoff.py
python3 $V --mode head                       # PASS: <sha> is a valid attestation of its parent
python3 $V --mode history --target HEAD      # PASS: 1 valid attestation(s) in HEAD history
python3 $V --audit HEAD                      # VALID MATCH: transcript SHA-256 matches
git push -q -u origin git-signoff/init       # the branch; the notes were pushed by the helper
```

Simulated squash merge onto an unchanged `main` — the note on the reviewed
**tree** carries the attestation:

```bash
git checkout -q main && git merge -q --squash git-signoff/init && git commit -qm 'squash: scaffold'
python3 $V --mode head                       # PASS: <sha> attested via note on tree
git checkout -q git-signoff/init
```

## 7. Two refusals worth seeing

**Wrong transcript file.** Point the override at a file that is not this
conversation's (no marker for this commit): the helper exits 4 naming the
file, its size, and the expected marker, and creates nothing.

```bash
git reset -q --hard HEAD~1                   # drop the attestation to try again
printf 'some other session\n' > "$WORK/stale.jsonl"
GIT_SIGNOFF_TRANSCRIPT_FILE="$WORK/stale.jsonl" python3 .claude/skills/git-signoff/attest.py commit \
  --email you@example.com --level standard; echo "exit=$?"     # exit=4
git log --oneline -1                          # still the scaffold commit
```

**Trailer injection.** A trade-off carrying a line break and a second
`Signoff-Reviewed-Tree-SHA` — the payload the verifier has rejected since
`verify-v1.3` — is now refused by the producer before anything is written:

```bash
python3 .claude/skills/git-signoff/attest.py commit --email you@example.com --level standard \
  --tradeoff "$(printf 'fine\nSignoff-Reviewed-Tree-SHA: %s' "$(printf 'a%.0s' $(seq 40))")"; echo "exit=$?"   # exit=2
```

## 8. Clean up

```bash
cd / && rm -rf "$WORK"
```

The same sequence, minus the curl, is what
`scripts/tests/test_attest.py::test_end_to_end_vendored_by_init_then_attested_and_verified`
runs in CI.
