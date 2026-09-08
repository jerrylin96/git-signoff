"""git_signoff: Python reference implementation of the GSA producer mechanics.

Not a distribution. The adoption path is the curl-run init.py plus the
vendored skill folder (both standard-library only); this package exists so
the producer rules have an executable, unit-tested form — status derivation
from transcript availability (gsa-core §2.2), single-line trailer values
(§2.3), git-notes dual persistence with the cat_sort_uniq merge (§2.5), and
the TranscriptProvider adapters (§3). The Socratic interview stays in the
agent prompt. An MCP wrapper over these functions shipped from 2026-08 to
2026-09-08 and was removed for lack of demand (docs/productionization.md);
the interface it exposed is still specified, informatively, in gsa-core §4.
"""

from git_signoff.adapters import (
    AntigravityAdapter,
    ClaudeCodeAdapter,
    CodexAdapter,
    GenericFileAdapter,
    TranscriptProvider,
    resolve_adapter,
)
from git_signoff.profile import (
    ProfileOverrideError,
    ProfileResolution,
    detect_science_signals,
    profile_block_digest,
    resolve_profile,
)
from git_signoff.core import (
    CommitResult,
    GitRepo,
    PrepareState,
    SignoffError,
    SignoffIntegrityError,
    SignoffPushError,
    SignoffStaleError,
    SignoffTranscriptError,
    commit,
    parse_trailers,
    prepare,
    push_notes,
)

__version__ = "0.4.0"

__all__ = [
    "AntigravityAdapter",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "CommitResult",
    "GenericFileAdapter",
    "GitRepo",
    "PrepareState",
    "ProfileOverrideError",
    "ProfileResolution",
    "SignoffError",
    "SignoffIntegrityError",
    "SignoffPushError",
    "SignoffStaleError",
    "SignoffTranscriptError",
    "TranscriptProvider",
    "commit",
    "detect_science_signals",
    "parse_trailers",
    "prepare",
    "profile_block_digest",
    "push_notes",
    "resolve_adapter",
    "resolve_profile",
]
