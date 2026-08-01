from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest
from podlake import lake
from podlake.config import Config

from podlake_web import queries, suppress

# --- fixtures / builders -----------------------------------------------------


def _dev_config(tmp_path: Path) -> Config:
    return Config(
        env="development",
        data_path=str(tmp_path / "data") + "/",
        catalog_uri=str(tmp_path / "podlake.ducklake"),
    )


def _008(year: str = "2014", country: str = "cau", lang: str = "eng") -> str:
    """A 40-char 008 with date1 at 8-11, country at 16-18, language at 36-38."""
    v = list(" " * 40)
    v[0:6] = list("000000")
    v[6] = "s"
    v[7:11] = list(year)
    v[15:18] = list(country)
    v[35:38] = list(lang)
    return "".join(v)


LEADER = "00000nam a2200000 a 4500"  # type-of-record 'a' at position 7


def _record(
    org: str,
    rid: str,
    gr: str,
    *,
    year: str = "2014",
    country: str = "cau",
    lang: str = "eng",
    subjects: tuple[str, ...] = (),
    extra_tags: tuple[str, ...] = (),
) -> tuple[list[tuple], tuple]:
    """Return (eav_rows, meta_row) for one record with control + optional fields."""
    pid = f"{org}:{rid}"
    seq = 0
    rows: list[tuple] = [
        (org, pid, "LDR", seq, None, None, None, None, LEADER),
        (org, pid, "001", seq + 1, None, None, None, None, rid),
        (org, pid, "008", seq + 2, None, None, None, None, _008(year, country, lang)),
        (org, pid, "245", seq + 3, "1", "0", "a", 0, f"Title {rid}"),
    ]
    seq += 4
    for subject in subjects:
        rows.append((org, pid, "650", seq, " ", "0", "a", 0, subject))
        seq += 1
    for tag in extra_tags:
        rows.append((org, pid, tag, seq, " ", " ", "a", 0, f"{tag}-value"))
        seq += 1
    return rows, (org, pid, gr)


def _records_parquet(path: Path, rows: list[tuple]) -> None:
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE t (org VARCHAR, pod_record_id VARCHAR, field_tag VARCHAR, "
        "field_seq INTEGER, ind1 VARCHAR, ind2 VARCHAR, subfield_code VARCHAR, "
        "subfield_seq INTEGER, value VARCHAR)"
    )
    if rows:
        con.executemany("INSERT INTO t VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.execute(f"COPY t TO '{path}' (FORMAT parquet)")
    con.close()


def _meta_parquet(path: Path, rows: list[tuple]) -> None:
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE m (org VARCHAR, pod_record_id VARCHAR, goldrush_key VARCHAR)"
    )
    if rows:
        con.executemany("INSERT INTO m VALUES (?,?,?)", rows)
    con.execute(f"COPY m TO '{path}' (FORMAT parquet)")
    con.close()


def _build_lake(tmp_path: Path, records_by_org: dict[str, list]) -> Config:
    """Load one records+meta parquet pair per org into a fresh dev lake."""
    config = _dev_config(tmp_path)
    con = lake.connect(read_only=False, config=config)
    for org, records in records_by_org.items():
        rec_rows = [r for recs, _ in records for r in recs]
        meta_rows = [meta for _, meta in records]
        rpq = tmp_path / f"{org}.records.parquet"
        mpq = tmp_path / f"{org}.meta.parquet"
        _records_parquet(rpq, rec_rows)
        _meta_parquet(mpq, meta_rows)
        lake.load_pair(con, org, rpq, mpq)
    con.close()
    return config


