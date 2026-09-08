# Specification: Extract Roadmap from GSA Core Protocol Specification

**Feature:** `extract-gsa-roadmap-c49a12`  
**Status:** Revised / Phase 1a  
**Target Scope:** `skills/signoff/specs/gsa-core.md`, `docs/roadmap.md`, `scripts/tests/test_skill_references.py`, `README.md`, `docs/productionization.md`, `scripts/recover_notes.py`, `.github/workflows/notes-recovery.yml`

---

## 1. Background & Rationale

`skills/signoff/specs/gsa-core.md` is the canonical protocol specification for the Git Signoff Attestation (GSA) Protocol Core, licensed under the Community Specification License 1.0 (`Community-Spec-1.0`). Its purpose is to serve as an open, platform-neutral standard suitable for review and adoption by external developers and standards bodies (e.g., OpenSSF / Linux Foundation).

Currently, Section 6 (`## 6. Phase Gate Status`) embeds internal project development logs, sprint checklists, obsolete distribution details (e.g. retired Claude Code plugin marketplace references), and ephemeral workflow instructions directly within the protocol spec. 

Mixing internal repo sprint tracking into a formal protocol specification violates specification hygiene and introduces stale implementation details into a public spec.

## 2. Requirements & Goals

### 2.1 Pure Protocol Spec (`skills/signoff/specs/gsa-core.md`)
- Remove Section 6 (`## 6. Phase Gate Status`) in its entirety (lines 181 to EOF) from `skills/signoff/specs/gsa-core.md`, trimming the trailing horizontal rule (`---`) immediately preceding it.
- Ensure `gsa-core.md` strictly contains normative protocol architecture, data structures, trailers, adapter interfaces, and verification algorithms (Sections 1 through 5).
- Bump Document Version on line 3 from `3.4.0 (adds the specification license declaration)` to `3.5.0 (removes Section 6 project tracking; moved to docs/roadmap.md)`.
- Clean up header metadata: standardize line 4 to `**Status:** Draft / Pending Review` (stripping `(Stage 1a)` only; preserving the existing `Community-Spec-1.0` declaration on line 7 without duplicate insertion into Status).
- Self-containment & Vendoring Hygiene: Ensure `gsa-core.md` ends at Section 5 with no relative markdown links escaping `skills/signoff/`, preserving compliance with `test_skill_folder_is_self_contained` when vendored into downstream repositories via `init.py`.

### 2.2 Dedicated Roadmap Document (`docs/roadmap.md`)
- Create `docs/roadmap.md` under the repository MIT license to house the phase gate status and milestone roadmap.
- Header & Provenance:
  - Document title and purpose statement explaining that this is an internal, non-normative development milestone roadmap.
  - Explicit provenance notice: "Extracted from `skills/signoff/specs/gsa-core.md` §6 in v3.5.0".
  - Link back to normative protocol core specification (`skills/signoff/specs/gsa-core.md`).
- Content Cleanup:
  - Remove session-ephemeral instructions (e.g., *"before ending a session, adversarially review any plan changes..."*).
  - Prune obsolete Claude Code plugin marketplace notes from Phase 4, keeping the authoritative record of the current per-repo vendoring model (`.claude/skills/signoff/`).
  - Prune or qualify unverified/retired external helper script paths (e.g., clarify that `scripts/sync_signoff_subtree.sh` was a dotgemini-side script, not present in this repository).
