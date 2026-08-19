"""
Repository tasks: lint/test, run the site, and refresh the published data.

These sit on the same ``podlake-web`` CLI as ``extract`` and ``probe``, so one
command covers everything this repo does — mirroring how ``podlake`` exposes
``sync-all``:

    uv run podlake-web site                      # dev server
    uv run podlake-web build                     # static site into site/dist
    uv run podlake-web refresh --catalog …       # extract, commit, push

They replace a Makefile. Living in the package rather than in a standalone script
means they are importable, so the logic deciding whether to publish is covered by
tests instead of only being exercised at 4:30 on a Monday.

Lint, type-check and tests are deliberately NOT wrapped here — `uv run pytest`,
`uv run ruff check .` and `uv run ty check .` are the ordinary invocations, and CI
runs them as separate steps. A wrapper would only duplicate that, with the added
cost that the names in the docs would not match the names in the failure output.

Deploying a host and scheduling the refresh on it is a different repository —
sul-dlss/podlake-deploy — because that ordering spans podlake and podlake-web both
and neither can express it alone.
"""

from __future__ import annotations

import fcntl
import logging
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import typer

from podlake_web.build import (
    CATALOG_OPTION,
    DATA_PATH_OPTION,
    DEFAULT_OUT,
    app,
)
from podlake_web.build import extract as build_extract

logger = logging.getLogger(__name__)

# tasks.py lives at src/podlake_web/, so the repo root is two parents up.
ROOT = Path(__file__).resolve().parents[2]
SITE_DIR = ROOT / "site"

# Relative, because it is used both as a git pathspec and in messages.
ARTIFACT_DIR = "site/src/data"

# Who unattended commits are attributed to. A deliberately non-routable address
# (.invalid is reserved by RFC 2606 and can never resolve) rather than a plausible
# mailbox: these commits are made by a machine, nobody should reply to them, and
# inventing an address that might belong to a real person or team is worse than one
# that obviously cannot. Point these at a machine user to have them link to a
# GitHub account instead.
AUTHOR_NAME = "podlake-web refresh"
AUTHOR_EMAIL = "podlake-web-refresh@noreply.invalid"


def _run(cmd: list[str], *, cwd: Path = ROOT) -> None:
    """
    Run a command with its output going straight to the terminal.

    Not captured: these are long, chatty tasks (pytest, npm, an extract that runs
    for about an hour) where watching progress is the point.
    """
    typer.secho(f"$ {shlex.join(cmd)}", fg="bright_black")
    proc = subprocess.run(cmd, cwd=cwd, check=False)
    if proc.returncode != 0:
        raise typer.Exit(proc.returncode)


# --- development tasks --------------------------------------------------------


@app.command()
def site() -> None:
    """Preview the dashboard locally (expects artifacts to exist; run extract first)."""
    _run(["npm", "run", "dev"], cwd=SITE_DIR)


@app.command()
def build() -> None:
    """Produce the static site in site/dist."""
    _run(["npm", "run", "build"], cwd=SITE_DIR)


@app.command()
def install() -> None:
    """Install the site's npm deps (Python deps are handled by uv)."""
    _run(["npm", "install"], cwd=SITE_DIR)


# --- refresh: the cron entry point, run on the host ---------------------------


