# Implementation Plan: Extract Roadmap from GSA Core Protocol Specification

**Feature:** `extract-gsa-roadmap-c49a12`  
**Status:** Draft / Phase 1b  
**Target Worktree:** `/Users/jerrylin/.gemini/tmp/worktrees/gemini_extract-gsa-roadmap-c49a12`  
**Base Branch:** `main` (`9ea80748e0de0874fe63552ff7e868251ddf1deb`)  
**Feature Branch:** `gemini/extract-gsa-roadmap-c49a12`

---

## Execution Strategy
- [x] Standard Single Agent (Fast, atomic tasks)
- [ ] Sequential Subagents (`Workspace: inherit`) — *Recommended for 5 or more complex multi-file slices or external plan handoffs*

---

## 1. Overview & Architecture

Extract internal development milestone tracking and Section 6 (`## 6. Phase Gate Status`) out of `skills/signoff/specs/gsa-core.md` into dedicated `docs/roadmap.md`, while preserving protocol self-containment, updating contract tests, and maintaining historical cross-references (specifically the Phase 4 decision log anchor and Phase 5 open gates).

### Key Invariants:
1. **Zero Escaping Links**: `gsa-core.md` must end at Section 5 with zero relative links escaping `skills/signoff/` (`test_skill_folder_is_self_contained`).
2. **Anchor Resolution**: `docs/roadmap.md` must include heading `### Phase 4 amendment 2026-08-30` matching citations in `docs/productionization.md:212` and `README.md:286`.
3. **Accurate Empirical Statuses**: Document Pages deployed, live adaptive dogfood completed (`20c7120`, `2558ebc`), and PyPI `signoff-mcp` squatted on 2026-05-02.
4. **Atomic Commit Cadence**: All file modifications and test updates land in a single atomic commit in Phase 2 to ensure tests remain green.

---

## 2. Granular Task Breakdown & TDD Specifications

### Task 1: Write RED Test Suite (Contract Test Update)
Update `scripts/tests/test_skill_references.py` with failing contract assertions targeting the extracted roadmap and cleaned protocol spec.

- **RED Test Spec**:
  - File: `scripts/tests/test_skill_references.py`
  - Function: `test_signoff_phase3f_adaptive_intensity_contract`
  - Modifications:
    - Add `"docs/roadmap.md": None` to the `paths` dictionary while keeping `"skills/signoff/specs/gsa-core.md": None`.
    - Assert `docs/roadmap.md` contains:
      - `"Phase 3f (Adaptive Signoff Interview Intensity)"`
      - `"test_signoff_phase3f_adaptive_intensity_contract"`
      - `"Phase 5 (Cloud & Productionization)"`
      - `"Gate 0"`
      - `"Gate 1"`
      - `"Gate 2"`
      - `"Gate 3"`
      - `"Phase 4 amendment 2026-08-30"`
    - Assert `skills/signoff/specs/gsa-core.md` does NOT contain:
      - `"## 6. Phase Gate Status"`
      - `"Phase Gate Status"`
      - `"Phase 3f"`
      - `"Phase 5"`
      - `"(Stage 1a)"`
- **Expected Failure**:
  `docs/roadmap.md` does not exist on disk, causing `paths["docs/roadmap.md"]` to fail to load, and `gsa-core.md` currently contains `## 6. Phase Gate Status`.
- **Verify Command**:
  ```bash
  python3 ~/.gemini/scripts/run_in_env.py /Users/jerrylin/.gemini/tmp/worktrees/gemini_extract-gsa-roadmap-c49a12 pytest scripts/tests/test_skill_references.py -k test_signoff_phase3f_adaptive_intensity_contract
  ```

---

### Task 2: Pure Protocol Spec Cleanup & Dedicated Roadmap Creation
Implement `skills/signoff/specs/gsa-core.md` truncation and create `docs/roadmap.md`.

- **Target Files**:
  - `skills/signoff/specs/gsa-core.md`
  - `docs/roadmap.md`