- Retained Backlog Items & Milestones:
  - **Phase 4 Decision Log Anchor**: Explicitly retain the heading `### Phase 4 amendment 2026-08-30` (or `Phase 4 amendment 2026-08-30`) documenting the consolidation of distribution to per-repo vendoring and retirement of marketplace channels, ensuring the decision log citation in `docs/productionization.md:212` resolves.
  - **Phase 3f (Adaptive Signoff Interview Intensity)**: Retain heading and test identifier `test_signoff_phase3f_adaptive_intensity_contract`; update status to reflect prompt-level shipped and note live adaptive-classification dogfood attestations recorded on `main` (`20c7120` and `2558ebc`).
  - **Phase 5 (Cloud & Productionization)**: Keep as an open backlog item (`[ ] Phase 5 (Cloud & Productionization)`) with numbered gates (0)–(3):
    - Gate 0: Notes-recovery automation (shipped & verified on `main`).
    - Gate 1: Dedicated project website (shipped and deployed via GitHub Pages).
    - Gate 2: Cloud concept promoted to reviewed spec (`specs/gsa-escrow.md` reviewed draft; user-owned baseline).
    - Gate 3: Cloud storage for conversations (deferred pending demand).
    - Retain actionable to-do items: `verify-v1` tag self-healing check, and PyPI publish status updated to note package name `signoff-mcp` squatted on 2026-05-02.
    - Retain standing instruction: iterate `docs/productionization.md` whenever Phase 5 is touched.
  - **Historical Milestones**: Concisely summarize Stages 1a–b, Phases 1–4, and Phases 3a–e with stable markdown anchors.

### 2.3 Cross-Reference & Contract Test Updates
- **Atomic Single Commit**: Ensure `gsa-core.md` extraction, `docs/roadmap.md` creation, documentation updates, and test updates land in a single commit so contract tests never fail between intermediate edits.
- Update `scripts/tests/test_skill_references.py`:
  - In `test_signoff_phase3f_adaptive_intensity_contract`:
    - Add `"docs/roadmap.md": None` to the `paths` dictionary while retaining `"skills/signoff/specs/gsa-core.md": None`.
    - Assert `docs/roadmap.md` contains `"Phase 3f (Adaptive Signoff Interview Intensity)"`, `"test_signoff_phase3f_adaptive_intensity_contract"`, `"Phase 5 (Cloud & Productionization)"`, `"Gate 0"`, `"Gate 1"`, and `"Phase 4 amendment 2026-08-30"`.
    - Assert `skills/signoff/specs/gsa-core.md` does NOT contain `"## 6. Phase Gate Status"`, `"Phase Gate Status"`, `"Phase 3f"`, `"Phase 5"`, or `"(Stage 1a)"`.
- Update documentation cross-links:
  - `README.md`:
    - Add `docs/roadmap.md` to the document list under documentation overview (`README.md:278-280`).
    - Update line 286 phrase and deep-link to `[docs/roadmap.md#phase-4-amendment-2026-08-30](docs/roadmap.md#phase-4-amendment-2026-08-30)`.
    - Update line 310 link `[gsa-core.md §6](skills/signoff/specs/gsa-core.md)` to `[docs/roadmap.md](docs/roadmap.md)`.
  - `docs/productionization.md`:
    - Update header reference on line 5 from `gsa-core.md §6 Phase 5` to `docs/roadmap.md Phase 5`.
    - Update decision log reference on line 212 from `gsa-core.md Phase 4 amendment 2026-08-30` to `docs/roadmap.md Phase 4 amendment 2026-08-30`.
  - `scripts/recover_notes.py`:
    - Update header comment reference on line 4 from `Phase 5 Gate 0 (gsa-core.md §6)` to `Phase 5 Gate 0 (docs/roadmap.md)`.
  - `.github/workflows/notes-recovery.yml`:
    - Update header comment reference on line 3 from `# Phase 5 Gate 0 (gsa-core.md §6)` to `# Phase 5 Gate 0 (docs/roadmap.md)`.

## 3. Non-Goals
- No changes to GSA protocol wire format, trailer grammar, or algorithms in Sections 1–5.
- No changes to `signoff_mcp` runtime behavior or adapter implementations.
- No relative markdown links escaping `skills/signoff/` from `skills/signoff/specs/gsa-core.md` (enforced by `test_skill_folder_is_self_contained`).
- No deletion of open roadmap gates or pending user action items.

## 4. Verification & Testing
- In-repo test runner:
  - `pytest scripts/tests/test_skill_references.py`
  - `pytest`
- Isolated runner:
  - `python3 ~/.gemini/scripts/run_in_env.py /Users/jerrylin/.gemini/tmp/worktrees/gemini_extract-gsa-roadmap-c49a12 pytest`
- Automated cross-reference verification:
  - Verify grep returns 0 hits for `gsa-core.md §6` across the entire repository.
  - Verify all relative links across touched documents resolve to valid existing files.