def git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    """Run git in the repo and return stdout. Raises RuntimeError on failure."""
    proc = subprocess.run(
        ["git", "-C", str(cwd or ROOT), *args],
        capture_output=True,
        text=True,
        # check=False, not the `check` parameter above: failures are surfaced as a
        # RuntimeError with git's stderr, which is more useful than CalledProcessError.
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def substantive_diff(cwd: Path | None = None) -> tuple[str, str]:
    """
    Return ``(diffstat, substantive)`` for the artifact directory.

    Every artifact carries a ``generated_at``, so a re-run ALWAYS produces a diff
    even when every number is identical. ``substantive`` is that diff with those
    lines removed: empty means the data did not actually move, and committing it
    would put a churn commit in the history that reads like a data change.

    Getting this wrong is expensive in both directions — too loose and the history
    fills with noise, too strict and real updates are silently discarded — which is
    why it is a module-level function with tests rather than a closure.
    """
    diffstat = git("--no-pager", "diff", "--stat", "--", ARTIFACT_DIR, cwd=cwd).strip()
    raw = git("--no-pager", "diff", "-U0", "--", ARTIFACT_DIR, cwd=cwd)
    substantive = "\n".join(
        line
        for line in raw.splitlines()
        if line[:1] in "+-"
        and not line.startswith(("+++", "---"))
        and '"generated_at"' not in line
    )
    return diffstat, substantive


def unrelated_changes(cwd: Path | None = None) -> list[str]:
    """
    Porcelain lines for tracked changes outside the artifact directory.

    A refresh commits with ``git add -- site/src/data``, so anything else in the
    tree would be left behind and the pushed commit would not correspond to the
    code that produced it. On an unattended host nobody would notice.
    """
    # The trailing slash is load-bearing. Without it `site/src/data-notes.md` counts
    # as inside `site/src/data` and is passed over — while `git add -- site/src/data`,
    # a real pathspec, correctly declines to stage it. The file would be stranded in
    # the tree, which is precisely what this refuses to allow.
    inside = ARTIFACT_DIR + "/"
    return [
        line
        for line in git("status", "--porcelain", cwd=cwd).splitlines()
        if line[3:] and not line[3:].startswith(inside)
    ]


@app.command()
def refresh(
    catalog: str = CATALOG_OPTION,
    data_path: str = DATA_PATH_OPTION,
    branch: str = typer.Option(
        "main",
        "--branch",
        help="Branch to push. main is what deploys the live site; a branch name "
        "stages the change for review instead.",
    ),
    run_tests: bool = typer.Option(
        True,
        "--test/--no-test",
        help="Run the test suite first, so a broken checkout fails in seconds "
        "rather than an hour later.",
    ),
    allow_timestamp_only: bool = typer.Option(
        False,
        "--allow-timestamp-only",
        help="Commit even when only generated_at changed.",
    ),
    push: bool = typer.Option(True, "--push/--no-push", help="Push after committing."),
    lock_file: Path = typer.Option(
        Path("/tmp/podlake-web-refresh.lock"),
        "--lock-file",
        help="Advisory lock, so overlapping runs cannot collide.",
    ),
) -> None:
    """
    Rebuild the artifacts from the lake, then commit and push them. For cron.

    The extract is the slow part — about 65 minutes against the full
    13-institution lake, and it grows with the corpus, so treat any timeout built
    around this as a floor rather than a ceiling.

    Meant to run on the host that can reach the lake, unattended. It exits 0 both
    when it published and when there was nothing to publish, so a quiet week does
    not page anyone; any nonzero exit is a real failure.

    NOT the whole pipeline: it must run *after* podlake has finished syncing, or it
    publishes a comparison in which some institutions are updated and others are
    not. sul-dlss/podlake-deploy owns that ordering — do not schedule this alone.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    started = datetime.now(UTC)
    typer.echo(f"=== refresh {started.isoformat(timespec='seconds')}")

    # flock rather than a pidfile: the kernel releases it however this process
    # dies, so a killed run cannot leave a stale lock blocking every run after it.
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock = lock_file.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        typer.secho(f"another refresh holds {lock_file}; exiting", fg="yellow")
        raise typer.Exit(0) from None

    dirty = unrelated_changes()
    if dirty:
        typer.secho(
            f"working tree has changes outside {ARTIFACT_DIR}; refusing to run:\n  "
            + "\n  ".join(dirty),
            fg="red",
        )
        typer.echo("Re-deploy the host to get back to a known state.")
        raise typer.Exit(2)

    head = git("rev-parse", "--short", "HEAD").strip()
    typer.echo(f"code: {head} {git('log', '-1', '--format=%s').strip()}")

    # Tests only, not the linters. A failing test means this code does not work
    # against this environment, which should stop a publish. Formatting and typing
    # are gated by CI on the way to main, and have nothing to say about whether the
    # data should go out — coupling them here would let a stray blank line block a
    # week of updates.
    if run_tests:
        _run(["uv", "run", "pytest", "-q"])
    # Called directly rather than through the CLI. Every argument is passed
    # explicitly because typer leaves OptionInfo objects as the defaults — relying
    # on them here would hand DuckDB an OptionInfo instead of a path.
    build_extract(catalog=catalog, data_path=data_path, out=DEFAULT_OUT, threshold=10)

    diffstat, substantive = substantive_diff()
    if not diffstat:
        typer.secho("no artifact changes at all — nothing to publish", fg="green")
        raise typer.Exit(0)
    typer.echo("\n" + diffstat)

    if not substantive and not allow_timestamp_only:
        # Reset, so the next run starts clean rather than inheriting a
        # timestamp-only diff that would mask the following run's real changes.
        git("checkout", "--", ARTIFACT_DIR)
        typer.secho(
            "\nonly generated_at changed — the numbers match what is already "
            "committed; discarded",
            fg="green",
        )
        raise typer.Exit(0)

    typer.secho("\nsubstantive changes (generated_at excluded):", fg="cyan")
    typer.echo("\n".join(substantive.splitlines()[:40]))

    elapsed = datetime.now(UTC) - started
    message = f"""Refresh published artifacts from the lake

Rebuilt {ARTIFACT_DIR}/*.json from podlake-web {head} in {elapsed.seconds // 60}m.
Aggregate counts only — no record-level data.

Produced by `podlake-web refresh`.
"""
    git("add", "--", ARTIFACT_DIR)
    # Identity via -c so an unattended host needs no global git config, and the
    # commit is attributable to the job rather than whoever last logged in there.
    git(
        "-c",
        f"user.name={AUTHOR_NAME}",
        "-c",
        f"user.email={AUTHOR_EMAIL}",
        "commit",
        "-q",
        "-m",
        message,
    )
    new = git("rev-parse", "--short", "HEAD").strip()
    typer.secho(f"\ncommitted {new}", fg="green")

    if not push:
        typer.echo("--no-push: stopping before push")
        raise typer.Exit(0)
    try:
        git("push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    except RuntimeError as exc:
        typer.secho(f"\npush failed: {exc}", fg="red")
        typer.echo(
            "cron has no SSH agent, so this needs a deploy key or credential helper "
            "on the host — see sul-dlss/podlake-deploy."
        )
        raise typer.Exit(1) from None
    typer.secho(f"pushed {new} -> {branch}", fg="green")
    if branch == "main":
        typer.echo("GitHub Actions will now rebuild and deploy the site.")
