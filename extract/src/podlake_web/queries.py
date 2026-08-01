"""
Tier-1 aggregate queries against a read-only podlake DuckLake.

Every function returns a JSON-serializable dict of **aggregates only** — counts,
distributions, percentages — never a ``pod_record_id``, ``goldrush_key``, title,
or raw field value used as an identifier. Categorical distributions are passed
through :mod:`podlake_web.suppress` so no small cell is exposed on its own.

Each artifact embeds, in a ``sql`` field, the exact DuckDB query (or queries)
that produced it — so the dashboard can show the query behind every chart, and
the "About the data" / "Query it yourself" pages stay in sync with what actually
runs. The Python post-processing (suppression, the comparison share matrix, the
place roll-ups) is *not* expressible in that SQL; the site links back to this
module for it.

MARC notes (DuckDB ``substr`` is 1-indexed):

- ``record_meta`` has one row per record: ``org``, ``pod_record_id``,
  ``goldrush_key`` (the consortial Gold Rush match key).
- ``records`` is tall/EAV: ``org, pod_record_id, field_tag, field_seq, ind1,
  ind2, subfield_code, subfield_seq, value``. The leader is ``field_tag='LDR'``;
  control fields (00X) carry their data in ``value`` with a NULL subfield_code.
- 008 fixed field: date1 = chars 8-11, place/country = 16-18, language = 36-38.
- Leader: type-of-record = char 7, bibliographic level = char 8.
"""

from __future__ import annotations

import duckdb

from podlake_web import suppress

Connection = duckdb.DuckDBPyConnection


# --- SQL --------------------------------------------------------------------

Q_TOTALS = """\
SELECT count(*) AS records,
       count(DISTINCT goldrush_key) AS titles,
       count(DISTINCT org) AS institutions
FROM record_meta"""

Q_PER_ORG = """\
SELECT org, count(*) AS records, count(DISTINCT goldrush_key) AS titles
FROM record_meta
GROUP BY org
ORDER BY org"""

Q_ORG_TITLES = """\
SELECT org, count(DISTINCT goldrush_key) AS titles
FROM record_meta
GROUP BY org
ORDER BY org"""

Q_OVERLAP_HISTOGRAM = """\
SELECT institutions, count(*) AS titles
FROM (
  SELECT goldrush_key, count(DISTINCT org) AS institutions
  FROM record_meta
  GROUP BY goldrush_key
)
GROUP BY institutions
ORDER BY institutions"""

Q_PAIRWISE = """\
WITH holdings AS (SELECT DISTINCT org, goldrush_key FROM record_meta)
SELECT a.org AS a, b.org AS b, count(*) AS shared
FROM holdings a
JOIN holdings b USING (goldrush_key)
WHERE a.org < b.org
GROUP BY a.org, b.org
ORDER BY shared DESC"""

Q_UNIQUENESS = """\
SELECT org, count(*) AS unique_titles
FROM (
  SELECT any_value(org) AS org
  FROM record_meta
  GROUP BY goldrush_key
  HAVING count(DISTINCT org) = 1
)
GROUP BY org
ORDER BY unique_titles DESC"""

# {4} is a regexp quantifier, not a format field — this string is executed as-is
# (never .format()-ed), so the brace stays literal.
Q_DECADE = """\
SELECT org,
       (CAST(substr(value, 8, 4) AS INTEGER) // 10) * 10 AS decade,
       count(*) AS records
FROM records
WHERE field_tag = '008'
  AND regexp_matches(substr(value, 8, 4), '^[0-9]{4}$')
  AND CAST(substr(value, 8, 4) AS INTEGER) BETWEEN 1450 AND 2030
GROUP BY org, decade
ORDER BY org, decade"""

