"""Run one step of a composite action the way the runner does: its `run:`
block in bash, against a real `origin` and a stand-in `gh` that serves
fixture pages.

The actions' pull-request lookup is shell, so a text assertion on the YAML
proves only that the text is there. This extracts the step's script from the
action file (never a hand copy, which would drift), points PATH at a `gh` that
answers `gh api [--paginate] URL --jq FILTER` from `page1.json`, `page2.json`,
... — walking every page only under `--paginate`, as gh follows Link headers
only then — and lets the real `git fetch` run against a bare origin that
carries `refs/pull/N/head`. Skipped where jq is not installed (GitHub runners
have it)."""

import json
import os
import shutil
import stat
import subprocess

import pytest
from helpers import commit_file, git, init_repo

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

MOCK_GH = r"""#!/usr/bin/env bash
# Stand-in for `gh api [--paginate] [--method M] URL [-f k=v] [-F k=v] --jq FILTER`
# (see action_harness.py). Each call appends one record to $MOCK_LOG:
# `url <endpoint>`, `method <M>`, `paginate <0|1>`, one `field <k>=<v>` per
# parameter, exactly as received — what gh would URL-encode — then `end`.
set -eu
paginate=0 filter="" url="" method=""
fields=()
while [ $# -gt 0 ]; do
  case "$1" in
    api) ;;
    --paginate) paginate=1 ;;
    --method|-X) method="$2"; shift ;;
    -f|--raw-field|-F|--field) fields+=("$2"); shift ;;
    --jq) filter="$2"; shift ;;
    *) url="$1" ;;
  esac
  shift
done
{
  printf 'url %s\n' "$url"
  printf 'method %s\n' "$method"
  printf 'paginate %s\n' "$paginate"
  for f in "${fields[@]+"${fields[@]}"}"; do printf 'field %s\n' "$f"; done
  printf 'end\n'
} >> "$MOCK_LOG"
if [ "$paginate" = 1 ]; then
  for page in "$MOCK_PAGES"/page*.json; do jq -r "$filter" "$page"; done
else
  jq -r "$filter" "$MOCK_PAGES/page1.json"
fi
"""


def step_script(action_relpath, step_name):
    """The `run: |` block of the named step, dedented, from the action file."""
    with open(os.path.join(ROOT, action_relpath), encoding="utf-8") as f:
        lines = f.read().splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == f"- name: {step_name}")
    run_at = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    indent = len(lines[run_at]) - len(lines[run_at].lstrip())
    body = []
    for line in lines[run_at + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        body.append(line[indent + 2 :] if line.strip() else "")
    return "\n".join(body) + "\n"


def pull_request(number, merged, merge_sha, head_repo):
    """One entry of GET /repos/{owner}/{repo}/pulls, reduced to the fields the
    filters read. GitHub fills merge_commit_sha for closed unmerged pull
    requests too (a test merge), and head.repo is null when a fork was deleted."""
    return {
        "number": number,
        "merged_at": "2026-09-17T00:00:00Z" if merged else None,
        "merge_commit_sha": merge_sha,
        "head": {"repo": None if head_repo is None else {"full_name": head_repo}},
    }


class Fixture:
    """A clone of a bare origin whose refs/pull/N/head exist for `pr_numbers`,
    plus the mock gh and its page directory."""

    def __init__(self, tmp_path, pr_numbers=(7,)):
        if not shutil.which("jq"):
            pytest.skip("jq not installed")
        self.tmp = tmp_path
        builder = init_repo(tmp_path / "builder")
        commit_file(builder, "a.txt", "hello", "initial commit")
        origin = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        subprocess.run(["git", "-C", str(origin), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
        git(builder, "remote", "add", "origin", str(origin))
        git(builder, "push", "-q", "origin", "main")
        self.pr_heads = {}
        for n in pr_numbers:
            git(builder, "checkout", "-q", "-b", f"pr{n}", "main")
            commit_file(builder, f"pr{n}.txt", f"work {n}", f"pull request {n}")
            self.pr_heads[n] = git(builder, "rev-parse", "HEAD").stdout.strip()
            git(builder, "push", "-q", "origin", f"HEAD:refs/pull/{n}/head")
        # the runner's checkout: a clone, which fetches no refs/pull objects
        self.repo = tmp_path / "work"
        subprocess.run(["git", "clone", "-q", str(origin), str(self.repo)], check=True)
        self.target_sha = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        self.pages = tmp_path / "pages"
        self.pages.mkdir()
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(MOCK_GH, encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        self.bin_dir = bin_dir
        self.log = tmp_path / "gh.log"
        self.log.touch()

    def serve(self, *pages):
        for i, page in enumerate(pages, start=1):
            (self.pages / f"page{i}.json").write_text(json.dumps(page), encoding="utf-8")

    def run(self, script, env):
        output = self.tmp / "github_output"
        output.write_text("", encoding="utf-8")
        full_env = {
            **os.environ,
            "PATH": f"{self.bin_dir}{os.pathsep}{os.environ['PATH']}",
            "MOCK_PAGES": str(self.pages),
            "MOCK_LOG": str(self.log),
            "GITHUB_OUTPUT": str(output),
            "GITHUB_REPOSITORY": "org/project",
            "GITHUB_REF_NAME": "main",
            "GH_TOKEN": "test-token",
            **env,
        }
        proc = subprocess.run(["bash", "-eo", "pipefail", "-c", script], cwd=self.repo, env=full_env, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        outputs = dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines() if "=" in line)
        return proc.stdout, outputs

    def gh_calls(self):
        """One dict per gh invocation: url, method, paginate, fields (dict)."""
        calls, current = [], None
        for line in self.log.read_text(encoding="utf-8").splitlines():
            kind, _, value = line.partition(" ")
            if kind == "url":
                current = {"url": value, "fields": {}}
            elif kind == "end":
                calls.append(current)
            elif kind == "field":
                key, _, val = value.partition("=")
                current["fields"][key] = val
            else:
                current[kind] = value
        return calls

    def fetched_pull_refs(self):
        proc = git(self.repo, "for-each-ref", "--format=%(refname)", "refs/remotes/pull/")
        return proc.stdout.split()
