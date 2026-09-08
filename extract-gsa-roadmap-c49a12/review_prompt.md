# External Adversarial Review Prompt: Code Implementation (GREEN)

### Reviewer Identity & Session Continuity Directive
1. If you ALREADY established your REVIEWER_ID in an earlier turn of this session (`reviewer-20402`, `reviewer-20183`), YOU MUST REUSE IT. Do NOT generate a new ID.
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
Files:
- `skills/signoff/specs/gsa-core.md`
- `docs/roadmap.md`
- `scripts/tests/test_skill_references.py`
- `README.md`
- `docs/productionization.md`
- `scripts/recover_notes.py`
- `.github/workflows/notes-recovery.yml`

### Task & Scope (GREEN Implementation Audit)
Audit full implementation against `extract-gsa-roadmap-c49a12/spec.md` and `plan.md`:
1. `skills/signoff/specs/gsa-core.md`: Section 6 removed; Version 3.5.0; status Draft / Pending Review; ends cleanly at Section 5.1 with single newline; self-containment intact (no relative links escaping `skills/signoff/`).
2. `docs/roadmap.md`: Full provenance, MIT license, back-link `../skills/signoff/specs/gsa-core.md`, stable heading `### Phase 4 amendment 2026-08-30`, Phase 3f dogfood notes on `main`, open Phase 5 gates with accurate empirical statuses.
3. Cross-references: Scoped grep `git grep -n "gsa-core.md §6" -- . ':(exclude)extract-gsa-roadmap-c49a12'` yields 0 hits.
4. Relative link resolution: All relative markdown links across touched files resolve to real repository paths.
5. Tests: `pytest scripts/tests/` passes 100% (113 passed), `ruff check .` passes cleanly.

### Output Protocol
Commit findings to `reviews/${REVIEWER_ID}.md`:
- Header must include `AUDITED_SHA: <current-feature-sha>`.
- Verdict: APPROVE or REVISE.
- 3-5 line Adversarial Audit Summary ("What Was Caught & Fixed").
