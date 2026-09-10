# git-signoff — Git Signoff Attestation (GSA)

[![attested by humans](https://github.com/jerrylin96/git-signoff/actions/workflows/git-signoff.yml/badge.svg)](https://github.com/jerrylin96/git-signoff/actions/workflows/git-signoff.yml)
[![DOI](https://zenodo.org/badge/1324190593.svg)](https://doi.org/10.5281/zenodo.22683016)

**Verify that a human actually understands an AI-assisted diff before it merges.**

Not `git commit --signoff` (the Developer Certificate of Origin trailer), and
not an approval button: a sign-off button records that someone clicked, a GSA
attestation records that someone understood — and it lives in your git
history, not in a hosted dashboard.

`/git-signoff` flips the usual review direction: instead of you interrogating the
AI's code, the AI interviews **you** — then records the outcome as a
machine-parsable, tamper-evident **Git Signoff Attestation** inside your
repository.

## What it does, in plain language

You (or your AI assistant) changed some code. Before that change merges — or
before its output goes into a paper, a report, or a decision — run `/git-signoff`.
The agent reads the full diff, then asks you a short series of pointed
questions across four fixed axes:

1. **Mechanics & intent** — what changed, and why this design?
2. **Trade-offs & edge cases** — what approximations were made, and are they intentional?
3. **Boundary conditions & failure loudness** — where does it break, and does it break *loudly* or silently?
4. **Ownership** — do you explicitly accept responsibility for the results and risks?

Vague answers don't pass. If you hand-wave, the agent pauses, explains the
relevant mechanics, and re-probes with a concrete scenario. When you do pass,
it writes an empty signed commit plus a mirrored git note
(`refs/notes/signoff`) recording who understood what, when, and at exactly
which state of the code — a record that survives squash merges and branch
deletion. The goal is preventing *cognitive surrender*: rubber-stamping AI
output nobody actually understands.

## Who it's for

**Software engineers** — the default interview profile emphasizes algorithmic
complexity, data-structure invariants, and API contract changes.

**Scientists, physicists, and mathematicians** — research code fails
differently: it rarely crashes, it produces *plausible-but-invalid results*.
An ML parameterization that quietly leaks energy, a unit slip between hPa and
Pa, a trend that vanishes at higher grid resolution — none of these throw an
exception. The shipped `domain-science` profile emphasizes unit and
dimensional validity, surrogate-vs-ground-truth boundaries, numerical
stability, statistical validity (leakage, multiple comparisons), uncertainty
quantification, and reproducibility (seeds, environments, data provenance).
And at the research frontier there is no oracle to check against —
`/git-signoff` deliberately does not claim to verify that the science is *right*;
it verifies that **you** know the assumptions, the validity regimes, and how
you'd notice drift outside them. That is exactly the part a human must own.

## Quickstart: Set up any repo in 60 seconds

Inside your repository root, run the zero-touch initializer (Python 3.10+ stdlib only — zero dependencies):

```bash
# Standard software engineering profile:
curl -fsSL https://raw.githubusercontent.com/jerrylin96/git-signoff/init-v7/init.py -o /tmp/signoff-init.py && python3 /tmp/signoff-init.py

# Scientific & research computing profile (math, physics, bio, climate, ML):
curl -fsSL https://raw.githubusercontent.com/jerrylin96/git-signoff/init-v7/init.py -o /tmp/signoff-init.py && python3 /tmp/signoff-init.py --profile domain-science
```

The script automatically:
1. Detects your repo, branch, and stack (suggests science or general software profile).
2. Vendors the `/git-signoff` skill into `.claude/skills/git-signoff/` and/or `.agents/skills/git-signoff` (cross-client convention, auto-detected from repository markers, or explicitly chosen via `--skill-target {auto,claude,agents,both}`) — committed with your repo, it loads for every collaborator, across Claude Code, Antigravity, Codex, Cursor, and other agent harnesses alike, with nothing account-scoped to install.
3. Scaffolds `.github/workflows/git-signoff.yml` and `.git-signoff/profile.md`.
4. Injects the **attested by humans** badge into your `README.md`.
5. Automates GitHub Ruleset protection (via `gh` CLI or a 1-click settings link).
6. Creates feature branch `git-signoff/init` with your scaffolded setup ready for you to run `/git-signoff` and merge.

---

### What an interview looks like

```text
AI: [Axis 1 — Mechanics] What changed in this diff, and why did you choose this design?
You: Added an automatic fallback to /dev/tty when stdin is connected to a curl pipe.

AI: [Axis 2 — Edge Cases] What happens if this runs in a headless CI environment without a TTY?
You: It catches OSError cleanly and gracefully degrades to non-interactive default choices.

AI: [Axis 3 — Ownership] Do you accept accountability for these failure modes and CI configurations?
You: Confirmed, my email is dev@example.com.

AI: ✅ Attestation commit [SIGNOFF a1b2c3d] created! Your badge is green.
```

## How to use it: four steps

1. **Install** — run the 60-second initializer above, or pick the one row for your harness below.
2. **Open the PR** — review the diff as usual (when the branch's commits are well-structured, reading them one at a time shows what changed when and why far better than one squashed diff); the `verify-signoff` check runs red until the branch ends in a valid attestation. Attest *after* the diff is final: the attestation must be the last commit on the branch, so pushing anything after it turns the check red again (just re-run `/git-signoff`).
3. **Run** — from the branch you want to merge, type `/git-signoff` (adaptive default auto-selects intensity from diff; `--deep` for skeptical rigor, `--quick` for low-risk diffs subject to safety clamps).
4. **Answer, confirm, merge** — respond in your own words, acknowledge the named trade-offs and risks, confirm your email. The attestation commit and note are created and pushed with your branch; when `verify-signoff` turns green, merge as usual.

---

## Auditing & retrieving interview transcripts

Git signoff attestations bind the interview transcript's SHA-256 digest (`Signoff-Transcript-Digest`) into immutable git history and notes. Transcripts remain locally on the reviewer's laptop for privacy and security. Anyone — leads, reviewers, compliance auditors — can verify or audit the transcript at any time using the verifier CLI.

### The 3-Step Verification Loop (Auditor $\leftrightarrow$ Reviewer)

```text
Auditor (Lead / Compliance)                  Reviewer (Employee)
           │                                          │
           │  1. Request transcript snapshot          │
           │  (quotes commit or PR)                   │
           ├─────────────────────────────────────────>│
           │                                          │  2. Export snapshot:
           │                                          │     verify_signoff.py --audit HEAD
           │                                          │       --export transcript.jsonl
           │  3. Send transcript.jsonl                │
           │<─────────────────────────────────────────┤
           │                                          │
           │  4. Verify against git trailers:         │
           │     GIT_SIGNOFF_TRANSCRIPT_FILE=transcript.jsonl
           │     python3 verify_signoff.py --audit HEAD
           │                                          │
           │  Output: ✅ VALID MATCH                   │
```

#### Step 1: Auditor requests transcript
The auditor identifies the attestation on the commit or PR (e.g. `[SIGNOFF 979cb45]`) and asks the reviewer to export the session transcript.

#### Step 2: Reviewer exports transcript
On the machine where the signoff interview occurred, the reviewer runs the verifier CLI with `--audit` and `--export`:
```bash
python3 .claude/skills/git-signoff/verify_signoff.py --audit HEAD --export /tmp/transcript.jsonl
```
The verifier resolves the local transcript for the harness (`claude-code`, `antigravity-cli`, `codex-cli`, etc.), checks that the first $N$ bytes match the `Signoff-Transcript-Digest` trailer, and writes the snapshot to the specified path:
```text
✅ VALID MATCH: Transcript SHA-256 matches sha256:1675b6...
  Harness: claude-code
  Conversation ID: 979cb45-session
  Bytes verified: 8432
  Exported snapshot to: /tmp/transcript.jsonl
```
The reviewer sends `/tmp/transcript.jsonl` to the auditor.

#### Step 3: Auditor verifies snapshot against git trailers
The auditor points `GIT_SIGNOFF_TRANSCRIPT_FILE` at the received file and audits the target commit:
```bash
GIT_SIGNOFF_TRANSCRIPT_FILE=/tmp/transcript.jsonl python3 .claude/skills/git-signoff/verify_signoff.py --audit HEAD
```
The verifier recomputes the SHA-256 digest and confirms it matches the git attestation byte-for-byte.

---

## Installation

One channel, everywhere: the skill is a self-contained folder — the
interview prompt (`SKILL.md`), the deterministic producer (`attest.py`) and
the verifier (`verify_signoff.py`), both standard-library Python — that lives
*in the repository under review*. Committed once, `/git-signoff` works for
every collaborator — no plugins, no marketplaces, no downloads, nothing
account-scoped, nothing to pip-install.

| Where you work | One-time action |
|---|---|
| **Any repository (Zero-touch)** | `curl -fsSL https://raw.githubusercontent.com/jerrylin96/git-signoff/init-v7/init.py -o /tmp/signoff-init.py && python3 /tmp/signoff-init.py` (use `--skill-target {auto,claude,agents,both}` to control destinations) |
| **Any repository (manual)** | Copy this repo's `skills/git-signoff/` folder to `<your-repo>/.claude/skills/git-signoff/` (Claude Code) or `<your-repo>/.agents/skills/git-signoff/` (Antigravity, Codex, Cursor, etc.) and commit before running the initializer; an untracked skill destination now aborts as an unrelated working-tree change. Update by re-copying (or re-running the initializer) on new releases. |
| **Other harnesses (Antigravity, Codex, Cursor, …)** | Same folder, cross-client convention: copy `skills/git-signoff/` into `.agents/skills/git-signoff` (or `.claude/skills/git-signoff`) and set the transcript adapter env vars — full matrix in [HARNESSES.md](skills/git-signoff/HARNESSES.md). |

> [!NOTE]
> **Initializer Flags & Policy A:**
> - `--skill-target {auto,claude,agents,both}`: Selects target client destinations (defaults to auto-detect based on repo markers).
> - `--allow-dirty`: Permits unrelated unstaged/untracked work to remain in place. It still refuses any pre-staged change, any uncommitted or ignored state under paths the initializer manages, and all Policy A violations (symbolic links, parent-path collisions, unrelated non-empty directories, and destination-level `.gitignore` rules). This boundary prevents user work from being swept into the scaffold commit or overwritten during vendoring/rollback.

## Make it yours: changing what gets asked

The four axes above are fixed for everyone. What you customize is the
**interview profile** — a single, clearly delimited text block that weights
the questions toward your domain's failure modes. It is the sole
customization point of the skill; profiles can add domain emphases but can
never remove axes or lower pass criteria, so a customized interview is never
a weaker one.

### 🔬 Designing a Profile for Scientific & Research Code

Generic software engineering questions ($O(N \log N)$ complexity, API contracts, thread safety) will **not** catch research bugs. Scientific code fails silently with plausible-looking numbers:
- **Numerical Stability & Conditioning:** Catastrophic cancellation in floating-point diffs, ill-conditioned matrices, underflow/overflow in log-space computations, gradient explosion/vanishing.
- **Physical Invariants & Conservation:** Leakage of mass, energy, momentum, or probability across time steps; violation of positivity constraints (e.g. negative tracer concentrations); CFL condition violations when time-stepping.
- **Statistical Validity & Data Leakage:** Contamination between spatial/temporal training and test splits, lookahead bias in climate/financial series, uncorrected multiple hypothesis testing ($p$-hacking), circular feature engineering.
- **Surrogate Boundaries & Validity Regimes:** Out-of-distribution neural network surrogates used outside their training domain, unquantified epistemic uncertainty, lack of physics-informed fallback.
- **Provenance & Reproducibility:** Floating-point non-determinism across GPU architectures, unseeded RNG streams, dataset version drift.

See [**skills/git-signoff/profiles/README.md**](skills/git-signoff/profiles/README.md) for the complete authoring guide and ready-to-use templates for:
1. **Fluid Dynamics & Climate Simulation** (CFL stability, discrete conservation laws, grid interpolation)
2. **Bioinformatics & Computational Genomics** (multiple testing correction, reference genome versions, batch effects)
3. **AI for Science & Neural Operators** (PDE surrogates, spectral bias, physical boundary condition compliance)
4. **Numerical Linear Algebra & Optimization** (condition numbers, matrix decompositions, convergence tolerances)

---

### The dead-simple path — commit a profile to your own repository:

1. In the repo you want reviewed, scaffold or create `.git-signoff/profile.md`:
   ```bash
   python3 /tmp/signoff-init.py --profile domain-science
   ```
2. Or paste in a shipped profile block —
   [`domain-science`](skills/git-signoff/profiles/domain-science.md) for research
   code, [`software-general`](skills/git-signoff/profiles/software-general.md)
   for classic engineering — or adapt a discipline template from
   [`skills/git-signoff/profiles/README.md`](skills/git-signoff/profiles/README.md).
3. Done. Every `/git-signoff` run on that repository now uses your profile — for
   every collaborator, on every install channel, surviving skill updates.

**Write your own profile for your lab or team:** copy a shipped profile as a
template, set your own `Profile-ID:` (lowercase, hyphens), and rewrite the
emphasis bullets to name *your* failure modes — conservation properties of a
new parameterization, grid-resolution sensitivity of a reported trend,
CFL-limited timestep choices, leakage between reanalysis training and
evaluation periods, what the ensemble spread does and doesn't capture —
whatever "wrong but plausible" looks like in your field.

**Science is probed by default:** even with no customization at all, any
diff that touches scientific computation — numpy/scipy/jax-style imports,
notebooks, RNG seeding, unit-bearing constants, netCDF/GRIB/zarr datasets —
automatically triggers the science questions on top of the active profile.

Every attestation records which question set actually ran: the profile ID
plus, for repo-supplied profiles, a content digest
(`Signoff-Agent: ... interview=standard/<your-profile-id>/sha256:<digest>`),
so downstream readers can always see which questions the human was held to —
and a diluted profile is distinguishable from a shipped one.

Other knobs: `GIT_SIGNOFF_PROFILE_FILE=<path>` overrides everything for one
machine; editing the block inside the vendored `SKILL.md` also works, but
re-vendoring on update overwrites such edits — prefer the repo-local
`.git-signoff/profile.md`. Full details:
[HARNESSES.md](skills/git-signoff/HARNESSES.md).

## What an attestation looks like

```text
[SIGNOFF <short-sha>]: human comprehension and risk attestation

Signoff-Spec-Version: 1.0
Signoff-Status: VERIFIED_BY_HUMAN
Signoff-Base-SHA: ...
Signoff-Reviewed-Commit-SHA: ...
Signoff-Reviewed-Tree-SHA: ...
Signoff-Harness-ID: claude-code
Signoff-Transcript-Digest: sha256:...
Signoff-Tradeoff: ...
Signoff-Risk: ...
Signoff-Verified-By: you@example.com
Signoff-Agent: harness=claude-code/2.x model=... reasoning=... interview=standard/software-general
```

Verification survives squash merges via the reviewed **tree SHA** and the
notes mirror — lookup order in [gsa-core.md §5](skills/git-signoff/specs/gsa-core.md).

**Show it: the badge & CI gate.** A two-minute GitHub Actions check turns attestations into a visible, enforceable claim — PRs fail until the branch ends in a valid attestation, and your README carries an **attested by humans** badge (the one at the top of this file):

```yaml
# .github/workflows/git-signoff.yml
name: attested by humans
on:
  pull_request:
  push:
    branches: [ main ]
jobs:
  verify-signoff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history — attestations live in it
      - uses: jerrylin96/git-signoff/verify@verify-v1.4
```

Supports standard merge strategies: **2-parent PR merges** (verifies clean merge tree & attested PR head in `head` mode), **fast-forward merges** (`head` mode), **squash merges** (`history` mode; in `head` mode when base is unchanged), and **rebase merges** (`history` mode; in `head` mode, re-run `/git-signoff` after rebase). Enforce strictly with preconfigured [`ruleset.json`](verify/ruleset.json). Full setup & badge markdown: [`verify/`](verify/README.md).

The protocol is harness-, model-, and vendor-neutral, and nothing is
installed by name: the initializer is a curl-run script, and the skill folder
carries the interview prompt plus two standard-library Python files. The
agent conducts the interview; **`attest.py`** does every mechanical step
deterministically — it resolves the SHAs, snapshots the transcript once,
requires an approval marker naming the reviewed commit to be present in that
snapshot (so a stale or wrong session file is refused instead of hashed),
derives the status from the bytes, writes the commit and the notes, and runs
the verifier on its own output before reporting success. What this does
*not* close is a malicious agent or human with push rights writing a false
attestation; that needs an identity the agent does not hold and stays
deferred (see [docs/roadmap.md](docs/roadmap.md)).

- **Protocol spec:** [`skills/git-signoff/specs/gsa-core.md`](skills/git-signoff/specs/gsa-core.md)
- **Producer and verifier reference (flags, exit codes, env vars):** [`docs/reference.md`](docs/reference.md)
- **Reproducible walkthrough:** [`docs/walkthrough.md`](docs/walkthrough.md)
- **Project roadmap:** [`docs/roadmap.md`](docs/roadmap.md)
- **Per-harness install & portability guide:** [`skills/git-signoff/HARNESSES.md`](skills/git-signoff/HARNESSES.md)
- **Skill entry point:** [`skills/git-signoff/SKILL.md`](skills/git-signoff/SKILL.md)

Distribution is deliberately boring: one folder committed to the
repository under review, loaded by the harness from disk. Earlier
account-scoped channels (a Claude Code plugin marketplace and a release-zip
skill upload) were retired in v0.4.0 — the vendored folder replaced them on
every surface; [docs/roadmap.md#phase-4-amendment-2026-08-30](docs/roadmap.md#phase-4-amendment-2026-08-30) records the history.

## Status & roadmap

**v0.5.0** ships the researcher-facing feature set described above —
repo-local profiles, the default-on science guard, and profile provenance
digests — plus the deterministic producer `attest.py` with approval-marker
binding, on a single distribution channel (the vendored skill folder),
verified end-to-end by scripted mechanics checks plus live interview runs:
this repository signs off its own branches, and the resulting attestations
are in its history (`git log --grep='SIGNOFF'`).
Phase 5 (tracked in [docs/roadmap.md](docs/roadmap.md))
adds the production surface: a [project website](https://jerrylin96.github.io/git-signoff/),
the [attested-by-humans badge + CI verifier](verify/README.md),
automated `refs/notes/signoff` recovery, an open
[spec license](LICENSE-SPEC) with [conformance vectors](conformance/README.md)
for third-party implementations, and a reviewed
[transcript-escrow spec](skills/git-signoff/specs/gsa-escrow.md) whose
privacy baseline is user-owned storage with client-side encryption.
Cloud escrow implementation remains next.

## Development

```bash
pip install pytest ruff   # the only development dependencies; nothing from this repo is installed
ruff check . && pytest
```

Tests live in `scripts/tests/` (the producer `attest.py`, the verifier, skill
contracts, conformance vectors, notes recovery, the site) and `tests/` (the
repository initializer). See [CONTRIBUTING.md](CONTRIBUTING.md).

## Citing

Releases are archived on Zenodo. Each release has its own DOI (v0.5.0 is
`10.5281/zenodo.22683017`); the concept DOI `10.5281/zenodo.22683016`
represents all versions and always resolves to the newest, so cite it unless
you mean one specific release. `CITATION.cff` in the repository root carries the citation
metadata (GitHub's "Cite this repository" button reads it), and
[`docs/reference.md`](docs/reference.md) documents the protocol version each
release implements.

```text
Lin, J. (2026). git-signoff: Git Signoff Attestation (GSA) (v0.5.0) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.22683017
```

## License

Code is MIT licensed; the GSA specifications are licensed under the
[Community Specification License 1.0](LICENSE-SPEC), so anyone can implement,
verify, or extend the protocol.
