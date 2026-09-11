# Project Roadmap & Phase Gate Status

**Status:** Living Document  
**License:** MIT License (reference implementation and project documentation)  
**Provenance:** Extracted from [skills/git-signoff/specs/gsa-core.md](../skills/git-signoff/specs/gsa-core.md) §6 in v3.5.0  
**Canonical Protocol Specification:** [skills/git-signoff/specs/gsa-core.md](../skills/git-signoff/specs/gsa-core.md)

This document tracks development milestones, retrospective phase gate logs, and operational backlog items for the `git-signoff` repository. While the core attestation protocol is specified under `Community-Spec-1.0` in [skills/git-signoff/specs/gsa-core.md](../skills/git-signoff/specs/gsa-core.md), this roadmap records implementation progress and project-level tracking under the repository's MIT license.

---

## 1. Active Backlog & Ongoing Phases

### Phase 3f (Adaptive Signoff Interview Intensity)
- [x] **Prompt-Level Implementation**: Dynamic auto-classification of interview intensity based on diff semantics and blast radius when bare `/git-signoff` is invoked without explicit modifiers: Tier 0 (`cursory` for pure docs/types <50 LoC), Tier 1 (`standard` for default feature work, with pure docs of any size capped at Tier 1), and Tier 2 (`skeptical` for high-impact changes: security/auth, schema/migrations, public APIs, numerical/science invariants, or >200 LoC / >5 files). Safety clamps strictly block `--quick` on high-impact diffs and enforce graduated one-way escalation.
- [x] **Contract Test**: Enforced by `scripts/tests/test_skill_references.py::test_signoff_phase3f_adaptive_intensity_contract`.
- [x] **Live Dogfood Attestations**: Live classification dogfood verified on `main` in commit `20c7120` (Tier 1 standard intensity) and commit `2558ebc` (Tier 2 skeptical intensity).
- [x] **Release**: shipped in the `v0.5.0` line. Adaptive tiering remains agent-authoritative; since 2026-09-09 `attest.py prepare` supplies informative intensity hints (changed files, executable lines, matched Tier 2 triggers) so the agent cannot miscount, without moving the classification out of the prompt.

---

### Phase 5 (Cloud & Productionization)
Take signoff from a local experimental tool to production-ready for a growing user base. Strategy and evidence milestones are maintained in `docs/productionization.md` (iterate whenever Phase 5 is touched).

#### Numbered Gate Status:
- [x] **Gate 0: Notes-recovery automation**: Automated CI workflow (`.github/workflows/notes-recovery.yml` running `scripts/recover_notes.py`) reconstructs `refs/notes/signoff` server-side from `[SIGNOFF *]` commit messages on pushes to `main`. Verified live on `main` (`refs/notes/signoff` resolves on origin).
- [x] **Gate 1: Dedicated project website**: Shipped static site (`site/index.html`) deployed via GitHub Pages (`.github/workflows/pages.yml`). Live at `https://jerrylin96.github.io/git-signoff/`. Remaining open user action: purchase custom domain (top credibility item).
- [x] **Gate 2: Cloud concept promoted to reviewed spec**: Shipped reviewed specification draft in `skills/git-signoff/specs/gsa-escrow.md`. Establishes user-owned storage and client-side encryption as normative baseline.
- [ ] **Gate 3: Cloud storage for conversations**: Transcript escrow implementation per `gsa-escrow.md` (deferred pending demand evidence).

