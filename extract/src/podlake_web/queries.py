"""
Tier-1 aggregate queries against a read-only podlake DuckLake.

Every function returns a JSON-serializable dict of **aggregates only** — counts,
distributions, percentages — never a ``pod_record_id``, ``goldrush_key``, title,
or raw field value used as an identifier. Categorical distributions are passed
through :mod:`podlake_web.suppress` so no small cell is exposed on its own.

The core SQL lives in named ``Q_*`` constants that both the query functions
execute *and* :func:`showcase` publishes to the dashboard's "About the data"
page — so what visitors see is exactly what runs.

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


# --- SQL (also surfaced verbatim on the "About the data" page) ---------------

Q_PER_ORG = """\
SELECT org, count(*) AS records, count(DISTINCT goldrush_key) AS titles
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

# {top_n} / {threshold} are filled in at build time via .format().
Q_SUBJECTS = """\
WITH subjects AS (
  SELECT org, rtrim(value, ' .,;:/') AS subject, count(*) AS records
  FROM records
  WHERE field_tag = '650' AND subfield_code = 'a'
    AND value IS NOT NULL AND trim(value) <> ''
  GROUP BY org, subject
),
ranked AS (
  SELECT *, row_number() OVER (PARTITION BY org ORDER BY records DESC) AS rn
  FROM subjects
)
SELECT org, subject, records
FROM ranked
WHERE rn <= {top_n} AND records >= {threshold}
ORDER BY org, records DESC"""

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


def showcase(*, top_n: int = 25, threshold: int = 10) -> list[dict]:
    """
    The core queries behind the dashboard, as copy-pasteable DuckDB SQL, for the
    "About the data" page. Ordered from the headline consortial questions to the
    MARC-parsing examples that invite people to write their own.
    """
    return [
        {
            "id": "overlap",
            "title": "Titles held by N institutions",
            "note": "The rarity curve: group each title (by its Gold Rush key) by "
            "how many distinct institutions hold it. The left of the curve is rare "
            "material; the right is the widely-duplicated core.",
            "sql": Q_OVERLAP_HISTOGRAM,
        },
        {
            "id": "pairwise",
            "title": "Shared titles between institutions",
            "note": "A self-join on the Gold Rush key counts, for every pair of "
            "institutions, how many titles both hold — the basis of comparative "
            "collection analysis.",
            "sql": Q_PAIRWISE,
        },
        {
            "id": "uniqueness",
            "title": "Titles held by a single institution",
            "note": "Titles whose Gold Rush key appears at exactly one institution — "
            'the "last copies" that preservation and shared-print decisions turn on.',
            "sql": Q_UNIQUENESS,
        },
        {
            "id": "per_org",
            "title": "Records and titles per institution",
            "note": "Records are individual bibliographic records; titles collapse "
            "them by Gold Rush key, so the gap shows within-library duplication.",
            "sql": Q_PER_ORG,
        },
        {
            "id": "decade",
            "title": "Publication era from the MARC 008 field",
            "note": "Characters 8–11 of the 008 fixed field hold the publication "
            "year — pull them straight out of the record with substr and bucket "
            "into decades.",
            "sql": Q_DECADE,
        },
        {
            "id": "subjects",
            "title": "Top subject headings (MARC 650 $a)",
            "note": f"The {top_n} most common subject headings per institution "
            "(the tall/EAV layout makes any subfield a plain WHERE clause).",
            "sql": Q_SUBJECTS.format(top_n=top_n, threshold=threshold),
        },
        {
            "id": "coverage",
            "title": "Metadata coverage",
            "note": "For each record, does it carry a given field? A boolean pivot "
            "per record, then averaged — a quick metadata-completeness scorecard.",
            "sql": Q_COVERAGE,
        },
    ]


# --- query functions ---------------------------------------------------------


