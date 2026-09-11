#!/usr/bin/env python3
"""Git Signoff Attestation (GSA) producer — deterministic mechanics for /git-signoff.

The interviewing agent conducts the Socratic interview; this helper does every
mechanical step of the attestation so the agent never computes a digest,
derives a status, formats a trailer, or merges notes. Standard library only,
Python 3.10+, vendored into adopter repositories with the rest of this folder.

Commands:

  attest.py prepare  [--reference REF] [--json]
      Resolve reviewed/base/tree SHAs, the range diff summary, the active
      interview profile, science-guard signals, transcript availability,
      intensity hints, and the approval marker the agent must emit.
  attest.py commit   --email EMAIL --level {cursory,standard,skeptical}
                     [--tradeoff T]... [--risk R]... [--summary TEXT]
                     [--model ID] [--reference REF] [--ack-no-transcript]
                     [--no-sign] [--dry-run] [--no-push] [--json]
      Snapshot the transcript, require the approval marker, derive the status,
      write the empty attestation commit and the refs/notes/signoff mirror,
      self-check with the sibling verifier, and push the notes.
  attest.py marker   [--reference REF]
      Reprint the approval marker line for the current HEAD.
  attest.py --version

Exit codes:

  0  success (a refused notes push is reported, not fatal: the attestation
     commit and local notes stand; the recovery workflow rebuilds notes)
  2  usage or argument error, including a line break or a `Signoff-` line in
     free text, or a missing sibling verify_signoff.py
  3  stale or dirty: HEAD moved since prepare, unstaged / staged changes, or
     HEAD is already an attestation commit (nothing new to attest)
  4  transcript problem: unresolvable without --ack-no-transcript, or the
     approval marker for this reviewed commit is not in the resolved transcript
  5  profile problem: GIT_SIGNOFF_PROFILE_FILE is set but unreadable (a
     malformed repo-local profile is not an error: it falls back, reported)
  6  git failure (rev-parse, commit, notes append)
  7  self-check failure: the verifier rejects the produced attestation; the
     empty commit and the notes just written are removed before exit. If a
     rollback step itself fails, the message says ROLLBACK INCOMPLETE and
     names the step, so the exit never describes a state that is not true.

Environment:

  GIT_SIGNOFF_TRANSCRIPT_FILE  explicit transcript path (generic-file adapter;
                               takes precedence over every harness adapter)
  ANTIGRAVITY_CONVERSATION_ID, CLAUDE_CODE_SESSION_ID, CODEX_SESSION_ID
                               harness adapters, in that resolution order
  CODEX_HOME                   Codex sessions root (default ~/.codex)
  GIT_SIGNOFF_PROFILE_FILE     interview profile override (unreadable → exit 5)
  CLAUDE_CODE_VERSION, CLAUDE_EFFORT, ANTHROPIC_MODEL
                               Signoff-Agent provenance (Claude Code only for
                               version and reasoning)

Approval marker (gsa-core §2.3, SHOULD for producers):

  GSA-APPROVAL <reviewed-commit-sha> <utc-timestamp-of-prepare>

`prepare` prints it; after the human explicitly approves the trade-offs,
risks, and email, the agent emits that line verbatim as its own paragraph,
then runs `commit`. `commit` requires the marker to appear in the last 64 KiB
of the transcript snapshot it hashes, and the last marker's SHA must equal
HEAD. A stale session file from another conversation cannot name this
reviewed commit, so a resolution error fails closed (exit 4) instead of
producing a well-formed digest of the wrong file. Note that the marker
printed by `prepare` is itself recorded in the transcript as tool output; the
check binds the file and the reviewed commit — the approval turn precedes
`commit` and is therefore inside the hashed bytes regardless.
"""

import sys

if sys.version_info < (3, 10):  # loud, before anything that only parses on newer Pythons
    sys.exit(
        "attest.py needs Python 3.10 or newer; this is Python %d.%d. "
        "Run it with a newer interpreter (python3.10+)." % sys.version_info[:2]
    )

import argparse  # noqa: E402
import glob  # noqa: E402
import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from dataclasses import asdict, dataclass, field  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Mapping, Protocol  # noqa: E402

VERSION = "0.5.0"
SPEC_VERSION = "1.0"
NOTES_REF = "refs/notes/signoff"
NOTES_TRACKING_REF = "refs/notes/signoff-remote"
STATUS_VERIFIED = "VERIFIED_BY_HUMAN"
STATUS_NO_DIGEST = "VERIFIED_BY_HUMAN_NO_TRANSCRIPT_DIGEST"
UNAVAILABLE = "unavailable"
LEVELS = ("cursory", "standard", "skeptical")

MARKER_PREFIX = "GSA-APPROVAL"
MARKER_RE = re.compile(rb"GSA-APPROVAL ([0-9a-f]{40}) (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")
MARKER_WINDOW = 64 * 1024
# Harnesses append the assistant's reply before executing its next tool call;
# one short retry covers a slow flush, after which a missing marker is real.
MARKER_RETRY_DELAY = 1.0

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_STALE = 3
EXIT_TRANSCRIPT = 4
EXIT_PROFILE = 5
EXIT_GIT = 6
EXIT_SELFCHECK = 7

TOKEN_RE = re.compile(r"^[A-Za-z0-9._:/-]+$")
ATTESTATION_SUBJECT_RE = re.compile(r"^\[SIGNOFF [0-9a-f]{7,40}\]: ")
TRAILER_LINE_RE = re.compile(r"^Signoff-[A-Za-z0-9-]+:")
TRAILER_RE = re.compile(r"^(Signoff-[A-Za-z0-9-]+):\s*(.*)$")


class AttestError(Exception):
    """Every failure the helper reports: an exit code and a message."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- git ---------------------------------------------------------------------


class GitRepo:
    """Thin subprocess wrapper; every command runs with cwd=self.path."""

    def __init__(self, path: str):
        self.path = path

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        try:
            proc = subprocess.run(["git", *args], cwd=self.path, capture_output=True, text=True)
        except OSError as exc:
            raise AttestError(EXIT_GIT, f"git {' '.join(args)} could not run: {exc}") from exc
        if check and proc.returncode != 0:
            raise AttestError(EXIT_GIT, f"git {' '.join(args)} failed: {proc.stderr.strip()}")
        return proc

    def out(self, *args: str) -> str:
        return self.git(*args).stdout.strip()


def repo_root(cwd: str | None = None) -> str:
    """Repository root of the working directory (`git rev-parse --show-toplevel`)."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=cwd or os.getcwd(), capture_output=True, text=True
        )
    except OSError as exc:
        raise AttestError(EXIT_GIT, f"git could not run: {exc}") from exc
    if proc.returncode != 0 or not proc.stdout.strip():
        raise AttestError(EXIT_GIT, f"not inside a git repository: {proc.stderr.strip()}")
    return proc.stdout.strip()


