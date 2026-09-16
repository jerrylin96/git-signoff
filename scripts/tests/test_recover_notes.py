"""Tests for scripts/recover_notes.py (Phase 5 Gate 0 notes recovery).

Covers: reconstruction from [SIGNOFF *] commits, payload-file ingestion for
targets whose objects don't exist locally (pre-extraction attestations),
idempotency, append semantics on pre-existing notes, cat_sort_uniq
compatibility (gsa-core.md §2.5), and malformed-target skipping.
"""

import importlib.util
import os
import subprocess

import pytest
from helpers import commit_file, git, init_repo

_SPEC = importlib.util.spec_from_file_location(
    "recover_notes",
    os.path.join(os.path.dirname(__file__), "..", "recover_notes.py"),
)
recover_notes = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(recover_notes)

MISSING_COMMIT = "453c633078ecdd82d93c33eefac4d5f4cbe2ef55"
MISSING_TREE = "83679c5222ef2c7a7b8e5c83bc56c526d7f95567"


def attestation_message(reviewed_sha, tree_sha, extra=""):
    short = reviewed_sha[:7]
    return (
        f"[SIGNOFF {short}]: human comprehension and risk attestation\n"
        "\n"
        "Signoff-Spec-Version: 1.0\n"
        "Signoff-Status: VERIFIED_BY_HUMAN\n"
        f"Signoff-Reviewed-Commit-SHA: {reviewed_sha}\n"
        f"Signoff-Reviewed-Tree-SHA: {tree_sha}\n"
        "Signoff-Verified-By: tester@example.com\n" + extra
    )


@pytest.fixture
def repo(tmp_path):
    r = init_repo(tmp_path / "repo")
    commit_file(r, "a.txt", "hello", "initial commit")
    return r


def add_attestation(repo):
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    git(repo, "commit", "--allow-empty", "-m", attestation_message(reviewed, tree))
    return reviewed, tree


def notes_show(repo, target):
    return git(repo, "notes", "--ref=signoff", "show", target).stdout


def test_reconstructs_notes_for_reviewed_commit_and_tree(repo):
    reviewed, tree = add_attestation(repo)
    assert recover_notes.recover(str(repo), "HEAD", []) == 0
    for target in (reviewed, tree):
        assert f"Signoff-Reviewed-Commit-SHA: {reviewed}" in notes_show(repo, target)


def test_idempotent_second_run_creates_no_commit(repo):
    add_attestation(repo)
    recover_notes.recover(str(repo), "HEAD", [])
    ref1 = git(repo, "rev-parse", "refs/notes/signoff").stdout.strip()
    recover_notes.recover(str(repo), "HEAD", [])
    ref2 = git(repo, "rev-parse", "refs/notes/signoff").stdout.strip()
    assert ref1 == ref2


def test_payload_file_attaches_to_missing_objects(repo, tmp_path):
    payload = tmp_path / "attestation.txt"
    payload.write_text(attestation_message(MISSING_COMMIT, MISSING_TREE))
    assert recover_notes.recover(str(repo), "HEAD", [str(payload)]) == 0
    listing = git(repo, "ls-tree", "-r", "refs/notes/signoff").stdout
    assert MISSING_COMMIT in listing
    assert MISSING_TREE in listing
    # The annotated objects don't exist locally, but the note blobs do.
    blob = [ln for ln in listing.splitlines() if MISSING_COMMIT in ln][0].split()[2]
    assert MISSING_COMMIT in git(repo, "cat-file", "blob", blob).stdout


def test_appends_to_existing_note_and_preserves_it(repo):
    reviewed, tree = add_attestation(repo)
    git(repo, "notes", "--ref=signoff", "add", "-m", "pre-existing note", reviewed)
    recover_notes.recover(str(repo), "HEAD", [])
    note = notes_show(repo, reviewed)
    assert "pre-existing note" in note
    assert f"Signoff-Reviewed-Commit-SHA: {reviewed}" in note


def test_recognizes_cat_sort_uniq_rewritten_note(repo):
    reviewed, tree = add_attestation(repo)
    recover_notes.recover(str(repo), "HEAD", [])
    # Simulate a §2.5 cat_sort_uniq merge: note becomes sorted unique lines.
    sorted_note = "\n".join(sorted(set(notes_show(repo, reviewed).splitlines()))) + "\n"
    git(repo, "notes", "--ref=signoff", "remove", reviewed)
    git(repo, "notes", "--ref=signoff", "add", "-m", sorted_note, reviewed)
    ref1 = git(repo, "rev-parse", "refs/notes/signoff").stdout.strip()
    recover_notes.recover(str(repo), "HEAD", [])
    assert git(repo, "rev-parse", "refs/notes/signoff").stdout.strip() == ref1


def test_reconstructed_ref_merges_with_cat_sort_uniq(repo, tmp_path):
    reviewed, tree = add_attestation(repo)
    recover_notes.recover(str(repo), "HEAD", [])
    # Diverged notes ref (as another clone would produce), then §2.5 merge.
    git(repo, "notes", "--ref=other", "add", "-m", "diverged note", reviewed)
    git(
        repo, "notes", "--ref=signoff", "merge", "-s", "cat_sort_uniq", "refs/notes/other"
    )
    note = notes_show(repo, reviewed)
    assert "diverged note" in note
    assert f"Signoff-Reviewed-Commit-SHA: {reviewed}" in note


