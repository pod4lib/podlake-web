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
        profile="file",
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


def test_self_codes_are_unambiguous():
    # No lake needed: a code must not be claimed by two members, and one member's
    # 'BASE-*' rule must not swallow another's exact code (the PU / PUL hazard).
    # This is the guard for when POD adds an institution.
    # a code must also not be both confirmed and inferred
    for org, inferred in queries._SELF_CODES_INFERRED.items():
        overlap = set(inferred) & set(queries._SELF_CODES.get(org, ()))
        assert not overlap, f"{org} lists {overlap} as both confirmed and inferred"

    exact: dict[str, str] = {}
    for org, codes in queries._ALL_SELF_CODES.items():
        for code in codes:
            if not code.endswith("-*"):
                assert code not in exact, (
                    f"{code} claimed by {exact.get(code)} and {org}"
                )
                exact[code] = org
    for org, codes in queries._ALL_SELF_CODES.items():
        for prefix in (c[:-1] for c in codes if c.endswith("-*")):
            for code, owner in exact.items():
                if owner != org:
                    assert not code.startswith(prefix), (
                        f"{org}'s {prefix}* pattern also matches {owner}'s {code}"
                    )


def test_cataloging_source(tmp_path):
    # 040 $a is the original cataloging agency, $d each modifying agency. Uses real
    # org names because the self/pod buckets key off queries._SELF_CODES.
    def rec(org, rid, source=None, mods=(), extra_a=(), second_040=None):
        pid = f"{org}:{rid}"
        rows = [(org, pid, "LDR", 0, None, None, None, None, LEADER)]
        seq = 1
        if source is not None:
            rows.append((org, pid, "040", seq, " ", " ", "a", 0, source))
            # a second $a in the same field: later subfield_seq, must lose
            for i, extra in enumerate(extra_a, start=1):
                rows.append((org, pid, "040", seq, " ", " ", "a", i, extra))
            for i, mod in enumerate(mods):
                rows.append((org, pid, "040", seq, " ", " ", "d", i + 10, mod))
            seq += 1
        if second_040 is not None:  # a whole second 040 field, later field_seq
            rows.append((org, pid, "040", seq, " ", " ", "a", 0, second_040))
        return rows, (org, pid, rid)

    records = {
        "stanford": [
            rec("stanford", "s1", "DLC"),  # lc
            rec("stanford", "s2", "DLC-R"),  # lc (retrospective conversion)
            rec("stanford", "s3", "OCoLC"),  # other -- no dedicated oclc bucket
            rec("stanford", "s4", "CSt"),  # self
            rec("stanford", "s5", "CSt-H"),  # self, via the sub-unit rule
            rec("stanford", "s6", "stf"),  # self, case-normalized OCLC symbol
            rec("stanford", "s7", "NjP"),  # pod (Princeton)
            rec("stanford", "s8", "UkOxU"),  # other
            rec("stanford", "s9"),  # none — no 040 at all
            rec("stanford", "s10", "DLC.", extra_a=("CSt",)),  # trailing dot; 1st wins
            # 3 distinct modifying agencies (one repeated, one case variant)
            rec("stanford", "s11", "DLC", mods=("CSt", "cst", "NjP", "OCoLC")),
            rec("stanford", "s12", "DLC", mods=("CSt",)),  # 1 modifying agency
            # the real shape of a repeated $a: a mangled delimiter glued $d on
            rec("stanford", "s13", "DLC", extra_a=("dOCLCO",)),
            # asterisk-wrapped codes normalize to the bare code, in $a and $d alike
            rec("stanford", "s14", "*YNH*", mods=("*OCLCQ*", "OCLCQ")),
            # a second whole 040 field loses to the first by field_seq
            rec("stanford", "s15", "CSt", second_040="DLC"),
        ],
        "princeton": [
            rec("princeton", "p1", "NjP"),  # self
            rec("princeton", "p2", "CSt"),  # pod (Stanford)
            rec("princeton", "p3", "DLC"),  # lc
        ],
        # PUL is Princeton's OCLC symbol, so at Penn it must read as 'pod' — the
        # exact case a careless PU prefix rule would misfile as 'self'
        "penn": [rec("penn", "e1", "PUL"), rec("penn", "e2", "PU")],
        # HVL is an *inferred* Harvard symbol: at Harvard it must land in
        # self_inferred, not self; held elsewhere it still reads as 'pod'
        "harvard": [
            rec("harvard", "h1", "MH"),  # self (confirmed)
            rec("harvard", "h2", "HVL"),  # self_inferred
            rec("harvard", "h3", "HLS"),  # self (confirmed)
        ],
    }
    config = _build_lake(tmp_path, records)
    connection = lake.connect(read_only=True, config=config)
    try:
        out = queries.cataloging_source(connection, threshold=1)
    finally:
        connection.close()

    by_org = {o["org"]: o for o in out["per_org"]}
    assert by_org["stanford"]["records"] == 15
    counts = by_org["stanford"]["counts"]
    # s1, s2, s10, s11, s12, s13 -> lc; s4/s5/s6/s15 -> self; s7 -> pod;
    # s8, s14 -> other; s9 -> none; s3 -> oclc
    # s3's $a OCoLC is no longer its own bucket -- 040 records authorship, not
    # distribution channel -- so it falls to 'other' alongside s8 and s14
    assert counts == {
        "lc": 6,
        "self": 4,
        "self_inferred": 0,
        "pod": 1,
        "other": 3,
        "none": 1,
    }
    mix = by_org["stanford"]["mix"]
    assert mix["lc"] == round(6 / 15, 4)
    assert sum(mix.values()) == pytest.approx(1.0, abs=1e-3)

    # every bucket is published in a fixed order, even when a share is 0
    assert list(mix) == list(queries._CAT_BUCKETS)

    # one member's OCLC symbol seen at another member reads as 'pod', not 'self'
    assert by_org["penn"]["counts"] == {
        "lc": 0,
        "self": 1,  # e2, PU
        "self_inferred": 0,
        "pod": 1,  # e1, PUL -> Princeton
        "other": 0,
        "none": 0,
    }
    # an inferred symbol is reported apart from confirmed self-attribution, so the
    # unratified part of the figure stays visible instead of being folded in
    harvard = by_org["harvard"]["counts"]
    assert harvard["self"] == 2 and harvard["self_inferred"] == 1  # MH+HLS, HVL
    # but flow counts both together — it measures direction, not certainty
    assert out["dimensions"]["flow"]["matrix"]["harvard"]["harvard"] == 3

    # flow is asymmetric: the diagonal is self-cataloging, off-diagonal is copy
    flow = out["dimensions"]["flow"]
    assert flow["categories"] == sorted(queries._SELF_CODES)  # full member roster
    assert flow["matrix"]["stanford"]["stanford"] == 4  # s4, s5, s6, s15
    assert flow["matrix"]["stanford"]["princeton"] == 1  # s7
    assert flow["matrix"]["princeton"]["stanford"] == 1  # p2
    assert flow["matrix"]["princeton"]["princeton"] == 1  # p1
    # totals are withheld: categories exhaust the total, so publishing them would
    # make a suppressed cell recoverable by subtraction
    assert "totals" not in flow

    # top agencies keeps the raw normalized code, ranked by consortium total
    agency = out["dimensions"]["agency"]
    assert agency["categories"][0] == "DLC"
    assert agency["matrix"]["stanford"]["DLC"] == 5  # s1, s10, s11, s12, s13
    assert "STF" in agency["categories"]  # normalized from "stf"
    assert "DOCLCO" not in agency["categories"]  # the mangled repeat never wins
    assert "YNH" in agency["categories"]  # '*YNH*' normalized to the bare code
    assert "*YNH*" not in agency["categories"]
    # the shared axis is the union of each institution's own top agencies, so a
    # code carried only by one (small) institution still gets a row, and its
    # counts at the *other* institutions come through rather than reading as zero
    assert "PUL" in agency["categories"]  # only penn has it, 1 record
    assert agency["matrix"]["harvard"]["HVL"] == 1  # harvard's, and only harvard's
    assert agency["matrix"]["stanford"]["HVL"] == 0  # a real zero, not a gap
    # the share denominator is every record carrying an $a, not just the displayed
    # codes — otherwise selecting fewer rows would silently inflate the rest
    assert agency["totals"]["stanford"] == 14  # 15 records, s9 has no 040 at all
    assert agency["totals"]["harvard"] == 3

    # modification depth: distinct $d agencies, with "no 040 at all" kept apart
    depth = out["dimensions"]["mod_depth"]
    assert depth["categories"] == list(queries._MOD_DEPTH_BUCKETS)
    assert depth["matrix"]["stanford"]["3-4"] == 1  # s11: CSt/cst dedupe -> 3
    assert depth["matrix"]["stanford"]["1"] == 2  # s12, and s14 after * normalizing
    assert depth["matrix"]["stanford"]["no_040"] == 1  # s9 only
    assert depth["matrix"]["stanford"]["0"] == 11  # has an 040, but no $d
    assert depth["matrix"]["stanford"]["10+"] == 0  # empty bucket kept, not dropped