# --- transcript adapters (gsa-core §3) ---------------------------------------


class TranscriptProvider(Protocol):
    """Minimal interface for transcript discovery across AI agent runtimes."""

    harness_id: str

    def resolve_conversation_id(self) -> str | None: ...

    def fetch_transcript_bytes(self) -> bytes | None: ...

    def describe_path(self) -> str | None: ...


def _slug(path: str) -> str:
    return path.replace("/", "-")


def _read_bytes(path: str | None) -> bytes | None:
    if not path:
        return None
    try:
        with open(os.path.expanduser(path), "rb") as f:
            return f.read()
    except OSError:
        return None


class GenericFileAdapter:
    """Explicit transcript override via GIT_SIGNOFF_TRANSCRIPT_FILE (§3.2)."""

    harness_id = "generic-file"

    def __init__(self, path: str, conversation_id: str | None = None):
        self.path = path
        self.conversation_id = conversation_id

    def resolve_conversation_id(self) -> str | None:
        return self.conversation_id

    def describe_path(self) -> str | None:
        return os.path.expanduser(self.path)

    def fetch_transcript_bytes(self) -> bytes | None:
        return _read_bytes(self.path)


class AntigravityAdapter:
    """Antigravity CLI harness (§3.2)."""

    harness_id = "antigravity-cli"

    def __init__(self, conversation_id: str, home: str | None = None):
        self.conversation_id = conversation_id
        self.home = home or os.path.expanduser("~")

    def resolve_conversation_id(self) -> str | None:
        return self.conversation_id

    def describe_path(self) -> str | None:
        return os.path.join(
            self.home,
            ".gemini",
            "antigravity-cli",
            "brain",
            self.conversation_id,
            ".system_generated",
            "logs",
            "transcript.jsonl",
        )

    def fetch_transcript_bytes(self) -> bytes | None:
        return _read_bytes(self.describe_path())


class ClaudeCodeAdapter:
    """Claude Code harness (§3.2) with linked-worktree fallback.

    Session transcripts are keyed to the primary repository root slug. Inside a
    linked worktree (or a subdirectory of the main worktree) the cwd slug
    misses, so fall back to the primary root via `git rev-parse
    --git-common-dir`, anchored to the injected cwd rather than the process cwd.
    """

    harness_id = "claude-code"

    def __init__(self, session_id: str, cwd: str | None = None, home: str | None = None):
        self.session_id = session_id
        self.cwd = os.path.abspath(cwd or os.getcwd())
        self.home = home or os.path.expanduser("~")

    def resolve_conversation_id(self) -> str | None:
        return self.session_id

    def _transcript_path(self, root: str) -> str:
        return os.path.join(self.home, ".claude", "projects", _slug(root), f"{self.session_id}.jsonl")

    def describe_path(self) -> str | None:
        path = self._transcript_path(self.cwd)
        if os.path.exists(path):
            return path
        try:
            git_dir = subprocess.check_output(
                ["git", "rev-parse", "--git-common-dir"], text=True, stderr=subprocess.DEVNULL, cwd=self.cwd
            ).strip()
        except Exception:
            return path
        main_root = os.path.abspath(os.path.join(self.cwd, git_dir, os.pardir))
        return self._transcript_path(main_root)

    def fetch_transcript_bytes(self) -> bytes | None:
        return _read_bytes(self.describe_path())


class CodexAdapter:
    """ChatGPT Codex CLI harness: newest `$CODEX_HOME/sessions/**/rollout-*-<sid>.jsonl`."""

    harness_id = "codex-cli"

    def __init__(self, session_id: str, codex_home: str | None = None, home: str | None = None):
        self.session_id = session_id
        base = codex_home or os.path.join(home or os.path.expanduser("~"), ".codex")
        self.sessions_dir = os.path.join(base, "sessions")

    def resolve_conversation_id(self) -> str | None:
        return self.session_id

    def describe_path(self) -> str | None:
        escaped_sid = glob.escape(self.session_id)
        pattern = os.path.join(glob.escape(self.sessions_dir), "**", f"rollout-*-{escaped_sid}.jsonl")
        try:
            matches = glob.glob(pattern, recursive=True)
            if not matches:
                return None
            return max(matches, key=lambda p: (os.path.getmtime(p), p))
        except OSError:
            return None

    def fetch_transcript_bytes(self) -> bytes | None:
        return _read_bytes(self.describe_path())


def resolve_adapter(
    env: Mapping[str, str] | None = None,
    cwd: str | None = None,
    home: str | None = None,
) -> TranscriptProvider | None:
    """Resolve the active harness adapter, or None when no harness is detected.

    Resolution order: GIT_SIGNOFF_TRANSCRIPT_FILE → ANTIGRAVITY_CONVERSATION_ID →
    CLAUDE_CODE_SESSION_ID → CODEX_SESSION_ID (gsa-core §3.2; the matrix is
    informative and adapter-owned).
    """
    env = os.environ if env is None else env
    override = env.get("GIT_SIGNOFF_TRANSCRIPT_FILE", "").strip()
    ag_cid = env.get("ANTIGRAVITY_CONVERSATION_ID", "").strip()
    cc_cid = env.get("CLAUDE_CODE_SESSION_ID", "").strip()
    codex_sid = env.get("CODEX_SESSION_ID", "").strip()

    if override:
        return GenericFileAdapter(override, conversation_id=ag_cid or cc_cid or codex_sid or None)
    if ag_cid:
        return AntigravityAdapter(ag_cid, home=home)
    if cc_cid:
        return ClaudeCodeAdapter(cc_cid, cwd=cwd, home=home)
    if codex_sid:
        return CodexAdapter(codex_sid, codex_home=env.get("CODEX_HOME", "").strip() or None, home=home)
    return None


# --- interview profile (SKILL.md Section 1) ----------------------------------

PROFILE_ENV_VAR = "GIT_SIGNOFF_PROFILE_FILE"
REPO_PROFILE_RELPATH = os.path.join(".git-signoff", "profile.md")
EMBEDDED_PROFILE_ID = "software-general"

SOURCE_ENV_OVERRIDE = "env-override"
SOURCE_REPO_LOCAL = "repo-local"
SOURCE_EMBEDDED = "embedded-default"

_BEGIN_MARKER = b"INTERVIEW-PROFILE:BEGIN"
_END_MARKER = b"INTERVIEW-PROFILE:END"
_PROFILE_ID_RE = re.compile(rb"^Profile-ID:[ \t]*([a-z0-9-]+)[ \t]*$", re.MULTILINE)


@dataclass
class ProfileResolution:
    """``digest`` is the 12-hex prefix written as ``/sha256:<digest>`` in the
    ``interview=`` token; None exactly when the embedded default is active.
    ``fallback_reason`` is set when a file-sourced profile was malformed and
    therefore announced-and-ignored in favor of the embedded default."""

    source: str
    path: str | None
    profile_id: str
    digest: str | None
    fallback_reason: str | None = None


