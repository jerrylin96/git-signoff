"""Contract tests for verify/action.yml (verify-v1.6): head mode on every event,
and evidence eligibility resolved from the API — the merged, same-repository
pull request whose merge commit is the target — never from a ref-name pattern
(docs/attest-any-target.md §2.13, §3.3). The eligibility step runs for real
(action_harness.py): its shell against a bare origin carrying refs/pull/N/head
and a stand-in gh serving fixture pages."""

import os
import re

from action_harness import Fixture, pull_request, step_script
from helpers import git

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPO = "org/project"
STEP = "Resolve eligible pull-request heads"


def _action():
    with open(os.path.join(ROOT, "verify", "action.yml"), encoding="utf-8") as f:
        return f.read()


def push_env(**extra):
    return {"MODE": "head", "SCAN_INPUT": "auto", "GITHUB_EVENT_NAME": "push", "TARGET": "HEAD", **extra}


def unrelated(count, start=1000):
    """A full page of merged same-repository pull requests whose merge commits are other commits."""
    return [pull_request(start + i, True, f"{i:040x}", REPO) for i in range(count)]


def test_auto_mode_is_head_on_every_event():
    text = _action()
    assert re.search(r'if \[ "\$MODE" = auto \]; then\s+MODE=head', text), "auto must resolve to head unconditionally"
    assert "MODE=history" not in text, "history mode is explicit, never an event default"


def test_lookup_is_the_paginated_branch_pull_request_list():
    text = _action()
    assert "scan-refs:" in text and "default: 'auto'" in text
    assert 'gh api --paginate --method GET "repos/$GITHUB_REPOSITORY/pulls"' in text
    assert '-f "base=$GITHUB_REF_NAME"' in text, "the branch name is a field gh encodes, never spliced into the URL"
    assert "pulls?" not in text
    assert "gh pr list" not in text, "gh pr list orders by creation date, has no sort option, and stops at --limit"
    assert "refs/pull/*/head" not in text, "no wildcard fetch of every pull request"
    assert "--scan-refs $SCAN" in text
    assert "GH_TOKEN: ${{ github.token }}" in text


def test_eligible_pull_request_on_page_two_is_found_and_fetched(tmp_path):
    """The reviewer's reproduction: a hundred more recently updated pull
    requests ahead of the eligible one (a delayed or re-run workflow). One
    page would miss it and fail a valid squash or rebase merge."""
    fx = Fixture(tmp_path, pr_numbers=(7,))
    fx.serve(unrelated(100), [pull_request(7, True, fx.target_sha, REPO)])
    stdout, outputs = fx.run(step_script("verify/action.yml", STEP), push_env())
    assert outputs["scan"].split() == ["refs/remotes/pull/7/head"]
    assert fx.fetched_pull_refs() == ["refs/remotes/pull/7/head"]
    assert git(fx.repo, "rev-parse", "refs/remotes/pull/7/head").stdout.strip() == fx.pr_heads[7]
    assert "eligible: pull request #7" in stdout
    (call,) = fx.gh_calls()
    assert call["url"] == "repos/org/project/pulls" and call["method"] == "GET" and call["paginate"] == "1"
    assert call["fields"] == {"state": "closed", "base": "main", "sort": "updated", "direction": "desc", "per_page": "100"}


def test_ineligible_entries_on_later_pages_are_excluded(tmp_path):
    fx = Fixture(tmp_path, pr_numbers=(7, 9, 10, 11))
    fx.serve(
        unrelated(100),
        [
            pull_request(9, False, fx.target_sha, REPO),  # closed unmerged: GitHub still fills merge_commit_sha
            pull_request(10, True, fx.target_sha, "someone/fork"),  # fork: never trusted
            pull_request(11, True, fx.target_sha, None),  # fork whose repository was deleted
        ],
        [pull_request(7, True, fx.target_sha, REPO)],
    )
    _, outputs = fx.run(step_script("verify/action.yml", STEP), push_env())
    assert outputs["scan"].split() == ["refs/remotes/pull/7/head"]
    assert fx.fetched_pull_refs() == ["refs/remotes/pull/7/head"]


def test_no_eligible_pull_request_scans_nothing(tmp_path):
    fx = Fixture(tmp_path, pr_numbers=(7,))
    fx.serve(unrelated(3), [pull_request(7, True, "d" * 40, REPO)])
    stdout, outputs = fx.run(step_script("verify/action.yml", STEP), push_env())
    assert outputs["scan"].strip() == ""
    assert fx.fetched_pull_refs() == []
    assert "nothing scanned" in stdout