def test_malformed_target_skipped(repo, capsys):
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(
        repo,
        "commit",
        "--allow-empty",
        "-m",
        attestation_message(reviewed, "b96a7889c2258c1f1282cef20f05accc"),  # 32 hex
    )
    recover_notes.recover(str(repo), "HEAD", [])
    assert "malformed" in capsys.readouterr().out
    listing = git(repo, "ls-tree", "-r", "refs/notes/signoff").stdout
    assert "b96a7889" not in listing


def test_non_attestation_commits_ignored(repo):
    commit_file(repo, "b.txt", "x", "mentions [SIGNOFF abc1234]: in body only\n\nnot a subject match")
    reviewed, tree = add_attestation(repo)
    recover_notes.recover(str(repo), "HEAD", [])
    listing = git(repo, "ls-tree", "-r", "refs/notes/signoff").stdout
    assert len(listing.splitlines()) == 2  # reviewed commit + tree only


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _full_history_main_ref():
    """The ref in this checkout — local `main` or remote-tracking `origin/main`
    — that carries the 2026-08 attestations, or None on shallow clones and on
    checkouts without main, where the live-repo test skips. CI fetches full
    history so it runs there (see CONTRIBUTING.md)."""
    for ref in ("refs/heads/main", "refs/remotes/origin/main"):
        proc = subprocess.run(
            ["git", "log", "--format=%s", r"--grep=^\[SIGNOFF ", ref],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and "[SIGNOFF 979cb45]" in proc.stdout:
            return ref
    return None


MAIN_REF = _full_history_main_ref()


@pytest.mark.skipif(MAIN_REF is None, reason="shallow clone or stale local main")
def test_end_to_end_against_this_repo(tmp_path):
    """The workflow's exact invocation, against a local clone of this repo."""
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", REPO_ROOT, str(clone)], check=True, capture_output=True
    )
    # `git clone` only turns the source's *local* branches into `origin/*`. A
    # pull-request checkout in CI has main solely as `origin/main`, so the
    # clone would have no `origin/main` at all; fetch it explicitly from
    # whichever ref the guard found.
    git(clone, "fetch", "-q", "origin", f"+{MAIN_REF}:refs/remotes/origin/main")
    git(clone, "config", "user.email", "tester@example.com")
    git(clone, "config", "user.name", "Tester")
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "production_attestation.txt")
    assert recover_notes.recover(str(clone), "origin/main", [fixture]) == 0
    # Recent attestations: notes resolve on the reviewed commits in main.
    for reviewed in ("a4d1c6c", "daf4939", "979cb45"):
        assert "VERIFIED_BY_HUMAN" in notes_show(clone, reviewed)
    # Pre-extraction production attestation: entry present for missing object.
    listing = git(clone, "ls-tree", "-r", "refs/notes/signoff").stdout
    assert MISSING_COMMIT in listing


def test_payload_with_repeated_target_trailer_is_skipped_loudly(repo, capsys):
    """An attestation whose Reviewed-Tree-SHA appears twice is not one
    attestation; recovery must not attach it to either tree (a second value
    smuggled via free text would otherwise attach a note to an unreviewed tree)."""
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    git(
        repo,
        "commit",
        "--allow-empty",
        "-m",
        attestation_message(reviewed, tree, extra=f"Signoff-Reviewed-Tree-SHA: {'9' * 40}\n"),
    )
    assert recover_notes.recover(str(repo), "HEAD", []) == 0
    out = capsys.readouterr().out
    assert "skip" in out and "Signoff-Reviewed-Tree-SHA" in out
    assert git(repo, "notes", "--ref=signoff", "show", "9" * 40, check=False).returncode != 0
    assert git(repo, "notes", "--ref=signoff", "show", tree, check=False).returncode != 0


# --- evidence, not trailers (external review 2026-09-16) ---------------------------


