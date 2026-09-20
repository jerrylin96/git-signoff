"""Learning is read-only; only actual session control messages forbid promotion."""

import json
from pathlib import Path

import pytest
from _attest_loader import attest
from helpers import commit_file, git, init_repo


def _record(repo):
    return Path(attest.record_path(attest.GitRepo(str(repo))))


def _adapter(tmp_path, sid="learning-session"):
    path = tmp_path / "transcript.jsonl"
    path.write_text("")
    return attest.GenericFileAdapter(str(path), sid)


def _event(adapter, shape="normalized"):
    marker = f"GSA-PRACTICE {attest.practice_session_key(adapter)} 2026-09-19T12:00:00Z"
    if shape == "claude":
        event = {"type": "assistant", "sessionId": adapter.resolve_conversation_id(),
                 "message": {"role": "assistant", "content": [{"type": "text", "text": marker}]}}
    elif shape == "codex":
        event = {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                 "content": [{"type": "output_text", "text": marker}]}}
    else:
        event = {"role": "assistant", "content": marker}
    return marker, (json.dumps(event) + "\n").encode()


def _approval(repo):
    return f"GSA-APPROVAL {git(repo, 'rev-parse', 'HEAD').stdout.strip()} 2026-09-19T12:00:01Z\n".encode()


@pytest.mark.parametrize("mode", ["explain", "practice"])
def test_learning_captures_dirty_content_without_writing_git_state(scratch_repo, tmp_path, mode):
    repo = scratch_repo
    adapter = _adapter(tmp_path)
    attest.prepare(str(repo), "main", env={})
    old_record = _record(repo).read_bytes()
    (repo / "feat.txt").write_text("staged\n")
    git(repo, "add", "feat.txt")
    (repo / "feat.txt").write_text("working\n")
    (repo / "untracked.txt").write_text("excluded")
    index = repo / git(repo, "rev-parse", "--git-path", "index").stdout.strip()
    old_index = index.read_bytes()
    old_refs = git(repo, "show-ref").stdout
    state = attest.prepare(str(repo), mode=mode, adapter=adapter, env={})
    data = state.to_json()
    assert data["mode"] == mode and data["state_kind"] == "working-tree"
    assert "+working" in data["diff"] and "excluded" not in data["diff"]
    assert data["staged_differs"] and data["untracked_files"] == ["untracked.txt"]
    assert data["reviewed_commit_sha"] is None and data["tree_sha"] is None
    assert data["context_head_sha"] == git(repo, "rev-parse", "HEAD").stdout.strip()
    assert "marker" not in data and "record" not in data and "GSA-APPROVAL" not in json.dumps(data)
    assert ("practice_marker" in data) == (mode == "practice")
    assert _record(repo).read_bytes() == old_record and index.read_bytes() == old_index
    assert git(repo, "show-ref").stdout == old_refs
    with pytest.raises(attest.AttestError, match="cannot create"):
        attest.write_record(attest.GitRepo(str(repo)), state)


@pytest.mark.parametrize("configured", [False, True])
def test_dirty_main_in_a_local_only_repo_is_a_learning_range(tmp_path, configured):
    repo = init_repo(tmp_path / "repo")
    head = commit_file(repo, "app.py", "value = 1\n", "base")
    if configured:
        (repo / ".git-signoff").mkdir()
        (repo / ".git-signoff/config.json").write_text('{"integration_branch":"main"}')
    (repo / "app.py").write_text("import numpy as np\nvalue = 2\n")
    state = attest.prepare(str(repo), mode="practice", env={})
    assert state.base_sha == head and "+value = 2" in state.diff
    assert "scientific-imports" in state.science_signals
    assert state.hints["components"] == ["app.py"]
    assert "scientific-computation" in state.hints["tier2_triggers"]
    assert not _record(repo).exists()


def test_staged_change_reverted_in_working_files_is_reported(tmp_path):
    repo = init_repo(tmp_path / "repo")
    commit_file(repo, "app.py", "old\n", "base")
    (repo / "app.py").write_text("new\n")
    git(repo, "add", "app.py")
    (repo / "app.py").write_text("old\n")
    state = attest.prepare(str(repo), mode="explain", env={})
    assert state.to_json()["empty"] and state.staged_differs
    assert any("staged snapshot" in w for w in state.warnings)
    assert any("No differences" in w for w in state.warnings)


def test_snapshot_checks_drift_without_creating_a_record(scratch_repo):
    root = str(scratch_repo)
    state = attest.prepare(root, "main", mode="explain", env={})
    again = attest.prepare(root, "main", mode="explain", check_snapshot=state.snapshot_id, env={})
    assert again.snapshot_id == state.snapshot_id
    (scratch_repo / "feat.txt").write_text("changed during walkthrough\n")
    with pytest.raises(attest.AttestError, match="scope changed") as exc:
        attest.prepare(root, "main", mode="explain", check_snapshot=state.snapshot_id, env={})
    assert exc.value.code == 3 and not _record(scratch_repo).exists()