def test_cataloging_source_agency_axis_represents_every_institution(tmp_path):
    # The point of unioning per-institution top-N instead of ranking globally: a
    # small library's own principal agency must survive even when a large library's
    # middling agencies all outrank it consortium-wide.
    def rec(org, rid, source):
        pid = f"{org}:{rid}"
        return (
            [
                (org, pid, "LDR", 0, None, None, None, None, LEADER),
                (org, pid, "040", 1, " ", " ", "a", 0, source),
            ],
            (org, pid, rid),
        )

    # harvard has 15 distinct agencies of 40 records each; brown has one agency of
    # 25. A global top-12 would be all harvard's and would drop brown's entirely.
    records = {
        "harvard": [
            rec("harvard", f"h{i}-{j}", f"BIG{i:02d}")
            for i in range(15)
            for j in range(40)
        ],
        "brown": [rec("brown", f"b{j}", "SMALLONE") for j in range(25)],
    }
    config = _build_lake(tmp_path, records)
    connection = lake.connect(read_only=True, config=config)
    try:
        out = queries.cataloging_source(connection, threshold=10)
    finally:
        connection.close()

    cats = out["dimensions"]["agency"]["categories"]
    assert "SMALLONE" in cats, "brown's only agency was ranked off the shared axis"
    # brown contributes 1 row, harvard its own top 12 of 15 -> 13 rows total
    assert len(cats) == queries._CAT_AGENCY_PER_ORG + 1
    # and every institution has at least one non-zero cell on the axis
    for org, row in out["dimensions"]["agency"]["matrix"].items():
        assert any(v for v in row.values()), f"{org} has no agency represented"


