from __future__ import annotations

import re
import tempfile
from pathlib import Path

import duckdb
import pytest
from podlake import lake
from podlake.config import Config
from typer.testing import CliRunner

from podlake_web import app, source

# --- catalog / data-path classification --------------------------------------


def test_is_postgres_and_is_s3():
    assert source.is_postgres("postgres:host=x dbname=y")
    assert not source.is_postgres("/local/podlake.ducklake")
    assert source.is_s3("s3://bucket/prefix/podlake.ducklake")
    assert not source.is_s3("/local/lake-data/")


# --- default_data_path --------------------------------------------------------


def test_default_data_path_local_is_absolute_sibling(tmp_path: Path):
    catalog = tmp_path / "podlake.ducklake"
    assert (
        source.default_data_path(str(catalog))
        == str(tmp_path.resolve() / "lake-data") + "/"
    )


def test_default_data_path_local_is_independent_of_cwd(tmp_path: Path):
    # a relative catalog still derives an absolute data path, so the result
    # does not depend on where the process happens to be running.
    catalog = tmp_path / "sub" / "podlake.ducklake"
    catalog.parent.mkdir()
    assert source.default_data_path(str(catalog)).startswith("/")


def test_default_data_path_s3_with_prefix():
    assert (
        source.default_data_path("s3://bucket/prefix/podlake.ducklake")
        == "s3://bucket/prefix/lake-data/"
    )


def test_default_data_path_s3_without_prefix():
    assert (
        source.default_data_path("s3://bucket/podlake.ducklake")
        == "s3://bucket/lake-data/"
    )


def test_default_data_path_postgres_raises():
    with pytest.raises(ValueError, match="Postgres catalog has no location"):
        source.default_data_path("postgres:host=x dbname=y")


# --- ATTACH SQL ---------------------------------------------------------------


def test_attach_sql_read_only_sets_override_and_read_only():
    sql = source._attach_sql("/x/podlake.ducklake", "/x/lake-data/", read_only=True)
    assert "ATTACH 'ducklake:/x/podlake.ducklake' AS podlake" in sql
    assert "DATA_PATH '/x/lake-data/'" in sql
    assert "OVERRIDE_DATA_PATH true" in sql
    assert "READ_ONLY" in sql


def test_attach_sql_omits_read_only_when_writable():
    sql = source._attach_sql("/x/c.ducklake", "/x/d/", read_only=False)
    assert "READ_ONLY" not in sql
    # override is applied regardless of read-only, so a relocated lake resolves
    assert "OVERRIDE_DATA_PATH true" in sql


def test_attach_sql_escapes_embedded_quotes():
    # a Postgres DSN could carry a password with a single quote; it must be
    # doubled so it can't break out of the inlined SQL literal.
    sql = source._attach_sql("postgres:password=a'b", "s3://bucket/lake-data/", True)
    assert "ducklake:postgres:password=a''b" in sql


# --- end-to-end connect against a real lake -----------------------------------


def _build_min_lake(catalog: Path, data_path: Path) -> None:
    """Create a tiny writable lake with a single record_meta row."""
    cfg = Config(
        profile="file",
        data_path=str(data_path) + "/",
        catalog_uri=str(catalog),
    )
    con = lake.connect(read_only=False, config=cfg)
    lake.ensure_schema(con)
    con.execute("INSERT INTO record_meta VALUES ('stanford', 'stanford:a1', 'k1')")
    con.close()


def test_connect_reads_a_file_catalog_lake(tmp_path: Path):
    catalog = tmp_path / "podlake.ducklake"
    data_path = tmp_path / "lake-data"
    _build_min_lake(catalog, data_path)

    con = source.connect(str(catalog), read_only=True)  # sibling data path derived
    try:
        row = con.execute("SELECT count(*) FROM record_meta").fetchone()
        assert row is not None and row[0] == 1
    finally:
        con.close()


def test_connect_read_only_rejects_writes(tmp_path: Path):
    catalog = tmp_path / "podlake.ducklake"
    data_path = tmp_path / "lake-data"
    _build_min_lake(catalog, data_path)

    con = source.connect(str(catalog), str(data_path) + "/", read_only=True)
    try:
        with pytest.raises(duckdb.Error):
            con.execute("INSERT INTO record_meta VALUES ('x', 'x:1', 'k')")
    finally:
        con.close()


