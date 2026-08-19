#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["typer>=0.16.0"]
# ///
"""
Task runner for podlake-web. Replaces the Makefile.

    uv run tools/tasks.py check                        # lint, type-check, test
    uv run tools/tasks.py extract --catalog ../../podlake/podlake.ducklake
    uv run tools/tasks.py site                         # dev server
    uv run tools/tasks.py refresh --catalog …          # extract, commit, push

Run it with `uv run` and nothing needs installing: the PEP 723 header above tells
uv what to fetch. It deliberately does NOT import podlake_web, so `--help` and the
site tasks work even without the sibling podlake checkout that `extract/` requires.

Everything here runs against a local checkout. Provisioning a host and scheduling
the refresh on it is a different repository — sul-dlss/podlake-deploy — because
that ordering spans podlake and podlake-web both, and neither can express it.

WHAT `refresh` NEEDS, AND WHY IT DOES NOT INSTALL IT

A git credential that can push, since cron has no SSH agent to forward: a deploy
key with write access, or a credential helper. Also uv, and podlake as a sibling
checkout. podlake-deploy installs and verifies all of that; `refresh` only checks
and refuses, so a misprovisioned host fails loudly rather than pushing something
surprising.

IT IS ALSO NOT THE WHOLE PIPELINE. `refresh` must run after podlake has finished
syncing the lake, or it publishes a comparison where some institutions are updated
and others are not. podlake-deploy owns that ordering; do not schedule this on its
own.
"""

from __future__ import annotations

import fcntl
import os
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import typer

ROOT = Path(__file__).resolve().parents[1]
EXTRACT_DIR = ROOT / "extract"
SITE_DIR = ROOT / "site"
ARTIFACT_DIR = "site/src/data"

app = typer.Typer(add_completion=False, help=__doc__, no_args_is_help=True)


# --- local process helpers ----------------------------------------------------


def _run(cmd: list[str], *, cwd: Path) -> None:
    """
    Run a command with its output going straight to the terminal.

    Not captured: these are long, chatty tasks (pytest, npm, an extract that runs
    for about an hour) where watching progress is the point.

    VIRTUAL_ENV is dropped because `uv run` gave *this script* an environment of
    its own, and a nested `uv run` in extract/ then warns that it does not match
    that project's .venv — on every single task. Unsetting it lets each nested
    call resolve its own environment, which is what we want anyway.
    """
    typer.secho(f"$ {shlex.join(cmd)}", fg="bright_black")
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    proc = subprocess.run(cmd, cwd=cwd, env=env)
    if proc.returncode != 0:
        raise typer.Exit(proc.returncode)


# The lake location cannot be guessed, and getting it wrong produces a confusing
# error rather than an obvious one: an empty value still satisfies a required
# option and reaches DuckDB as a relative path, which fails with "Could not read
# from file …: Is a directory". So say what it wants, with examples.
CATALOG_HELP = (
    "The lake to read: a local .ducklake path, an s3://…/x.ducklake URI, or a "
    "postgres: DSN."
)
CATALOG_MISSING = """\
--catalog is required: it names the lake to read.

  a local podlake checkout (data path defaults to its sibling lake-data/):
    --catalog ../../podlake/podlake.ducklake

  a lake published to S3 by `podlake publish`:
    --catalog s3://my-bucket/podlake/podlake.ducklake

  a Postgres-catalog lake (--data-path is required, it cannot be derived):
    --catalog "postgres:host=… dbname=… user=… password=…" \\
      --data-path s3://my-bucket/podlake/lake-data/
"""


def _require_catalog(catalog: str | None) -> str:
    if not catalog:
        typer.secho(CATALOG_MISSING, fg="red")
        raise typer.Exit(2)
    return catalog


def _lake_args(catalog: str, data_path: str | None) -> list[str]:
    args = ["--catalog", catalog]
    if data_path:
        args += ["--data-path", data_path]
    return args


CatalogArg = typer.Option(None, "--catalog", help=CATALOG_HELP)
DataPathArg = typer.Option(
    None,
    "--data-path",
    help="Where the lake's Parquet data lives. Defaults to the catalog's sibling "
    "lake-data/ for file catalogs; required for a Postgres catalog.",
)