Q_COVERAGE = """\
WITH present AS (
  SELECT org, pod_record_id,
         max(field_tag = '020')                AS isbn,
         max(field_tag LIKE '6%')              AS subjects,
         max(field_tag IN ('100','110','111')) AS author,
         max(field_tag = '856')                AS online,
         max(field_tag = '300')                AS phys_desc,
         max(field_tag IN ('050','082','090')) AS classification
  FROM records
  GROUP BY org, pod_record_id
)
SELECT org, count(*) AS records,
       sum(isbn) AS isbn, sum(subjects) AS subjects, sum(author) AS author,
       sum(online) AS online, sum(phys_desc) AS phys_desc,
       sum(classification) AS classification
FROM present
GROUP BY org
ORDER BY org"""


# --- query functions ---------------------------------------------------------


def overview(con: Connection, **_: object) -> dict:
    """Corpus totals and per-institution record/title counts (+ last sync)."""
    totals_row = con.execute(Q_TOTALS).fetchone()
    assert totals_row is not None
    records, titles, institutions = totals_row
    last_sync = _last_sync(con)
    per_org = [
        {"org": org, "records": recs, "titles": tts, "last_sync": last_sync.get(org)}
        for org, recs, tts in con.execute(Q_PER_ORG).fetchall()
    ]
    return {
        "totals": {"records": records, "titles": titles, "institutions": institutions},
        "per_org": per_org,
        "sql": [
            {"label": "Corpus totals", "sql": Q_TOTALS},
            {"label": "Records and titles per institution", "sql": Q_PER_ORG},
        ],
    }


def overlap_histogram(con: Connection, **_: object) -> dict:
    """How many titles are held by exactly N institutions (the rarity curve)."""
    rows = con.execute(Q_OVERLAP_HISTOGRAM).fetchall()
    return {
        "held_by": [{"institutions": n, "titles": t} for n, t in rows],
        "sql": [{"label": "Titles held by N institutions", "sql": Q_OVERLAP_HISTOGRAM}],
    }


def overlap_pairwise(con: Connection, **_: object) -> dict:
    """
    For every pair of institutions, the number of titles both hold, plus each
    institution's own title total. Symmetric, so only a<b pairs are emitted.
    """
    totals = dict(con.execute(Q_ORG_TITLES).fetchall())
    pairs = con.execute(Q_PAIRWISE).fetchall()
    return {
        "institutions": sorted(totals),
        "titles": totals,
        "pairs": [{"a": a, "b": b, "shared": s} for a, b, s in pairs],
        "sql": [
            {"label": "Titles per institution (the diagonal)", "sql": Q_ORG_TITLES},
            {"label": "Shared titles for each pair", "sql": Q_PAIRWISE},
        ],
    }


def uniqueness(con: Connection, **_: object) -> dict:
    """Per-institution count of titles held by that institution alone."""
    rows = con.execute(Q_UNIQUENESS).fetchall()
    return {
        "per_org": [{"org": org, "unique_titles": n} for org, n in rows],
        "sql": [{"label": "Titles held by a single institution", "sql": Q_UNIQUENESS}],
    }


def publication_decade(con: Connection, *, threshold: int = 10, **_: object) -> dict:
    """
    Records by decade of publication (008 date1), per institution — plausible
    years only (1450–2030), with sparse decades folded into an Other bucket.
    """
    data = _decade_histogram(con, threshold=threshold)
    data["sql"] = [{"label": "Records by decade of publication", "sql": Q_DECADE}]
    return data


def coverage(con: Connection, **_: object) -> dict:
    """
    Per-institution metadata completeness: share of records carrying selected
    fields (ISBN, subjects, author, electronic access, physical description,
    classification). Denominators are large, so no suppression is needed.
    """
    rows = con.execute(Q_COVERAGE).fetchall()
    fields = ["isbn", "subjects", "author", "online", "phys_desc", "classification"]
    per_org = []
    for org, records, *counts in rows:
        pct = {
            field: (round(count / records, 4) if records else 0.0)
            for field, count in zip(fields, counts)
        }
        per_org.append({"org": org, "records": records, "coverage": pct})
    return {
        "fields": fields,
        "per_org": per_org,
        "sql": [
            {"label": "Records carrying each field, per institution", "sql": Q_COVERAGE}
        ],
    }


