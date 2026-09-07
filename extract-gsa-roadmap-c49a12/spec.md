# Specification: Extract Roadmap from GSA Core Protocol Specification

**Feature:** `extract-gsa-roadmap-c49a12`  
**Status:** Draft / Phase 1a  
**Target Scope:** `skills/signoff/specs/gsa-core.md`, `docs/roadmap.md`, `scripts/tests/test_skill_references.py`, `README.md`, `docs/productionization.md`, `scripts/recover_notes.py`, `.github/workflows/notes-recovery.yml`

---

## 1. Background & Rationale

`skills/signoff/specs/gsa-core.md` is the canonical protocol specification for the Git Signoff Attestation (GSA) Protocol Core, licensed under the Community Specification License 1.0 (`Community-Spec-1.0`). Its purpose is to serve as an open, platform-neutral standard suitable for review and adoption by external developers and standards bodies (e.g., OpenSSF / Linux Foundation).

Currently, Section 6 (`## 6. Phase Gate Status`) embeds internal project development logs, sprint checklists, obsolete distribution details (e.g. retired Claude Code plugin marketplace references), and ephemeral workflow instructions directly within the protocol spec. 

Mixing internal repo sprint tracking into a formal protocol specification violates specification hygiene and introduces stale implementation details into a public spec.

## 2. Requirements & Goals

### 2.1 Pure Protocol Spec (`skills/signoff/specs/gsa-core.md`)
- Remove Section 6 (`## 6. Phase Gate Status`) in its entirety from `skills/signoff/specs/gsa-core.md`.
- Ensure `gsa-core.md` strictly contains normative protocol architecture, data structures, trailers, adapter interfaces, and verification algorithms (Sections 1 through 5).
- Clean up stale header metadata: remove `(Stage 1a)` sprint token from `gsa-core.md` line 4, standardizing on `**Status:** Draft / Pending Review (Community-Spec-1.0)`.

### 2.2 Dedicated Roadmap Document (`docs/roadmap.md`)
- Create `docs/roadmap.md` to house the phase gate status and milestone roadmap.
- Clean up outdated content:
  - Remove session-ephemeral instructions (e.g., *"before ending a session, adversarially review any plan changes..."*).
  - Prune obsolete Claude Code plugin marketplace notes from Phase 4, keeping the authoritative record of the current per-repo vendoring model (`.claude/skills/signoff/`).
- Retain active backlog items and status records:
  - Phase 3f (Adaptive Signoff Interview Intensity): prompt-level shipped, live classification dogfood pending; must explicitly retain the test identifier string `test_signoff_phase3f_adaptive_intensity_contract`.
  - Phase 5 (Cloud & Productionization): notes-recovery automation (shipped), project website (shipped, pending repo-level Pages enablement), escrow spec (reviewed draft), cloud storage escrow implementation (deferred pending demand).
  - Historical milestones (Stages 1a-b, Phases 1-4, Phase 3a-e) summarized concisely.

### 2.3 Cross-Reference & Contract Test Updates
- Update `scripts/tests/test_skill_references.py`:
  - Update `test_signoff_phase3f_adaptive_intensity_contract` to load `docs/roadmap.md` into `paths`, assert `docs/roadmap.md` contains `"Phase 3f (Adaptive Signoff Interview Intensity)"`, `"test_signoff_phase3f_adaptive_intensity_contract"`, and `"live classification dogfood pending"`, and assert `skills/signoff/specs/gsa-core.md` no longer contains `"## 6. Phase Gate Status"`, `"Phase 3f"`, or `"Phase 5"`.
- Update documentation cross-links:
  - `README.md`: Update reference from `[gsa-core.md §6](skills/signoff/specs/gsa-core.md)` to `[docs/roadmap.md](docs/roadmap.md)` (line 310) and update phrase `every surface; the spec's phase log records the history.` (line 286) to reference `[docs/roadmap.md](docs/roadmap.md)`.
  - `docs/productionization.md`: Update header reference `gsa-core.md §6 Phase 5` (line 5) to `docs/roadmap.md Phase 5`, and update decision log reference `gsa-core.md Phase 4 amendment 2026-08-30` (line 212) to `docs/roadmap.md Phase 4 amendment 2026-08-30`.
  - `scripts/recover_notes.py`: Update header comment reference `Phase 5 Gate 0 (gsa-core.md §6)` to `Phase 5 Gate 0 (docs/roadmap.md)`.
  - `.github/workflows/notes-recovery.yml`: Update header comment reference `# Phase 5 Gate 0 (gsa-core.md §6)` to `# Phase 5 Gate 0 (docs/roadmap.md)`.

## 3. Non-Goals
- No changes to GSA protocol wire format, trailer grammar, or algorithms in Sections 1–5.
- No changes to `signoff_mcp` runtime behavior or adapter implementations.
- No deletion of still-relevant roadmap items (Phase 3f and Phase 5 gates).
- No relative markdown links escaping `skills/signoff/` from `skills/signoff/specs/gsa-core.md` (enforced by `test_skill_folder_is_self_contained`).

## 4. Verification & Testing
- Run contract test suite: `python3 ~/.gemini/scripts/run_in_env.py <worktree> pytest scripts/tests/test_skill_references.py`.
- Run full test suite: `python3 ~/.gemini/scripts/run_in_env.py <worktree> pytest`.
- Verify markdown link validity across all touched documents.