def test_cataloging_source_suppresses_small_cells(tmp_path):
    # A lone off-diagonal flow cell ("brown holds 1 record cataloged by X") is
    # exactly the small cell disclosure control has to hide.
    def rec(org, rid, source):
        pid = f"{org}:{rid}"
        return (
            [
                (org, pid, "LDR", 0, None, None, None, None, LEADER),
                (org, pid, "040", 1, " ", " ", "a", 0, source),
            ],
            (org, pid, rid),
        )

    records = {
        "brown": [rec("brown", f"b{i}", "RPB") for i in range(20)]
        + [rec("brown", "b99", "CSt")]  # a single Stanford-cataloged record
    }
    config = _build_lake(tmp_path, records)
    connection = lake.connect(read_only=True, config=config)
    try:
        out = queries.cataloging_source(connection, threshold=10)
    finally:
        connection.close()

    flow = out["dimensions"]["flow"]
    assert flow["matrix"]["brown"]["brown"] == 20  # above threshold, published
    assert flow["matrix"]["brown"]["stanford"] is None  # 1 record -> suppressed
    # the mix folds that record into 'other' rather than publishing a 1-record
    # bucket, so the bar still sums to 1.0 and the count isn't recoverable
    brown = {o["org"]: o for o in out["per_org"]}["brown"]
    assert brown["counts"]["pod"] == 0
    assert brown["counts"]["other"] == 1
    assert list(brown["counts"]) == list(queries._CAT_BUCKETS)
    assert sum(brown["counts"].values()) == brown["records"] == 21
    assert (
        suppress.small_cells(
            [{"category": k, "count": v} for k, v in brown["counts"].items()],
            threshold=10,
            other_label="other",
        )
        == []
    )