@pytest.fixture
def con(tmp_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    """A small two-org lake: stanford holds a shared + a unique work; harvard the shared."""
    config = _build_lake(
        tmp_path,
        {
            "stanford": [
                _record("stanford", "a1", "shared", subjects=("Music",)),
                _record("stanford", "a2", "stanford_only", lang="fre"),
            ],
            "harvard": [_record("harvard", "b1", "shared")],
        },
    )
    connection = lake.connect(read_only=True, config=config)
    yield connection
    connection.close()


# --- query tests -------------------------------------------------------------


def test_overview(con):
    out = queries.overview(con)
    assert out["totals"] == {"records": 3, "titles": 2, "institutions": 2}
    per_org = {r["org"]: r for r in out["per_org"]}
    assert per_org["stanford"]["records"] == 2
    assert per_org["stanford"]["titles"] == 2
    assert per_org["harvard"]["records"] == 1


def test_overlap_histogram(con):
    out = queries.overlap_histogram(con)
    held = {r["institutions"]: r["titles"] for r in out["held_by"]}
    assert held == {1: 1, 2: 1}  # stanford_only held by 1, shared by 2


def test_overlap_pairwise(con):
    out = queries.overlap_pairwise(con)
    assert out["institutions"] == ["harvard", "stanford"]
    assert out["pairs"] == [{"a": "harvard", "b": "stanford", "shared": 1}]
    assert out["titles"] == {"harvard": 1, "stanford": 2}


def test_uniqueness(con):
    out = queries.uniqueness(con)
    per_org = {r["org"]: r["unique_titles"] for r in out["per_org"]}
    # only stanford has a title nobody else holds
    assert per_org == {"stanford": 1}


def test_coverage(con):
    out = queries.coverage(con)
    per_org = {r["org"]: r for r in out["per_org"]}
    # stanford:a1 has a 650, a2 does not -> 50% subject coverage
    assert per_org["stanford"]["coverage"]["subjects"] == 0.5
    # nobody has an 856
    assert per_org["harvard"]["coverage"]["online"] == 0.0


def test_publication_decade(con):
    out = queries.publication_decade(con, threshold=1)
    decades = {
        r["org"]: {v["decade"]: v["count"] for v in r["values"]} for r in out["per_org"]
    }
    assert decades["harvard"] == {2010: 1}
    assert out["sql"]  # the query is embedded for the "behind this chart" panel


def test_comparison_matrix(con):
    out = queries.comparison(con, threshold=1)
    dims = out["dimensions"]
    assert set(dims) == {"language", "country", "record_type", "classification"}

    lang = dims["language"]
    assert lang["institutions"] == ["harvard", "stanford"]
    assert lang["categories"] == ["ENG", "FRE"]  # ordered by consortium total
    assert lang["totals"] == {"harvard": 1, "stanford": 2}
    assert lang["matrix"]["stanford"] == {"ENG": 1, "FRE": 1}
    assert lang["matrix"]["harvard"] == {"ENG": 1, "FRE": 0}

    # every record is country 'cau' (a U.S. state) -> rolled up to United States
    country = dims["country"]
    assert country["categories"] == ["XXU"]
    assert country["matrix"]["stanford"]["XXU"] == 2

    # leader type-of-record is 'a' for all
    assert dims["record_type"]["categories"] == ["a"]


def test_comparison_suppresses_small_cells(con):
    out = queries.comparison(con)  # default threshold 10; every count here is < 10
    lang = out["dimensions"]["language"]
    assert lang["matrix"]["stanford"]["ENG"] is None  # 1 < 10 -> suppressed
    assert lang["matrix"]["harvard"]["FRE"] == 0  # a genuine zero stays 0
    assert lang["totals"] == {"harvard": 1, "stanford": 2}  # totals are pre-suppression


# --- suppression tests -------------------------------------------------------


def test_bucket_top_n_folds_tail_and_small_cells():
    rows = [
        {"category": "a", "count": 100},
        {"category": "b", "count": 50},
        {"category": "c", "count": 5},  # below threshold -> Other
        {"category": "d", "count": 3},  # beyond top-n and small -> Other
    ]
    out = suppress.bucket_top_n(rows, n=2, threshold=10)
    assert out == [
        {"category": "a", "count": 100},
        {"category": "b", "count": 50},
        {"category": "Other", "count": 8},
    ]
    assert suppress.small_cells(out, threshold=10) == []


def test_artifacts_expose_runnable_sql(con):
    # Every published artifact embeds the SQL that produced it, and that SQL
    # actually executes against the lake (so the per-chart "behind this chart"
    # panels stay honest).
    for fn in (
        queries.overview,
        queries.overlap_histogram,
        queries.overlap_pairwise,
        queries.uniqueness,
        queries.publication_decade,
        queries.coverage,
    ):
        out = fn(con, top_n=7, threshold=1)
        assert out["sql"], f"{fn.__name__} exposes no sql"
        for q in out["sql"]:
            con.execute(q["sql"])
    # comparison carries one query per dimension
    for dim in queries.comparison(con, threshold=1)["dimensions"].values():
        assert dim["sql"]
        con.execute(dim["sql"])


def test_fold_small_keeps_all_above_threshold():
    rows = [{"category": x, "count": c} for x, c in [("a", 30), ("b", 20), ("c", 1)]]
    out = suppress.fold_small(rows, threshold=10)
    assert {r["category"]: r["count"] for r in out} == {"a": 30, "b": 20, "Other": 1}
