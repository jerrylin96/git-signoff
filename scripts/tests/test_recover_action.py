"""Contract tests for recover/action.yml: the same eligibility as the verifier
(merged pull requests into the branch from this repository; forks never
fetched), read exhaustively — every page — because recovery is what makes an
attestation from a squash- or rebase-merged branch survive, and a pull request
outside a fixed window would otherwise never be recovered."""

import os

from test_verify_action import FIXTURE, REPO, jq_filter, run_jq

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _action():
    with open(os.path.join(ROOT, "recover", "action.yml"), encoding="utf-8") as f:
        return f.read()


def test_lookup_walks_every_page_of_the_branch_pull_requests():
    text = _action()
    assert 'gh api --paginate "repos/$GITHUB_REPOSITORY/pulls?state=closed&base=$BRANCH&sort=updated&direction=desc&per_page=100"' in text
    assert "gh pr list" not in text
    assert 'git fetch -q origin "+refs/pull/$N/head:refs/remotes/pull/$N/head"' in text
    assert "refs/pull/*/head" not in text, "no wildcard fetch of every pull request"
    assert 'REFS="--ref origin/$BRANCH"' in text and 'REFS="$REFS --ref refs/remotes/pull/$N/head"' in text
    assert "GH_TOKEN: ${{ github.token }}" in text


def test_eligibility_filter_keeps_every_merged_same_repository_pull_request():
    numbers = run_jq(jq_filter(_action(), GITHUB_REPOSITORY=REPO), FIXTURE)
    assert numbers == ["7", "8"]  # unmerged, fork, and deleted-fork entries dropped


def test_pull_requests_input_none_scans_the_branch_only():
    text = _action()
    assert '[ "$PRS" = auto ]' in text and "default: 'auto'" in text
