"""TranscriptProvider adapters in skills/git-signoff/attest.py (gsa-core §3)."""

import os

from _attest_loader import attest
from helpers import git, init_repo

AntigravityAdapter = attest.AntigravityAdapter
ClaudeCodeAdapter = attest.ClaudeCodeAdapter
CodexAdapter = attest.CodexAdapter
GenericFileAdapter = attest.GenericFileAdapter
resolve_adapter = attest.resolve_adapter


def _slug(p):
    # Claude Code's project-directory rule; locked by value in
    # test_claude_slug_replaces_every_non_alphanumeric_character below.
    return attest._slug(str(p))


def _plant_claude_transcript(home, root, sid, data=b'{"role":"user"}\n'):
    d = home / ".claude" / "projects" / _slug(root)
    d.mkdir(parents=True)
    (d / f"{sid}.jsonl").write_bytes(data)
    return data


def test_resolution_order_override_wins(tmp_path):
    f = tmp_path / "t.log"
    f.write_bytes(b"hello")
    env = {
        "GIT_SIGNOFF_TRANSCRIPT_FILE": str(f),
        "ANTIGRAVITY_CONVERSATION_ID": "ag-1",
        "CLAUDE_CODE_SESSION_ID": "cc-1",
    }
    a = resolve_adapter(env)
    assert isinstance(a, GenericFileAdapter)
    assert a.harness_id == "generic-file"
    assert a.resolve_conversation_id() == "ag-1"
    assert a.fetch_transcript_bytes() == b"hello"


def test_resolution_order_antigravity_over_claude(tmp_path):
    env = {"ANTIGRAVITY_CONVERSATION_ID": "ag-1", "CLAUDE_CODE_SESSION_ID": "cc-1"}
    a = resolve_adapter(env, home=str(tmp_path))
    assert isinstance(a, AntigravityAdapter)
    assert a.harness_id == "antigravity-cli"


def test_resolution_claude_then_none(tmp_path):
    a = resolve_adapter({"CLAUDE_CODE_SESSION_ID": "cc-1"}, cwd=str(tmp_path), home=str(tmp_path))
    assert isinstance(a, ClaudeCodeAdapter)
    assert a.harness_id == "claude-code"
    assert resolve_adapter({}) is None
    assert resolve_adapter({"GIT_SIGNOFF_TRANSCRIPT_FILE": "  "}) is None  # whitespace stripped


def test_generic_missing_file_degrades_to_none(tmp_path):
    a = GenericFileAdapter(str(tmp_path / "nope.log"))
    assert a.fetch_transcript_bytes() is None
    assert a.resolve_conversation_id() is None


def test_antigravity_transcript_path(tmp_path):
    cid = "conv-42"
    p = tmp_path / ".gemini" / "antigravity-cli" / "brain" / cid / ".system_generated" / "logs"
    p.mkdir(parents=True)
    (p / "transcript.jsonl").write_bytes(b"data")
    a = AntigravityAdapter(cid, home=str(tmp_path))
    assert a.fetch_transcript_bytes() == b"data"
    assert AntigravityAdapter("missing", home=str(tmp_path)).fetch_transcript_bytes() is None


def test_claude_primary_cwd_slug_hit(tmp_path):
    home, cwd = tmp_path / "home", tmp_path / "proj"
    cwd.mkdir()
    data = _plant_claude_transcript(home, cwd, "sid-1")
    a = ClaudeCodeAdapter("sid-1", cwd=str(cwd), home=str(home))
    assert a.fetch_transcript_bytes() == data


def test_claude_linked_worktree_fallback(tmp_path):
    """cwd slug misses inside a linked worktree; --git-common-dir resolves primary root."""
    home = tmp_path / "home"
    main = init_repo(tmp_path / "main")
    git(main, "commit", "-q", "--allow-empty", "-m", "base")
    wt = tmp_path / "wt"
    git(main, "worktree", "add", "-q", str(wt))
    data = _plant_claude_transcript(home, main, "sid-2")
    a = ClaudeCodeAdapter("sid-2", cwd=str(wt), home=str(home))
    assert a.fetch_transcript_bytes() == data


