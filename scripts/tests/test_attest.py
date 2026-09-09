"""Tests for skills/git-signoff/attest.py — the deterministic GSA producer.

Everything runs against scratch repositories (helpers.py) with attest.py loaded
by path, the way the vendored folder is used. The CLI is exercised in-process
through attest.main(argv) so exit codes and stdout/stderr are asserted exactly.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest
from _attest_loader import SKILL_DIR, attest, verify_signoff
from helpers import commit_file, git, init_repo

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(autouse=True)
def _fast_marker_retry(monkeypatch):
    monkeypatch.setattr(attest, "MARKER_RETRY_DELAY", 0)


def _head(repo):
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def _tree(repo):
    return git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()


def _transcript(tmp_path, repo, extra=b"", name="transcript.jsonl", with_marker=True, sha=None):
    """Transcript file whose tail carries the approval marker for HEAD (or `sha`)."""
    body = b'{"role":"user","content":"hi"}\n{"role":"assistant","model":"model-from-transcript","content":"ok"}\n'
    if with_marker:
        body += f"GSA-APPROVAL {sha or _head(repo)} 2026-09-09T00:00:00Z\n".encode()
    body += extra
    f = tmp_path / name
    f.write_bytes(body)
    return f


def run(monkeypatch, capsys, cwd, *argv, env=None):
    """Run the CLI in-process from `cwd`; returns (exit_code, stdout, stderr)."""
    monkeypatch.chdir(cwd)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    try:
        code = attest.main(list(argv))
    except SystemExit as exc:  # argparse errors
        code = exc.code
    out, err = capsys.readouterr()
    return code, out, err


def run_json(monkeypatch, capsys, cwd, *argv, env=None):
    code, out, err = run(monkeypatch, capsys, cwd, *argv, "--json", env=env)
    return code, json.loads(out), err


# --- prepare ------------------------------------------------------------------


def test_prepare_resolves_shas_diff_profile_and_marker(scratch_repo, monkeypatch, capsys):
    code, data, err = run_json(monkeypatch, capsys, scratch_repo, "prepare", "--reference", "main")
    assert code == 0, err
    assert data["ok"] is True and data["command"] == "prepare"
    assert data["reviewed_commit_sha"] == _head(scratch_repo)
    assert data["base_sha"] == git(scratch_repo, "rev-parse", "main").stdout.strip()
    assert data["tree_sha"] == _tree(scratch_repo)
    assert data["reference"] == "main"
    assert data["name_status"] == ["A\tfeat.txt"]
    assert "1 file changed" in data["shortstat"]
    assert data["diff_command"] == f"git diff {data['base_sha']}..{data['reviewed_commit_sha']}"
    assert data["profile"] == {
        "source": "embedded-default", "path": None, "id": "software-general", "digest": None, "fallback_reason": None,
    }
    assert data["science_signals"] == []
    assert data["transcript"]["harness_id"] == "unknown"
    assert data["transcript"]["available"] is False
    assert data["marker"] == f"GSA-APPROVAL {data['reviewed_commit_sha']} " + data["marker"].split()[-1]
    assert attest.MARKER_RE.search(data["marker"].encode())
    assert data["hints"]["changed_files"] == 1
    assert data["hints"]["executable_lines_changed"] == 0  # feat.txt is documentation
    assert any("--ack-no-transcript" in w for w in data["warnings"])


def test_prepare_human_output_ends_with_marker_line(scratch_repo, monkeypatch, capsys):
    code, out, err = run(monkeypatch, capsys, scratch_repo, "prepare", "--reference", "main")
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == f"reviewed commit: {_head(scratch_repo)}"
    assert lines[-1].startswith(f"GSA-APPROVAL {_head(scratch_repo)} ")
    assert "approval marker" in lines[-2]
    assert "warning:" in err and "warning:" not in out  # diagnostics never pollute stdout


def test_marker_command_prints_only_the_marker(scratch_repo, monkeypatch, capsys):
    code, out, _ = run(monkeypatch, capsys, scratch_repo, "marker", "--reference", "main")
    assert code == 0
    assert out.strip().split("\n") == [out.strip()]
    assert out.startswith(f"GSA-APPROVAL {_head(scratch_repo)} ")


def test_prepare_works_from_a_subdirectory(scratch_repo, monkeypatch, capsys):
    sub = scratch_repo / "sub" / "dir"
    sub.mkdir(parents=True)
    commit_file(scratch_repo, "sub/dir/x.py", "x = 1\n", "sub file")
    code, data, _ = run_json(monkeypatch, capsys, sub, "prepare", "--reference", "main")
    assert code == 0
    assert data["reviewed_commit_sha"] == _head(scratch_repo)
    assert data["hints"]["executable_lines_changed"] == 1


def test_prepare_reference_defaults_to_upstream(tmp_path, monkeypatch, capsys):
    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(origin, "init", "-q", "--bare", "-b", "main")
    work = init_repo(tmp_path / "work")
    commit_file(work, "base.txt", "base\n", "base commit")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-q", "-u", "origin", "main")
    git(work, "checkout", "-q", "-b", "feature")
    commit_file(work, "feat.txt", "feature\n", "feature commit")
    git(work, "branch", "-q", "--set-upstream-to=origin/main")
    code, data, err = run_json(monkeypatch, capsys, work, "prepare")
    assert code == 0
    assert data["reference"] == "origin/main"
    assert data["base_sha"] == git(work, "rev-parse", "origin/main").stdout.strip()
    assert not [w for w in data["warnings"] if "assuming base branch" in w]


def test_prepare_reference_falls_back_to_main_with_warning(scratch_repo, monkeypatch, capsys):
    code, data, err = run_json(monkeypatch, capsys, scratch_repo, "prepare")
    assert code == 0
    assert data["reference"] == "main"
    assert any("assuming base branch 'main'" in w for w in data["warnings"])
    assert "assuming base branch 'main'" in err


def test_prepare_reference_falls_back_to_master(tmp_path, monkeypatch, capsys):
    path = init_repo(tmp_path / "repo_master", branch="master")
    commit_file(path, "base.txt", "base\n", "base commit")
    git(path, "checkout", "-q", "-b", "feature")
    commit_file(path, "feat.txt", "feat\n", "feat commit")
    code, data, _ = run_json(monkeypatch, capsys, path, "prepare")
    assert code == 0 and data["reference"] == "master"


def test_prepare_ignores_an_upstream_that_is_the_branch_itself(tmp_path, monkeypatch, capsys):
    """`git push -u origin feature` makes origin/feature the upstream; it contains
    HEAD, so it is an empty range, not a base. prepare must fall back to main."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(origin, "init", "-q", "--bare", "-b", "main")
    work = init_repo(tmp_path / "work")
    commit_file(work, "base.txt", "base\n", "base commit")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-q", "-u", "origin", "main")
    git(work, "checkout", "-q", "-b", "feature")
    commit_file(work, "feat.py", "x = 1\n", "feature commit")
    git(work, "push", "-q", "-u", "origin", "feature")
    assert git(work, "rev-parse", "--abbrev-ref", "HEAD@{upstream}").stdout.strip() == "origin/feature"
    code, data, err = run_json(monkeypatch, capsys, work, "prepare")
    assert code == 0, err
    assert data["reference"] == "main"
    assert data["base_sha"] == git(work, "rev-parse", "main").stdout.strip()
    assert data["name_status"] == ["A\tfeat.py"]
    assert any("origin/feature" in w and "already contains HEAD" in w for w in data["warnings"])


