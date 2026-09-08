# External Adversarial Review Prompt: Feature Spec (Round 2 Re-Audit)

### Reviewer Identity & Session Continuity Directive
1. If you ALREADY established your REVIEWER_ID in an earlier turn of this session (`reviewer-3203`, `reviewer-20402`, `reviewer-20183`), YOU MUST REUSE IT. Do NOT generate a new ID.
2. If this is a fresh session, set your ID matching ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ (no '..' or '.lock'):
   `export REVIEWER_ID="reviewer-$(head -c 3 /dev/urandom 2>/dev/null | xxd -p 2>/dev/null || echo $RANDOM)"`
3. MANDATORY CHAT BANNER: In the very first lines of your chat response, you MUST print:
   ```text
   ### 🪪 Reviewer Identification Proof
   - Reviewer ID: ${REVIEWER_ID}
   - Target SHA Audited: <commit-sha>
   - Review File: reviews/${REVIEWER_ID}.md
   - Push Commit SHA: <your-push-sha or "pending — confirm post-push">
   ```

### Anti-Collision & Peer Isolation Invariants
1. FILE ISOLATION: You own ONLY `reviews/${REVIEWER_ID}.md`. Repository object-store reads (e.g. `git show`, `git diff`) of the audited branch and ephemeral review artifacts are permitted; WRITES to any file outside `reviews/${REVIEWER_ID}.md` are strictly forbidden. Never modify peer files in `reviews/`.
2. BRANCH ISOLATION: You are authorized to push ONLY to your assigned review branch. Never push to `main`, `gemini/extract-gsa-roadmap-c49a12`, or peer branches. Never force-push.
3. TARGETED STAGING: NEVER run `git add .` or `git add -A`. Run ONLY `git add reviews/${REVIEWER_ID}.md`.
4. ABORT ON FOREIGN CONFLICT: On conflict outside `reviews/${REVIEWER_ID}.md`, immediately run `git rebase --abort`. If caused by duplicate ID (add/add conflict on your own file), regenerate `REVIEWER_ID` and retry with a fresh file. If retries exhausted, fall back to chat markdown or `scratch/external_reviews/<REVIEWER_ID>.md`.
5. UNIVERSAL TAMPER TRIPWIRE: All files outside `reviews/${REVIEWER_ID}.md` and all branches outside your assigned review branch are strictly READ-ONLY / UNTOUCHABLE. Touching unauthorized files or branches triggers immediate session termination by the user and permanent disqualification.

### Inspection Target
```bash
git fetch origin main && BASE_SHA=$(git rev-parse FETCH_HEAD)
git fetch origin gemini/extract-gsa-roadmap-c49a12 && git diff "${BASE_SHA}" FETCH_HEAD
```
Spec File: `extract-gsa-roadmap-c49a12/spec.md`  
Scorecard: `extract-gsa-roadmap-c49a12/reviewer_scorecard.md`

### Task & Scope (Re-Audit)
Audit the revised `extract-gsa-roadmap-c49a12/spec.md` to verify whether prior Round 1 findings have been fully and accurately addressed:
1. Retention of `Phase 4 amendment 2026-08-30` anchor for `docs/productionization.md:212`.
2. Clean self-containment with zero escaping relative markdown links in `skills/signoff/specs/gsa-core.md`.
3. Open Phase 5 gates (0)–(3) retention with accurate empirical status (Pages deployed, live dogfood done, PyPI name squatted, actionable checklists preserved).
4. Atomic single commit and updated contract tests in `scripts/tests/test_skill_references.py`.
5. Document Version bump to `3.5.0` on `gsa-core.md` line 3.

### Output Protocol
Append or update your findings in `reviews/${REVIEWER_ID}.md` on your assigned review branch:
- Header must include `AUDITED_SHA: <current-feature-sha>`.
- If all prior findings are resolved, emit `VERDICT: APPROVE` and mark resolved items `[x] (Resolved in commit <sha>)`.
- If open issues remain, emit `VERDICT: REVISE` with concrete line citations.
- 3-5 line Adversarial Audit Summary ("What Was Caught & Fixed").
