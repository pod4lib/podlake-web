"""
Tests for the publish decision in ``podlake_web.tasks``.

This is the logic a weekly cron job leans on with nobody watching, and it is wrong
in two expensive directions. Too loose and every run commits a diff — because each
artifact carries a fresh ``generated_at`` — filling the history with churn that
reads like data changes. Too strict and a real update is silently discarded and the
dashboard quietly stops moving. Neither failure announces itself, hence these tests.

They build throwaway git repos in tmp_path rather than touching the real one, in the
same spirit as test_extract.py building small DuckLakes.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from podlake_web import tasks

ARTIFACT = "site/src/data/overview.json"


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout


def _write(repo: Path, rel: str, payload: dict) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with one committed artifact, mimicking the published snapshot."""
    repo = tmp_path / "podlake-web"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "test")
    _git(repo, "config", "user.email", "test@example.invalid")
    _write(repo, ARTIFACT, {"generated_at": "2026-01-01T00:00:00+00:00", "records": 10})
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "initial")
    return repo


def test_no_change_at_all_reports_nothing(repo: Path) -> None:
    diffstat, substantive = tasks.substantive_diff(cwd=repo)
    assert diffstat == ""
    assert substantive == ""


def test_timestamp_only_change_is_not_substantive(repo: Path) -> None:
    """A re-run that finds identical numbers must not look like a data change."""
    _write(repo, ARTIFACT, {"generated_at": "2026-06-01T00:00:00+00:00", "records": 10})

    diffstat, substantive = tasks.substantive_diff(cwd=repo)

    # git does see a change — that is exactly the trap this guards.
    assert diffstat != ""
    assert substantive == ""


def test_real_change_is_substantive(repo: Path) -> None:
    _write(repo, ARTIFACT, {"generated_at": "2026-06-01T00:00:00+00:00", "records": 11})

    _diffstat, substantive = tasks.substantive_diff(cwd=repo)

    assert substantive != ""
    assert '"records": 11' in substantive


def test_a_number_changing_to_zero_still_counts(repo: Path) -> None:
    """Guards against any falsiness check creeping into the diff filter."""
    _write(repo, ARTIFACT, {"generated_at": "2026-01-01T00:00:00+00:00", "records": 0})

    _diffstat, substantive = tasks.substantive_diff(cwd=repo)

    assert '"records": 0' in substantive


def test_new_artifact_file_is_substantive(repo: Path) -> None:
    """An added artifact is untracked, so it must be picked up by intent-to-add."""
    _write(repo, "site/src/data/brand_new.json", {"generated_at": "x", "records": 1})
    _git(repo, "add", "-N", "site/src/data/brand_new.json")

    _diffstat, substantive = tasks.substantive_diff(cwd=repo)

    assert '"records": 1' in substantive


def test_generated_at_only_matches_the_field_not_the_value(repo: Path) -> None:
    """
    The filter drops lines containing the generated_at *key*.

    A data value that merely mentions the string must still register, or an
    artifact describing its own provenance could mask a real change.
    """
    _write(
        repo,
        ARTIFACT,
        {"generated_at": "2026-01-01T00:00:00+00:00", "note": "see generated_at"},
    )

    _diffstat, substantive = tasks.substantive_diff(cwd=repo)

    assert substantive != "", "a changed non-timestamp field was wrongly filtered out"


class TestUnrelatedChanges:
    """
    The refresh commits `git add -- site/src/data`, so anything else in the tree
    would be stranded and the pushed commit would not match the code that made it.
    """

    def test_clean_tree_has_none(self, repo: Path) -> None:
        assert tasks.unrelated_changes(cwd=repo) == []

    def test_artifact_changes_are_not_unrelated(self, repo: Path) -> None:
        _write(repo, ARTIFACT, {"generated_at": "later", "records": 12})
        assert tasks.unrelated_changes(cwd=repo) == []

    def test_source_edit_is_unrelated(self, repo: Path) -> None:
        (repo / "src").mkdir(parents=True, exist_ok=True)
        (repo / "src" / "thing.py").write_text("x = 1\n")
        _git(repo, "add", "-A")
        assert any("thing.py" in line for line in tasks.unrelated_changes(cwd=repo))

    def test_a_path_merely_prefixed_like_the_artifact_dir_is_unrelated(
        self, repo: Path
    ) -> None:
        """`site/src/database.md` starts with the same characters but is not in it."""
        (repo / "site" / "src").mkdir(parents=True, exist_ok=True)
        (repo / "site" / "src" / "data-notes.md").write_text("hi\n")
        _git(repo, "add", "-A")
        assert any(
            "data-notes.md" in line for line in tasks.unrelated_changes(cwd=repo)
        )