def test_learning_accepts_attested_tip_but_real_prepare_still_refuses(scratch_repo):
    git(scratch_repo, "commit", "-q", "--allow-empty", "-m", "[SIGNOFF abc1234]: previous interview")
    state = attest.prepare(str(scratch_repo), "main", mode="practice", env={})
    assert state.diff and any("already an attestation" in w for w in state.warnings)
    with pytest.raises(attest.AttestError, match="already an attestation"):
        attest.prepare(str(scratch_repo), "main", env={})


def test_learning_target_uses_remote_content_not_dirty_checkout(scratch_repo, tmp_path):
    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(origin, "init", "--bare", "-q")
    git(scratch_repo, "remote", "add", "origin", str(origin))
    git(scratch_repo, "push", "-q", "origin", "main", "feature")
    target = git(scratch_repo, "rev-parse", "feature").stdout.strip()
    git(scratch_repo, "checkout", "-q", "main")
    (scratch_repo / "base.txt").write_text("local dirty state\n")
    state = attest.prepare(str(scratch_repo), "origin/main", target="feature", mode="practice", env={})
    data = state.to_json()
    assert data["state_kind"] == "commit" and data["reviewed_commit_sha"] == target
    assert "+feature" in data["diff"] and "local dirty" not in data["diff"]
    assert (scratch_repo / "base.txt").read_text() == "local dirty state\n"
    assert not _record(scratch_repo).exists()


def test_learning_profile_override_errors_are_not_silenced(scratch_repo):
    with pytest.raises(attest.AttestError) as exc:
        attest.prepare(str(scratch_repo), mode="practice", env={"GIT_SIGNOFF_PROFILE_FILE": "/missing-profile"})
    assert exc.value.code == 5


def test_learning_cli_modes_conflict_and_snapshot_flag_is_learning_only(scratch_repo, monkeypatch):
    monkeypatch.chdir(scratch_repo)
    with pytest.raises(SystemExit) as exc:
        attest.main(["prepare", "--practice", "--explain"])
    assert exc.value.code == 2
    assert attest.main(["prepare", "--check-snapshot", "a" * 64]) == 2
    assert not _record(scratch_repo).exists()