# --- cross-institution comparison matrices -----------------------------------

# MARC country codes for the 50 U.S. states + D.C. (plus "xxu", the whole-US
# code). Place of publication normalizes these to "xxu" so state-level codes roll
# up into one "United States" total instead of scattering across the top-n. An
# explicit list — not a "3 chars ending in u" pattern — because a long tail of
# malformed codes (gwu, fru, 9xu, …) also ends in u but is not a U.S. state.
_US_PLACE_CODES = (
    "xxu",
    "alu",
    "aku",
    "azu",
    "aru",
    "cau",
    "cou",
    "ctu",
    "dcu",
    "deu",
    "flu",
    "gau",
    "hiu",
    "idu",
    "ilu",
    "inu",
    "iau",
    "ksu",
    "kyu",
    "lau",
    "meu",
    "mdu",
    "mau",
    "miu",
    "mnu",
    "msu",
    "mou",
    "mtu",
    "nbu",
    "nvu",
    "nhu",
    "nju",
    "nmu",
    "nyu",
    "ncu",
    "ndu",
    "ohu",
    "oku",
    "oru",
    "pau",
    "riu",
    "scu",
    "sdu",
    "tnu",
    "txu",
    "utu",
    "vtu",
    "vau",
    "wau",
    "wvu",
    "wiu",
    "wyu",
)
# Canadian provinces/territories (+ "xxc" Canada) and the UK's constituent
# countries (+ "xxk" United Kingdom, "uik" UK Misc. Islands). Same explicit-list
# rationale as the U.S. codes above (junk codes such as "nbc"/"-hk" also share a
# suffix but are not real subdivisions).
_CANADA_PLACE_CODES = (
    "xxc",
    "abc",
    "bcc",
    "mbc",
    "nkc",
    "nfc",
    "nsc",
    "ntc",
    "nuc",
    "onc",
    "pic",
    "quc",
    "snc",
    "ykc",
)
_UK_PLACE_CODES = ("xxk", "enk", "stk", "wlk", "nik", "uik")
# Non-standard "undetermined place" fills (some systems emit an all-"u" 008), the
# same meaning as the standard "xx" (no place / unknown), so folded in with it.
_UNKNOWN_PLACE_CODES = ("uuu",)

# Roll sub-national place codes up to their country before the top-n cut, so each
# country's total is complete rather than split across states/provinces/nations;
# fold undetermined-place fills into the standard unknown ("xx") bucket.
_PLACE_ROLLUP = (
    ("XXU", _US_PLACE_CODES),
    ("XXC", _CANADA_PLACE_CODES),
    ("XXK", _UK_PLACE_CODES),
    ("XX", _UNKNOWN_PLACE_CODES),
)
_PLACE_CODE = "upper(trim(substr(value, 16, 3)))"
_COUNTRY_EXPR = (
    "CASE "
    + " ".join(
        f"WHEN {_PLACE_CODE} IN ({', '.join(f'{c.upper()!r}' for c in codes)}) "
        f"THEN '{country}'"
        for country, codes in _PLACE_ROLLUP
    )
    + f" ELSE {_PLACE_CODE} END"
)

# Dimensions offered as cross-institution comparison matrices (the Languages,
# Place of publication, Format, and LC classification heatmaps). Each is a coded
# categorical read straight out of MARC — (value expression, WHERE clause).
_COMPARE_DIMENSIONS = {
    "language": (
        "upper(trim(substr(value, 36, 3)))",
        "field_tag = '008' AND length(value) >= 38",
    ),
    "country": (_COUNTRY_EXPR, "field_tag = '008' AND length(value) >= 18"),
    "record_type": ("substr(value, 7, 1)", "field_tag = 'LDR' AND length(value) >= 7"),
    # Library of Congress class = first letter of the LC call number (050, or the
    # locally-assigned 090). A shared controlled scheme, so it compares cleanly
    # across institutions. Restricted to a leading A–Z so stray values drop out.
    "classification": (
        "upper(substr(trim(value), 1, 1))",
        (
            "field_tag IN ('050', '090') AND subfield_code = 'a' "
            "AND regexp_matches(upper(substr(trim(value), 1, 1)), '[A-Z]')"
        ),
    ),
}
# Global top-k categories per dimension shown in the comparison heatmaps. Large
# enough to surface the long tail, small enough that rows stay legible.
_COMPARE_TOP_K = 15


