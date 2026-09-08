# Project Roadmap & Phase Gate Status

**Status:** Living Document  
**License:** MIT License (reference implementation and project documentation)  
**Provenance:** Extracted from [skills/signoff/specs/gsa-core.md](../skills/signoff/specs/gsa-core.md) §6 in v3.5.0  
**Canonical Protocol Specification:** [skills/signoff/specs/gsa-core.md](../skills/signoff/specs/gsa-core.md)

This document tracks development milestones, retrospective phase gate logs, and operational backlog items for the `signoff` repository. While the core attestation protocol is specified under `Community-Spec-1.0` in [skills/signoff/specs/gsa-core.md](../skills/signoff/specs/gsa-core.md), this roadmap records implementation progress and project-level tracking under the repository's MIT license.

---

## 1. Active Backlog & Ongoing Phases

### Phase 3f (Adaptive Signoff Interview Intensity)
- [x] **Prompt-Level Implementation**: Dynamic auto-classification of interview intensity based on diff semantics and blast radius when bare `/signoff` is invoked without explicit modifiers: Tier 0 (`cursory` for pure docs/types <50 LoC), Tier 1 (`standard` for default feature work, with pure docs of any size capped at Tier 1), and Tier 2 (`skeptical` for high-impact changes: security/auth, schema/migrations, public APIs, numerical/science invariants, or >200 LoC / >5 files). Safety clamps strictly block `--quick` on high-impact diffs and enforce graduated one-way escalation.
- [x] **Contract Test**: Enforced by `scripts/tests/test_skill_references.py::test_signoff_phase3f_adaptive_intensity_contract`.
- [x] **Live Dogfood Attestations**: Live classification dogfood verified on `main` in commit `20c7120` (Tier 1 standard intensity) and commit `2558ebc` (Tier 2 skeptical intensity).
- [ ] **Release (deferred)**: Release cut deferred to post-merge release workflow. Adaptive tiering is prompt-level only and is not mirrored server-side in `signoff_mcp`.

---

### Phase 5 (Cloud & Productionization)
Take signoff from a local experimental tool to production-ready for a growing user base. Strategy and evidence milestones are maintained in `docs/productionization.md` (iterate whenever Phase 5 is touched).

#### Numbered Gate Status:
- [x] **Gate 0: Notes-recovery automation**: Automated CI workflow (`.github/workflows/notes-recovery.yml` running `scripts/recover_notes.py`) reconstructs `refs/notes/signoff` server-side from `[SIGNOFF *]` commit messages on pushes to `main`. Verified live on `main` (`refs/notes/signoff` resolves on origin).
- [x] **Gate 1: Dedicated project website**: Shipped static site (`site/index.html`) deployed via GitHub Pages (`.github/workflows/pages.yml`). Live at `https://jerrylin96.github.io/signoff/`. Remaining open user action: purchase custom domain (top credibility item).
- [x] **Gate 2: Cloud concept promoted to reviewed spec**: Shipped reviewed specification draft in `skills/signoff/specs/gsa-escrow.md`. Establishes user-owned storage and client-side encryption as normative baseline.
- [ ] **Gate 3: Cloud storage for conversations**: Transcript escrow implementation per `gsa-escrow.md` (deferred pending demand evidence).

#### Operational Checklist & Standardization:
- [x] **Pin Tag**: Tag `verify-v1` created and verified on origin (`f01ac253`), self-healed via `.github/workflows/tag.yml`.
- [ ] **Pins `verify-v1.3` and `init-v6`** (2026-09-08): created by `tag.yml` on the next push to `main`. `verify-v1.3` closes the trailer-injection PR-gate bypass and the multi-block note rejection (gsa-core 3.6.0 §2.3/§5.1); `init-v6` carries the initializer rollback/symlink fixes, the Python-floor guard, and the `git-signoff` command. Install snippets and the scaffolded workflow already reference the new pins; they resolve once the tags exist.
- [x] **PyPI Package Name Conflict (resolved by rename)**: the PyPI name `signoff-mcp` has been held since 2026-05-02 by an unrelated project (a verification layer for AI agents; no relation to GSA). The distribution and primary command are renamed `git-signoff` (`git-signoff serve` / `git-signoff init`; bare invocation prints help because git dispatches `git signoff` to it); `signoff-mcp` stays as a compatibility alias and the import package `signoff_mcp` is unchanged. Nothing is on PyPI yet. Remaining user action: register `git-signoff` on PyPI as a pending trusted publisher (see `docs/productionization.md` → User actions), then dispatch `pypi-publish.yml`.
- [x] **Standardization Track**: Badge and CI verifier (`verify/`), specification licensing (`LICENSE-SPEC`), conformance vectors (`conformance/`), and in-toto predicate draft (`skills/signoff/specs/gsa-in-toto-predicate.md`).

---

## 2. Historical Milestone Archive

### Stage 1a — Core Protocol Spec Finalization
- [x] Core GSA Spec finalized with repo-relative paths (`skills/signoff/specs/gsa-core.md`), Git Notes concurrency merge handling (`cat_sort_uniq` via tracking ref), and `ack_no_transcript` parameter circuit breaker.

### Stage 1b — Implementation Planning
- [x] Implementation plan drafted, adversarially reviewed, and executed.

### Phase 1 — Skill-Level Compliance
- [x] `skills/signoff/SKILL.md` implements GSA v1.0 trailers, portable harness adapter resolution (`SIGNOFF_TRANSCRIPT_FILE` → `ANTIGRAVITY_CONVERSATION_ID` → `CLAUDE_CODE_SESSION_ID`), signed attestation commits, and `refs/notes/signoff` dual persistence.

### Phase 2 — MCP Server Implementation
- [x] `signoff-mcp` package (`signoff_mcp/`): programmatic `TranscriptProvider` adapters, MCP tools `signoff_prepare`/`signoff_commit`/`signoff_push_notes`, `ack_no_transcript` circuit breaker, stale-state checks, and `cat_sort_uniq` notes push flow.

### Phase 3a — Portability
- [x] Per-harness install and portability guide (`skills/signoff/HARNESSES.md`); self-contained skill directory. Enforced by `test_skill_folder_is_self_contained`.

### Phase 3b — Dogfood Attestations
- [x] End-to-end `/signoff` runs on Claude Code web (`ad1f5ee`, `0c54122`), and later `codex-cli` and `antigravity-cli` (see `git log --grep=SIGNOFF`). Notes recovery automated via Gate 0.

### Phase 3c — Interview Customization & Provenance
- [x] Attestations record interviewer provenance via `Signoff-Agent` trailer. Named interview intensity levels (`cursory`, `standard`, `skeptical`). Swappable interview profile blocks in `skills/signoff/profiles/`.

### Phase 4 — Extraction & Distribution
- [x] Dedicated GitHub repository `jerrylin96/signoff` created via `git filter-repo`.

### Phase 4 amendment 2026-08-30
- [x] Distribution consolidated on a single per-repo channel — vendoring into `.claude/skills/signoff/` (via `init.py` or symlink). Plugin-marketplace and release-zip channels retired. (Note: historical reference `scripts/sync_signoff_subtree.sh` was an external dotgemini-side script, not present in this repo).

### Phase 3d — Research Accessibility
- [x] Repo-local profile selection (`.signoff/profile.md`), science-detection escalation guard, profile provenance SHA256 digest in `interview=` token, and domain-science profile authoring guidelines.

### Phase 3e — Runtime Verification & Distribution
- [x] Live dogfood of repo-local profiles and science guard with atmospheric science fixture. Release cut `v0.2.0`. MCP profile resolution mirroring.
