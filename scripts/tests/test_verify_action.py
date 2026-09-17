"""Contract tests for verify/action.yml (verify-v1.5): head mode on every event,
and evidence eligibility resolved from the API — the merged, same-repository
pull request whose merge commit is the target — never from a ref-name pattern
(docs/attest-any-target.md §2.13, §3.3)."""

import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _action():
    with open(os.path.join(ROOT, "verify", "action.yml"), encoding="utf-8") as f:
        return f.read()


def test_auto_mode_is_head_on_every_event():
    text = _action()
    assert re.search(r'if \[ "\$MODE" = auto \]; then\s+MODE=head', text), "auto must resolve to head unconditionally"
    assert "MODE=history" not in text, "history mode is explicit, never an event default"


def test_scan_refs_input_and_eligibility_rule():
    text = _action()
    assert "scan-refs:" in text and "default: 'auto'" in text
    # eligibility: merged PRs into the pushed branch whose merge commit is the target, from this repository
    assert "gh pr list --state merged --base \"$GITHUB_REF_NAME\"" in text
    assert ".mergeCommit.oid == \\\"$SHA\\\"" in text
    assert '(.headRepositoryOwner.login + \\"/\\" + .headRepository.name) == \\"$GITHUB_REPOSITORY\\"' in text
    # exactly the eligible heads are fetched, from the repository's own refs/pull namespace
    assert 'git fetch -q origin "+refs/pull/$N/head:refs/remotes/pull/$N/head"' in text
    assert "refs/pull/*/head" not in text, "no wildcard fetch of every pull request"
    # and passed to the verifier
    assert "--scan-refs $SCAN" in text
    assert "GH_TOKEN: ${{ github.token }}" in text


def test_auto_scan_only_on_push_events_and_degrades_without_gh():
    text = _action()
    assert '[ "$GITHUB_EVENT_NAME" = push ]' in text
    assert "command -v gh" in text and "no pull-request heads scanned" in text


def test_explicit_scan_refs_pass_through_and_none_disables():
    text = _action()
    assert '[ "$SCAN_INPUT" != none ]' in text and 'SCAN="$SCAN_INPUT"' in text