def _verify_module():
    spec = importlib.util.spec_from_file_location(
        "verify_signoff",
        os.path.join(os.path.dirname(__file__), "..", "..", "skills", "git-signoff", "verify_signoff.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _forged_attestation_of(repo, target_commit, target_tree, on_branch="forge"):
    """An empty [SIGNOFF] commit on an unrelated branch whose trailers name the
    target's commit and tree. Structurally it attests its own parent, which is
    not the target."""
    git(repo, "checkout", "-q", "-b", on_branch)
    commit_file(repo, "unrelated.txt", "different content", "unrelated work")
    git(repo, "commit", "--allow-empty", "-m", attestation_message(target_commit, target_tree))
    forged = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "-q", "main")
    return forged


def test_forged_tree_trailer_earns_no_note_and_target_stays_unattested(repo, capsys, monkeypatch):
    """The reviewer's construction: a [SIGNOFF] commit on an unrelated tree whose
    trailer names the target's tree. Recovery used to attach a tree note on the
    trailer's say-so, after which the unchanged verifier accepted the target."""
    monkeypatch.setenv("GIT_SIGNOFF_NO_UPDATE_CHECK", "1")
    commit_file(repo, "b.txt", "target", "target: never attested")
    target = git(repo, "rev-parse", "HEAD").stdout.strip()
    target_tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    _forged_attestation_of(repo, target, target_tree)
    assert recover_notes.recover(str(repo), "forge", []) == 0
    out = capsys.readouterr().out
    assert "skip" in out and "not the declared reviewed commit" in out
    listing = git(repo, "ls-tree", "-r", "refs/notes/signoff", check=False).stdout
    assert target not in listing and target_tree not in listing
    ok, lines = _verify_module().check_head(str(repo), target)
    assert not ok, lines


def test_declared_tree_that_is_not_the_parents_tree_attaches_to_the_commit_only(repo, capsys):
    """Eight attestations in this repository's own early history (2026-08-01..05,
    the bash-heredoc skill) declare a tree no reviewed commit has. Their commit
    anchor is earned; their tree anchor is not."""
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    wrong_tree = "f" * 40
    git(repo, "commit", "--allow-empty", "-m", attestation_message(reviewed, wrong_tree))
    assert recover_notes.recover(str(repo), "HEAD", []) == 0
    out = capsys.readouterr().out
    assert "tree-only-skip" in out and wrong_tree[:7] in out
    listing = git(repo, "ls-tree", "-r", "refs/notes/signoff").stdout
    assert reviewed in listing and wrong_tree not in listing


def test_non_empty_attestation_commit_is_skipped(repo, capsys):
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    (repo / "smuggled.txt").write_text("payload")
    git(repo, "add", "smuggled.txt")
    git(repo, "commit", "-m", attestation_message(reviewed, tree))
    assert recover_notes.recover(str(repo), "HEAD", []) == 0
    assert "not an empty commit" in capsys.readouterr().out
    assert git(repo, "rev-parse", "-q", "--verify", "refs/notes/signoff", check=False).returncode != 0


def test_attestation_after_a_merge_commit_is_skipped(repo, capsys):
    """An attestation committed on the integration branch after merging, naming
    the PR head: real in this repository's history (c2754c7), but its parent is
    the merge commit, so the commit object does not back the claim."""
    git(repo, "checkout", "-q", "-b", "feature")
    commit_file(repo, "f.txt", "feature", "feature work")
    pr_head = git(repo, "rev-parse", "HEAD").stdout.strip()
    pr_tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "Merge feature", "feature")
    git(repo, "commit", "--allow-empty", "-m", attestation_message(pr_head, pr_tree))
    assert recover_notes.recover(str(repo), "HEAD", []) == 0
    out = capsys.readouterr().out
    assert "skip" in out and "not the declared reviewed commit" in out
    assert git(repo, "rev-parse", "-q", "--verify", "refs/notes/signoff", check=False).returncode != 0


def test_two_parent_signoff_subject_is_skipped(repo, capsys):
    git(repo, "checkout", "-q", "-b", "side")
    commit_file(repo, "s.txt", "side", "side work")
    git(repo, "checkout", "-q", "main")
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    git(repo, "merge", "-q", "--no-ff", "-m", attestation_message(reviewed, tree), "side")
    assert recover_notes.recover(str(repo), "HEAD", []) == 0
    assert "2 parents" in capsys.readouterr().out
    assert git(repo, "rev-parse", "-q", "--verify", "refs/notes/signoff", check=False).returncode != 0


def test_valid_attestation_from_a_pull_request_head_recovers_a_squash_tip(repo, tmp_path, monkeypatch):
    """The positive case the whole design rests on: the PR head carries a sound
    attestation; the squash tip has the same tree; recovery over the PR ref
    reconstructs the tree note; the verifier then passes the squash tip."""
    monkeypatch.setenv("GIT_SIGNOFF_NO_UPDATE_CHECK", "1")
    git(repo, "checkout", "-q", "-b", "feature")
    commit_file(repo, "f.txt", "feature", "feature work")
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    digest = "Signoff-Transcript-Digest: sha256:" + "0123456789abcdef" * 4 + "\n"  # a complete payload, as the producer writes
    git(repo, "commit", "--allow-empty", "-m", attestation_message(reviewed, tree, extra=digest))
    pr_head = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "update-ref", "refs/pull/1/head", pr_head)  # what GitHub retains
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--squash", "feature")
    git(repo, "commit", "-q", "-m", "squash: feature")
    squash = git(repo, "rev-parse", "HEAD").stdout.strip()
    verify = _verify_module()
    ok, _ = verify.check_head(str(repo), squash)
    assert not ok  # no note yet, attestation commit not in main's history
    assert recover_notes.recover(str(repo), "refs/pull/1/head", []) == 0
    ok, lines = verify.check_head(str(repo), squash)
    assert ok and "note on tree" in " ".join(lines)
    # and a later change to the tree is not covered
    commit_file(repo, "g.txt", "more", "after the squash")
    ok, _ = verify.check_head(str(repo), git(repo, "rev-parse", "HEAD").stdout.strip())
    assert not ok
