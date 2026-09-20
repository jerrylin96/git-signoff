"""Contract tests for recover/action.yml: the same eligibility as the verifier
(merged pull requests into the branch from this repository; forks never
fetched), read exhaustively — every page — because recovery is what makes an
attestation from a squash- or rebase-merged branch survive, and a pull request
outside a fixed window would otherwise never be recovered. The step runs for
real, as in test_verify_action.py."""

import os
import shutil
import subprocess

import pytest
from action_harness import Fixture, pull_request, step_script

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPO = "org/project"
STEP = "Resolve eligible pull-request heads"


def _action():
    with open(os.path.join(ROOT, "recover", "action.yml"), encoding="utf-8") as f:
        return f.read()


def test_lookup_is_the_paginated_branch_pull_request_list():
    text = _action()
    assert 'gh api --paginate --method GET "repos/$GITHUB_REPOSITORY/pulls"' in text
    assert '-f "base=$BRANCH"' in text and "pulls?" not in text
    assert "gh pr list" not in text
    assert "refs/pull/*/head" not in text, "no wildcard fetch of every pull request"
    assert "GH_TOKEN: ${{ github.token }}" in text


def test_every_merged_same_repository_pull_request_across_pages_is_fetched(tmp_path):
    fx = Fixture(tmp_path, pr_numbers=(5, 6, 7, 9, 10, 11))
    fx.serve(
        [pull_request(5, True, "1" * 40, REPO), pull_request(6, True, "2" * 40, REPO)],
        [
            pull_request(9, False, "3" * 40, REPO),  # closed unmerged
            pull_request(10, True, "4" * 40, "someone/fork"),  # fork
            pull_request(11, True, "5" * 40, None),  # deleted fork
        ],
        [pull_request(7, True, "6" * 40, REPO)],
    )
    _, outputs = fx.run(step_script("recover/action.yml", STEP), {"BRANCH_INPUT": "", "PRS": "auto"})
    assert outputs["branch"] == "main"
    assert outputs["refs"].split() == [
        "--ref", "origin/main",
        "--ref", "refs/remotes/pull/5/head",
        "--ref", "refs/remotes/pull/6/head",
        "--ref", "refs/remotes/pull/7/head",
    ]
    assert sorted(fx.fetched_pull_refs()) == ["refs/remotes/pull/5/head", "refs/remotes/pull/6/head", "refs/remotes/pull/7/head"]
    (call,) = fx.gh_calls()
    assert call["url"] == "repos/org/project/pulls" and call["method"] == "GET" and call["paginate"] == "1"
    assert call["fields"] == {"state": "closed", "base": "main", "sort": "updated", "direction": "desc", "per_page": "100"}


def test_unfetchable_head_and_failed_lookup_mark_the_run_incomplete(tmp_path):
    """One head that cannot be fetched used to be dropped silently and the run
    finished green with an incomplete notes ref (external review of e54887d).
    The step now records what it did not reach; the action pushes what it
    rebuilt and then fails on that record."""
    fx = Fixture(tmp_path, pr_numbers=(5, 7))  # no refs/pull/6/head on origin
    fx.serve([pull_request(5, True, "1" * 40, REPO), pull_request(6, True, "2" * 40, REPO), pull_request(7, True, "3" * 40, REPO)])
    stdout, outputs = fx.run(step_script("recover/action.yml", STEP), {"BRANCH_INPUT": "", "PRS": "auto"})
    assert outputs["refs"].split() == ["--ref", "origin/main", "--ref", "refs/remotes/pull/5/head", "--ref", "refs/remotes/pull/7/head"]
    assert outputs["incomplete"] == "#6"
    assert "::warning::could not fetch refs/pull/6/head" in stdout

    fx.serve([pull_request(5, True, "1" * 40, REPO)], [pull_request(7, True, "3" * 40, REPO)])
    stdout, outputs = fx.run(step_script("recover/action.yml", STEP), {"BRANCH_INPUT": "", "PRS": "auto"}, fail_after=1)
    assert outputs["refs"].split() == ["--ref", "origin/main", "--ref", "refs/remotes/pull/5/head"]  # page one was used
    assert outputs["incomplete"] == "pull-request-lookup"
    assert "::warning::pull-request lookup failed or stopped early: gh: HTTP 403" in stdout


def test_complete_run_records_nothing_incomplete(tmp_path):
    fx = Fixture(tmp_path, pr_numbers=(5,))
    fx.serve([pull_request(5, True, "1" * 40, REPO)])
    _, outputs = fx.run(step_script("recover/action.yml", STEP), {"BRANCH_INPUT": "", "PRS": "auto"})
    assert outputs["incomplete"] == ""


def test_incomplete_recovery_fails_the_run_after_the_push():
    text = _action()
    push_at = text.index("- name: Push notes ref")
    report_at = text.index("- name: Report incomplete recovery")
    assert push_at < report_at, "what was rebuilt is pushed before the run is failed"
    assert "if: steps.eligible.outputs.incomplete != ''" in text
    assert "exit 1" in text[report_at:]


def test_branch_input_overrides_the_pushed_branch(tmp_path):
    fx = Fixture(tmp_path, pr_numbers=())
    fx.serve([])
    _, outputs = fx.run(step_script("recover/action.yml", STEP), {"BRANCH_INPUT": "release/1+hotfix#2&x", "PRS": "auto"})
    assert outputs["branch"] == "release/1+hotfix#2&x" and outputs["refs"] == "--ref origin/release/1+hotfix#2&x"
    (call,) = fx.gh_calls()
    assert call["fields"]["base"] == "release/1+hotfix#2&x", "a legal ref name reaches gh verbatim, as a field it encodes"
    assert "?" not in call["url"]


def test_pull_requests_none_scans_the_branch_only(tmp_path):
    fx = Fixture(tmp_path, pr_numbers=(7,))
    fx.serve([pull_request(7, True, "6" * 40, REPO)])
    _, outputs = fx.run(step_script("recover/action.yml", STEP), {"BRANCH_INPUT": "", "PRS": "none"})
    assert outputs["refs"] == "--ref origin/main"
    assert fx.gh_calls() == [] and fx.fetched_pull_refs() == []


@pytest.mark.parametrize("mode", ["auto", "none"])
def test_missing_gh_is_incomplete_only_for_auto(tmp_path, mode):
    fx = Fixture(tmp_path, pr_numbers=(7,))
    runner_bin = tmp_path / "runner-bin"
    runner_bin.mkdir()
    for executable in ("bash", "git", "mktemp", "head", "tr"):
        (runner_bin / executable).symlink_to(shutil.which(executable))
    stdout, outputs = fx.run(
        step_script("recover/action.yml", STEP),
        {"BRANCH_INPUT": "", "PRS": mode, "PATH": str(runner_bin)},
    )
    assert outputs["refs"] == "--ref origin/main"
    assert fx.gh_calls() == [] and fx.fetched_pull_refs() == []
    if mode == "auto":
        assert outputs["incomplete"] == "gh-unavailable"
        assert "::warning::gh CLI not available" in stdout
        report = subprocess.run(
            ["bash", "-eo", "pipefail", "-c", step_script("recover/action.yml", "Report incomplete recovery")],
            env={**os.environ, "INCOMPLETE": outputs["incomplete"]}, capture_output=True, text=True,
        )
        assert report.returncode == 1 and "gh-unavailable" in report.stdout
    else:
        assert outputs["incomplete"] == "" and stdout == ""