def test_branch_name_with_url_characters_reaches_gh_verbatim_as_a_field(tmp_path):
    """`release/1+hotfix#2&x` is a legal ref name. Spliced into a URL it read as
    `release/1 hotfix` with the rest lost (external review of 2ee9b73); as a
    field, gh URL-encodes it and the eligible pull request is found."""
    fx = Fixture(tmp_path, pr_numbers=(7,))
    fx.serve([pull_request(7, True, fx.target_sha, REPO)])
    _, outputs = fx.run(step_script("verify/action.yml", STEP), push_env(GITHUB_REF_NAME="release/1+hotfix#2&x"))
    (call,) = fx.gh_calls()
    assert call["fields"]["base"] == "release/1+hotfix#2&x"
    assert "?" not in call["url"] and "#" not in call["url"]
    assert outputs["scan"].split() == ["refs/remotes/pull/7/head"]


def test_failed_lookup_is_told_apart_from_an_empty_one(tmp_path):
    """A 403 (token without pull-requests: read) used to be swallowed and
    reported as 'no merged pull request has this SHA' — sending the adopter
    to look for a missing pull request instead of at the token. The error is
    kept and the log says the lookup failed."""
    fx = Fixture(tmp_path, pr_numbers=(7,))
    fx.serve([pull_request(7, True, fx.target_sha, REPO)])
    stdout, outputs = fx.run(step_script("verify/action.yml", STEP), push_env(), fail_after=0)
    assert outputs["scan"].strip() == ""
    assert "::warning::pull-request lookup failed or stopped early: gh: HTTP 403" in stdout
    assert "the pull-request lookup failed before it found one; nothing scanned" in stdout
    assert "no merged same-repository pull request has" not in stdout


def test_partial_lookup_keeps_what_it_got_and_still_warns(tmp_path):
    """Rate limit hit on page two: the eligible pull request on page one is
    scanned (partial results only add candidates), and the run still carries
    the warning so a later red badge is not blamed on a missing pull request."""
    fx = Fixture(tmp_path, pr_numbers=(7,))
    fx.serve([pull_request(7, True, fx.target_sha, REPO)], unrelated(100))
    stdout, outputs = fx.run(step_script("verify/action.yml", STEP), push_env(), fail_after=1)
    assert outputs["scan"].split() == ["refs/remotes/pull/7/head"]
    assert "::warning::pull-request lookup failed or stopped early" in stdout
    assert "eligible: pull request #7" in stdout


def test_unfetchable_eligible_head_is_reported_not_silently_skipped(tmp_path):
    fx = Fixture(tmp_path, pr_numbers=(7,))  # origin has refs/pull/7/head only
    fx.serve([pull_request(8, True, fx.target_sha, REPO), pull_request(7, True, fx.target_sha, REPO)])
    stdout, outputs = fx.run(step_script("verify/action.yml", STEP), push_env())
    assert outputs["scan"].split() == ["refs/remotes/pull/7/head"]
    assert "::warning::could not fetch refs/pull/8/head" in stdout


def test_auto_scan_happens_only_on_push_events(tmp_path):
    fx = Fixture(tmp_path, pr_numbers=(7,))
    fx.serve([pull_request(7, True, fx.target_sha, REPO)])
    _, outputs = fx.run(step_script("verify/action.yml", STEP), push_env(GITHUB_EVENT_NAME="pull_request"))
    assert outputs["scan"].strip() == ""
    assert fx.gh_calls() == []
    assert fx.fetched_pull_refs() == []


def test_explicit_scan_refs_pass_through_and_none_disables(tmp_path):
    fx = Fixture(tmp_path, pr_numbers=(7,))
    fx.serve([pull_request(7, True, fx.target_sha, REPO)])
    script = step_script("verify/action.yml", STEP)
    _, outputs = fx.run(script, push_env(SCAN_INPUT="refs/remotes/pull/7/head refs/heads/topic"))
    assert outputs["scan"] == "refs/remotes/pull/7/head refs/heads/topic"
    _, outputs = fx.run(script, push_env(SCAN_INPUT="none"))
    assert outputs["scan"].strip() == ""
    assert fx.gh_calls() == [], "an explicit value never consults the API"


def test_degrades_without_gh():
    text = _action()
    assert "command -v gh" in text and "no pull-request heads scanned" in text