def test_claude_relative_git_common_dir_resolved_against_repo_cwd(tmp_path):
    """From a main-worktree subdirectory git returns a relative path (e.g. ../.git);
    it must be joined against the adapter's injected cwd, not the process cwd."""
    home = tmp_path / "home"
    main = init_repo(tmp_path / "main")
    git(main, "commit", "-q", "--allow-empty", "-m", "base")
    sub = main / "sub"
    sub.mkdir()
    data = _plant_claude_transcript(home, main, "sid-3")
    assert os.getcwd() != str(sub)  # process cwd differs from injected cwd
    a = ClaudeCodeAdapter("sid-3", cwd=str(sub), home=str(home))
    assert a.fetch_transcript_bytes() == data


def test_claude_slug_replaces_every_non_alphanumeric_character():
    """Claude Code names ~/.claude/projects/<slug> by replacing every character
    outside [A-Za-z0-9] with "-". Replacing only "/" (the rule until init-v11)
    missed any repository path with an underscore, a dot or a space, and the
    interview was steered toward --ack-no-transcript for a transcript that
    existed. Expected values are literals, not the function under test."""
    assert attest._slug("/work/bu/ea_barnes_bu/jlin404/project-rewind/dev-clean") == (
        "-work-bu-ea-barnes-bu-jlin404-project-rewind-dev-clean"
    )
    assert attest._slug("/home/u/my.repo v2") == "-home-u-my-repo-v2"
    assert attest._slug("/home/user/plain") == "-home-user-plain"


def test_claude_transcript_found_for_path_with_underscore_and_dot(tmp_path):
    home, cwd = tmp_path / "home", tmp_path / "ea_barnes_bu" / "v0.5"
    cwd.mkdir(parents=True)
    data = _plant_claude_transcript(home, cwd, "sid-5")
    a = ClaudeCodeAdapter("sid-5", cwd=str(cwd), home=str(home))
    assert a.describe_path() == str(home / ".claude" / "projects" / attest._slug(str(cwd)) / "sid-5.jsonl")
    assert a.fetch_transcript_bytes() == data
    # The slash-only directory the old rule looked in is not where Claude Code writes.
    assert not (home / ".claude" / "projects" / str(cwd).replace("/", "-")).exists()


def test_claude_missing_transcript_names_the_exact_slug_path(tmp_path):
    home, cwd = tmp_path / "home", tmp_path / "x_y"
    cwd.mkdir()
    a = ClaudeCodeAdapter("sid-7", cwd=str(cwd), home=str(home))
    assert a.describe_path() == str(home / ".claude" / "projects" / attest._slug(str(cwd)) / "sid-7.jsonl")
    assert a.fetch_transcript_bytes() is None


def test_claude_long_slug_matched_by_prefix(tmp_path):
    """A slug over 200 characters is truncated and suffixed by Claude Code (no
    suffix before 2.1.x, a base-36 hash since); the adapter matches it by
    prefix, and an untruncated directory wins when both exist."""
    home = tmp_path / "home"
    # Aim for a slug just over the cap but under the 255-byte file-name limit,
    # so the untruncated directory (what an older Claude Code wrote) can exist.
    pad = max(1, 215 - len(attest._slug(str(tmp_path))) - 1)
    cwd = tmp_path / ("p" * pad)
    cwd.mkdir()
    slug = attest._slug(str(cwd))
    assert len(slug) > attest._CLAUDE_SLUG_MAX
    truncated = home / ".claude" / "projects" / (slug[: attest._CLAUDE_SLUG_MAX] + "-1k2j3h")
    truncated.mkdir(parents=True)
    (truncated / "sid-6.jsonl").write_bytes(b"long")
    a = ClaudeCodeAdapter("sid-6", cwd=str(cwd), home=str(home))
    assert a.fetch_transcript_bytes() == b"long"
    if len(slug) <= 255:  # a longer tmp_path (macOS) makes the exact name uncreatable; the prefix match above still holds
        exact = home / ".claude" / "projects" / slug
        exact.mkdir(parents=True)
        (exact / "sid-6.jsonl").write_bytes(b"exact")
        assert a.fetch_transcript_bytes() == b"exact"
    # Another session's file under a sibling prefix directory is never picked up.
    other = home / ".claude" / "projects" / (slug[: attest._CLAUDE_SLUG_MAX] + "-zzzzzz")
    other.mkdir(parents=True)
    (other / "sid-other.jsonl").write_bytes(b"not mine")
    assert ClaudeCodeAdapter("sid-8", cwd=str(cwd), home=str(home)).fetch_transcript_bytes() is None


def _plant_codex_rollout(base, day, ts, sid, data):
    d = base / "sessions" / "2026" / "08" / day
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"rollout-{ts}-{sid}.jsonl"
    f.write_bytes(data)
    return f


