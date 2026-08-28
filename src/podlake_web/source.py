"""
Read-only consumer connection to a podlake DuckLake.

podlake's own ``lake.connect`` resolves the lake from environment variables and
only supports the profiles podlake writes to (a local file catalog, or the
production Postgres+S3 lake). This extract step is a *consumer*: it is handed an
explicit catalog and reads whatever lake that points at, wherever it lives. So
it builds its own read-only ATTACH here rather than going through podlake's
profile resolution.

A DuckLake is two independently-addressed pieces:

- a **catalog** (metadata) — a local ``.ducklake`` file, an ``s3://…/x.ducklake``
  object, or a ``postgres:…`` DSN, and
- a **data path** — where the Parquet files live (a local dir or ``s3://…/``).

For the two file-catalog forms the data path defaults to the sibling
``lake-data/`` next to the catalog (how ``podlake publish`` lays a lake out, and
the podlake dev-checkout default). A Postgres catalog has no location to hang a
sibling off of, so ``data_path`` is required there.

Because a consumed lake is almost always relocated relative to where its catalog
was written (moved dir, or uploaded to S3), the ATTACH always sets
``OVERRIDE_DATA_PATH`` so reads resolve against the data path we pass rather than
the one baked into the catalog.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import duckdb

# The alias the DuckLake catalog is attached as; podlake_web.queries reference
# `records` / `record_meta` unqualified, so this must be the current database.
LAKE_ALIAS = "podlake"

logger = logging.getLogger(__name__)


def is_postgres(catalog: str) -> bool:
    return catalog.startswith("postgres:")


def is_s3(location: str) -> bool:
    return location.startswith("s3://")


def default_data_path(catalog: str) -> str:
    """
    Derive the conventional sibling ``lake-data/`` data path for a file catalog
    (local or s3://). Raises for a Postgres catalog, which has no location.
    """
    if is_postgres(catalog):
        raise ValueError(
            "a Postgres catalog has no location to derive a data path from; "
            "pass --data-path explicitly"
        )
    if is_s3(catalog):
        base, _, _name = catalog.rpartition("/")
        return f"{base}/lake-data/"
    # local file: absolute sibling dir so the result is independent of CWD
    return str(Path(catalog).resolve().parent / "lake-data") + "/"


def connect(
    catalog: str,
    data_path: str | None = None,
    *,
    read_only: bool = True,
) -> duckdb.DuckDBPyConnection:
    """
    Attach the DuckLake at ``catalog`` (a local ``.ducklake`` path, an
    ``s3://…/x.ducklake`` URI, or a ``postgres:…`` DSN) read-only and return an
    open connection with the lake selected. ``data_path`` defaults to the
    catalog's sibling ``lake-data/`` for file catalogs.
    """
    resolved_data_path = data_path or default_data_path(catalog)

    # a local file catalog is resolved to an absolute path so a relative
    # --catalog doesn't silently depend on the current working directory.
    catalog_uri = catalog
    if not is_postgres(catalog) and not is_s3(catalog):
        catalog_uri = str(Path(catalog).resolve())

    con = duckdb.connect()
    _configure_temp_dir(con)
    _load_extensions(con, catalog_uri, resolved_data_path)
    _configure_s3(con, catalog_uri, resolved_data_path)

    logger.info(
        "attaching ducklake (catalog=%s, data_path=%s, read_only=%s)",
        catalog_uri,
        resolved_data_path,
        read_only,
    )
    con.execute(_attach_sql(catalog_uri, resolved_data_path, read_only))
    con.execute(f"USE {LAKE_ALIAS}")
    return con


def _attach_sql(catalog_uri: str, data_path: str, read_only: bool) -> str:
    """
    Build the ATTACH statement. The catalog URI (which may embed a Postgres
    password) and data path can't be bind parameters, so they are inlined as
    single-quoted SQL literals with embedded quotes escaped.
    """
    options = [
        f"DATA_PATH '{_sql_literal(data_path)}'",
        # the consumed lake is relocated relative to where its catalog recorded
        # the data path, so always resolve reads against the path we pass.
        "OVERRIDE_DATA_PATH true",
    ]
    if read_only:
        options.append("READ_ONLY")
    target = _sql_literal(f"ducklake:{catalog_uri}")
    return f"ATTACH '{target}' AS {LAKE_ALIAS} ({', '.join(options)})"


def _configure_temp_dir(con: duckdb.DuckDBPyConnection) -> None:
    """
    Point DuckDB's spill directory at $TMPDIR, matching how ``podlake.lake.connect``
    does it, so the two halves of this pipeline behave the same way on one host.

    Not left to DuckDB. Its own default for an in-memory database is the *relative*
    path '.tmp', resolved against the process's working directory: the repo when a
    person runs a task by hand, and whatever directory cron happened to start in
    otherwise. Where that is not writable the buffer manager has nothing it can
    evict, so a query too large for memory dies with "failed to pin block" instead
    of spilling — and the same extract then succeeds from a shell and fails from
    cron, which is a miserable thing to debug.

    ``gettempdir()`` rather than ``os.environ["TMPDIR"]`` because it *probes* its
    candidates and returns one that is actually writable, falling back through
    TMPDIR, TEMP, TMP, /tmp and /var/tmp. Redirect it by setting TMPDIR, which is
    worth doing on a host whose /tmp is small or a tmpfs: this extract has been
    observed spilling past 20 GiB, and DuckDB bounds itself by
    ``max_temp_directory_size`` — 90% of the *spill volume's* free space — not by
    the memory limit.
    """
    spill = tempfile.gettempdir()
    con.execute(f"SET temp_directory = '{_sql_literal(spill)}'")
    # Logged, not silent: when a refresh dies for want of spill space, the first
    # thing worth knowing is which volume it was spilling onto.
    logger.info("spilling to %s if a query outgrows memory", spill)


def _load_extensions(
    con: duckdb.DuckDBPyConnection, catalog: str, data_path: str
) -> None:
    extensions = ["ducklake"]
    if is_s3(catalog) or is_s3(data_path):
        extensions += ["httpfs", "aws"]
    if is_postgres(catalog):
        extensions.append("postgres")
    for ext in extensions:
        con.execute(f"INSTALL {ext}")
        con.execute(f"LOAD {ext}")


def _configure_s3(con: duckdb.DuckDBPyConnection, catalog: str, data_path: str) -> None:
    """
    When any part of the lake lives in S3, register a secret that resolves
    credentials via DuckDB's credential_chain (standard AWS_* env vars, shared
    config, or an assumed role) — matching how podlake connects in production.
    """
    if is_s3(catalog) or is_s3(data_path):
        con.execute(
            "CREATE SECRET IF NOT EXISTS pod_s3 (TYPE s3, PROVIDER credential_chain)"
        )


def _sql_literal(value: str) -> str:
    """Escape a value for use inside a single-quoted SQL string literal."""
    return value.replace("'", "''")
