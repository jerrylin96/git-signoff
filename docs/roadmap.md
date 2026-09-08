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
- [ ] **Release (deferred)**: Release cut deferred to post-merge release workflow. Adaptive tiering is prompt-level only and is not mirrored server-side in `git_signoff`.

---

### Phase 5 (Cloud & Productionization)
Take signoff from a local experimental tool to production-ready for a growing user base. Strategy and evidence milestones are maintained in `docs/productionization.md` (iterate whenever Phase 5 is touched).

#### Numbered Gate Status:
- [x] **Gate 0: Notes-recovery automation**: Automated CI workflow (`.github/workflows/notes-recovery.yml` running `scripts/recover_notes.py`) reconstructs `refs/notes/signoff` server-side from `[SIGNOFF *]` commit messages on pushes to `main`. Verified live on `main` (`refs/notes/signoff` resolves on origin).
- [x] **Gate 1: Dedicated project website**: Shipped static site (`site/index.html`) deployed via GitHub Pages (`.github/workflows/pages.yml`). Live at `https://jerrylin96.github.io/git-signoff/`. Remaining open user action: purchase custom domain (top credibility item).
- [x] **Gate 2: Cloud concept promoted to reviewed spec**: Shipped reviewed specification draft in `skills/signoff/specs/gsa-escrow.md`. Establishes user-owned storage and client-side encryption as normative baseline.
- [ ] **Gate 3: Cloud storage for conversations**: Transcript escrow implementation per `gsa-escrow.md` (deferred pending demand evidence).

#### Operational Checklist & Standardization:
- [x] **Pin Tag**: Tag `verify-v1` created and verified on origin (`f01ac253`), self-healed via `.github/workflows/tag.yml`.
- [ ] **Pins `verify-v1.3` and `init-v6`** (2026-09-08): created by `tag.yml` on the next push to `main`. `verify-v1.3` closes the trailer-injection PR-gate bypass and the multi-block note rejection (gsa-core 3.6.0 §2.3/§5.1); `init-v6` carries the initializer rollback/symlink fixes and the Python-floor guard. Install snippets and the scaffolded workflow already reference the new pins; they resolve once the tags exist.
- [x] **PyPI publication: dropped (2026-09-08).** The only pip-installable component was the optional MCP server, and it was removed for lack of demand (see `docs/productionization.md`, simplification backlog). Nothing in the adoption path is installed by name: `init.py` is curl-run and the verifier is a single stdlib file. For the record, should a distribution ever be published: `signoff-mcp` has belonged to an unrelated project since 2026-05-02, and PyPI rejects `git-signoff` as too similar to the unrelated `git-sign-off` (2020); `git-attest` was free at the time of checking. The `pypi-publish` workflow was deleted with the server.
- [ ] **Deferred-decision review, due 2026-11-08** (two months after the 2026-09-08 simplification). Reopen each item only on its named evidence; otherwise re-defer with a new date.
  - *Deterministic producer mechanics* (a stdlib helper script inside the vendored skill folder, replacing the inline bash heredoc) — evidence: a live run where an agent miscomputed a digest, mis-derived status, or skipped the notes merge, or an adopter asking for it.
  - *MCP wrapper over `git_signoff/`* — evidence: an adopter whose harness has no shell, or one who asks for the §4 tool surface by name.
  - *Authenticity beyond structure* (mandatory reviewer signing, or a service-created attestation per the escrow spec) — evidence: a threat model in which forgery by a compromised or prompt-injected agent matters to an adopter, i.e. someone who needs the gate to prove more than "a person with push rights asserted this".
  - *Distribution name* (only if any of the above ships a pip-installable component): `git-signoff` is rejected by PyPI as too similar to `git-sign-off`; `git-attest` was free on 2026-09-08.
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
- [x] MCP server package (then `signoff-mcp` / `signoff_mcp/`; renamed `git_signoff/` and reduced to an unpublished reference library on 2026-09-08 when the MCP wrapper and PyPI path were removed for lack of demand): programmatic `TranscriptProvider` adapters, MCP tools `signoff_prepare`/`signoff_commit`/`signoff_push_notes`, `ack_no_transcript` circuit breaker, stale-state checks, and `cat_sort_uniq` notes push flow.

### Phase 3a — Portability
- [x] Per-harness install and portability guide (`skills/signoff/HARNESSES.md`); self-contained skill directory. Enforced by `test_skill_folder_is_self_contained`.

### Phase 3b — Dogfood Attestations
- [x] End-to-end `/signoff` runs on Claude Code web (`ad1f5ee`, `0c54122`), and later `codex-cli` and `antigravity-cli` (see `git log --grep=SIGNOFF`). Notes recovery automated via Gate 0.

### Phase 3c — Interview Customization & Provenance
- [x] Attestations record interviewer provenance via `Signoff-Agent` trailer. Named interview intensity levels (`cursory`, `standard`, `skeptical`). Swappable interview profile blocks in `skills/signoff/profiles/`.

### Phase 4 — Extraction & Distribution
- [x] Dedicated GitHub repository `jerrylin96/signoff` created via `git filter-repo` (renamed `jerrylin96/git-signoff` 2026-09-08 so repository, distribution, import package, and command share one name; GitHub redirects the old URL).

### Phase 4 amendment 2026-08-30
- [x] Distribution consolidated on a single per-repo channel — vendoring into `.claude/skills/signoff/` (via `init.py` or symlink). Plugin-marketplace and release-zip channels retired. (Note: historical reference `scripts/sync_signoff_subtree.sh` was an external dotgemini-side script, not present in this repo).

### Phase 3d — Research Accessibility
- [x] Repo-local profile selection (`.signoff/profile.md`), science-detection escalation guard, profile provenance SHA256 digest in `interview=` token, and domain-science profile authoring guidelines.

### Phase 3e — Runtime Verification & Distribution
- [x] Live dogfood of repo-local profiles and science guard with atmospheric science fixture. Release cut `v0.2.0`. MCP profile resolution mirroring.