def profile_block_digest(data: bytes) -> str:
    """12-hex digest prefix of the delimited profile block.

    Byte-equivalent to the historical pipeline
    ``sed -n '/INTERVIEW-PROFILE:BEGIN/,/INTERVIEW-PROFILE:END/p' | sha256sum | cut -c1-12``,
    including sed's range semantics (the end pattern is not tested on the line
    that opened the range, and an unclosed range runs to EOF). Pinned by the
    digest-parity test so file-sourced profile digests never change meaning.
    """
    selected = []
    in_range = False
    for line in data.splitlines(keepends=True):
        if in_range:
            selected.append(line)
            if _END_MARKER in line:
                in_range = False
        elif _BEGIN_MARKER in line:
            selected.append(line)
            in_range = True
    return hashlib.sha256(b"".join(selected)).hexdigest()[:12]


def _validate_profile(data: bytes) -> tuple[str | None, str | None]:
    begins = data.count(_BEGIN_MARKER)
    ends = data.count(_END_MARKER)
    if begins != 1 or ends != 1:
        return None, (
            f"expected exactly one delimited INTERVIEW-PROFILE block, found {begins} BEGIN / {ends} END marker(s)"
        )
    start = data.index(_BEGIN_MARKER)
    end = data.index(_END_MARKER)
    if end < start:
        return None, "INTERVIEW-PROFILE:END marker precedes BEGIN marker"
    m = _PROFILE_ID_RE.search(data, start, end)
    if not m:
        return None, "missing or malformed Profile-ID line inside the profile block"
    return m.group(1).decode("ascii"), None


def _embedded(fallback_reason: str | None = None) -> ProfileResolution:
    return ProfileResolution(SOURCE_EMBEDDED, None, EMBEDDED_PROFILE_ID, None, fallback_reason)


def _resolve_file(path: str, source: str) -> ProfileResolution:
    with open(path, "rb") as f:
        data = f.read()
    profile_id, reason = _validate_profile(data)
    if profile_id is None:
        return _embedded(f"malformed profile at {path} ({reason}); using embedded default")
    return ProfileResolution(source, path, profile_id, profile_block_digest(data))


def resolve_profile(root: str, env: Mapping[str, str] | None = None) -> ProfileResolution:
    """GIT_SIGNOFF_PROFILE_FILE (unreadable → exit 5, never a fallback) →
    <root>/.git-signoff/profile.md → embedded default."""
    environ = os.environ if env is None else env
    override = (environ.get(PROFILE_ENV_VAR) or "").strip()
    if override:
        expanded = os.path.expanduser(override)
        if not (os.path.isfile(expanded) and os.access(expanded, os.R_OK)):
            raise AttestError(EXIT_PROFILE, f"{PROFILE_ENV_VAR} is set but unreadable: {override}. Aborting signoff.")
        return _resolve_file(expanded, SOURCE_ENV_OVERRIDE)
    repo_local = os.path.join(root, REPO_PROFILE_RELPATH)
    if os.path.isfile(repo_local) and os.access(repo_local, os.R_OK):
        return _resolve_file(repo_local, SOURCE_REPO_LOCAL)
    return _embedded()


# --- science guard and intensity hints (SKILL.md Section 2) -------------------

# Content signals match added (+) diff lines only; file signals also match diff
# headers, so renames and deletions of e.g. notebooks still count.
SCIENCE_SIGNAL_PATTERNS: dict[str, re.Pattern] = {
    "scientific-imports": re.compile(
        r"^\+\s*(?:import|from)\s+(?:numpy|scipy|jax|torch|astropy|pandas|xarray)\b", re.MULTILINE
    ),
    "notebooks": re.compile(r"^(?:diff --git|\+\+\+|---) .*\.ipynb\b", re.MULTILINE),
    "rng-seeding": re.compile(r"^\+.*(?:\bseed\s*=|\.seed\(|default_rng|random_state\s*=|manual_seed)", re.MULTILINE),
    "units-or-constants": re.compile(
        r"^\+.*(?:\bhPa\b|\bkPa\b|\bkg/kg\b|\bkg[ /]?m(?:\^?-?[23]|²|³)?\b|\bm\s?s\^?-2\b|\bW[ /]?m-?2\b"
        r"|9\.80665|6\.674\d*e-11|1\.380649e-23|6\.02214)",
        re.MULTILINE,
    ),
    "solvers-integrators": re.compile(
        r"^\+.*(?:solve_ivp|odeint|scipy\.integrate|np\.linalg|scipy\.linalg|trapezoid\(|cumulative_trapezoid"
        r"|runge.?kutta|newton_krylov)",
        re.MULTILINE | re.IGNORECASE,
    ),
    "datasets-model-config": re.compile(
        r"^(?:diff --git|\+\+\+|---|\+).*(?:\.nc4?\b|netcdf|\.grib2?\b|\.zarr\b|to_zarr|open_zarr)",
        re.MULTILINE | re.IGNORECASE,
    ),
}


def detect_science_signals(diff: str) -> list[str]:
    """Names of science-guard signal categories present in a range diff, sorted."""
    return sorted(name for name, pattern in SCIENCE_SIGNAL_PATTERNS.items() if pattern.search(diff))


DOC_SUFFIXES = {".md", ".markdown", ".rst", ".txt", ".adoc"}
DOC_BASENAMES = {"LICENSE", "NOTICE", "CHANGELOG", "AUTHORS", "CODEOWNERS"}
LOCKFILE_RE = re.compile(r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock|uv\.lock|Pipfile\.lock)$")
TEST_PATH_RE = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*$|(_test|\.test|_spec|\.spec)\.[A-Za-z0-9]+$")

# Canonical High-Impact Tier 2 triggers (SKILL.md), by path and by content.
TIER2_PATH_TRIGGERS: tuple[tuple[str, re.Pattern], ...] = (
    ("security-auth", re.compile(r"(^|/)(auth|crypto|permissions)/", re.IGNORECASE)),
    ("schemas-migrations", re.compile(r"(^|/)migrations/|(^|/)schema\.sql$", re.IGNORECASE)),
    ("public-api-contracts", re.compile(r"\.proto$|(^|/)[^/]*(openapi|swagger)[^/]*\.(ya?ml|json)$", re.IGNORECASE)),
)
TIER2_CONTENT_TRIGGERS: tuple[tuple[str, re.Pattern], ...] = (
    ("schemas-migrations", re.compile(r"^\+.*\bALTER\s+TABLE\b", re.MULTILINE | re.IGNORECASE)),
)


def _is_doc_path(path: str) -> bool:
    name = os.path.basename(path)
    return name in DOC_BASENAMES or os.path.splitext(name)[1].lower() in DOC_SUFFIXES


def _is_test_path(path: str) -> bool:
    return bool(TEST_PATH_RE.search(path))