- **Implementation Details**:
  - `skills/signoff/specs/gsa-core.md`:
    - Line 3: Update version header to `**Document Version:** 3.5.0 (removes Section 6 project tracking; moved to docs/roadmap.md)`.
    - Line 4: Update status header to `**Status:** Draft / Pending Review` (drop `(Stage 1a)`).
    - Line 179: Trim trailing `---` and remove Section 6 (`## 6. Phase Gate Status`, lines 181–196) to EOF.
  - `docs/roadmap.md`:
    - Create file under MIT license with title, purpose, provenance line (`Extracted from skills/signoff/specs/gsa-core.md §6 in v3.5.0`), and link back to `skills/signoff/specs/gsa-core.md`.
    - Retain historical summaries of Stages 1a–b, Phases 1–4, and Phases 3a–e.
    - Retain heading `### Phase 4 amendment 2026-08-30` with per-repo vendoring consolidation details.
    - Retain Phase 3f section with test identifier `test_signoff_phase3f_adaptive_intensity_contract` and live dogfood evidence (`20c7120`, `2558ebc`).
    - Retain open `[ ] Phase 5 (Cloud & Productionization)` with numbered gates 0–3, verified status notes (Gate 0 verified, Gate 1 Pages live, Gate 2 escrow spec draft, Gate 3 deferred), `verify-v1` tag status, PyPI name squatted notice, and standing instruction to iterate `docs/productionization.md`.
    - Prune session-ephemeral instructions and qualify/prune `scripts/sync_signoff_subtree.sh`.
- **Verify Command**:
  ```bash
  python3 ~/.gemini/scripts/run_in_env.py /Users/jerrylin/.gemini/tmp/worktrees/gemini_extract-gsa-roadmap-c49a12 pytest scripts/tests/test_skill_references.py -k "test_signoff_phase3f_adaptive_intensity_contract or test_skill_folder_is_self_contained"
  ```

---

### Task 3: Retarget Repository Cross-References
Update all references from `gsa-core.md §6` across documentation and CI scripts.

- **Target Files**:
  - `README.md`
  - `docs/productionization.md`
  - `scripts/recover_notes.py`
  - `.github/workflows/notes-recovery.yml`
- **Implementation Details**:
  - `README.md`:
    - Add `docs/roadmap.md` to document list around line 278–280.
    - Line 286: Update phrase and deep link to `[docs/roadmap.md#phase-4-amendment-2026-08-30](docs/roadmap.md#phase-4-amendment-2026-08-30)`.
    - Line 310: Update link `[gsa-core.md §6](skills/signoff/specs/gsa-core.md)` to `[docs/roadmap.md](docs/roadmap.md)`.
  - `docs/productionization.md`:
    - Line 5: Update `gsa-core.md §6 Phase 5` to `docs/roadmap.md Phase 5`.
    - Line 212: Update `gsa-core.md Phase 4 amendment 2026-08-30` to `docs/roadmap.md Phase 4 amendment 2026-08-30`.
  - `scripts/recover_notes.py`:
    - Line 4: Update `Phase 5 Gate 0 (gsa-core.md §6)` to `Phase 5 Gate 0 (docs/roadmap.md)`.
  - `.github/workflows/notes-recovery.yml`:
    - Line 3: Update `# Phase 5 Gate 0 (gsa-core.md §6)` to `# Phase 5 Gate 0 (docs/roadmap.md)`.
- **Verify Command**:
  ```bash
  git grep -n "gsa-core.md §6" # Must return 0 hits
  python3 ~/.gemini/scripts/run_in_env.py /Users/jerrylin/.gemini/tmp/worktrees/gemini_extract-gsa-roadmap-c49a12 pytest scripts/tests/
  ```

---

### Task 4: Complete Suite Verification, Linter, & Manifest
Run full verification across all tests and linters, compile review manifest.

- **Verify Commands**:
  ```bash
  python3 ~/.gemini/scripts/run_in_env.py /Users/jerrylin/.gemini/tmp/worktrees/gemini_extract-gsa-roadmap-c49a12 pytest
  python3 ~/.gemini/scripts/run_in_env.py /Users/jerrylin/.gemini/tmp/worktrees/gemini_extract-gsa-roadmap-c49a12 ruff check .
  ```
- Generate `review_manifest_extract-gsa-roadmap-c49a12.md`.