def test_codex_rollout_discovery(tmp_path):
    home = tmp_path / "home"
    _plant_codex_rollout(home / ".codex", "05", "2026-08-05T10-00-00", "sid-9", b"codex-data")
    a = CodexAdapter("sid-9", home=str(home))
    assert a.harness_id == "codex-cli"
    assert a.resolve_conversation_id() == "sid-9"
    assert a.fetch_transcript_bytes() == b"codex-data"
    assert CodexAdapter("missing", home=str(home)).fetch_transcript_bytes() is None


def test_codex_home_override_and_newest_match(tmp_path):
    codex_home = tmp_path / "custom-codex"
    old = _plant_codex_rollout(codex_home, "04", "2026-08-04T09-00-00", "sid-9", b"old")
    new = _plant_codex_rollout(codex_home, "05", "2026-08-05T10-00-00", "sid-9", b"new")
    os.utime(old, (1, 1))
    os.utime(new, (2, 2))
    a = CodexAdapter("sid-9", codex_home=str(codex_home), home=str(tmp_path / "unused-home"))
    assert a.fetch_transcript_bytes() == b"new"


def test_resolution_codex_after_claude(tmp_path):
    env = {"CLAUDE_CODE_SESSION_ID": "cc-1", "CODEX_SESSION_ID": "cx-1"}
    assert isinstance(resolve_adapter(env, cwd=str(tmp_path), home=str(tmp_path)), ClaudeCodeAdapter)
    a = resolve_adapter({"CODEX_SESSION_ID": "cx-1", "CODEX_HOME": str(tmp_path / "ch")}, home=str(tmp_path))
    assert isinstance(a, CodexAdapter)
    assert a.sessions_dir == str(tmp_path / "ch" / "sessions")


def test_claude_outside_git_repo_degrades_to_none(tmp_path):
    cwd = tmp_path / "plain"
    cwd.mkdir()
    a = ClaudeCodeAdapter("sid-4", cwd=str(cwd), home=str(tmp_path / "home"))
    assert a.fetch_transcript_bytes() is None


def test_codex_adapter_rollout_pattern_matching(tmp_path):
    home = tmp_path / "home"
    _plant_codex_rollout(home / ".codex", "05", "2026-08-05T10-00-00", "my-session", b"matched")
    a = CodexAdapter("my-session", home=str(home))
    assert a.fetch_transcript_bytes() == b"matched"


def test_codex_adapter_rejects_similar_suffix(tmp_path):
    home = tmp_path / "home"
    codex_home = home / ".codex"
    d = codex_home / "sessions" / "2026" / "08" / "05"
    d.mkdir(parents=True, exist_ok=True)
    (d / "rollout-2026-08-05T10-00-00-my-session-extra.jsonl").write_bytes(b"extra-suffix")
    (d / "2026-08-05T10-00-00-my-session.jsonl").write_bytes(b"no-prefix")
    a = CodexAdapter("my-session", home=str(home))
    assert a.fetch_transcript_bytes() is None


def test_codex_adapter_escaped_metacharacters(tmp_path):
    home = tmp_path / "home"
    codex_home = home / ".codex"
    d = codex_home / "sessions" / "2026" / "08" / "05"
    d.mkdir(parents=True, exist_ok=True)
    sid = "sess[123]"
    (d / f"rollout-2026-08-05T10-00-00-{sid}.jsonl").write_bytes(b"literal-brackets")
    (d / "rollout-2026-08-05T10-00-00-sess1.jsonl").write_bytes(b"globbed-match")
    a = CodexAdapter(sid, home=str(home))
    assert a.fetch_transcript_bytes() == b"literal-brackets"


def test_codex_adapter_equal_mtime_tie_breaking(tmp_path):
    home = tmp_path / "home"
    codex_home = home / ".codex"
    f_a = _plant_codex_rollout(codex_home, "05", "2026-08-05T10-00-00-a", "sid-tie", b"alpha")
    f_b = _plant_codex_rollout(codex_home, "05", "2026-08-05T10-00-00-b", "sid-tie", b"beta")
    os.utime(f_a, (100, 100))
    os.utime(f_b, (100, 100))
    a = CodexAdapter("sid-tie", home=str(home))
    assert a.fetch_transcript_bytes() == b"beta"


def test_codex_adapter_missing_rollout(tmp_path):
    home = tmp_path / "home"
    a = CodexAdapter("nonexistent", home=str(home))
    assert a.fetch_transcript_bytes() is None
