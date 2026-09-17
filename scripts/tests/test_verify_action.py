"""Contract tests for verify/action.yml (verify-v1.6): head mode on every event,
and evidence eligibility resolved from the API — the merged, same-repository
pull request whose merge commit is the target — never from a ref-name pattern
(docs/attest-any-target.md §2.13, §3.3). The jq filter is extracted from the
action and executed, as the workflow's own shell would, against fixture pull
requests (skipped where jq is not installed)."""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPO = "org/project"
SHA = "a" * 40


def _action():
    with open(os.path.join(ROOT, "verify", "action.yml"), encoding="utf-8") as f:
        return f.read()


def jq_filter(action_text, **shell_vars):
    """The `--jq "..."` argument as bash would hand it to gh: escaped quotes
    unescaped, `$NAME` expanded from shell_vars."""
    m = re.search(r'--jq "((?:[^"\\]|\\.)*)"', action_text)
    assert m, "no --jq filter in the action"
    text = m.group(1).replace('\\"', '"')
    for name, value in shell_vars.items():
        text = text.replace(f"${name}", value)
    assert "$" not in text, f"unexpanded shell variable in jq filter: {text}"
    return text


def run_jq(filter_text, data):
    if not shutil.which("jq"):
        pytest.skip("jq not installed")
    proc = subprocess.run(["jq", "-r", filter_text], input=json.dumps(data), capture_output=True, text=True, check=True)
    return proc.stdout.split()


def pull_request(number, merged, merge_sha, head_repo):
    return {
        "number": number,
        "merged_at": "2026-09-17T00:00:00Z" if merged else None,
        "merge_commit_sha": merge_sha,
        "head": {"repo": None if head_repo is None else {"full_name": head_repo}},
    }


# What the pulls list can hold for a pushed merge commit SHA.
FIXTURE = [
    pull_request(7, True, SHA, REPO),  # the eligible one
    pull_request(8, True, "b" * 40, REPO),  # merged elsewhere
    pull_request(9, False, SHA, REPO),  # closed unmerged; GitHub still fills merge_commit_sha
    pull_request(10, True, SHA, "someone/fork"),  # fork: never trusted
    pull_request(11, True, SHA, None),  # fork whose repository was deleted
]


def test_auto_mode_is_head_on_every_event():
    text = _action()
    assert re.search(r'if \[ "\$MODE" = auto \]; then\s+MODE=head', text), "auto must resolve to head unconditionally"
    assert "MODE=history" not in text, "history mode is explicit, never an event default"


def test_eligibility_lookup_reads_the_most_recently_updated_pull_requests():
    text = _action()
    assert "scan-refs:" in text and "default: 'auto'" in text
    # the pushed branch's closed pull requests, newest update first, so the
    # pull request whose merge was just pushed is on the page however old it is
    assert 'gh api "repos/$GITHUB_REPOSITORY/pulls?state=closed&base=$GITHUB_REF_NAME&sort=updated&direction=desc&per_page=100"' in text
    assert "gh pr list" not in text, "gh pr list orders by creation date and has no sort option"
    assert "--paginate" not in text, "one page suffices here; recovery is the exhaustive walk"
    # exactly the eligible heads are fetched, from the repository's own refs/pull namespace
    assert 'git fetch -q origin "+refs/pull/$N/head:refs/remotes/pull/$N/head"' in text
    assert "refs/pull/*/head" not in text, "no wildcard fetch of every pull request"
    # and passed to the verifier
    assert "--scan-refs $SCAN" in text
    assert "GH_TOKEN: ${{ github.token }}" in text


def test_eligibility_filter_selects_only_the_merged_same_repository_pull_request_for_the_sha():
    numbers = run_jq(jq_filter(_action(), SHA=SHA, GITHUB_REPOSITORY=REPO), FIXTURE)
    assert numbers == ["7"]


def test_eligibility_filter_yields_nothing_for_an_unrelated_sha():
    assert run_jq(jq_filter(_action(), SHA="c" * 40, GITHUB_REPOSITORY=REPO), FIXTURE) == []


def test_auto_scan_only_on_push_events_and_degrades_without_gh():
    text = _action()
    assert '[ "$GITHUB_EVENT_NAME" = push ]' in text
    assert "command -v gh" in text and "no pull-request heads scanned" in text


def test_explicit_scan_refs_pass_through_and_none_disables():
    text = _action()
    assert '[ "$SCAN_INPUT" != none ]' in text and 'SCAN="$SCAN_INPUT"' in text