def overview(con: Connection, **_: object) -> dict:
    """Corpus totals and per-institution record/title counts (+ last sync)."""
    totals_row = con.execute(
        "SELECT count(*), count(DISTINCT goldrush_key), count(DISTINCT org) "
        "FROM record_meta"
    ).fetchone()
    assert totals_row is not None
    records, titles, institutions = totals_row

    per_org_rows = con.execute(Q_PER_ORG).fetchall()

    last_sync = _last_sync(con)
    per_org = [
        {
            "org": org,
            "records": recs,
            "titles": tts,
            "last_sync": last_sync.get(org),
        }
        for org, recs, tts in per_org_rows
    ]

    return {
        "totals": {
            "records": records,
            "titles": titles,
            "institutions": institutions,
        },
        "per_org": per_org,
    }


def overlap_histogram(con: Connection, **_: object) -> dict:
    """How many titles are held by exactly N institutions (the rarity curve)."""
    rows = con.execute(Q_OVERLAP_HISTOGRAM).fetchall()
    return {"held_by": [{"institutions": n, "titles": t} for n, t in rows]}


def overlap_pairwise(con: Connection, **_: object) -> dict:
    """
    For every pair of institutions, the number of titles both hold, plus each
    institution's own title total. Symmetric, so only a<b pairs are emitted.
    """
    totals = dict(
        con.execute(
            "SELECT org, count(DISTINCT goldrush_key) FROM record_meta GROUP BY org"
        ).fetchall()
    )
    pairs = con.execute(Q_PAIRWISE).fetchall()
    return {
        "institutions": sorted(totals),
        "titles": totals,
        "pairs": [{"a": a, "b": b, "shared": s} for a, b, s in pairs],
    }


def uniqueness(con: Connection, **_: object) -> dict:
    """Per-institution count of titles held by that institution alone."""
    rows = con.execute(Q_UNIQUENESS).fetchall()
    return {"per_org": [{"org": org, "unique_titles": n} for org, n in rows]}


def characterization(con: Connection, *, top_n: int = 25, threshold: int = 10) -> dict:
    """
    Per-institution collection characterization: publication-decade histogram,
    and top languages / countries / subjects / record types. Each distribution
    is suppressed (top-n + small-cell folding).
    """
    return {
        "publication_decade": _decade_histogram(con, threshold=threshold),
        "language": _small_card_dist(
            con,
            expr="upper(trim(substr(value, 36, 3)))",
            where="field_tag = '008' AND length(value) >= 38",
            top_n=top_n,
            threshold=threshold,
        ),
        "country": _small_card_dist(
            con,
            expr="upper(trim(substr(value, 16, 3)))",
            where="field_tag = '008' AND length(value) >= 18",
            top_n=top_n,
            threshold=threshold,
        ),
        "record_type": _small_card_dist(
            con,
            expr="substr(value, 7, 1)",
            where="field_tag = 'LDR' AND length(value) >= 7",
            top_n=top_n,
            threshold=threshold,
        ),
        "subject": _subject_dist(con, top_n=top_n, threshold=threshold),
    }


def coverage(con: Connection, **_: object) -> dict:
    """
    Per-institution metadata coverage: share of records carrying selected
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
    return {"fields": fields, "per_org": per_org}


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


def _small_card_dist(
    con: Connection, *, expr: str, where: str, top_n: int, threshold: int
) -> dict:
    """A low-cardinality categorical (language/country/record type), top-n + Other."""
    rows = con.execute(
        f"SELECT org, {expr} AS cat, count(*) AS count "
        f"FROM records WHERE {where} AND {expr} IS NOT NULL AND trim({expr}) <> '' "
        "GROUP BY org, cat"
    ).fetchall()
    return _group_and_suppress(
        rows,
        fold=lambda bucket: suppress.bucket_top_n(bucket, n=top_n, threshold=threshold),
        label_key="category",
    )


def _subject_dist(con: Connection, *, top_n: int, threshold: int) -> dict:
    """
    Top 650 $a subject headings per org. High cardinality, so the top-n cut is
    done in SQL (a window per org) before anything leaves the database.
    """
    rows = con.execute(
        Q_SUBJECTS.format(top_n=int(top_n), threshold=int(threshold))
    ).fetchall()
    by_org: dict[str, list[dict]] = {}
    for org, subject, count in rows:
        by_org.setdefault(org, []).append({"category": subject, "count": count})
    return {"per_org": [{"org": org, "values": vals} for org, vals in by_org.items()]}


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