def intensity_hints(numstat: str, diff: str, science_signals: list[str]) -> dict:
    """Informative counts for the agent's intensity classification.

    The agent remains authoritative for classification; these numbers keep it
    from miscounting. `executable_lines_changed` excludes documentation,
    lockfiles, tests, and binary files (numstat `-`).
    """
    changed_files = 0
    executable_files = 0
    executable_lines = 0
    tier2: dict[str, set[str]] = {}
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        # renames are reported as `old => new` or `{a => b}/c`; use the new name
        path = re.sub(r"\{[^{}]* => ([^{}]*)\}", r"\1", path)
        if " => " in path:
            path = path.split(" => ", 1)[1]
        changed_files += 1
        for name, pattern in TIER2_PATH_TRIGGERS:
            if pattern.search(path) and not _is_doc_path(path):
                tier2.setdefault(name, set()).add(path)
        if _is_doc_path(path) or _is_test_path(path) or LOCKFILE_RE.search(path):
            continue
        executable_files += 1
        if added.isdigit() and deleted.isdigit():
            executable_lines += int(added) + int(deleted)
    for name, pattern in TIER2_CONTENT_TRIGGERS:
        if pattern.search(diff):
            tier2.setdefault(name, set()).add("<diff content>")
    if science_signals:
        tier2["scientific-computation"] = set(science_signals)
    if executable_files > 5 or executable_lines > 200:
        tier2["executable-blast-radius"] = {f"{executable_files} files / {executable_lines} lines"}
    return {
        "changed_files": changed_files,
        "executable_files": executable_files,
        "executable_lines_changed": executable_lines,
        "tier2_triggers": {name: sorted(paths) for name, paths in sorted(tier2.items())},
    }


# --- prepare -----------------------------------------------------------------


@dataclass
class PrepareState:
    reviewed_commit_sha: str
    base_sha: str
    tree_sha: str
    reference: str
    name_status: list[str]
    shortstat: str
    numstat: str
    diff: str
    profile: ProfileResolution
    science_signals: list[str]
    harness_id: str
    conversation_id: str
    transcript_available: bool
    transcript_path: str | None
    hints: dict
    prepared_at: str
    warnings: list[str] = field(default_factory=list)

    @property
    def marker(self) -> str:
        return f"{MARKER_PREFIX} {self.reviewed_commit_sha} {self.prepared_at}"

    def to_json(self) -> dict:
        return {
            "ok": True,
            "command": "prepare",
            "reviewed_commit_sha": self.reviewed_commit_sha,
            "short_sha": self.reviewed_commit_sha[:7],
            "base_sha": self.base_sha,
            "tree_sha": self.tree_sha,
            "reference": self.reference,
            "diff_command": f"git diff {self.base_sha}..{self.reviewed_commit_sha}",
            "name_status": self.name_status,
            "shortstat": self.shortstat,
            "profile": {
                "source": self.profile.source,
                "path": self.profile.path,
                "id": self.profile.profile_id,
                "digest": self.profile.digest,
                "fallback_reason": self.profile.fallback_reason,
            },
            "science_signals": self.science_signals,
            "transcript": {
                "harness_id": self.harness_id,
                "conversation_id": self.conversation_id,
                "available": self.transcript_available,
                "path": self.transcript_path,
            },
            "hints": self.hints,
            "marker": self.marker,
            "warnings": self.warnings,
        }


def _range_is_empty(repo: GitRepo, reference: str, reviewed: str) -> bool:
    """True when `reference` already contains `reviewed`: there is nothing to review."""
    return repo.git("merge-base", "--is-ancestor", reviewed, reference, check=False).returncode == 0


def _resolve_reference(repo: GitRepo, reference: str | None, reviewed: str, warnings: list[str]) -> str:
    if reference:
        if repo.git("rev-parse", "--verify", "-q", f"{reference}^{{commit}}", check=False).returncode != 0:
            raise AttestError(EXIT_USAGE, f"--reference {reference!r} does not resolve to a commit")
        if _range_is_empty(repo, reference, reviewed):
            # Explicit choice: honored (a post-hoc attestation of a merged
            # commit has Base-SHA == Reviewed-Commit-SHA), but said out loud.
            warnings.append(
                f"--reference {reference!r} already contains HEAD: the range to review is empty "
                "(Base-SHA will equal the reviewed commit). If you meant the base branch, pass that instead."
            )
        return reference
    proc = repo.git("rev-parse", "--abbrev-ref", "HEAD@{upstream}", check=False)
    upstream = proc.stdout.strip() if proc.returncode == 0 else ""
    # After `git push -u origin <feature>` the upstream is the branch's own
    # remote counterpart, which contains HEAD — an empty range, not a base.
    # Only an upstream that is *behind* HEAD (the base branch) is usable.
    if upstream and not _range_is_empty(repo, upstream, reviewed):
        return upstream
    if upstream:
        warnings.append(
            f"Upstream '{upstream}' already contains HEAD (it is this branch's own remote counterpart, "
            "not a base); falling back."
        )
    head_full = repo.git("rev-parse", "--symbolic-full-name", "HEAD", check=False).stdout.strip()
    # On main or master itself there is no sensible default base: never diff a
    # default branch against the other one.
    candidates = () if head_full in ("refs/heads/main", "refs/heads/master") else ("main", "master", "origin/main", "origin/master")
    for candidate in candidates:
        if repo.git("rev-parse", "--verify", "-q", f"{candidate}^{{commit}}", check=False).returncode != 0:
            continue
        if _range_is_empty(repo, candidate, reviewed):
            continue
        warnings.append(
            f"No usable upstream for HEAD; assuming base branch '{candidate}'. "
            "If this is incorrect, pass --reference explicitly."
        )
        return candidate
    raise AttestError(
        EXIT_USAGE,
        "No base branch could be inferred for HEAD (no upstream behind it, and no main/master that does not "
        "already contain it); pass --reference <branch-or-commit> (no hardcoded remote assumptions per GSA §2.3).",
    )


def check_clean_tree(repo: GitRepo) -> None:
    """Unstaged or staged changes → exit 3: the interview must cover the committed state."""
    unstaged = repo.git("diff", "--quiet", check=False)
    if unstaged.returncode == 1:
        raise AttestError(EXIT_STALE, "Unstaged changes present; commit or stash them (the interview covers the committed state).")
    if unstaged.returncode != 0:
        raise AttestError(EXIT_GIT, f"git diff --quiet failed: {unstaged.stderr.strip()}")
    staged = repo.git("diff", "--cached", "--quiet", check=False)
    if staged.returncode == 1:
        raise AttestError(EXIT_STALE, "Staged changes present; commit or unstage them (the interview covers the committed state).")
    if staged.returncode != 0:
        raise AttestError(EXIT_GIT, f"git diff --cached --quiet failed: {staged.stderr.strip()}")


