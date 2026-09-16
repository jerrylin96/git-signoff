#!/usr/bin/env python3
"""Reconstruct refs/notes/signoff from [SIGNOFF *] attestation messages.

Phase 5 Gate 0 (docs/roadmap.md): cloud sessions cannot push notes refs
through the session git proxy (403), so attestation notes have never reached
origin. This script rebuilds the notes ref deterministically from the
attestation payloads already present in history — plus optional payload
files, e.g. the production-attestation fixture whose attestation commit
predates the repo extraction — and runs in GitHub Actions
(.github/workflows/notes-recovery.yml), where pushes are unrestricted.

Per SKILL.md Section 5, each payload attaches to its
Signoff-Reviewed-Commit-SHA and Signoff-Reviewed-Tree-SHA. Pre-extraction
payloads may reference objects that no longer exist in this repository, so
the notes tree is built with plumbing: a note is a tree entry named by the
annotated object's hex SHA, and the object need not exist locally —
downstream clones that do carry it (e.g. the repo this one was extracted
from) can resolve the note after fetching the ref.

Idempotent: payloads already present in a note — including notes rewritten
by a cat_sort_uniq merge (gsa-core.md §2.5), which sorts lines — are
detected by line-set containment and skipped; an up-to-date ref produces no
new commit. Appends use the blank-line separator of `git notes append`.

Evidence, not trailers (external review, 2026-09-16): a note is what makes
a tree "attested" to every verifier that reads notes, so recovery attaches
one only where the *commit object* backs the claim, never on the trailer's
say-so. A commit-sourced payload attaches to its reviewed commit only if the
attestation commit is empty and that reviewed commit is its sole parent — the
shape the producer writes and check_head verifies at HEAD — and to its
declared tree only if that tree is the parent's actual tree. A [SIGNOFF]
commit on an unrelated tree whose trailer names some target's tree would
otherwise mint a tree note that turns an unattested target green.
Payload files are the explicit exception: they exist for attestations whose
objects are gone, are committed to this repository, and are trusted as such.
"""

import argparse
import re
import subprocess
import sys

NOTES_REF = "refs/notes/signoff"
SUBJECT_RE = re.compile(r"^\[SIGNOFF [0-9a-f]{7,40}\]: ")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TARGET_TRAILERS = ("Signoff-Reviewed-Commit-SHA", "Signoff-Reviewed-Tree-SHA")


def git(repo, *args, check=True, data=None):
    proc = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, input=data
    )
    if check and proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def attestation_payloads(repo, ref):
    """Yield (label, payload, sha) for every attestation commit in ref's history."""
    shas = git(
        repo, "log", ref, "--format=%H", r"--grep=^\[SIGNOFF "
    ).stdout.split()
    for sha in shas:
        payload = git(repo, "log", "-1", "--format=%B", sha).stdout.strip("\n")
        if SUBJECT_RE.match(payload):
            yield sha[:7], payload, sha


def payload_targets(label, payload):
    """Extract valid 40-hex attachment targets from a payload's trailers.

    One attestation names exactly one reviewed commit and one reviewed tree
    (gsa-core §2.3). A payload that repeats either trailer is skipped whole:
    attaching it would put a note on whichever tree the extra line names,
    which is exactly how a value smuggled through free text would turn into
    a passing verification for an unreviewed commit.
    """
    found = {}
    for trailer in TARGET_TRAILERS:
        found[trailer] = [
            m.group(1) for m in re.finditer(rf"^{trailer}: (\S+)$", payload, re.MULTILINE)
        ]
    repeated = [t for t, shas in found.items() if len(shas) > 1]
    if repeated:
        print(f"skip {label}: repeated {', '.join(repeated)} (one attestation carries exactly one)")
        return []
    targets = []
    for trailer, shas in found.items():
        for sha in shas:
            if not SHA_RE.match(sha):
                print(f"skip {label}: malformed {trailer} {sha!r}")
            elif sha not in targets:
                targets.append(sha)
    return targets