def test_prepare_falls_back_to_origin_main_when_no_local_main(tmp_path, monkeypatch, capsys):
    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(origin, "init", "-q", "--bare", "-b", "main")
    seed = init_repo(tmp_path / "seed")
    commit_file(seed, "base.txt", "base\n", "base commit")
    git(seed, "remote", "add", "origin", str(origin))
    git(seed, "push", "-q", "origin", "main")
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(origin), "work")
    git(work, "config", "user.email", "t@example.com")
    git(work, "config", "user.name", "T")
    git(work, "checkout", "-q", "-b", "feature", "origin/main")
    git(work, "branch", "-q", "-D", "main")
    commit_file(work, "feat.py", "x = 1\n", "feature commit")
    git(work, "push", "-q", "-u", "origin", "feature")
    code, data, err = run_json(monkeypatch, capsys, work, "prepare")
    assert code == 0, err
    assert data["reference"] == "origin/main"


def test_prepare_warns_when_explicit_reference_contains_head(scratch_repo, monkeypatch, capsys):
    """An explicit --reference is honored even when it already contains HEAD
    (post-hoc attestation of a merged commit), but the empty range is announced."""
    code, data, err = run_json(monkeypatch, capsys, scratch_repo, "prepare", "--reference", "HEAD")
    assert code == 0
    assert data["base_sha"] == data["reviewed_commit_sha"] and data["name_status"] == []
    assert any("range to review is empty" in w for w in data["warnings"])
    assert "range to review is empty" in err


def test_prepare_never_diffs_main_against_itself(tmp_path, monkeypatch, capsys):
    path = init_repo(tmp_path / "repo_main", branch="main")
    commit_file(path, "base.txt", "base\n", "base commit")
    git(path, "branch", "master")
    code, data, err = run_json(monkeypatch, capsys, path, "prepare")
    assert code == 2
    assert data["ok"] is False and data["exit_code"] == 2
    assert "pass --reference" in err


def test_prepare_rejects_unresolvable_reference(scratch_repo, monkeypatch, capsys):
    code, _, err = run(monkeypatch, capsys, scratch_repo, "prepare", "--reference", "no-such-branch")
    assert code == 2 and "does not resolve" in err


def test_prepare_refuses_unstaged_changes(scratch_repo, monkeypatch, capsys):
    (scratch_repo / "feat.txt").write_text("dirty\n")
    code, _, err = run(monkeypatch, capsys, scratch_repo, "prepare", "--reference", "main")
    assert code == 3 and "Unstaged" in err


def test_prepare_refuses_staged_changes(scratch_repo, monkeypatch, capsys):
    (scratch_repo / "staged.txt").write_text("s\n")
    git(scratch_repo, "add", "staged.txt")
    code, _, err = run(monkeypatch, capsys, scratch_repo, "prepare", "--reference", "main")
    assert code == 3 and "Staged" in err


def test_prepare_refuses_unborn_head(tmp_path, monkeypatch, capsys):
    path = init_repo(tmp_path / "unborn")
    code, _, err = run(monkeypatch, capsys, path, "prepare")
    assert code == 6 and "unborn" in err