def prepare(
    root: str,
    reference: str | None = None,
    env: Mapping[str, str] | None = None,
    adapter: TranscriptProvider | None = None,
) -> PrepareState:
    repo = GitRepo(root)
    environ = os.environ if env is None else env
    warnings: list[str] = []

    head = repo.git("rev-parse", "--verify", "-q", "HEAD^{commit}", check=False)
    if head.returncode != 0 or not head.stdout.strip():
        raise AttestError(EXIT_GIT, "HEAD does not point at a commit (unborn branch?); nothing to attest.")
    reviewed = head.stdout.strip()
    subject = repo.git("log", "-1", "--format=%s", reviewed, check=False).stdout.strip()
    if ATTESTATION_SUBJECT_RE.match(subject):
        # Attesting an attestation is never meaningful, and this is exactly the
        # state a failed rollback leaves behind: a rejected attestation commit at
        # HEAD. Re-running from Section 1 here would attest *that* commit and the
        # verifier would pass it. Stop instead.
        parent = repo.git("rev-parse", f"{reviewed}~1", check=False).stdout.strip()
        raise AttestError(
            EXIT_STALE,
            f"HEAD {reviewed[:7]} is already an attestation commit ({subject[:40]}...) on top of {parent[:7]}; "
            "there is nothing new to attest. If it was left behind by a failed rollback, remove it with "
            "`git reset --soft HEAD~1` and re-run; if it is a valid attestation, the branch is done.",
        )
    check_clean_tree(repo)

    ref = _resolve_reference(repo, reference, reviewed, warnings)
    base = repo.out("merge-base", ref, reviewed)
    tree = repo.out("rev-parse", f"{reviewed}^{{tree}}")
    rng = f"{base}..{reviewed}"
    diff = repo.git("diff", rng).stdout
    name_status = [line for line in repo.out("diff", "--name-status", rng).splitlines() if line]
    shortstat = repo.out("diff", "--shortstat", rng)
    numstat = repo.git("diff", "--numstat", rng).stdout

    profile = resolve_profile(root, environ)
    if profile.fallback_reason:
        warnings.append(profile.fallback_reason)
    signals = detect_science_signals(diff)

    if adapter is None:
        adapter = resolve_adapter(environ, cwd=root)
    harness_id = adapter.harness_id if adapter else "unknown"
    conversation_id = (adapter.resolve_conversation_id() if adapter else None) or UNAVAILABLE
    transcript_path = adapter.describe_path() if adapter else None
    # Informative only; the binding snapshot happens inside commit (§2.3).
    transcript_available = bool(adapter and adapter.fetch_transcript_bytes() is not None)
    if adapter is None:
        warnings.append(
            "No transcript adapter detected (no GIT_SIGNOFF_TRANSCRIPT_FILE or harness session id); "
            "commit will need --ack-no-transcript after the human's explicit second confirmation."
        )
    elif not transcript_available:
        warnings.append(f"Transcript not readable at {transcript_path}; commit will need --ack-no-transcript.")

    return PrepareState(
        reviewed_commit_sha=reviewed,
        base_sha=base,
        tree_sha=tree,
        reference=ref,
        name_status=name_status,
        shortstat=shortstat,
        numstat=numstat,
        diff=diff,
        profile=profile,
        science_signals=signals,
        harness_id=harness_id,
        conversation_id=conversation_id,
        transcript_available=transcript_available,
        transcript_path=transcript_path,
        hints=intensity_hints(numstat, diff, signals),
        prepared_at=_utc_now(),
        warnings=warnings,
    )


# --- message construction (gsa-core §2.1, §2.3) --------------------------------


def parse_trailers(message: str) -> dict[str, list[str]]:
    trailers: dict[str, list[str]] = {}
    for line in message.splitlines():
        m = TRAILER_RE.match(line)
        if m:
            trailers.setdefault(m.group(1), []).append(m.group(2).strip())
    return trailers


def reject_unsafe_text(name: str, value: str, *, multiline: bool = False) -> None:
    """Free text is interpolated into a line-oriented trailer format (§2.3).

    A line break inside a tradeoff, risk, agent string, or email would start a
    new line that the verifier reads as a trailer — a second
    Signoff-Reviewed-Tree-SHA smuggled that way anchors an unreviewed tree.
    The summary paragraph may span lines but none of them may look like a
    trailer. Carriage returns are refused everywhere.
    """
    if "\r" in value:
        raise AttestError(EXIT_USAGE, f"{name} must not contain carriage returns (line-oriented trailer format)")
    if not multiline and "\n" in value:
        raise AttestError(EXIT_USAGE, f"{name} must be a single line (line-oriented trailer format): {value!r}")
    if multiline:
        for line in value.splitlines():
            if TRAILER_LINE_RE.match(line.strip()):
                raise AttestError(EXIT_USAGE, f"{name} must not contain a line that reads as a Signoff- trailer: {line!r}")
    if not multiline and not value.strip():
        raise AttestError(EXIT_USAGE, f"{name} must not be empty")


def agent_provenance(
    env: Mapping[str, str], data: bytes | None, level: str, profile: ProfileResolution, model_override: str | None
) -> str:
    """Signoff-Agent value (§2.3 grammar). Version/reasoning are Claude Code
    env vars and are scoped to that harness; the model comes from
    ANTHROPIC_MODEL, else the last "model" field in the same snapshot bytes as
    the digest, else the agent's self-report (--model), else `unavailable`."""
    in_claude_code = bool(env.get("CLAUDE_CODE_SESSION_ID", "").strip())
    hver = env.get("CLAUDE_CODE_VERSION", "").strip() if in_claude_code else ""
    reasoning = env.get("CLAUDE_EFFORT", "").strip() if in_claude_code else ""
    model = env.get("ANTHROPIC_MODEL", "").strip()
    if not model and data:
        hits = re.findall(rb'"model"\s*:\s*"([^"]+)"', data)
        if hits:
            model = hits[-1].decode("utf-8", "replace")
    if not model and model_override:
        model = model_override
    hver, model, reasoning = [
        value if value and TOKEN_RE.match(value) else missing
        for value, missing in ((hver, "N/A"), (model, UNAVAILABLE), (reasoning, "N/A"))
    ]
    harness_id = _harness_id(env)
    interview = f"{level}/{profile.profile_id}"
    if profile.digest:
        interview += f"/sha256:{profile.digest}"
    return f"harness={harness_id}/{hver} model={model} reasoning={reasoning} interview={interview}"


def _harness_id(env: Mapping[str, str]) -> str:
    adapter = resolve_adapter(env)
    return adapter.harness_id if adapter else "unknown"


