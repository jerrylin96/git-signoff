"""Contract tests for recover/action.yml: the same eligibility as the verifier
(merged pull requests into the branch from this repository; forks never
fetched), read exhaustively — every page — because recovery is what makes an
attestation from a squash- or rebase-merged branch survive, and a pull request
outside a fixed window would otherwise never be recovered. The step runs for
real, as in test_verify_action.py."""

import os

from action_harness import Fixture, pull_request, step_script

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPO = "org/project"
STEP = "Resolve eligible pull-request heads"


def _action():
    with open(os.path.join(ROOT, "recover", "action.yml"), encoding="utf-8") as f:
        return f.read()


def test_lookup_is_the_paginated_branch_pull_request_list():
    text = _action()
    assert 'gh api --paginate "repos/$GITHUB_REPOSITORY/pulls?state=closed&base=$BRANCH&sort=updated&direction=desc&per_page=100"' in text
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
    assert "base=main" in call and "state=closed" in call


def test_branch_input_overrides_the_pushed_branch(tmp_path):
    fx = Fixture(tmp_path, pr_numbers=())
    fx.serve([])
    _, outputs = fx.run(step_script("recover/action.yml", STEP), {"BRANCH_INPUT": "dev", "PRS": "auto"})
    assert outputs["branch"] == "dev" and outputs["refs"] == "--ref origin/dev"
    (call,) = fx.gh_calls()
    assert "base=dev" in call


def test_pull_requests_none_scans_the_branch_only(tmp_path):
    fx = Fixture(tmp_path, pr_numbers=(7,))
    fx.serve([pull_request(7, True, "6" * 40, REPO)])
    _, outputs = fx.run(step_script("recover/action.yml", STEP), {"BRANCH_INPUT": "", "PRS": "none"})
    assert outputs["refs"] == "--ref origin/main"
    assert fx.gh_calls() == [] and fx.fetched_pull_refs() == []