#### Operational Checklist & Standardization:
- [x] **Pin Tag**: Tag `verify-v1` created and verified on origin (`f01ac253`), self-healed via `.github/workflows/tag.yml`.
- [x] **Pins `verify-v1.3` and `init-v6`** (2026-09-08): created by `tag.yml` on the push of PR #20 to `main`. `verify-v1.3` closes the trailer-injection PR-gate bypass and the multi-block note rejection (gsa-core 3.6.0 §2.3/§5.1); `init-v6` carries the initializer rollback/symlink fixes and the Python-floor guard.
- [x] **Pins `verify-v1.4` and `init-v7`** (created by `tag.yml` at `c6143d5` on the merge of PR #21; `v0.5.0` cut 2026-09-10 from `0861610`, archived on Zenodo under concept DOI `10.5281/zenodo.22683016`): `verify-v1.4` moves the verifier into the skill folder (`skills/git-signoff/verify_signoff.py`), renames the `--audit` override to `GIT_SIGNOFF_TRANSCRIPT_FILE`, and adds the stale-pin warning; `init-v7` vendors the renamed folder with `attest.py`, scaffolds `.github/workflows/git-signoff.yml` and `.git-signoff/`, and creates the branch `git-signoff/init`. `v0.5.0` is the release the paper cites (`v0.4.0`, released from `49187c4` on 2026-09-09, predates the deterministic producer).
- [x] **Naming closed 2026-09:** `git-signoff` for everything a user installs, types, or configures (`skills/git-signoff/`, `.claude/skills/git-signoff`, `/git-signoff`, `.git-signoff/profile.md`, `.github/workflows/git-signoff.yml`, `GIT_SIGNOFF_*` env vars, branch `git-signoff/init`); `signoff` only inside protocol identifiers (`Signoff-*` trailers, `refs/notes/signoff`, `[SIGNOFF <sha>]`, GSA). Ergonomic trade recorded in `docs/productionization.md`: longer command, reads as a noun; accepted for discoverability.
- [x] **PyPI publication: dropped (2026-09-08).** The only pip-installable component was the optional MCP server, and it was removed for lack of demand (see `docs/productionization.md`, simplification backlog). Nothing in the adoption path is installed by name: `init.py` is curl-run and the verifier is a single stdlib file. For the record, should a distribution ever be published: `signoff-mcp` has belonged to an unrelated project since 2026-05-02, and PyPI rejects `git-signoff` as too similar to the unrelated `git-sign-off` (2020); `git-attest` was free at the time of checking. The `pypi-publish` workflow was deleted with the server.
- [ ] **Deferred-decision review, due 2026-11-08** (two months after the 2026-09-08 simplification). Reopen each item only on its named evidence; otherwise re-defer with a new date.
  - ~~*Deterministic producer mechanics*~~ — **resolved 2026-09-09:** shipped as `skills/git-signoff/attest.py` (stdlib helper inside the vendored folder, replacing the inline bash heredoc) with approval-marker binding; decision record in `docs/productionization.md`. The evidence that unlocked it was the wrong-file failure class identified during the 2026-09-08 review, not a live fumble.
  - ~~*MCP wrapper over `git_signoff/`*~~ — **closed 2026-09-09:** `git_signoff/` no longer exists; the mechanics live in `attest.py`, which any harness with a shell runs. An MCP wrapper would now wrap `attest.py` (its `prepare`/`commit` map onto §4's informative tool surface); reopen only on an adopter whose harness has no shell, or one who asks for the §4 tool surface by name.
  - *Authenticity beyond structure* (mandatory reviewer signing, or a service-created attestation per the escrow spec) — **remains open.** `attest.py` closes agent *mistakes* (wrong file, mis-derived status, skipped merge), not forgery: a malicious agent or human with push rights can still write a false attestation. Evidence: a threat model in which forgery by a compromised or prompt-injected agent matters to an adopter, i.e. someone who needs the gate to prove more than "a person with push rights asserted this".
  - *Distribution name* (only if any of the above ships a pip-installable component): `git-signoff` is rejected by PyPI as too similar to `git-sign-off`; `git-attest` was free on 2026-09-08.
- [x] **Standardization Track**: Badge and CI verifier (`verify/`), specification licensing (`LICENSE-SPEC`), conformance vectors (`conformance/`), and in-toto predicate draft (`skills/git-signoff/specs/gsa-in-toto-predicate.md`).

---

## 2. Historical Milestone Archive

### Stage 1a — Core Protocol Spec Finalization
- [x] Core GSA Spec finalized with repo-relative paths (`skills/git-signoff/specs/gsa-core.md`), Git Notes concurrency merge handling (`cat_sort_uniq` via tracking ref), and `ack_no_transcript` parameter circuit breaker.

### Stage 1b — Implementation Planning
- [x] Implementation plan drafted, adversarially reviewed, and executed.

### Phase 1 — Skill-Level Compliance
- [x] `skills/signoff/SKILL.md` (now `skills/git-signoff/SKILL.md`) implements GSA v1.0 trailers, portable harness adapter resolution (`SIGNOFF_TRANSCRIPT_FILE`, now `GIT_SIGNOFF_TRANSCRIPT_FILE` → `ANTIGRAVITY_CONVERSATION_ID` → `CLAUDE_CODE_SESSION_ID`), signed attestation commits, and `refs/notes/signoff` dual persistence.

### Phase 2 — MCP Server Implementation
- [x] MCP server package (then `signoff-mcp` / `signoff_mcp/`; renamed `git_signoff/` and reduced to an unpublished reference library on 2026-09-08 when the MCP wrapper and PyPI path were removed for lack of demand; package removed 2026-09-09 — the mechanics live in `skills/git-signoff/attest.py`, tested directly in `scripts/tests/`): programmatic `TranscriptProvider` adapters, MCP tools `signoff_prepare`/`signoff_commit`/`signoff_push_notes`, `ack_no_transcript` circuit breaker, stale-state checks, and `cat_sort_uniq` notes push flow.

### Phase 3a — Portability
- [x] Per-harness install and portability guide (`skills/git-signoff/HARNESSES.md`); self-contained skill directory. Enforced by `test_skill_folder_is_self_contained`.

### Phase 3b — Dogfood Attestations
- [x] End-to-end `/git-signoff` runs on Claude Code web (`ad1f5ee`, `0c54122`), and later `codex-cli` and `antigravity-cli` (see `git log --grep=SIGNOFF`). Notes recovery automated via Gate 0.

### Phase 3c — Interview Customization & Provenance
- [x] Attestations record interviewer provenance via `Signoff-Agent` trailer. Named interview intensity levels (`cursory`, `standard`, `skeptical`). Swappable interview profile blocks in `skills/git-signoff/profiles/`.

### Phase 4 — Extraction & Distribution
- [x] Dedicated GitHub repository `jerrylin96/signoff` created via `git filter-repo` (renamed `jerrylin96/git-signoff` 2026-09-08 so repository, distribution, import package, and command share one name; GitHub redirects the old URL).

### Phase 4 amendment 2026-08-30
- [x] Distribution consolidated on a single per-repo channel — vendoring into `.claude/skills/git-signoff/` (via `init.py` or symlink). Plugin-marketplace and release-zip channels retired. (Note: historical reference `scripts/sync_signoff_subtree.sh` was an external dotgemini-side script, not present in this repo).

### Phase 3d — Research Accessibility
- [x] Repo-local profile selection (`.git-signoff/profile.md`), science-detection escalation guard, profile provenance SHA256 digest in `interview=` token, and domain-science profile authoring guidelines.

### Phase 3e — Runtime Verification & Distribution
- [x] Live dogfood of repo-local profiles and science guard with atmospheric science fixture. Release cut `v0.2.0`. MCP profile resolution mirroring.