def build_message(
    state: PrepareState,
    status: str,
    timestamp: str,
    transcript_digest: str,
    transcript_bytes: str,
    tradeoffs: list[str],
    risks: list[str],
    user_email: str,
    agent: str,
    summary: str | None = None,
    harness_id: str | None = None,
    conversation_id: str | None = None,
) -> str:
    lines = [f"[SIGNOFF {state.reviewed_commit_sha[:7]}]: human comprehension and risk attestation", ""]
    if summary and summary.strip():
        lines += [summary.strip(), ""]
    lines += [
        f"Signoff-Spec-Version: {SPEC_VERSION}",
        f"Signoff-Status: {status}",
        f"Signoff-Timestamp: {timestamp}",
        f"Signoff-Base-SHA: {state.base_sha}",
        f"Signoff-Reviewed-Commit-SHA: {state.reviewed_commit_sha}",
        f"Signoff-Reviewed-Tree-SHA: {state.tree_sha}",
        f"Signoff-Harness-ID: {harness_id or state.harness_id}",
        f"Signoff-Conversation-ID: {conversation_id or state.conversation_id}",
        f"Signoff-Transcript-Digest: {transcript_digest}",
        f"Signoff-Transcript-Bytes: {transcript_bytes}",
    ]
    # Repeat rule (§2.3): one trailer per item; 'none' exactly once when empty.
    lines += [f"Signoff-Tradeoff: {t}" for t in tradeoffs] or ["Signoff-Tradeoff: none"]
    lines += [f"Signoff-Risk: {r}" for r in risks] or ["Signoff-Risk: none"]
    lines += [f"Signoff-Verified-By: {user_email}", f"Signoff-Agent: {agent}"]
    return "\n".join(lines)


# --- approval marker (§2.3) ------------------------------------------------------


@dataclass
class MarkerCheck:
    found: bool
    sha: str | None = None
    timestamp: str | None = None
    window_bytes: int = 0


def find_marker(data: bytes) -> MarkerCheck:
    """Last GSA-APPROVAL marker in the final MARKER_WINDOW bytes of a snapshot."""
    window = data[-MARKER_WINDOW:]
    matches = list(MARKER_RE.finditer(window))
    if not matches:
        return MarkerCheck(False, window_bytes=len(window))
    last = matches[-1]
    return MarkerCheck(True, last.group(1).decode("ascii"), last.group(2).decode("ascii"), len(window))


def _marker_error(repo: GitRepo, reviewed: str, check: MarkerCheck, path: str | None, nbytes: int) -> AttestError:
    expected = f"{MARKER_PREFIX} {reviewed} <utc-timestamp>"
    where = f"transcript {path} ({nbytes} bytes; last {check.window_bytes} bytes searched)"
    if not check.found:
        return AttestError(
            EXIT_TRANSCRIPT,
            f"approval marker not found in {where}. Expected a line `{expected}`. "
            "Emit the marker line in the conversation (as its own paragraph, after the human's explicit "
            "approval), then re-run commit. If the resolved file is not this conversation's transcript, "
            "set GIT_SIGNOFF_TRANSCRIPT_FILE to the right file.",
        )
    ancestor = repo.git("merge-base", "--is-ancestor", check.sha, reviewed, check=False).returncode == 0
    if ancestor:
        return AttestError(
            EXIT_STALE,
            f"stale: the last approval marker in {where} names {check.sha}, but HEAD is now {reviewed} "
            "(the branch moved after prepare). Re-run prepare, re-confirm with the human, emit a new marker, "
            "then re-run commit.",
        )
    return AttestError(
        EXIT_TRANSCRIPT,
        f"the last approval marker in {where} names commit {check.sha}, but the reviewed commit (HEAD) is "
        f"{reviewed}. This transcript is not this conversation's approval of this commit; check "
        "GIT_SIGNOFF_TRANSCRIPT_FILE / the harness session id, then re-run prepare and commit.",
    )


# --- commit ------------------------------------------------------------------


@dataclass
class CommitOptions:
    email: str
    level: str
    tradeoffs: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    summary: str | None = None
    model: str | None = None
    reference: str | None = None
    ack_no_transcript: bool = False
    sign: bool = True
    dry_run: bool = False
    push: bool = True
    timestamp: str | None = None


@dataclass
class CommitResult:
    attestation_sha: str | None
    status: str
    transcript_digest: str
    transcript_bytes: str
    transcript_path: str | None
    marker_found: bool
    message: str
    signed: bool
    dry_run: bool
    noted_shas: list[str] = field(default_factory=list)
    notes_pushed: bool = False
    notes_push_reason: str | None = None
    notes_merged_remote: bool = False
    verifier: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        d = asdict(self)
        d.update({"ok": True, "command": "commit"})
        return d


def validate_commit_options(opts: CommitOptions) -> None:
    if not opts.email or "@" not in opts.email:
        raise AttestError(EXIT_USAGE, f"--email must be an address containing '@': {opts.email!r}")
    reject_unsafe_text("--email", opts.email)
    if opts.level not in LEVELS:
        raise AttestError(EXIT_USAGE, f"--level must be one of {', '.join(LEVELS)}: {opts.level!r}")
    for t in opts.tradeoffs:
        reject_unsafe_text("--tradeoff", t)
    for r in opts.risks:
        reject_unsafe_text("--risk", r)
    if opts.summary:
        reject_unsafe_text("--summary", opts.summary, multiline=True)
    if opts.model is not None and not TOKEN_RE.match(opts.model):
        raise AttestError(EXIT_USAGE, f"--model must match [A-Za-z0-9._:/-]+: {opts.model!r}")