def comparison(con: Connection, *, threshold: int = 10, **_: object) -> dict:
    """
    Cross-institution comparison matrices for the heatmap views. For each
    dimension: the global top-k categories (ranked by total count across all
    institutions), every institution's count per category, each institution's
    dimension total (the denominator for a share), and the SQL that produced the
    raw counts. Counts in ``1..threshold-1`` are suppressed to null so no small
    cell is exposed; a genuine zero stays 0. Category codes are labeled
    client-side.
    """
    return {
        "dimensions": {
            name: _comparison_matrix(con, expr=expr, where=where, threshold=threshold)
            for name, (expr, where) in _COMPARE_DIMENSIONS.items()
        }
    }


def _comparison_matrix(
    con: Connection, *, expr: str, where: str, threshold: int
) -> dict:
    sql = (
        f"SELECT org, {expr} AS category, count(*) AS n\n"
        f"FROM records\n"
        f"WHERE {where}\n"
        f"  AND {expr} IS NOT NULL AND trim({expr}) <> ''\n"
        f"GROUP BY org, category"
    )
    rows = con.execute(sql).fetchall()

    orgs = sorted({org for org, _cat, _n in rows})
    totals: dict[str, int] = dict.fromkeys(orgs, 0)
    cat_totals: dict[str, int] = {}
    counts: dict[tuple[str, str], int] = {}
    for org, cat, n in rows:
        totals[org] += n
        cat_totals[cat] = cat_totals.get(cat, 0) + n
        counts[(org, cat)] = n

    categories = [
        cat for cat, _ in sorted(cat_totals.items(), key=lambda kv: (-kv[1], kv[0]))
    ][:_COMPARE_TOP_K]

    def cell(org: str, cat: str) -> int | None:
        n = counts.get((org, cat), 0)
        return n if (n == 0 or n >= threshold) else None

    return {
        "categories": categories,
        "institutions": orgs,
        "totals": totals,
        "matrix": {org: {cat: cell(org, cat) for cat in categories} for org in orgs},
        "sql": sql,
    }


# --- internals ---------------------------------------------------------------


def _last_sync(con: Connection) -> dict[str, str | None]:
    """Per-org last-processed ResourceSync lastmod, if the lake tracks it."""
    try:
        rows = con.execute("SELECT org, last_modified FROM harvest_state").fetchall()
    except duckdb.Error:
        return {}
    return {org: (ts.isoformat() if ts else None) for org, ts in rows}


def _decade_histogram(con: Connection, *, threshold: int) -> dict:
    """008 date1 → decade, per org, plausible years only (1450–2030)."""
    rows = con.execute(Q_DECADE).fetchall()
    return _group_and_suppress(
        rows,
        fold=lambda bucket: suppress.fold_small(
            bucket, threshold=threshold, label_key="decade"
        ),
        label_key="decade",
    )


def _group_and_suppress(rows, *, fold, label_key: str) -> dict:
    """
    Group flat (org, category, count) rows by org and apply a suppression
    ``fold`` (which must read/write ``label_key``) to each org's bucket.
    Returns {"per_org": [{"org", "values"}]}.
    """
    by_org: dict[str, list[dict]] = {}
    for org, cat, count in rows:
        by_org.setdefault(org, []).append({label_key: cat, "count": count})
    return {
        "per_org": [{"org": org, "values": fold(by_org[org])} for org in sorted(by_org)]
    }
