from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest
from podlake import lake
from podlake.config import Config

from podlake_web import queries, record, suppress

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


def test_serials_timeline(tmp_path):
    # A serial is active in every year of its run; 'c'/9999 run to NOW_YEAR,
    # 'd' uses its numeric end. Non-serials and undated serials drop out.
    serial_leader = "00000nas a2200000 a 4500"  # leader/07 = 's'

    def serial(rid, gr, date_type, y1, y2):
        pid = f"z:{rid}"
        v = list(" " * 40)
        v[0:6] = list("000000")
        v[6] = date_type
        v[7:11] = list(y1)
        v[11:15] = list(y2)
        rows = [
            ("z", pid, "LDR", 0, None, None, None, None, serial_leader),
            ("z", pid, "008", 1, None, None, None, None, "".join(v)),
        ]
        return rows, ("z", pid, gr)

    records = [
        serial("a", "k1", "d", "1990", "1995"),  # ceased: active 1990..1995
        serial("b", "k2", "c", "2000", "9999"),  # ongoing: active 2000..NOW_YEAR
        serial("c", "k3", "u", "18uu", "9999"),  # unknown start -> dropped
    ]
    config = _build_lake(tmp_path, {"z": records})
    connection = lake.connect(read_only=True, config=config)
    try:
        out = queries.serials_timeline(connection)
    finally:
        connection.close()

    assert out["now_year"] == queries.NOW_YEAR
    by_year = {v["year"]: v["count"] for v in out["active"][0]["values"]}
    assert by_year[1990] == 1 and by_year[1995] == 1  # ceased serial spans these
    assert 1996 not in by_year  # and not beyond its end
    assert by_year[2000] == 1 and by_year[queries.NOW_YEAR] == 1  # ongoing to present
    assert 1998 not in by_year  # gap between the two serials

    # start-decade vintage: the two dated serials fall in the 1990s and 2000s;
    # the undated one (18uu) is excluded.
    decades = {v["decade"]: v["count"] for v in out["start_decade"][0]["values"]}
    assert decades == {1990: 1, 2000: 1}


def test_serials_succession(tmp_path):
    # 780 (predecessor) / 785 (successor) links, measured against total serials.
    serial_leader = "00000nas a2200000 a 4500"  # leader/07 = 's'

    def serial(rid, *links):  # links: (tag, ind2)
        pid = f"w:{rid}"
        rows = [("w", pid, "LDR", 0, None, None, None, None, serial_leader)]
        for i, (tag, ind2) in enumerate(links, start=1):
            rows.append(("w", pid, tag, i, " ", ind2, "t", 0, "Linked title"))
        return rows, ("w", pid, rid)

    records = [
        serial("s1", ("780", "0"), ("785", "0")),  # predecessor + "continued by"
        serial("s2", ("785", "7")),  # "merged to form"
        serial("s3"),  # no links
    ]
    config = _build_lake(tmp_path, {"w": records})
    connection = lake.connect(read_only=True, config=config)
    try:
        out = queries.serials_succession(connection, threshold=1)
    finally:
        connection.close()

    link = out["dimensions"]["succession_link"]
    assert link["totals"]["w"] == 3  # denominator is all serials
    assert link["matrix"]["w"]["pred"] == 1  # only s1 has a 780
    assert link["matrix"]["w"]["succ"] == 2  # s1 and s2 have a 785

    types = out["dimensions"]["succession_type"]
    assert types["matrix"]["w"]["0"] == 1  # s1 continued by
    assert types["matrix"]["w"]["7"] == 1  # s2 merged
    # ranked most-common-first; only present types kept
    assert set(types["categories"]) == {"0", "7"}


def test_comparison_matrix(con):
    out = queries.comparison(con, threshold=1)
    dims = out["dimensions"]
    assert set(dims) == {
        "language",
        "country",
        "record_type",
        "classification",
        "serial_classification",
        "serial_status",
    }

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


def test_classification_first_lc_match(tmp_path):
    # LC class comes from the first LC-shaped call number across the priority of
    # locations; non-LC values (Dewey, NLM, and 852s whose scheme indicator is
    # not LC) are skipped, one class per record.
    def rec(rid, gr, *fields):
        # each field is (tag, code, val) or (tag, code, val, ind1)
        org, pid = "x", f"x:{rid}"
        rows = [(org, pid, "LDR", 0, None, None, None, None, LEADER)]
        for i, field in enumerate(fields, start=1):
            tag, code, val = field[:3]
            ind1 = field[3] if len(field) > 3 else " "
            rows.append((org, pid, tag, i, ind1, " ", code, 0, val))
        return rows, (org, pid, gr)

    records = [
        rec("a", "k1", ("050", "a", "QA76 .A1")),  # 050 -> Q
        rec("b", "k2", ("852", "h", "PN1993 .B7", "0")),  # 852 ind1=0 (LC) -> P
        rec("c", "k3", ("852", "h", "823.91 A437", "0")),  # Dewey value -> dropped
        rec(
            "e", "k5", ("852", "h", "PN1993 .B7", "1")
        ),  # 852 ind1=1 (Dewey) -> dropped
        rec("f", "k6", ("050", "a", "QW 100")),  # NLM QW in 050 -> dropped
        rec(
            "d", "k4", ("852", "h", "500 X9", "0"), ("900", "f", "DA10 .Z9")
        ),  # skip Dewey 852 -> first LC match is 900$f -> D
    ]
    config = _build_lake(tmp_path, {"x": records})
    connection = lake.connect(read_only=True, config=config)
    try:
        out = queries.comparison(connection, threshold=1)
    finally:
        connection.close()

    cls = out["dimensions"]["classification"]
    counts = {c: cls["matrix"]["x"][c] for c in cls["categories"]}
    # Q from record a only (NLM 'QW' dropped); P from the LC-indicator 852 only
    # (the Dewey-indicator 852 dropped); D from the 900$f fallback.
    assert counts == {"D": 1, "P": 1, "Q": 1}