# --- spill directory ----------------------------------------------------------
#
# Regression tests for a failure that only ever showed up under cron: DuckDB's
# default temp_directory for an in-memory database is the relative path '.tmp', so
# a query too large for memory spilled fine when run by hand from the repo and died
# with "failed to pin block" when cron started the process somewhere unwritable.
# What matters is that the setting never depends on the process's CWD. Mirrors
# podlake's own test_connect_caps_memory_and_sets_spill_dir.


def _temp_dir_of(con: duckdb.DuckDBPyConnection) -> str:
    row = con.execute("SELECT current_setting('temp_directory')").fetchone()
    assert row is not None
    return row[0]


def test_connect_temp_directory_does_not_follow_the_cwd(tmp_path: Path, monkeypatch):
    catalog = tmp_path / "podlake.ducklake"
    _build_min_lake(catalog, tmp_path / "lake-data")

    # Run from somewhere that is not the repo, as cron does. The bug this guards
    # against is DuckDB's relative '.tmp' default, so what matters is that the
    # resolved path is absolute and is not inside the CWD.
    monkeypatch.chdir(tmp_path)
    con = source.connect(str(catalog))
    try:
        resolved = Path(_temp_dir_of(con))
        assert resolved.is_absolute()
        assert not resolved.is_relative_to(tmp_path)
    finally:
        con.close()


def test_connect_temp_directory_honors_tmpdir(tmp_path: Path, monkeypatch):
    catalog = tmp_path / "podlake.ducklake"
    _build_min_lake(catalog, tmp_path / "lake-data")
    spill = tmp_path / "spill"
    spill.mkdir()

    monkeypatch.setenv("TMPDIR", str(spill))
    # gettempdir() caches its answer in tempfile.tempdir on first use, so a test
    # that only set the variable would assert against whatever earlier code
    # happened to resolve.
    monkeypatch.setattr(tempfile, "tempdir", None)

    con = source.connect(str(catalog))
    try:
        assert _temp_dir_of(con) == str(spill)
    finally:
        con.close()


# --- CLI guard for the Postgres case -----------------------------------------


def _plain(output: str) -> str:
    """
    Typer renders errors through Rich, which wraps them in a box at the terminal's
    width and colours them. Both are environment-dependent — a wide local terminal
    keeps the message on one line, while CI's 80 columns break it across two with
    box borders and ANSI codes in between — so a substring test against the raw
    output passes locally and fails in CI. Strip the presentation and match on the
    text.
    """
    no_ansi = re.sub(r"\x1b\[[0-9;]*m", "", output)
    no_box = re.sub(r"[│┃╭╮╰╯─━┌┐└┘]", " ", no_ansi)
    return " ".join(no_box.split())


def test_probe_command_emits_csv_of_agency_codes(tmp_path: Path):
    # The probe exists as a command so the query people run is the query the
    # extract matches on — a transcribed copy is how the normalization mismatch
    # went unnoticed. So this asserts the CSV shape callers depend on, not just
    # that it exits 0.
    catalog = tmp_path / "podlake.ducklake"
    data_path = tmp_path / "lake-data"
    cfg = Config(
        profile="file", data_path=str(data_path) + "/", catalog_uri=str(catalog)
    )
    con = lake.connect(read_only=False, config=cfg)
    lake.ensure_schema(con)
    con.execute("INSERT INTO record_meta VALUES ('stanford', 'stanford:a1', 'k1')")
    con.execute(
        "INSERT INTO records VALUES "
        "('stanford', 'stanford:a1', '040', 1, ' ', ' ', 'a', 0, '*CSt*')"
    )
    con.close()

    out = tmp_path / "codes.csv"
    result = CliRunner().invoke(
        app, ["probe", "--catalog", str(catalog), "--out", str(out)]
    )
    assert result.exit_code == 0, _plain(result.output)

    lines = out.read_text().splitlines()
    assert lines[0] == "org,code,n,pct_of_org,pct_at_this_org"
    # normalized to the form _SELF_CODES compares on, not the '*CSt*' in the data
    assert lines[1].startswith("stanford,CST,1,")


def test_extract_requires_data_path_for_postgres_catalog():
    result = CliRunner().invoke(
        app, ["extract", "--catalog", "postgres:host=x dbname=y"]
    )
    assert result.exit_code != 0
    assert "--data-path is required when --catalog is a Postgres DSN" in _plain(
        result.output
    )
