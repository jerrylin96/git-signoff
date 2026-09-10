"""Release metadata must agree with itself.

The tree a release tag points at is what Zenodo archives, so the version
in `CITATION.cff` has to match `pyproject.toml` at every commit, and the
top `CHANGELOG.md` heading has to be either an "Unreleased" section or the
current version — never a stale earlier one. Standard library only (no
tomllib on Python 3.10): both files are read with regular expressions.
"""

import datetime
import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _read(name):
    with open(os.path.join(REPO_ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def _pyproject_version():
    match = re.search(r'^version\s*=\s*"([^"]+)"\s*$', _read("pyproject.toml"), re.M)
    assert match, "pyproject.toml has no version"
    return match.group(1)


def _cff_field(name):
    match = re.search(rf"^{re.escape(name)}:\s*(.+?)\s*$", _read("CITATION.cff"), re.M)
    assert match, f"CITATION.cff has no top-level '{name}'"
    return match.group(1).strip().strip('"')


def test_citation_version_matches_pyproject():
    assert _cff_field("version") == _pyproject_version()


def test_citation_date_released_is_a_calendar_date():
    datetime.date.fromisoformat(_cff_field("date-released"))


def test_citation_points_at_this_repository():
    assert _cff_field("repository-code") == "https://github.com/jerrylin96/git-signoff"


def test_changelog_top_heading_is_unreleased_or_current_version():
    headings = re.findall(r"^## (.+)$", _read("CHANGELOG.md"), re.M)
    assert headings, "CHANGELOG.md has no '## ' headings"
    top = headings[0]
    version = _pyproject_version()
    assert top.startswith("Unreleased") or top.startswith(f"v{version} "), (
        f"top CHANGELOG heading {top!r} names neither 'Unreleased' nor v{version}"
    )


def test_readme_citation_names_current_version():
    assert f"(v{_pyproject_version()})" in _read("README.md")


def test_readme_carries_the_citation_doi():
    doi = _cff_field("doi")
    assert re.fullmatch(r"10\.\d{4,9}/\S+", doi), f"CITATION.cff doi {doi!r} is not a DOI"
    assert f"https://doi.org/{doi}" in _read("README.md")


def test_readme_carries_the_concept_doi():
    """The concept DOI (all versions) is declared once in CITATION.cff under
    identifiers and must be the one the README recommends citing."""
    match = re.search(r"^\s+value:\s*(10\.\d{4,9}/\S+)\s*$", _read("CITATION.cff"), re.M)
    assert match, "CITATION.cff declares no concept DOI under identifiers"
    concept = match.group(1)
    assert concept != _cff_field("doi"), "concept DOI must differ from the version DOI"
    readme = _read("README.md")
    assert f"https://doi.org/{concept}" in readme and f"`{concept}`" in readme