# --- local tasks (these are what the Makefile used to do) ---------------------


@app.command()
def check() -> None:
    """Lint, type-check, and test the extract step."""
    for cmd in (
        ["uv", "run", "ruff", "format", "--check", "."],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "ty", "check", "."],
        ["uv", "run", "pytest", "-q"],
    ):
        _run(cmd, cwd=EXTRACT_DIR)


@app.command()
def extract(
    catalog: str = CatalogArg,
    data_path: str | None = DataPathArg,
    out: Path | None = typer.Option(
        None, "--out", help="Artifact directory. Defaults to site/src/data."
    ),
) -> None:
    """
    Compile the public aggregate artifacts from the lake into site/src/data.

    Read-only against the lake, and aggregate-only on the way out: counts,
    distributions and percentages, never record identifiers or field values.
    """
    catalog = _require_catalog(catalog)
    args = ["uv", "run", "podlake-web", "extract", *_lake_args(catalog, data_path)]
    if out:
        args += ["--out", str(out)]
    _run(args, cwd=EXTRACT_DIR)


@app.command()
def probe(
    catalog: str = CatalogArg,
    data_path: str | None = DataPathArg,
    out: Path = typer.Option(
        ROOT / "codes.csv", "--out", help="Where to write the CSV."
    ),
) -> None:
    """
    Dump each institution's cataloging-agency codes (MARC 040 $a) as CSV.

    This is how you find codes missing from institution-codes.csv — sort the
    output by pct_at_this_org, since a code used almost only at one member is the
    shape worth looking at. See docs/institution-codes.md.
    """
    catalog = _require_catalog(catalog)
    _run(
        [
            "uv", "run", "podlake-web", "probe",
            *_lake_args(catalog, data_path),
            "--out", str(out),
        ],
        cwd=EXTRACT_DIR,
    )


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
    """Install the site's npm deps (extract's Python deps are handled by uv)."""
    _run(["npm", "install"], cwd=SITE_DIR)


# Deploying the code to a host is NOT a task here. It is pyinfra, invoked the way
# pyinfra is documented:
#
#     pyinfra inventory.py deploy_podlake.py deploy_podlake_web.py deploy_pipeline.py
#
# in sul-dlss/podlake-deploy. Not wrapped in a `tasks.py deploy` command even when
# it lived here: a wrapper would have to re-expose -v/-vv, --limit, --dry,
# debug-inventory and `exec` to stay useful, and until it did, every pyinfra doc
# would describe flags you could not reach.


# --- refresh: the cron entry point, run on the host ---------------------------

# Who the unattended commits are attributed to. See the commit call below.
AUTHOR_NAME = "podlake-web refresh"
AUTHOR_EMAIL = "podlake-web-refresh@noreply.invalid"