@pytest.mark.parametrize("mode", ["explain", "practice"])
def test_learning_cli_has_no_approval_protocol(scratch_repo, tmp_path, monkeypatch, capsys, mode):
    adapter = _adapter(tmp_path)
    monkeypatch.chdir(scratch_repo)
    monkeypatch.setenv("GIT_SIGNOFF_TRANSCRIPT_FILE", adapter.path)
    assert attest.main(["prepare", f"--{mode}", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["mode"] == mode and "GSA-APPROVAL" not in json.dumps(data)
    assert attest.main(["prepare", f"--{mode}"]) == 0
    output = capsys.readouterr().out
    assert "GSA-APPROVAL" not in output and "prepared state recorded" not in output
    assert not _record(scratch_repo).exists()
    assert attest.main(["marker"]) == 3


def test_prepare_output_in_a_tool_result_does_not_itself_start_practice(scratch_repo, tmp_path):
    adapter = _adapter(tmp_path)
    state = attest.prepare(str(scratch_repo), mode="practice", adapter=adapter, env={})
    result = json.dumps(state.to_json())
    for body in (result, json.dumps({"role": "tool", "content": result})):
        assert attest.find_practice_marker(body.encode(), adapter) is None
    live = json.dumps({"role": "assistant", "content": state.practice_marker})
    assert attest.find_practice_marker(live.encode(), adapter)


def test_capture_refuses_files_changing_while_it_collects_stats(scratch_repo, monkeypatch):
    original = attest.GitRepo.git
    changed = False

    def racing_git(self, *args, **kwargs):
        nonlocal changed
        result = original(self, *args, **kwargs)
        if not changed and "--no-optional-locks" in args and result.stdout.startswith("diff --git"):
            changed = True
            (scratch_repo / "feat.txt").write_text("edited concurrently\n")
        return result

    monkeypatch.setattr(attest.GitRepo, "git", racing_git)
    with pytest.raises(attest.AttestError, match="changed while capturing") as exc:
        attest.prepare(str(scratch_repo), mode="explain", env={})
    assert exc.value.code == 3 and not _record(scratch_repo).exists()


def test_bad_reference_is_an_error_not_an_empty_learning_scope(scratch_repo):
    with pytest.raises(attest.AttestError, match="does not resolve") as exc:
        attest.prepare(str(scratch_repo), "missing-reference", mode="practice", env={})
    assert exc.value.code == 2 and not _record(scratch_repo).exists()


@pytest.mark.parametrize("shape", ["normalized", "claude", "codex"])
def test_actual_practice_event_prevents_commit_even_outside_approval_window(scratch_repo, tmp_path, shape):
    adapter = _adapter(tmp_path)
    marker, event = _event(adapter, shape)
    attest.prepare(str(scratch_repo), "main", env={})
    old_head = git(scratch_repo, "rev-parse", "HEAD").stdout
    old_record = _record(scratch_repo).read_bytes()
    Path(adapter.path).write_bytes(event + b"padding\n" * 10000 + _approval(scratch_repo))
    for dry_run in (True, False):
        with pytest.raises(attest.AttestError, match="Practice started") as exc:
            attest.commit(str(scratch_repo), attest.CommitOptions(email="tester@example.com", level="standard", dry_run=dry_run, push=False, sign=False), adapter=adapter, env={})
        assert exc.value.code == 3 and marker in str(exc.value) and "byte 0" in str(exc.value)
    assert git(scratch_repo, "rev-parse", "HEAD").stdout == old_head
    assert not git(scratch_repo, "for-each-ref", "--format=%(refname)", "refs/notes").stdout
    assert _record(scratch_repo).read_bytes() == old_record
    prepared = attest.prepare(str(scratch_repo), "main", adapter=adapter, env={})
    assert any("Practice started" in w for w in prepared.warnings)


def test_quoted_markers_tool_results_and_foreign_sessions_are_not_practice(tmp_path):
    adapter = _adapter(tmp_path)
    marker, _ = _event(adapter)
    examples = [
        {"role": "user", "content": marker},
        {"role": "tool", "content": marker},
        {"role": "assistant", "content": f"Example: {marker}"},
        {"role": "assistant", "content": f"```text\n{marker}\n```"},
        {"role": "assistant", "content": json.dumps({"role": "assistant", "content": marker})},
        {"type": "function_call_output", "role": "assistant", "content": marker},
        {"role": "assistant", "content": marker, "session_id": "a-different-session"},
        {"type": "response_item", "payload": {"type": "function_call_output", "role": "assistant", "content": marker}},
    ]
    for example in examples:
        assert attest.find_practice_marker(json.dumps(example).encode(), adapter) is None
    _, foreign = _event(attest.GenericFileAdapter(adapter.path, "foreign-session"))
    assert attest.find_practice_marker(foreign, adapter) is None
    assert attest.find_practice_marker(marker.encode(), adapter) is None  # documented opaque-text limitation


def test_generic_path_binding_and_new_session_identity(tmp_path):
    adapter = _adapter(tmp_path, sid=None)
    _, event = _event(adapter)
    assert attest.find_practice_marker(event, adapter)
    other = attest.GenericFileAdapter(str(tmp_path / "other.jsonl"))
    assert attest.find_practice_marker(event, other) is None
    same_session = attest.GenericFileAdapter(other.path, "learning-session")
    assert attest.practice_session_key(same_session) == attest.practice_session_key(_adapter(tmp_path))


def test_practice_event_in_retried_snapshot_is_checked(scratch_repo, tmp_path, monkeypatch):
    adapter = _adapter(tmp_path)
    _, event = _event(adapter)
    attest.prepare(str(scratch_repo), "main", env={})
    reads = iter([b"not flushed yet\n", event + _approval(scratch_repo)])
    monkeypatch.setattr(adapter, "fetch_transcript_bytes", lambda: next(reads))
    monkeypatch.setattr(attest, "MARKER_RETRY_DELAY", 0)
    with pytest.raises(attest.AttestError, match="Practice started"):
        attest.commit(str(scratch_repo), attest.CommitOptions(email="tester@example.com", level="standard", push=False, sign=False), adapter=adapter, env={})
    assert not git(scratch_repo, "for-each-ref", "--format=%(refname)", "refs/notes").stdout


def test_explanation_then_fresh_real_prepare_can_attest(scratch_repo, tmp_path):
    adapter = _adapter(tmp_path)
    state = attest.prepare(str(scratch_repo), "main", mode="explain", adapter=adapter, env={})
    assert "practice_marker" not in state.to_json() and not _record(scratch_repo).exists()
    Path(adapter.path).write_text(json.dumps({"role": "assistant", "content": "Here is how the change works."}) + "\n")
    real = attest.prepare(str(scratch_repo), "main", adapter=adapter, env={})
    assert real.mode == "attest" and _record(scratch_repo).exists()
    with open(adapter.path, "ab") as stream:
        stream.write(_approval(scratch_repo))
    result = attest.commit(str(scratch_repo), attest.CommitOptions(email="tester@example.com", level="standard", push=False, sign=False), adapter=adapter, env={})
    assert result.attestation_sha and result.status == attest.STATUS_VERIFIED


def test_no_transcript_keeps_the_documented_prompt_only_boundary(scratch_repo, tmp_path):
    adapter = attest.GenericFileAdapter(str(tmp_path / "not-readable.jsonl"))
    practice = attest.prepare(str(scratch_repo), "main", mode="practice", adapter=adapter, env={})
    assert any("opaque or unavailable" in w for w in practice.warnings)
    attest.prepare(str(scratch_repo), "main", env={})
    result = attest.commit(str(scratch_repo), attest.CommitOptions(email="tester@example.com", level="standard", ack_no_transcript=True, push=False, sign=False), adapter=adapter, env={})
    assert result.status == attest.STATUS_NO_DIGEST
