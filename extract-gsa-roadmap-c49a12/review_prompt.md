# External Adversarial Review Prompt: Feature Spec

### Reviewer Identity & Session Continuity Directive
1. If you ALREADY established your REVIEWER_ID in an earlier turn of this session, YOU MUST REUSE IT. Do NOT generate a new ID.
2. If this is a fresh session, set your ID matching ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ (no '..' or '.lock'):
   `export REVIEWER_ID="reviewer-$(head -c 3 /dev/urandom 2>/dev/null | xxd -p 2>/dev/null || echo $RANDOM)"`
3. MANDATORY CHAT BANNER: In the very first lines of your chat response, you MUST print:
   ```text
   ### 🪪 Reviewer Identification Proof
   - Reviewer ID: ${REVIEWER_ID}
   - Target SHA Audited: 8c40819242d02ce94b95a7d28335a9b00b728b4f
   - Review File: reviews/${REVIEWER_ID}.md
   - Push Commit SHA: <your-push-sha or "pending — confirm post-push">
   ```

### Anti-Collision & Peer Isolation Invariants
1. FILE ISOLATION: You own ONLY `reviews/${REVIEWER_ID}.md`. Repository object-store reads (e.g. `git show`, `git diff`) of the audited branch and ephemeral review artifacts are permitted; WRITES to any file outside `reviews/${REVIEWER_ID}.md` are strictly forbidden. Never modify peer files in `reviews/`.
2. BRANCH ISOLATION: You are authorized to push ONLY to the specified review branch. Never push to `main`, `gemini/extract-gsa-roadmap-c49a12`, or peer branches. Never force-push.
3. TARGETED STAGING: NEVER run `git add .` or `git add -A`. Run ONLY `git add reviews/${REVIEWER_ID}.md`.
4. ABORT ON FOREIGN CONFLICT: On conflict outside `reviews/${REVIEWER_ID}.md`, immediately run `git rebase --abort`. If caused by duplicate ID (add/add conflict on your own file), regenerate `REVIEWER_ID` and retry with a fresh file. If retries exhausted, fall back to chat markdown or `scratch/external_reviews/<REVIEWER_ID>.md`.
5. UNIVERSAL TAMPER TRIPWIRE: All files outside `reviews/${REVIEWER_ID}.md` and all branches outside your assigned review branch are strictly READ-ONLY / UNTOUCHABLE. Touching unauthorized files or branches triggers immediate session termination by the user and permanent disqualification.

### Inspection Target
```bash
git fetch origin main && BASE_SHA=$(git rev-parse FETCH_HEAD)
git fetch origin gemini/extract-gsa-roadmap-c49a12 && git diff "${BASE_SHA}" FETCH_HEAD
```
Spec File: `extract-gsa-roadmap-c49a12/spec.md`

### Task & Scope
Audit `extract-gsa-roadmap-c49a12/spec.md` against codebase for:
1. Missing requirements or edge cases in extracting Section 6 from `skills/signoff/specs/gsa-core.md` into `docs/roadmap.md`.
2. Cross-reference correctness and broken link prevention across `README.md`, `docs/productionization.md`, `scripts/recover_notes.py`, `.github/workflows/notes-recovery.yml`.
3. Contract test consistency (`scripts/tests/test_skill_references.py` - `test_signoff_phase3f_adaptive_intensity_contract`).
4. Boundary self-containment rules (`test_skill_folder_is_self_contained` forbidding relative links escaping `skills/signoff/`).
5. Accuracy of roadmap contents and preservation of active Phase 3f and Phase 5 milestones.

### Output Protocol
Commit your findings to `reviews/${REVIEWER_ID}.md` on your assigned review branch (or push to `review/extract-gsa-roadmap-c49a12/${REVIEWER_ID}` in Mode A):
- Header must include `AUDITED_SHA: 8c40819242d02ce94b95a7d28335a9b00b728b4f` (or latest HEAD).
- Verdict: APPROVE or REVISE.
- Concrete technical findings with line citations.
- 3-5 line Adversarial Audit Summary ("What Was Caught & Fixed").