def _git(*args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _substantive_diff() -> tuple[str, str]:
    """
    Return (diffstat, substantive) for the artifact directory.

    Every artifact carries a ``generated_at``, so a re-run ALWAYS produces a diff
    even when every number is identical. ``substantive`` is the diff with those
    lines removed: empty means the data did not actually move, and committing it
    would put a churn commit in the history that reads like a data change.
    """
    diffstat = _git("--no-pager", "diff", "--stat", "--", ARTIFACT_DIR).strip()
    raw = _git("--no-pager", "diff", "-U0", "--", ARTIFACT_DIR)
    substantive = "\n".join(
        line
        for line in raw.splitlines()
        if line[:1] in "+-"
        and not line.startswith(("+++", "---"))
        and '"generated_at"' not in line
    )
    return diffstat, substantive


@app.command()
def refresh(
    catalog: str = CatalogArg,
    data_path: str | None = DataPathArg,
    branch: str = typer.Option(
        "main",
        "--branch",
        help="Branch to push. main is what deploys the live site; use a branch "
        "name to stage the change for review instead.",
    ),
    check_first: bool = typer.Option(
        True,
        "--check/--no-check",
        help="Run the check task first, so a broken checkout fails in seconds "
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
        help="Advisory lock, so overlapping cron runs cannot collide.",
    ),
) -> None:
    """
    Rebuild the artifacts from the lake, then commit and push them. For cron.

    The extract is the slow part — about 65 minutes against the full 13-institution
    lake, and it grows with the corpus, so treat any timeout you build around this
    as a floor rather than a ceiling.

    Designed to be run on the host that can reach the lake, unattended:

        30 4 * * 1  cd /opt/app/pod/podlake-web && uv run tools/tasks.py refresh
                    --catalog /opt/app/pod/podlake/podlake.ducklake
                    >> /var/log/podlake-refresh.log 2>&1

    Exits 0 both when it published and when there was nothing to publish, so a
    quiet week does not page anyone. Any nonzero exit is a real failure.
    """
    catalog = _require_catalog(catalog)
    started = datetime.now(UTC)
    typer.echo(f"=== refresh {started.isoformat(timespec='seconds')}")

    # flock rather than a pidfile: the kernel releases it however this process
    # dies, so a killed run cannot leave a stale lock that blocks every run after.
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock = lock_file.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        typer.secho(
            f"another refresh holds {lock_file}; exiting without doing anything",
            fg="yellow",
        )
        raise typer.Exit(0) from None

    # Refuse to run on a tree with unrelated local edits. Committing artifacts with
    # `git add -- site/src/data` would leave those edits behind uncommitted, so the
    # pushed commit would not correspond to the code that produced it — and on an
    # unattended host nobody would notice.
    dirty = [
        line
        for line in _git("status", "--porcelain").splitlines()
        if line[3:] and not line[3:].startswith(ARTIFACT_DIR)
    ]
    if dirty:
        typer.secho(
            "working tree has changes outside "
            f"{ARTIFACT_DIR}; refusing to run:\n  " + "\n  ".join(dirty),
            fg="red",
        )
        typer.echo("Re-deploy the host to get back to a known state.")
        raise typer.Exit(2)

    head = _git("rev-parse", "--short", "HEAD").strip()
    typer.echo(f"code: {head} {_git('log', '-1', '--format=%s').strip()}")

    if check_first:
        check()
    extract(catalog=catalog, data_path=data_path, out=None)

    diffstat, substantive = _substantive_diff()
    if not diffstat:
        typer.secho("no artifact changes at all — nothing to publish", fg="green")
        raise typer.Exit(0)
    typer.echo("\n" + diffstat)
    if not substantive and not allow_timestamp_only:
        # Reset, so the next run starts from a clean tree rather than inheriting
        # a timestamp-only diff that would mask the following run's real changes.
        _git("checkout", "--", ARTIFACT_DIR)
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

Produced by tools/tasks.py refresh.
"""
    _git("add", "--", ARTIFACT_DIR)
    # Identity via -c so an unattended host needs no global git config, and the commit
    # is attributable to the job rather than to whoever last logged in there.
    #
    # A deliberately non-routable address (.invalid is reserved by RFC 2606 and can
    # never resolve) rather than a plausible-looking mailbox: these commits are made
    # by a machine, nobody should reply to them, and inventing an address that might
    # belong to a real person or team is worse than one that obviously cannot. Point
    # AUTHOR at a machine user if you would rather these link to a GitHub account.
    _git(
        "-c", f"user.name={AUTHOR_NAME}",
        "-c", f"user.email={AUTHOR_EMAIL}",
        "commit", "-q", "-m", message,
    )
    new = _git("rev-parse", "--short", "HEAD").strip()
    typer.secho(f"\ncommitted {new}", fg="green")

    if not push:
        typer.echo("--no-push: stopping before push")
        raise typer.Exit(0)
    try:
        _git("push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    except RuntimeError as exc:
        typer.secho(f"\npush failed: {exc}", fg="red")
        typer.echo(
            "cron has no SSH agent, so this needs a deploy key or credential "
            "helper on the host — see sul-dlss/podlake-deploy."
        )
        raise typer.Exit(1) from None
    typer.secho(f"pushed {new} -> {branch}", fg="green")
    if branch == "main":
        typer.echo("GitHub Actions will now rebuild and deploy the site.")


if __name__ == "__main__":
    app()