def _tree_of(repo, obj):
    proc = git(repo, "rev-parse", "-q", "--verify", f"{obj}^{{tree}}", check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def commit_anchors(repo, label, sha, payload):
    """Anchors a commit-sourced payload has *earned*: the subset of its declared
    targets that the attestation commit object itself corroborates.

    Rules (the shape the producer writes and the verifier's head-mode check
    demands): exactly one parent; the attestation commit is empty (its tree
    is its parent's); the declared reviewed commit is that parent. A payload
    failing any of these is skipped whole. The declared tree is attached only
    when it is the parent's actual tree; otherwise the note goes on the commit
    alone and the mismatch is reported — a tree note is a claim about a code
    state, and only the object can back it.
    """
    declared = payload_targets(label, payload)
    if not declared:
        return []
    reviewed = re.search(r"^Signoff-Reviewed-Commit-SHA: (\S+)$", payload, re.MULTILINE)
    tree = re.search(r"^Signoff-Reviewed-Tree-SHA: (\S+)$", payload, re.MULTILINE)
    reviewed = reviewed.group(1) if reviewed and reviewed.group(1) in declared else None
    tree = tree.group(1) if tree and tree.group(1) in declared else None
    parents = git(repo, "log", "-1", "--format=%P", sha).stdout.split()
    if len(parents) != 1:
        print(f"skip {label}: {len(parents)} parents (an attestation commit has exactly one)")
        return []
    parent = parents[0]
    parent_tree = _tree_of(repo, parent)
    if _tree_of(repo, sha) != parent_tree:
        print(f"skip {label}: not an empty commit (its tree differs from its parent's)")
        return []
    if reviewed != parent:
        print(
            f"skip {label}: parent is {parent[:7]}, not the declared reviewed commit "
            f"{(reviewed or 'none')[:7]} (an attestation sits on the commit it attests)"
        )
        return []
    anchors = [reviewed]
    if tree is not None:
        if tree == parent_tree:
            anchors.append(tree)
        else:
            print(
                f"tree-only-skip {label}: declared Reviewed-Tree-SHA {tree[:7]} is not the reviewed "
                f"commit's tree {parent_tree[:7]}; attaching to the commit only"
            )
    return anchors


def read_notes(repo):
    """Current notes as {target-sha: note-text}; tolerates fanout paths."""
    if git(repo, "rev-parse", "-q", "--verify", NOTES_REF, check=False).returncode != 0:
        return {}
    notes = {}
    for line in git(repo, "ls-tree", "-r", NOTES_REF).stdout.splitlines():
        meta, path = line.split("\t", 1)
        blob = meta.split()[2]
        name = path.replace("/", "")
        if SHA_RE.match(name):
            notes[name] = git(repo, "cat-file", "blob", blob).stdout
    return notes


def contains(note, payload):
    """Payload already present? Line-set containment survives cat_sort_uniq."""
    lines = {ln for ln in payload.splitlines() if ln.strip()}
    return lines <= {ln for ln in note.splitlines()}


def write_notes(repo, notes, message):
    """Write {target: text} as a flat notes tree; commit only on change."""
    entries = []
    for target, text in sorted(notes.items()):
        blob = git(repo, "hash-object", "-w", "--stdin", data=text).stdout.strip()
        entries.append(f"100644 blob {blob}\t{target}")
    tree = git(repo, "mktree", data="".join(e + "\n" for e in entries)).stdout.strip()

    old = git(repo, "rev-parse", "-q", "--verify", NOTES_REF, check=False)
    parent = old.stdout.strip() if old.returncode == 0 else None
    if parent and git(repo, "rev-parse", f"{parent}^{{tree}}").stdout.strip() == tree:
        return None
    commit = git(
        repo, "commit-tree", tree, *(["-p", parent] if parent else []), "-m", message
    ).stdout.strip()
    git(repo, "update-ref", NOTES_REF, commit)
    return commit


def recover(repo, ref, payload_files):
    # (label, payload, anchors): anchors are earned for commit-sourced payloads
    # (commit_anchors) and taken from the trailers for trusted payload files.
    payloads = [
        (label, payload, commit_anchors(repo, label, sha, payload))
        for label, payload, sha in attestation_payloads(repo, ref)
    ]
    for path in payload_files:
        with open(path, encoding="utf-8") as f:
            text = f.read().strip("\n")
        if SUBJECT_RE.match(text):
            payloads.append((path, text, payload_targets(path, text)))
        else:
            print(f"skip {path}: not an attestation payload")

    notes = read_notes(repo)
    attached = 0
    for label, payload, anchors in payloads:
        for target in anchors:
            note = notes.get(target)
            if note is not None and contains(note, payload):
                print(f"present {target[:7]} <- {label}")
            elif note is not None:
                notes[target] = note.rstrip("\n") + "\n\n" + payload + "\n"
                print(f"append {target[:7]} <- {label}")
                attached += 1
            else:
                notes[target] = payload + "\n"
                print(f"attach {target[:7]} <- {label}")
                attached += 1

    if not notes:
        print("no attestation payloads found; nothing to do")
        return 0
    commit = write_notes(
        repo, notes, f"Recover signoff notes from attestation messages in {ref}"
    )
    print(
        f"{NOTES_REF} -> {commit[:12]} ({attached} attachment(s))"
        if commit
        else f"{NOTES_REF} up to date"
    )
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", default=".", help="repository to operate on")
    p.add_argument("--ref", default="HEAD", help="history to scan for [SIGNOFF *] commits")
    p.add_argument(
        "--payload-file",
        action="append",
        default=[],
        help="extra attestation payload file (repeatable)",
    )
    args = p.parse_args(argv)
    return recover(args.repo, args.ref, args.payload_file)


if __name__ == "__main__":
    sys.exit(main())