def load_verifier():
    """Import the sibling verify_signoff.py (same folder, vendored together)."""
    here = Path(__file__).resolve().parent
    path = here / "verify_signoff.py"
    if not path.is_file():
        raise AttestError(
            EXIT_USAGE,
            f"verify_signoff.py not found next to attest.py ({path}); the skill folder must be copied whole.",
        )
    spec = importlib.util.spec_from_file_location("gsa_verifier", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _snapshot(adapter: TranscriptProvider | None) -> bytes | None:
    return adapter.fetch_transcript_bytes() if adapter else None


def _note_blob(repo: GitRepo, target: str) -> str | None:
    proc = repo.git("notes", f"--ref={NOTES_REF}", "list", target, check=False)
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None


def _restore_notes(repo: GitRepo, prior: dict[str, str | None]) -> list[str]:
    """Put each note back as it was before this run. Returns the steps that failed."""
    failures = []
    for target, blob in prior.items():
        if blob is None:
            proc = repo.git("notes", f"--ref={NOTES_REF}", "remove", "--ignore-missing", target, check=False)
            action = f"remove the note on {target[:7]}"
        else:
            proc = repo.git("notes", f"--ref={NOTES_REF}", "add", "-f", "-C", blob, target, check=False)
            action = f"restore the prior note on {target[:7]}"
        if proc.returncode != 0:
            failures.append(f"{action}: {proc.stderr.strip() or f'exit {proc.returncode}'}")
    return failures


def _rollback_commit(repo: GitRepo) -> list[str]:
    """Drop the attestation commit just written (soft: its tree equals its parent's).
    Returns the failure, if any, so the caller never claims a removal that did not happen."""
    proc = repo.git("reset", "-q", "--soft", "HEAD~1", check=False)
    if proc.returncode != 0:
        return [f"remove the attestation commit (git reset --soft HEAD~1): {proc.stderr.strip() or f'exit {proc.returncode}'}"]
    return []


def _rollback_error(code: int, message: str, failures: list[str]) -> AttestError:
    """The exit message must describe the repository as it *is*: when any
    rollback step failed, say so loudly instead of asserting a clean state."""
    if not failures:
        return AttestError(code, message)
    return AttestError(
        code,
        message
        + " ROLLBACK INCOMPLETE — the repository is NOT back in its pre-commit state: "
        + "; ".join(failures)
        + ". Inspect `git log -1` and `git notes --ref=signoff list` before doing anything else.",
    )


def push_notes(repo: GitRepo, remote: str = "origin") -> tuple[bool, bool, str | None]:
    """(pushed, merged_remote, reason). Fetch origin's notes into the tracking
    ref (tolerating a remote with no notes yet), merge with cat_sort_uniq, push.
    Refusals are reported, never raised: the attestation commit stands."""
    fetch = repo.git("fetch", remote, f"+{NOTES_REF}:{NOTES_TRACKING_REF}", check=False)
    merged = False
    if fetch.returncode == 0:
        merge = repo.git("notes", f"--ref={NOTES_REF}", "merge", "-s", "cat_sort_uniq", NOTES_TRACKING_REF, check=False)
        if merge.returncode != 0:
            err = merge.stderr.strip().splitlines()
            return False, False, f"notes merge failed: {err[-1] if err else 'unknown error'}"
        merged = True
    push = repo.git("push", remote, NOTES_REF, check=False)
    if push.returncode != 0:
        err = push.stderr.strip().splitlines()
        return False, merged, f"notes push refused: {err[-1] if err else 'unknown error'}"
    return True, merged, None


def commit(root: str, opts: CommitOptions, env: Mapping[str, str] | None = None, adapter=None, verifier=None) -> CommitResult:
    environ = os.environ if env is None else env
    validate_commit_options(opts)
    verifier = verifier or load_verifier()
    repo = GitRepo(root)

    state = prepare(root, opts.reference, environ, adapter=adapter)
    reviewed, tree = state.reviewed_commit_sha, state.tree_sha
    if adapter is None:
        adapter = resolve_adapter(environ, cwd=root)
    harness_id = adapter.harness_id if adapter else "unknown"
    conversation_id = (adapter.resolve_conversation_id() if adapter else None) or UNAVAILABLE
    transcript_path = adapter.describe_path() if adapter else None

    # Snapshot timing (§2.3): read the bytes once, immediately before the
    # commit; every later check — marker, digest, provenance — uses this snapshot.
    data = _snapshot(adapter)
    marker_found = False
    marker_warning = None
    if data is not None:
        check = find_marker(data)
        if not (check.found and check.sha == reviewed) and not opts.dry_run:
            time.sleep(MARKER_RETRY_DELAY)
            data = _snapshot(adapter) or data
            check = find_marker(data)
        marker_found = bool(check.found and check.sha == reviewed)
        if not marker_found:
            if not opts.dry_run:
                raise _marker_error(repo, reviewed, check, transcript_path, len(data))
            # The dry run presents trailers *before* approval, so the marker
            # cannot be there yet; the real commit re-snapshots and requires it.
            marker_warning = (
                "dry run: approval marker not yet in the transcript (expected before approval); "
                "digest and byte count are provisional and are recomputed at commit"
            )
        status = STATUS_VERIFIED
        digest = f"sha256:{hashlib.sha256(data).hexdigest()}"
        nbytes = str(len(data))
    elif opts.ack_no_transcript:
        status = STATUS_NO_DIGEST
        digest = UNAVAILABLE
        nbytes = UNAVAILABLE
    else:
        where = f" at {transcript_path}" if transcript_path else ""
        raise AttestError(
            EXIT_TRANSCRIPT,
            f"transcript unavailable{where} (harness {harness_id}). Re-run with --ack-no-transcript only after the "
            "human's explicit second confirmation of the downgraded status VERIFIED_BY_HUMAN_NO_TRANSCRIPT_DIGEST.",
        )

    agent = agent_provenance(environ, data, opts.level, state.profile, opts.model)
    message = build_message(
        state,
        status,
        opts.timestamp or _utc_now(),
        digest,
        nbytes,
        opts.tradeoffs,
        opts.risks,
        opts.email,
        agent,
        opts.summary,
        harness_id=harness_id,
        conversation_id=conversation_id,
    )

    # Pre-commit structural self-check: a problem here is a bug in this helper.
    problems = verifier.validate_single(verifier.parse_trailers(message))
    if problems:
        raise AttestError(
            EXIT_SELFCHECK,
            "the helper produced a message the verifier rejects before committing — this is a bug in attest.py, "
            "not in your input: " + "; ".join(problems),
        )

    signed = bool(opts.sign and repo.git("config", "user.signingkey", check=False).stdout.strip())
    result = CommitResult(
        attestation_sha=None,
        status=status,
        transcript_digest=digest,
        transcript_bytes=nbytes,
        transcript_path=transcript_path,
        marker_found=marker_found,
        message=message,
        signed=signed,
        dry_run=opts.dry_run,
        warnings=list(state.warnings) + ([marker_warning] if marker_warning else []),
    )
    if opts.dry_run:
        return result

    # Re-check immediately before writing: HEAD recomputed, tree clean.
    if repo.out("rev-parse", "HEAD") != reviewed:
        raise AttestError(EXIT_STALE, f"HEAD moved during commit (expected {reviewed[:7]}); signoff stale.")
    check_clean_tree(repo)

    prior_notes = {reviewed: _note_blob(repo, reviewed), tree: _note_blob(repo, tree)}
    commit_args = ["commit", "--allow-empty", "-q"] + (["-S"] if signed else []) + ["-m", message]
    repo.git(*commit_args)
    attestation_sha = repo.out("rev-parse", "HEAD")

    if repo.out("rev-parse", "HEAD^{tree}") != tree or repo.out("rev-parse", "HEAD~1") != reviewed:
        failures = _rollback_commit(repo)
        raise _rollback_error(
            EXIT_SELFCHECK,
            "post-commit integrity check failed: tree or parent changed; "
            + ("commit removed." if not failures else "commit removal attempted."),
            failures,
        )

    # Dual persistence (§2.5): note on both the reviewed commit and its tree.
    for sha in (reviewed, tree):
        proc = repo.git("notes", f"--ref={NOTES_REF}", "append", "-m", message, sha, check=False)
        if proc.returncode != 0:
            failures = _restore_notes(repo, prior_notes) + _rollback_commit(repo)
            raise _rollback_error(
                EXIT_GIT,
                f"git notes append on {sha[:7]} failed: {proc.stderr.strip()}; "
                + ("commit removed and notes restored." if not failures else "rollback attempted."),
                failures,
            )

    # Post-commit self-check with the sibling verifier, on our own output.
    try:
        ok, lines = verifier.check_head(root, "HEAD")
    except SystemExit as exc:  # the verifier's git() raises SystemExit on git errors
        ok, lines = False, [str(exc)]
    if not ok:
        failures = _restore_notes(repo, prior_notes) + _rollback_commit(repo)
        raise _rollback_error(
            EXIT_SELFCHECK,
            "the verifier rejected the attestation just written; "
            + ("commit and notes removed: " if not failures else "rollback attempted: ")
            + " ".join(lines),
            failures,
        )

    result.attestation_sha = attestation_sha
    result.noted_shas = [reviewed, tree]
    result.verifier = lines
    if opts.push:
        pushed, merged, reason = push_notes(repo)
        result.notes_pushed = pushed
        result.notes_merged_remote = merged
        result.notes_push_reason = reason
    else:
        result.notes_push_reason = "skipped (--no-push)"
    return result


# --- CLI ---------------------------------------------------------------------


def _print_prepare(state: PrepareState) -> None:
    p = state.profile
    print(f"reviewed commit: {state.reviewed_commit_sha}")
    print(f"base (merge-base with {state.reference}): {state.base_sha}")
    print(f"tree: {state.tree_sha}")
    print(f"diff: git diff {state.base_sha}..{state.reviewed_commit_sha}")
    print(f"files ({len(state.name_status)}): {state.shortstat or 'no changes'}")
    for line in state.name_status:
        print(f"  {line}")
    prof = f"profile: {p.profile_id} ({p.source}"
    if p.path:
        prof += f", {p.path}"
    if p.digest:
        prof += f", sha256:{p.digest}"
    print(prof + ")")
    print(f"science signals: {', '.join(state.science_signals) or 'none'}")
    print(
        f"transcript: harness={state.harness_id} conversation={state.conversation_id} "
        f"available={'yes' if state.transcript_available else 'no'}"
        + (f" path={state.transcript_path}" if state.transcript_path else "")
    )
    h = state.hints
    triggers = ", ".join(f"{k} [{', '.join(v)}]" for k, v in h["tier2_triggers"].items()) or "none"
    print(
        f"intensity hints (informative): changed_files={h['changed_files']} executable_files={h['executable_files']} "
        f"executable_lines_changed={h['executable_lines_changed']} tier2_triggers={triggers}"
    )
    print("approval marker — after the human's explicit approval, emit this line verbatim as its own paragraph:")
    print(state.marker)
    for w in state.warnings:
        print(f"warning: {w}", file=sys.stderr)


def _print_commit(result: CommitResult) -> None:
    if result.dry_run:
        print(result.message)
        print()
        print("dry run: nothing committed. Proposed trailers above.")
    else:
        print(f"attestation commit: {result.attestation_sha}")
    print(f"status: {result.status}")
    print(f"transcript digest: {result.transcript_digest} ({result.transcript_bytes} bytes)")
    if result.transcript_path:
        print(f"transcript: {result.transcript_path}")
    if result.transcript_digest == UNAVAILABLE:
        marker = "not applicable (no transcript)"
    elif result.marker_found:
        marker = "found"
    else:
        marker = "not yet in the transcript (dry run; required at commit)"
    print(f"approval marker: {marker}")
    print(f"signed: {'yes' if result.signed else 'no'}")
    if not result.dry_run:
        print(f"notes: {NOTES_REF} on {result.noted_shas[0][:7]} (commit) and {result.noted_shas[1][:7]} (tree)")
        pushed = "yes" if result.notes_pushed else f"no ({result.notes_push_reason})"
        print(f"notes pushed: {pushed}")
        for line in result.verifier:
            print(f"verifier: {line}")
    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="attest.py", description="GSA producer mechanics for /git-signoff.")
    p.add_argument("--version", action="version", version=f"attest.py {VERSION} (GSA {SPEC_VERSION})")
    sub = p.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prepare", help="resolve SHAs, diff summary, profile, signals, hints, marker")
    prep.add_argument("--reference", help="base branch or commit (default: HEAD@{upstream}, else main/master)")
    prep.add_argument("--json", action="store_true", help="print one JSON object on stdout")

    mark = sub.add_parser("marker", help="reprint the approval marker for HEAD")
    mark.add_argument("--reference", help=argparse.SUPPRESS)

    com = sub.add_parser("commit", help="write the attestation commit and notes")
    com.add_argument("--email", required=True, help="Signoff-Verified-By, confirmed by the human")
    com.add_argument("--level", required=True, choices=LEVELS, help="interview level actually run")
    com.add_argument("--tradeoff", action="append", default=[], help="acknowledged trade-off (repeatable)")
    com.add_argument("--risk", action="append", default=[], help="acknowledged risk (repeatable)")
    com.add_argument("--summary", help="optional review summary paragraph")
    com.add_argument("--model", help="self-reported model id, used only when no deterministic source has one")
    com.add_argument("--reference", help="base branch or commit (default: HEAD@{upstream}, else main/master)")
    com.add_argument("--ack-no-transcript", action="store_true", help="human confirmed the downgraded status")
    com.add_argument("--no-sign", action="store_true", help="do not pass -S even if user.signingkey is set")
    com.add_argument("--dry-run", action="store_true", help="print the message; commit nothing")
    com.add_argument("--no-push", action="store_true", help="do not push refs/notes/signoff")
    com.add_argument("--json", action="store_true", help="print one JSON object on stdout")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    as_json = getattr(args, "json", False)
    try:
        root = repo_root()
        if args.command == "prepare":
            state = prepare(root, args.reference)
            if as_json:
                print(json.dumps(state.to_json(), indent=2))
                for w in state.warnings:
                    print(f"warning: {w}", file=sys.stderr)
            else:
                _print_prepare(state)
            return EXIT_OK
        if args.command == "marker":
            state = prepare(root, args.reference)
            print(state.marker)
            return EXIT_OK
        opts = CommitOptions(
            email=args.email,
            level=args.level,
            tradeoffs=args.tradeoff,
            risks=args.risk,
            summary=args.summary,
            model=args.model,
            reference=args.reference,
            ack_no_transcript=args.ack_no_transcript,
            sign=not args.no_sign,
            dry_run=args.dry_run,
            push=not args.no_push,
        )
        result = commit(root, opts)
        if as_json:
            print(json.dumps(result.to_json(), indent=2))
            for w in result.warnings:
                print(f"warning: {w}", file=sys.stderr)
        else:
            _print_commit(result)
        return EXIT_OK
    except AttestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if as_json:
            print(json.dumps({"ok": False, "command": args.command, "exit_code": exc.code, "error": str(exc)}, indent=2))
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