def test_prepare_outside_git_repo_is_git_failure(tmp_path, monkeypatch, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    code, _, err = run(monkeypatch, capsys, plain, "prepare")
    assert code == 6 and "not inside a git repository" in err


def test_prepare_unreadable_profile_override_is_exit_5(scratch_repo, tmp_path, monkeypatch, capsys):
    code, _, err = run(
        monkeypatch, capsys, scratch_repo, "prepare", "--reference", "main",
        env={"GIT_SIGNOFF_PROFILE_FILE": str(tmp_path / "missing.md")},
    )
    assert code == 5 and "GIT_SIGNOFF_PROFILE_FILE" in err


def test_prepare_reports_repo_local_profile_and_malformed_fallback(scratch_repo, monkeypatch, capsys):
    d = scratch_repo / ".git-signoff"
    d.mkdir()
    valid = (
        "<!-- INTERVIEW-PROFILE:BEGIN -->\n### Interview Profile: lab\nProfile-ID: lab-x\n- emphasis\n"
        "<!-- INTERVIEW-PROFILE:END -->\n"
    )
    (d / "profile.md").write_text(valid, encoding="utf-8")
    git(scratch_repo, "add", ".")
    git(scratch_repo, "commit", "-q", "-m", "profile")
    code, data, _ = run_json(monkeypatch, capsys, scratch_repo, "prepare", "--reference", "main")
    assert code == 0
    assert data["profile"]["source"] == "repo-local" and data["profile"]["id"] == "lab-x"
    assert len(data["profile"]["digest"]) == 12

    (d / "profile.md").write_text(valid.replace("Profile-ID: lab-x\n", ""), encoding="utf-8")
    git(scratch_repo, "commit", "-q", "-am", "break profile")
    code, data, err = run_json(monkeypatch, capsys, scratch_repo, "prepare", "--reference", "main")
    assert code == 0  # malformed repo-local profile is announced, not fatal
    assert data["profile"]["source"] == "embedded-default" and data["profile"]["digest"] is None
    assert "malformed profile" in data["profile"]["fallback_reason"]
    assert "malformed profile" in err


def test_prepare_science_signals_and_tier2_hints(scratch_repo, monkeypatch, capsys):
    (scratch_repo / "ciwv.py").write_text("import numpy as np\nG0 = 9.80665\nrng = np.random.default_rng(seed=7)\n")
    (scratch_repo / "auth").mkdir()
    (scratch_repo / "auth" / "login.py").write_text("def login(): pass\n")
    (scratch_repo / "migrations").mkdir()
    (scratch_repo / "migrations" / "001.sql").write_text("ALTER TABLE users ADD COLUMN x int;\n")
    (scratch_repo / "api.proto").write_text("syntax = 'proto3';\n")
    (scratch_repo / "tests").mkdir()
    (scratch_repo / "tests" / "test_x.py").write_text("def test(): pass\n" * 300)
    (scratch_repo / "docs.md").write_text("# doc\n" * 500)
    git(scratch_repo, "add", ".")
    git(scratch_repo, "commit", "-q", "-m", "science + auth")
    code, data, _ = run_json(monkeypatch, capsys, scratch_repo, "prepare", "--reference", "main")
    assert code == 0
    assert set(data["science_signals"]) >= {"scientific-imports", "rng-seeding", "units-or-constants"}
    triggers = data["hints"]["tier2_triggers"]
    assert triggers["security-auth"] == ["auth/login.py"]
    assert set(triggers["schemas-migrations"]) == {"migrations/001.sql", "<diff content>"}
    assert triggers["public-api-contracts"] == ["api.proto"]
    assert triggers["scientific-computation"] == data["science_signals"]
    assert "executable-blast-radius" not in triggers  # tests and docs are excluded from the count
    assert data["hints"]["changed_files"] == 7
    assert data["hints"]["executable_files"] == 4
    assert data["hints"]["executable_lines_changed"] == 3 + 1 + 1 + 1


def test_intensity_hints_blast_radius_and_renames():
    numstat = "\n".join(f"50\t0\tsrc/mod{i}.py" for i in range(6)) + "\n3\t2\tsrc/{old => new}/thing.py\n-\t-\timg.png\n"
    hints = attest.intensity_hints(numstat, "", [])
    assert hints["changed_files"] == 8
    assert hints["executable_files"] == 8
    assert hints["executable_lines_changed"] == 305
    assert "executable-blast-radius" in hints["tier2_triggers"]
    docs_only = attest.intensity_hints("500\t0\tREADME.md\n10\t0\tauth/README.md\n", "", [])
    assert docs_only["executable_lines_changed"] == 0
    assert docs_only["tier2_triggers"] == {}  # path tokens do not trigger on docs


# --- commit: happy path --------------------------------------------------------


def test_commit_happy_path_with_marker(scratch_repo, tmp_path, monkeypatch, capsys):
    reviewed, tree = _head(scratch_repo), _tree(scratch_repo)
    t = _transcript(tmp_path, scratch_repo)
    data_bytes = t.read_bytes()
    code, data, err = run_json(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--tradeoff", "t1", "--tradeoff", "t2", "--risk", "r1", "--summary", "Reviewed the widget.",
        "--reference", "main", "--no-push", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 0, err
    assert data["ok"] is True and data["command"] == "commit"
    assert data["status"] == "VERIFIED_BY_HUMAN"
    assert data["transcript_digest"] == f"sha256:{hashlib.sha256(data_bytes).hexdigest()}"
    assert data["transcript_bytes"] == str(len(data_bytes))
    assert data["marker_found"] is True
    assert data["transcript_path"] == str(t)
    assert data["attestation_sha"] == _head(scratch_repo)
    assert data["noted_shas"] == [reviewed, tree]
    assert data["notes_pushed"] is False and data["notes_push_reason"] == "skipped (--no-push)"
    assert data["signed"] is False
    assert data["verifier"][0].startswith("PASS:")

    # empty attestation commit parented on the reviewed commit with the same tree
    assert git(scratch_repo, "rev-parse", "HEAD~1").stdout.strip() == reviewed
    assert _tree(scratch_repo) == tree
    message = git(scratch_repo, "log", "-1", "--format=%B").stdout
    assert message.rstrip("\n") == data["message"]
    trailers = attest.parse_trailers(message)
    assert trailers["Signoff-Tradeoff"] == ["t1", "t2"]
    assert trailers["Signoff-Risk"] == ["r1"]
    assert trailers["Signoff-Harness-ID"] == ["generic-file"]
    assert trailers["Signoff-Conversation-ID"] == ["unavailable"]
    assert trailers["Signoff-Agent"] == ["harness=generic-file/N/A model=model-from-transcript reasoning=N/A interview=standard/software-general"]
    assert message.splitlines()[2] == "Reviewed the widget."
    # dual persistence
    for sha in (reviewed, tree):
        note = git(scratch_repo, "notes", "--ref=signoff", "show", sha).stdout
        assert note.rstrip("\n") == data["message"]
    # the independent verifier agrees, in head mode on the attestation tip
    ok, lines = verify_signoff.check_head(str(scratch_repo), "HEAD")
    assert ok, lines


def test_commit_human_output(scratch_repo, tmp_path, monkeypatch, capsys):
    t = _transcript(tmp_path, scratch_repo)
    code, out, _ = run(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "cursory",
        "--reference", "main", "--no-push", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 0
    assert out.startswith(f"attestation commit: {_head(scratch_repo)}\n")
    assert "status: VERIFIED_BY_HUMAN\n" in out
    assert "approval marker: found\n" in out
    assert "notes pushed: no (skipped (--no-push))" in out
    assert "verifier: PASS:" in out


def test_commit_none_rules_for_empty_tradeoffs_and_risks(scratch_repo, tmp_path, monkeypatch, capsys):
    t = _transcript(tmp_path, scratch_repo)
    code, data, _ = run_json(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 0
    trailers = attest.parse_trailers(data["message"])
    assert trailers["Signoff-Tradeoff"] == ["none"] and trailers["Signoff-Risk"] == ["none"]


def test_commit_provenance_from_claude_code_env(scratch_repo, tmp_path, monkeypatch, capsys):
    t = _transcript(tmp_path, scratch_repo)
    code, data, _ = run_json(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "skeptical",
        "--reference", "main", "--no-push",
        env={
            "GIT_SIGNOFF_TRANSCRIPT_FILE": str(t),
            "CLAUDE_CODE_SESSION_ID": "sess-1",
            "CLAUDE_CODE_VERSION": "2.1.0",
            "CLAUDE_EFFORT": "high",
            "ANTHROPIC_MODEL": "claude-x-1",
        },
    )
    assert code == 0
    trailers = attest.parse_trailers(data["message"])
    # the override file wins for bytes; the conversation id comes from the harness id
    assert trailers["Signoff-Harness-ID"] == ["generic-file"]
    assert trailers["Signoff-Conversation-ID"] == ["sess-1"]
    assert trailers["Signoff-Agent"] == ["harness=generic-file/2.1.0 model=claude-x-1 reasoning=high interview=skeptical/software-general"]


def test_commit_version_and_reasoning_are_scoped_to_claude_code(scratch_repo, tmp_path, monkeypatch, capsys):
    t = _transcript(tmp_path, scratch_repo)
    code, data, _ = run_json(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push",
        env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t), "CLAUDE_CODE_VERSION": "2.1.0", "CLAUDE_EFFORT": "high"},
    )
    assert code == 0
    assert "harness=generic-file/N/A model=model-from-transcript reasoning=N/A" in data["message"]


def test_commit_model_self_report_is_last_resort(scratch_repo, tmp_path, monkeypatch, capsys):
    t = tmp_path / "t.jsonl"
    t.write_bytes(b"no model field here\n" + f"GSA-APPROVAL {_head(scratch_repo)} 2026-09-09T00:00:00Z\n".encode())
    code, data, _ = run_json(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", "--model", "self-reported-model", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 0 and "model=self-reported-model" in data["message"]
    git(scratch_repo, "reset", "-q", "--hard", "HEAD~1")
    t2 = _transcript(tmp_path, scratch_repo)  # transcript carries a model field: it beats the self-report
    code, data, _ = run_json(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", "--model", "self-reported-model", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t2)},
    )
    assert code == 0 and "model=model-from-transcript" in data["message"]


def test_commit_repo_local_profile_digest_in_agent_token(scratch_repo, tmp_path, monkeypatch, capsys):
    d = scratch_repo / ".git-signoff"
    d.mkdir()
    (d / "profile.md").write_text(
        "<!-- INTERVIEW-PROFILE:BEGIN -->\nProfile-ID: lab-x\n<!-- INTERVIEW-PROFILE:END -->\n", encoding="utf-8"
    )
    git(scratch_repo, "add", ".")
    git(scratch_repo, "commit", "-q", "-m", "profile")
    t = _transcript(tmp_path, scratch_repo)
    code, data, _ = run_json(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 0
    digest = attest.profile_block_digest((d / "profile.md").read_bytes())
    assert f"interview=standard/lab-x/sha256:{digest}" in data["message"]


# --- commit: marker protocol ------------------------------------------------------


def test_commit_refuses_transcript_without_marker(scratch_repo, tmp_path, monkeypatch, capsys):
    head = _head(scratch_repo)
    t = _transcript(tmp_path, scratch_repo, with_marker=False)
    code, data, err = run_json(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 4 and data == {"ok": False, "command": "commit", "exit_code": 4, "error": data["error"]}
    assert str(t) in err and f"{t.stat().st_size} bytes" in err
    assert f"GSA-APPROVAL {head} <utc-timestamp>" in err
    assert "emit the marker line" in err.lower()
    assert _head(scratch_repo) == head  # no commit created
    assert git(scratch_repo, "notes", "--ref=signoff", "show", head, check=False).returncode != 0


def test_commit_refuses_marker_for_an_unrelated_commit(scratch_repo, tmp_path, monkeypatch, capsys):
    head = _head(scratch_repo)
    other = "f" * 40
    t = _transcript(tmp_path, scratch_repo, sha=other)
    code, _, err = run(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 4
    assert other in err and head in err
    assert _head(scratch_repo) == head


def test_commit_stale_when_marker_names_an_earlier_commit_on_this_branch(scratch_repo, tmp_path, monkeypatch, capsys):
    """prepare ran, the human approved, then the branch moved: the marker names
    an ancestor of HEAD — stale (exit 3), not a wrong file (exit 4)."""
    prepared = _head(scratch_repo)
    t = _transcript(tmp_path, scratch_repo, sha=prepared)
    commit_file(scratch_repo, "later.txt", "x\n", "moves HEAD after prepare")
    code, _, err = run(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 3
    assert "stale" in err and prepared in err and _head(scratch_repo) in err
    assert git(scratch_repo, "log", "--format=%s", "-1").stdout.strip() == "moves HEAD after prepare"


def test_commit_last_marker_governs(scratch_repo, tmp_path, monkeypatch, capsys):
    head = _head(scratch_repo)
    t = tmp_path / "t.jsonl"
    t.write_bytes(
        f"GSA-APPROVAL {head} 2026-09-09T00:00:00Z\nmore talk\nGSA-APPROVAL {'e' * 40} 2026-09-09T00:01:00Z\n".encode()
    )
    code, _, err = run(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 4 and "e" * 40 in err


def test_commit_marker_outside_last_64kib_is_not_found(scratch_repo, tmp_path, monkeypatch, capsys):
    head = _head(scratch_repo)
    marker = f"GSA-APPROVAL {head} 2026-09-09T00:00:00Z\n".encode()
    t = tmp_path / "t.jsonl"
    t.write_bytes(marker + b"x" * (attest.MARKER_WINDOW + 10))
    code, _, err = run(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 4 and "approval marker not found" in err
    assert f"last {attest.MARKER_WINDOW} bytes searched" in err
    t.write_bytes(b"x" * (attest.MARKER_WINDOW + 10) + marker)  # inside the window: accepted
    code, _, err = run(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 0, err


def test_commit_retries_once_for_a_late_flush(scratch_repo, tmp_path, monkeypatch):
    """The marker is not on disk on the first read but is on the second: one
    retry after MARKER_RETRY_DELAY covers a slow harness flush."""
    head = _head(scratch_repo)
    sleeps = []
    monkeypatch.setattr(attest, "MARKER_RETRY_DELAY", 0.25)
    monkeypatch.setattr(attest.time, "sleep", lambda s: sleeps.append(s))

    class LateAdapter:
        harness_id = "generic-file"

        def __init__(self):
            self.reads = 0

        def resolve_conversation_id(self):
            return "late"

        def describe_path(self):
            return "/virtual/late.jsonl"

        def fetch_transcript_bytes(self):
            # read 1: prepare's availability probe; read 2: the commit snapshot
            # (marker not flushed yet); read 3: the one retry.
            self.reads += 1
            return b"first read\n" if self.reads <= 2 else f"first read\nGSA-APPROVAL {head} 2026-09-09T00:00:00Z\n".encode()

    adapter = LateAdapter()
    opts = attest.CommitOptions(email="dev@example.com", level="standard", reference="main", push=False)
    result = attest.commit(str(scratch_repo), opts, env={}, adapter=adapter)
    assert result.marker_found and adapter.reads == 3 and sleeps == [0.25]
    assert result.transcript_bytes == str(len(f"first read\nGSA-APPROVAL {head} 2026-09-09T00:00:00Z\n"))
    assert result.transcript_digest == "sha256:" + hashlib.sha256(
        f"first read\nGSA-APPROVAL {head} 2026-09-09T00:00:00Z\n".encode()
    ).hexdigest()


def test_marker_survives_json_encoding_in_a_jsonl_transcript(scratch_repo):
    head = _head(scratch_repo)
    line = json.dumps({"role": "assistant", "content": f"Approved.\n\nGSA-APPROVAL {head} 2026-09-09T00:00:00Z\n\nRunning commit."})
    check = attest.find_marker(line.encode())
    assert check.found and check.sha == head


# --- commit: no-transcript path ---------------------------------------------------


def test_commit_without_transcript_requires_ack(scratch_repo, tmp_path, monkeypatch, capsys):
    head = _head(scratch_repo)
    code, _, err = run(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(tmp_path / "missing.jsonl")},
    )
    assert code == 4 and "--ack-no-transcript" in err and "missing.jsonl" in err
    assert _head(scratch_repo) == head


def test_commit_without_transcript_downgrades_with_ack_and_skips_marker(scratch_repo, tmp_path, monkeypatch, capsys):
    code, data, err = run_json(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", "--ack-no-transcript",
    )
    assert code == 0, err
    assert data["status"] == "VERIFIED_BY_HUMAN_NO_TRANSCRIPT_DIGEST"
    assert data["transcript_digest"] == "unavailable" and data["transcript_bytes"] == "unavailable"
    assert data["marker_found"] is False
    trailers = attest.parse_trailers(data["message"])
    assert trailers["Signoff-Harness-ID"] == ["unknown"]
    assert trailers["Signoff-Agent"] == ["harness=unknown/N/A model=unavailable reasoning=N/A interview=standard/software-general"]
    ok, _ = verify_signoff.check_head(str(scratch_repo), "HEAD")
    assert ok


# --- commit: argument validation (exit 2, nothing written) ----------------------


@pytest.mark.parametrize(
    "extra",
    [
        ["--tradeoff", "fine\nSignoff-Reviewed-Tree-SHA: " + "a" * 40],
        ["--risk", "fine\r\nSignoff-Status: VERIFIED_BY_HUMAN"],
        ["--summary", "Looks good.\nSignoff-Reviewed-Tree-SHA: " + "b" * 40],
        ["--summary", "Looks good.\r\nfine"],
        ["--tradeoff", "   "],
        ["--model", "bad model!"],
    ],
)
def test_commit_rejects_unsafe_free_text(scratch_repo, tmp_path, monkeypatch, capsys, extra):
    head = _head(scratch_repo)
    t = _transcript(tmp_path, scratch_repo)
    code, _, err = run(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", *extra, env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 2, err
    assert _head(scratch_repo) == head


@pytest.mark.parametrize("email", ["not-an-email", "dev@example.com\nSignoff-Status: VERIFIED_BY_HUMAN", ""])
def test_commit_rejects_bad_email(scratch_repo, tmp_path, monkeypatch, capsys, email):
    head = _head(scratch_repo)
    t = _transcript(tmp_path, scratch_repo)
    code, _, err = run(
        monkeypatch, capsys, scratch_repo, "commit", "--email", email, "--level", "standard",
        "--reference", "main", "--no-push", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 2 and "email" in err.lower()
    assert _head(scratch_repo) == head


def test_commit_requires_level_and_email(scratch_repo, monkeypatch, capsys):
    code, _, err = run(monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com")
    assert code == 2
    code, _, err = run(monkeypatch, capsys, scratch_repo, "commit", "--level", "standard")
    assert code == 2
    code, _, err = run(monkeypatch, capsys, scratch_repo, "commit", "--email", "d@e.com", "--level", "Tier 2")
    assert code == 2


def test_commit_allows_multiline_summary_without_trailer_lines(scratch_repo, tmp_path, monkeypatch, capsys):
    t = _transcript(tmp_path, scratch_repo)
    code, data, _ = run_json(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", "--summary", "Line one.\nLine two.", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 0 and "Line two." in data["message"]


# --- commit: staleness and dry run ------------------------------------------------


def test_commit_refuses_dirty_tree(scratch_repo, tmp_path, monkeypatch, capsys):
    t = _transcript(tmp_path, scratch_repo)
    (scratch_repo / "feat.txt").write_text("dirty\n")
    code, _, err = run(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 3 and "Unstaged" in err


def test_commit_dry_run_prints_message_and_creates_nothing(scratch_repo, tmp_path, monkeypatch, capsys):
    head = _head(scratch_repo)
    t = _transcript(tmp_path, scratch_repo, with_marker=False)  # dry run precedes approval: no marker yet
    code, out, err = run(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--tradeoff", "t1", "--reference", "main", "--dry-run", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 0, err
    assert out.startswith(f"[SIGNOFF {head[:7]}]: human comprehension and risk attestation\n")
    assert "Signoff-Tradeoff: t1\n" in out
    assert "dry run: nothing committed" in out
    assert "approval marker: not yet in the transcript (dry run; required at commit)" in out
    assert "provisional" in err
    assert _head(scratch_repo) == head
    assert git(scratch_repo, "notes", "--ref=signoff", "list", check=False).stdout.strip() == ""
    code, data, _ = run_json(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--dry-run", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 0 and data["dry_run"] is True and data["attestation_sha"] is None
    assert data["status"] == "VERIFIED_BY_HUMAN" and data["marker_found"] is False


# --- commit: self-checks and rollback ----------------------------------------------


def test_commit_post_commit_self_check_failure_rolls_back(scratch_repo, tmp_path, monkeypatch):
    head, tree = _head(scratch_repo), _tree(scratch_repo)
    git(scratch_repo, "notes", "--ref=signoff", "add", "-m", "pre-existing note on tree", tree)
    prior_tree_note = git(scratch_repo, "notes", "--ref=signoff", "show", tree).stdout
    t = _transcript(tmp_path, scratch_repo)
    adapter = attest.GenericFileAdapter(str(t))

    class RejectingVerifier:
        parse_trailers = staticmethod(verify_signoff.parse_trailers)
        validate_single = staticmethod(verify_signoff.validate_single)

        @staticmethod
        def check_head(repo, target):
            return False, ["FAIL: simulated verifier rejection"]

    opts = attest.CommitOptions(email="dev@example.com", level="standard", reference="main", push=False)
    with pytest.raises(attest.AttestError) as exc:
        attest.commit(str(scratch_repo), opts, env={}, adapter=adapter, verifier=RejectingVerifier())
    assert exc.value.code == 7 and "simulated verifier rejection" in str(exc.value)
    assert _head(scratch_repo) == head  # empty commit removed
    assert git(scratch_repo, "diff", "--quiet").returncode == 0 and git(scratch_repo, "diff", "--cached", "--quiet").returncode == 0
    assert git(scratch_repo, "notes", "--ref=signoff", "show", head, check=False).returncode != 0  # note removed
    assert git(scratch_repo, "notes", "--ref=signoff", "show", tree).stdout == prior_tree_note  # note restored


def test_commit_pre_commit_structural_self_check_failure_writes_nothing(scratch_repo, tmp_path, monkeypatch):
    head = _head(scratch_repo)
    t = _transcript(tmp_path, scratch_repo)
    adapter = attest.GenericFileAdapter(str(t))

    class ParanoidVerifier:
        parse_trailers = staticmethod(verify_signoff.parse_trailers)

        @staticmethod
        def validate_single(trailers):
            return ["simulated structural problem"]

        check_head = staticmethod(verify_signoff.check_head)

    opts = attest.CommitOptions(email="dev@example.com", level="standard", reference="main", push=False)
    with pytest.raises(attest.AttestError) as exc:
        attest.commit(str(scratch_repo), opts, env={}, adapter=adapter, verifier=ParanoidVerifier())
    assert exc.value.code == 7 and "bug in attest.py" in str(exc.value)
    assert _head(scratch_repo) == head
    assert git(scratch_repo, "notes", "--ref=signoff", "list", check=False).stdout.strip() == ""


def test_commit_integrity_failure_rolls_back(scratch_repo, tmp_path, monkeypatch):
    """If the commit lands with a different tree (simulated by a post-commit
    hook amending it), the helper removes it and exits 7."""
    head = _head(scratch_repo)
    hook = scratch_repo / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/sh\nif [ -z \"$GSA_IN_HOOK\" ]; then echo smuggled > smuggled.txt; git add smuggled.txt; GSA_IN_HOOK=1 git commit -q --amend --no-edit; fi\n")
    hook.chmod(0o755)
    t = _transcript(tmp_path, scratch_repo)
    adapter = attest.GenericFileAdapter(str(t))
    opts = attest.CommitOptions(email="dev@example.com", level="standard", reference="main", push=False)
    with pytest.raises(attest.AttestError) as exc:
        attest.commit(str(scratch_repo), opts, env={}, adapter=adapter)
    assert exc.value.code == 7 and "integrity" in str(exc.value)
    assert _head(scratch_repo) == head
    assert git(scratch_repo, "notes", "--ref=signoff", "list", check=False).stdout.strip() == ""


def test_load_verifier_requires_the_sibling_file(tmp_path, monkeypatch):
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    shutil.copy(os.path.join(SKILL_DIR, "attest.py"), lonely / "attest.py")
    repo = init_repo(tmp_path / "repo")
    commit_file(repo, "a.txt", "a", "a")
    proc = subprocess.run(
        [sys.executable, str(lonely / "attest.py"), "commit", "--email", "d@e.com", "--level", "standard", "--no-push"],
        cwd=str(repo), capture_output=True, text=True,
    )
    assert proc.returncode == 2
    assert "verify_signoff.py not found next to attest.py" in proc.stderr


# --- commit: notes push ------------------------------------------------------------


@pytest.fixture
def repo_with_origin(tmp_path):
    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(origin, "init", "-q", "--bare", "-b", "main")
    work = init_repo(tmp_path / "work")
    commit_file(work, "base.txt", "base\n", "base commit")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-q", "-u", "origin", "main")
    git(work, "checkout", "-q", "-b", "feature")
    commit_file(work, "feat.txt", "feature\n", "feature commit")
    git(work, "branch", "-q", "--set-upstream-to=origin/main")
    return work, origin


def test_commit_pushes_notes_by_default(repo_with_origin, tmp_path, monkeypatch, capsys):
    work, origin = repo_with_origin
    t = _transcript(tmp_path, work)
    code, data, err = run_json(
        monkeypatch, capsys, work, "commit", "--email", "dev@example.com", "--level", "standard",
        env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 0, err
    assert data["notes_pushed"] is True and data["notes_push_reason"] is None
    assert data["notes_merged_remote"] is False  # first notes push ever: nothing to merge
    remote_notes = git(work, "ls-remote", "origin", "refs/notes/signoff").stdout.split()
    assert remote_notes and remote_notes[0] == git(work, "rev-parse", "refs/notes/signoff").stdout.strip()
    # the branch itself is not pushed by the helper
    assert git(work, "ls-remote", "origin", "refs/heads/feature").stdout.strip() == ""


def test_commit_reports_refused_notes_push_and_exits_zero(repo_with_origin, tmp_path, monkeypatch, capsys):
    work, origin = repo_with_origin
    hook = origin / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'remote: notes refs are not accepted here (403)' >&2\nexit 1\n")
    hook.chmod(0o755)
    t = _transcript(tmp_path, work)
    code, data, err = run_json(
        monkeypatch, capsys, work, "commit", "--email", "dev@example.com", "--level", "standard",
        env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 0, err
    assert data["notes_pushed"] is False
    assert "notes push refused" in data["notes_push_reason"]
    assert data["attestation_sha"] == _head(work)  # the attestation commit stands
    assert git(work, "notes", "--ref=signoff", "show", data["noted_shas"][0]).returncode == 0


def test_commit_merges_diverged_remote_notes_before_push(repo_with_origin, tmp_path, monkeypatch, capsys):
    work, origin = repo_with_origin
    reviewed = _head(work)
    # a colleague already pushed a note on the same reviewed commit
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(origin), "other")
    git(other, "config", "user.email", "o@example.com")
    git(other, "config", "user.name", "O")
    git(other, "fetch", "-q", "origin", "refs/heads/main")
    git(other, "notes", "--ref=signoff", "add", "-m", "Signoff-Conversation-ID: colleague", git(other, "rev-parse", "origin/main").stdout.strip())
    git(other, "push", "-q", "origin", "refs/notes/signoff")
    # our own local notes ref already exists and diverges: a direct fetch would be rejected
    git(work, "notes", "--ref=signoff", "add", "-m", "Signoff-Conversation-ID: earlier-local", git(work, "rev-parse", "main").stdout.strip())
    t = _transcript(tmp_path, work)
    code, data, err = run_json(
        monkeypatch, capsys, work, "commit", "--email", "dev@example.com", "--level", "standard",
        env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 0, err
    assert data["notes_pushed"] is True and data["notes_merged_remote"] is True
    merged = git(work, "notes", "--ref=signoff", "show", git(work, "rev-parse", "main").stdout.strip()).stdout
    assert "colleague" in merged and "earlier-local" in merged
    assert git(work, "notes", "--ref=signoff", "show", reviewed).returncode == 0
    assert git(work, "ls-remote", "origin", "refs/notes/signoff").stdout.split()[0] == git(
        work, "rev-parse", "refs/notes/signoff"
    ).stdout.strip()


def test_commit_without_origin_reports_push_failure(scratch_repo, tmp_path, monkeypatch, capsys):
    t = _transcript(tmp_path, scratch_repo)
    code, data, err = run_json(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 0, err
    assert data["notes_pushed"] is False and "refused" in data["notes_push_reason"]


# --- signing ----------------------------------------------------------------------


def test_commit_no_sign_flag_suppresses_signing(scratch_repo, tmp_path, monkeypatch, capsys):
    git(scratch_repo, "config", "user.signingkey", "DEADBEEF")
    git(scratch_repo, "config", "gpg.program", "/nonexistent/gpg")
    t = _transcript(tmp_path, scratch_repo)
    code, data, err = run_json(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", "--no-sign", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 0, err
    assert data["signed"] is False


def test_commit_signing_failure_is_a_git_failure_with_nothing_written(scratch_repo, tmp_path, monkeypatch, capsys):
    head = _head(scratch_repo)
    git(scratch_repo, "config", "user.signingkey", "DEADBEEF")
    git(scratch_repo, "config", "gpg.program", "/nonexistent/gpg")
    t = _transcript(tmp_path, scratch_repo)
    code, _, err = run(
        monkeypatch, capsys, scratch_repo, "commit", "--email", "dev@example.com", "--level", "standard",
        "--reference", "main", "--no-push", env={"GIT_SIGNOFF_TRANSCRIPT_FILE": str(t)},
    )
    assert code == 6 and "git commit" in err
    assert _head(scratch_repo) == head
    assert git(scratch_repo, "notes", "--ref=signoff", "list", check=False).stdout.strip() == ""


# --- CLI surface ----------------------------------------------------------------------


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        attest.main(["--version"])
    assert exc.value.code == 0
    assert "attest.py 0.5.0" in capsys.readouterr().out


def test_no_subcommand_is_usage_error(capsys):
    with pytest.raises(SystemExit) as exc:
        attest.main([])
    assert exc.value.code == 2


def test_attest_exits_loudly_below_python_floor(tmp_path):
    script = os.path.join(SKILL_DIR, "attest.py")
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import runpy, sys\n"
        "sys.version_info = (3, 9, 18, 'final', 0)\n"
        "sys.argv = ['attest.py', 'prepare']\n"
        f"runpy.run_path({script!r}, run_name='__main__')\n"
    )
    proc = subprocess.run([sys.executable, str(probe)], capture_output=True, text=True)
    assert proc.returncode == 1
    assert "needs Python 3.10 or newer" in proc.stderr and "3.9" in proc.stderr


# --- end to end through the vendored copy ---------------------------------------


def test_end_to_end_vendored_by_init_then_attested_and_verified(tmp_path):
    """init.py vendors skills/git-signoff/ into a scratch repo; attest.py runs
    from the vendored copy; the verifier passes on the result (head mode on the
    attestation tip, history mode, and the tree-note lookup after a squash)."""
    sys.path.insert(0, REPO_ROOT)
    try:
        import init as init_mod
    finally:
        sys.path.pop(0)

    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(origin, "init", "-q", "--bare", "-b", "main")
    repo = init_repo(tmp_path / "adopter")
    (repo / "CLAUDE.md").write_text("# project\n")
    git(repo, "add", "CLAUDE.md")
    commit_file(repo, "README.md", "# Adopter\n", "initial")
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "-u", "origin", "main")

    result = init_mod.run_init(
        repo_root=repo, profile_id="software-general", skip_ruleset=True, non_interactive=True,
        skill_source=SKILL_DIR, skill_target="claude",
    )
    assert result.success and result.branch == "git-signoff/init"
    vendored = repo / ".claude" / "skills" / "git-signoff"
    assert (vendored / "attest.py").is_file() and (vendored / "verify_signoff.py").is_file()
    assert not (vendored / "__pycache__").exists()
    assert (repo / ".github" / "workflows" / "git-signoff.yml").is_file()
    assert (repo / ".git-signoff" / "profile.md").is_file()

    env = {**os.environ, "GIT_SIGNOFF_NO_UPDATE_CHECK": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    for var in ("CLAUDE_CODE_SESSION_ID", "GIT_SIGNOFF_TRANSCRIPT_FILE", "ANTHROPIC_MODEL", "CLAUDE_CODE_VERSION", "CLAUDE_EFFORT"):
        env.pop(var, None)

    # red before the attestation
    proc = subprocess.run([sys.executable, str(vendored / "verify_signoff.py"), "--mode", "head"], cwd=repo, capture_output=True, text=True, env=env)
    assert proc.returncode == 1 and "FAIL" in proc.stdout

    proc = subprocess.run([sys.executable, str(vendored / "attest.py"), "prepare", "--reference", "main", "--json"], cwd=repo, capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    prepared = json.loads(proc.stdout)
    assert prepared["profile"]["source"] == "repo-local" and prepared["profile"]["id"] == "software-general"
    transcript = tmp_path / "session.jsonl"
    transcript.write_bytes(b'{"model":"m-1"}\n' + f"agent: {prepared['marker']}\n".encode())
    env["GIT_SIGNOFF_TRANSCRIPT_FILE"] = str(transcript)

    proc = subprocess.run(
        [sys.executable, str(vendored / "attest.py"), "commit", "--email", "dev@example.com", "--level", "standard",
         "--tradeoff", "scaffold only", "--reference", "main", "--json"],
        cwd=repo, capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    committed = json.loads(proc.stdout)
    assert committed["status"] == "VERIFIED_BY_HUMAN" and committed["notes_pushed"] is True
    assert f"sha256:{prepared['profile']['digest']}" in committed["message"]

    proc = subprocess.run([sys.executable, str(vendored / "verify_signoff.py"), "--mode", "head"], cwd=repo, capture_output=True, text=True, env=env)
    assert proc.returncode == 0 and "PASS" in proc.stdout, proc.stdout
    proc = subprocess.run([sys.executable, str(vendored / "verify_signoff.py"), "--mode", "history", "--target", "HEAD"], cwd=repo, capture_output=True, text=True, env=env)
    assert proc.returncode == 0 and "1 valid attestation" in proc.stdout, proc.stdout

    # simulated squash merge onto an unchanged main: the tree-note lookup carries the attestation
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--squash", result.branch)
    git(repo, "commit", "-q", "-m", "squash: scaffold git signoff attestation")
    proc = subprocess.run([sys.executable, str(vendored / "verify_signoff.py"), "--mode", "head"], cwd=repo, capture_output=True, text=True, env=env)
    assert proc.returncode == 0 and "note on tree" in proc.stdout, proc.stdout