def test_archives(tmp_path):
    # archival subset = leader/06 in t/d/f/p OR leader/08 in c/d. A plain book
    # (leader "...nam...") must be excluded.
    ms_leader = "00000ntm a2200000 a 4500"  # leader/06='t' manuscript, /08='m'
    coll_leader = "00000npc a2200000 a 4500"  # leader/06='p' mixed, /08='c' collection

    def rec(rid, leader, *fields, date1=None):
        pid = f"z:{rid}"
        rows = [("z", pid, "LDR", 0, None, None, None, None, leader)]
        if date1 is not None:
            v = list(" " * 40)
            v[7:11] = list(date1)
            rows.append(("z", pid, "008", 1, None, None, None, None, "".join(v)))
        for i, (tag, code, val) in enumerate(fields, start=2):
            rows.append(("z", pid, tag, i, " ", " ", code, 0, val))
        return rows, ("z", pid, rid)

    records = [
        rec("m1", ms_leader, ("655", "a", "Photographs."), date1="1900"),
        rec(
            "c1",
            coll_leader,
            ("655", "a", "Correspondence"),
            ("856", "u", "https://findingaids.example.edu/coll/c1"),
            date1="1850",
        ),
        rec("b1", LEADER),  # plain book -> excluded
    ]
    config = _build_lake(tmp_path, {"z": records})
    connection = lake.connect(read_only=True, config=config)
    try:
        out = queries.archives(connection, threshold=1)
    finally:
        connection.close()

    mt = out["dimensions"]["material_type"]
    assert mt["totals"]["z"] == 2  # book excluded
    assert mt["matrix"]["z"]["t"] == 1 and mt["matrix"]["z"]["p"] == 1

    genre = {
        v["term"]: v["count"]
        for v in {o["org"]: o for o in out["genre"]}["z"]["values"]
    }
    assert genre.get("photographs") == 1 and genre.get("correspondence") == 1

    decades = {v["decade"]: v["count"] for v in out["start_decade"][0]["values"]}
    assert decades == {1900: 1, 1850: 1}

    link = {o["org"]: o for o in out["online_link"]}["z"]
    assert link["count"] == 1 and link["total"] == 2  # only c1 has an 856

    dest = out["dimensions"]["link_destination"]
    assert dest["matrix"]["z"]["finding_aid"] == 1  # findingaids.* host
    assert dest["matrix"]["z"]["vendor"] == 0  # fixed taxonomy keeps empty buckets


def test_electronic(tmp_path):
    # each institution's own top 856 link hosts, raw.
    def rec(rid, *urls):
        pid = f"e:{rid}"
        rows = [("e", pid, "LDR", 0, None, None, None, None, LEADER)]
        for i, u in enumerate(urls, start=1):
            rows.append(("e", pid, "856", i, "4", "0", "u", 0, u))
        return rows, ("e", pid, rid)

    records = [
        rec("r1", "https://jstor.org/a", "https://doi.org/x"),
        rec("r2", "https://jstor.org/b"),
        rec("r3", "http://catdir.loc.gov/toc"),  # no scheme-less; still http
    ]
    config = _build_lake(tmp_path, {"e": records})
    connection = lake.connect(read_only=True, config=config)
    try:
        out = queries.electronic(connection, threshold=1)
    finally:
        connection.close()

    row = {o["org"]: o for o in out["hosts"]}["e"]
    assert row["total"] == 4  # four 856 $u links total
    hosts = {v["host"]: v["count"] for v in row["values"]}
    assert hosts["jstor.org"] == 2  # top host
    assert hosts["doi.org"] == 1 and hosts["catdir.loc.gov"] == 1


def test_reconstitute_record(con):
    fields = record.reconstitute(con, "stanford", "stanford:a1")
    by_tag = {f.tag: f for f in fields}
    # leader + control field come back as control (value, no subfields)
    assert by_tag["LDR"].is_control and by_tag["LDR"].value
    # data field keeps indicators and ordered subfields
    assert by_tag["245"].ind1 == "1" and by_tag["245"].ind2 == "0"
    assert by_tag["245"].subfields == [("a", "Title a1")]
    assert by_tag["650"].subfields == [("a", "Music")]
    # and renders to text
    assert "245 10" in record.to_text(con, "stanford", "stanford:a1")
    # unknown id -> empty
    assert record.reconstitute(con, "stanford", "nope") == []


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
    # archives exposes a top-level sql list (and per-dimension sql)
    arch = queries.archives(con, threshold=1)
    assert arch["sql"]
    for q in arch["sql"]:
        con.execute(q["sql"])
    # electronic likewise
    for q in queries.electronic(con, threshold=1)["sql"]:
        con.execute(q["sql"])


def test_fold_small_keeps_all_above_threshold():
    rows = [{"category": x, "count": c} for x, c in [("a", 30), ("b", 20), ("c", 1)]]
    out = suppress.fold_small(rows, threshold=10)
    assert {r["category"]: r["count"] for r in out} == {"a": 30, "b": 20, "Other": 1}