def test_record_channels(tmp_path):
    # 035 $a is "(ORGCODE)number" — the system the number belongs to. Channels
    # overlap by design (a post-merger record carries both OCLC and RLIN numbers).
    def rec(org, rid, *namespaces):
        pid = f"{org}:{rid}"
        rows = [(org, pid, "LDR", 0, None, None, None, None, LEADER)]
        for i, ns in enumerate(namespaces, start=1):
            rows.append((org, pid, "035", i, " ", " ", "a", 0, ns))
        return rows, (org, pid, rid)

    records = {
        "stanford": [
            rec("stanford", "s1", "(OCoLC)12345"),
            # the Symphony-era variants must count as OCLC, not as separate systems
            rec("stanford", "s2", "(OCoLC-M)999"),
            rec("stanford", "s3", "(OCoLC-I)888"),
            # both OCLC and RLIN on one record: overlapping channels, not a split
            rec("stanford", "s4", "(OCoLC)7", "(CStRLIN)CSTX123"),
            rec("stanford", "s5", "(CSt)local-1"),  # own system
            rec("stanford", "s6", "(NjP)princeton-1"),  # another member's system
            rec("stanford", "s7", "(SIRSI)a123"),  # generic local ILS namespace
            rec("stanford", "s8"),  # no 035 at all
            rec("stanford", "s9", "no-parenthetical-prefix"),  # unparseable
        ],
        "duke": [
            rec("duke", "d1", "(EXLCZ)99123"),  # Alma Community Zone
            rec("duke", "d2", "(CKB)456"),  # ... and its knowledge base
            rec("duke", "d3", "(OCoLC)321"),
        ],
    }
    config = _build_lake(tmp_path, records)
    connection = lake.connect(read_only=True, config=config)
    try:
        out = queries.record_channels(connection, threshold=1)
    finally:
        connection.close()

    by_org = {o["org"]: o for o in out["per_org"]}
    st = by_org["stanford"]
    assert st["records"] == 9
    cov = st["coverage"]
    # s1, s2, s3, s4 -> OCLC (the -M/-I variants must not be missed)
    assert cov["oclc"] == round(4 / 9, 4)
    assert cov["rlin"] == round(1 / 9, 4)  # s4 only
    # s5 (its own code) and s7 (a generic local-ILS namespace) both count as local
    assert cov["local_system"] == round(2 / 9, 4)
    assert cov["pod_system"] == round(1 / 9, 4)  # s6
    # s8 has no 035, s9's value has no (namespace) to parse
    assert cov["any_system"] == round(7 / 9, 4)
    # channels overlap rather than partition, so they may sum past 1
    assert sum(cov.values()) > 1

    dk = by_org["duke"]["coverage"]
    assert dk["alma_cz"] == round(2 / 3, 4)  # EXLCZ + CKB
    assert dk["oclc"] == round(1 / 3, 4)

    # overlapping channels have no "other" bucket to fold a small count into, so a
    # sub-threshold cell is nulled rather than zeroed
    connection = lake.connect(read_only=True, config=config)
    try:
        strict = queries.record_channels(connection, threshold=10)
    finally:
        connection.close()
    strict_st = {o["org"]: o for o in strict["per_org"]}["stanford"]
    # this lake is tiny, so at threshold=10 every non-zero count is suppressed --
    # nulled, not zeroed, so the chart can tell "too few to report" from "none"
    assert strict_st["counts"]["rlin"] is None  # 1 record
    assert strict_st["coverage"]["rlin"] is None
    assert strict_st["counts"]["oclc"] is None  # 4 records
    assert strict_st["counts"]["any_system"] is None  # 7 records
    # a genuine zero survives as 0 rather than being confused with suppression
    assert {o["org"]: o for o in strict["per_org"]}["duke"]["counts"]["rlin"] == 0

    ns = out["dimensions"]["namespace"]
    # namespaces are the raw prefixes, uppercased, variants kept distinct here
    assert "OCOLC-M" in ns["categories"] and "SIRSI" in ns["categories"]
    # the denominator is every record, including the two with no usable 035
    assert ns["totals"]["stanford"] == 9
    assert ns["matrix"]["stanford"]["OCOLC"] == 2  # s1, s4
    assert ns["matrix"]["duke"]["OCOLC"] == 1
    assert ns["matrix"]["duke"]["SIRSI"] == 0  # a real zero, not a gap


def test_artifacts_expose_runnable_sql(con, tmp_path):
    # the `con` fixture built its lake under this same tmp_path, so _dev_config
    # re-derives the config needed to open a second, independent connection
    con_config = _dev_config(tmp_path)
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
    # cataloging_source's queries read a temp table, so each embedded sql list has
    # to carry the DDL in front of it or the panel shows something unrunnable.
    # Execute on a *fresh* connection to prove that, rather than accidentally
    # relying on the table cataloging_source() just created.
    cat = queries.cataloging_source(con, threshold=1)
    assert cat["sql"]
    # record_channels needs no temp table, so its queries stand alone already
    chan = queries.record_channels(con, threshold=1)
    assert chan["sql"]
    for q in chan["sql"] + chan["dimensions"]["namespace"]["sql"]:
        con.execute(q["sql"])

    for step_list in [cat["sql"], *(d["sql"] for d in cat["dimensions"].values())]:
        assert step_list, "cataloging_source exposes an empty sql list"
        fresh = lake.connect(read_only=True, config=con_config)
        try:
            for q in step_list:
                fresh.execute(q["sql"])
        finally:
            fresh.close()


def test_fold_small_keeps_all_above_threshold():
    rows = [{"category": x, "count": c} for x, c in [("a", 30), ("b", 20), ("c", 1)]]
    out = suppress.fold_small(rows, threshold=10)
    assert {r["category"]: r["count"] for r in out} == {"a": 30, "b": 20, "Other": 1}
