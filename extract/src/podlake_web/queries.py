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

# Treat "still published" (008/06='c') and the 9999 open-ended marker as running
# to this year — the snapshot's notion of "present". Records dated past it are
# clamped out; bump when the lake is refreshed well beyond it. Also the century
# pivot for two-digit dates entered (see ``_ENTERED_YEAR``), so leaving it behind
# the lake is not merely conservative — it would read this year's records as
# having been cataloged a hundred years ago.
NOW_YEAR = 2026

# Serials active per year: a serial (leader/07='s') is "active" in every year its
# publication run covers. Start = 008 date1; end = 008 date2, except 'c' (still
# published) and the 9999 marker run to NOW_YEAR. Serials with an unknown start
# or an undetermined end ('u' status, non-numeric date2) can't be placed on the
# timeline and drop out. The {N} tokens are filled with NOW_YEAR before running
# (an f-string would collide with the regexp {4} quantifier).
Q_SERIALS_ACTIVE = """\
WITH serial AS (
  SELECT DISTINCT org, pod_record_id FROM records
  WHERE field_tag = 'LDR' AND substr(value, 8, 1) = 's'
),
dated AS (
  SELECT s.org,
         substr(r.value, 7, 1) AS date_type,
         CAST(substr(r.value, 8, 4) AS INTEGER) AS y1,
         substr(r.value, 12, 4) AS d2
  FROM serial s JOIN records r USING (org, pod_record_id)
  WHERE r.field_tag = '008' AND length(r.value) >= 15
    AND regexp_matches(substr(r.value, 8, 4), '^[0-9]{4}$')
    AND CAST(substr(r.value, 8, 4) AS INTEGER) BETWEEN 1500 AND {N}
),
span AS (
  SELECT org, y1,
         CASE
           WHEN d2 = '9999' THEN {N}
           WHEN date_type = 'c' THEN {N}
           WHEN date_type = 'd' AND regexp_matches(d2, '^[0-9]{4}$')
                THEN CAST(d2 AS INTEGER)
         END AS y2
  FROM dated
),
active AS (
  SELECT org, y1, y2 FROM span
  WHERE y2 IS NOT NULL AND y2 >= y1 AND y2 <= {N}
)
SELECT org, yr AS year, count(*) AS records
FROM active, unnest(generate_series(y1, y2)) AS g(yr)
GROUP BY org, yr
ORDER BY org, yr"""

# Serials by decade of first publication (008 date1). Normalized per institution
# on the site, this shows collection *vintage* — deep historical runs vs mostly
# recent — independent of collection size.
Q_SERIALS_START_DECADE = """\
WITH serial AS (
  SELECT DISTINCT org, pod_record_id FROM records
  WHERE field_tag = 'LDR' AND substr(value, 8, 1) = 's'
)
SELECT s.org,
       (CAST(substr(r.value, 8, 4) AS INTEGER) // 10) * 10 AS decade,
       count(*) AS records
FROM serial s JOIN records r USING (org, pod_record_id)
WHERE r.field_tag = '008' AND length(r.value) >= 11
  AND regexp_matches(substr(r.value, 8, 4), '^[0-9]{4}$')
  AND CAST(substr(r.value, 8, 4) AS INTEGER) BETWEEN 1700 AND 2025
GROUP BY s.org, decade
ORDER BY s.org, decade"""

# Serial succession: catalogers record title changes with linking-entry fields —
# 780 (preceding entry, what this serial continues) and 785 (succeeding entry,
# what it became). These queries measure the *presence* of those links per
# serial, and the 785 relationship type (its indicator 2), against the total
# serial count. They do not reconstruct chains.
Q_SER_TOTAL = """\
SELECT org, count(*) AS n
FROM (SELECT DISTINCT org, pod_record_id FROM records
      WHERE field_tag = 'LDR' AND substr(value, 8, 1) = 's')
GROUP BY org"""

Q_SER_LINK = """\
WITH serial AS (
  SELECT DISTINCT org, pod_record_id FROM records
  WHERE field_tag = 'LDR' AND substr(value, 8, 1) = 's'
)
SELECT org, 'pred' AS category, count(*) AS n FROM serial
WHERE (org, pod_record_id) IN (SELECT org, pod_record_id FROM records WHERE field_tag = '780')
GROUP BY org
UNION ALL
SELECT org, 'succ' AS category, count(*) AS n FROM serial
WHERE (org, pod_record_id) IN (SELECT org, pod_record_id FROM records WHERE field_tag = '785')
GROUP BY org"""

Q_SER_TYPE = """\
WITH serial AS (
  SELECT DISTINCT org, pod_record_id FROM records
  WHERE field_tag = 'LDR' AND substr(value, 8, 1) = 's'
)
SELECT r.org, r.ind2 AS category, count(DISTINCT r.pod_record_id) AS n
FROM records r
JOIN serial USING (org, pod_record_id)
WHERE r.field_tag = '785' AND r.ind2 IN ('0','1','2','3','4','5','6','7','8')
GROUP BY r.org, r.ind2"""

# Where an LC call number lives, in priority order (first match wins): the
# standard 050/090, plus the local holdings/item fields libraries actually use
# (852 at Harvard/Princeton, 950 at Stanford, 900 $f at Brown, …). Shared by the
# LC-classification heatmap and the completeness scorecard.
#
# Each location is (field, subfield, extra) where `extra` is an additional SQL
# condition or None. The 852 holdings field's first indicator encodes the
# shelving scheme, so we require ind1='0' (LC classification) — otherwise its $h
# also carries Dewey, NLM, SuDoc, and local schemes. The 050/090 fields are LC
# by definition/convention; the local 9xx fields have no scheme indicator, so we
# lean on the LC-shaped value check and accept that a stray non-LC number there
# is indistinguishable (we would rather undercount than mislabel).
_LC_LOCATIONS = [
    ("050", "a", None),
    ("090", "a", None),
    ("852", "h", "ind1 = '0'"),
    ("950", "a", None),
    ("900", "f", None),
    ("099", "a", None),
    ("949", "a", None),
]


def _lc_loc_cond(field: str, subfield: str, extra: str | None) -> str:
    cond = f"field_tag = '{field}' AND subfield_code = '{subfield}'"
    return f"{cond} AND {extra}" if extra else cond


# LC-shaped value: leads with a class letter LC actually uses (A–H, J–N, P–V, Z
# — LC skips I, O, W, X, Y), and is not an NLM preclinical number (NLM reuses Q
# for QS–QZ, which LC never does). Dewey/UDC lead with a digit and fall out here.
_LC_SHAPE = (
    "regexp_matches(upper(substr(trim(value), 1, 1)), '[A-HJ-NP-VZ]') "
    "AND NOT regexp_matches(upper(substr(trim(value), 1, 2)), '^Q[S-Z]')"
)
_LC_CALLNUM = (
    "("
    + " OR ".join(f"({_lc_loc_cond(*loc)})" for loc in _LC_LOCATIONS)
    + f") AND {_LC_SHAPE}"
)

# Field tags the coverage query needs (besides the LIKE '6%' subjects). Derived
# from _LC_LOCATIONS so the pre-filter can't drift from the LC-classification set.
_COVERAGE_TAGS = ", ".join(
    f"'{t}'"
    for t in sorted(
        {"020", "100", "110", "111", "856", "300"} | {f for f, _s, _e in _LC_LOCATIONS}
    )
)

# Per-institution field coverage: for each field, the number of records that
# carry it, counted directly per org. The WHERE keeps the scan to the handful of
# relevant field tags; counting DISTINCT records per org avoids collapsing the
# whole (billions-of-rows) table into one group per record first. Denominators
# come from record_meta (one row per record).
Q_COVERAGE = f"""\
WITH totals AS (
  SELECT org, count(*) AS records FROM record_meta GROUP BY org
),
present AS (
  SELECT org,
    count(DISTINCT pod_record_id) FILTER (WHERE field_tag = '020')                AS isbn,
    count(DISTINCT pod_record_id) FILTER (WHERE field_tag LIKE '6%')              AS subjects,
    count(DISTINCT pod_record_id) FILTER (WHERE field_tag IN ('100','110','111')) AS author,
    count(DISTINCT pod_record_id) FILTER (WHERE field_tag = '856')                AS online,
    count(DISTINCT pod_record_id) FILTER (WHERE field_tag = '300')                AS phys_desc,
    count(DISTINCT pod_record_id) FILTER (WHERE {_LC_CALLNUM}) AS lc_classification
  FROM records
  WHERE field_tag LIKE '6%' OR field_tag IN ({_COVERAGE_TAGS})
  GROUP BY org
)
SELECT t.org, t.records,
       coalesce(p.isbn, 0)              AS isbn,
       coalesce(p.subjects, 0)          AS subjects,
       coalesce(p.author, 0)            AS author,
       coalesce(p.online, 0)            AS online,
       coalesce(p.phys_desc, 0)         AS phys_desc,
       coalesce(p.lc_classification, 0) AS lc_classification
FROM totals t LEFT JOIN present p USING (org)
ORDER BY t.org"""


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


def serials_timeline(con: Connection, **_: object) -> dict:
    """
    Two time views of each institution's serials, both counting holdings (a title
    held by several institutions is counted once per holder):

    - ``active``: serials being published in each year (start ≤ year ≤ end); see
      ``Q_SERIALS_ACTIVE`` for how the run is derived from the 008 dates.
    - ``start_decade``: serials by decade of first publication, for a normalized
      view of collection vintage.
    """
    active_sql = Q_SERIALS_ACTIVE.replace("{N}", str(NOW_YEAR))
    active: dict[str, list] = {}
    for org, year, records in con.execute(active_sql).fetchall():
        active.setdefault(org, []).append({"year": year, "count": records})

    starts: dict[str, list] = {}
    for org, decade, records in con.execute(Q_SERIALS_START_DECADE).fetchall():
        starts.setdefault(org, []).append({"decade": decade, "count": records})

    orgs = sorted(set(active) | set(starts))
    return {
        "now_year": NOW_YEAR,
        "active": [{"org": o, "values": active.get(o, [])} for o in orgs],
        "start_decade": [{"org": o, "values": starts.get(o, [])} for o in orgs],
        "sql": [
            {"label": "Active serials per year", "sql": active_sql},
            {
                "label": "Serials by decade of first publication",
                "sql": Q_SERIALS_START_DECADE,
            },
        ],
    }


def serials_succession(con: Connection, *, threshold: int = 10, **_: object) -> dict:
    """
    Serial succession as recorded in the 780/785 linking-entry fields, shaped as
    two share-heatmap dimensions (denominator = each institution's total serials,
    so the shares are of *all* serials, not just linked ones):

    - ``succession_link``: share of serials carrying a predecessor (780) or a
      successor (785) link — the two overlap and do not sum to 100%.
    - ``succession_type``: share of serials with each kind of 785 relationship
      (its indicator 2: continued by, merged, split, absorbed, …).

    Counts below ``threshold`` are suppressed to null.
    """
    totals = dict(con.execute(Q_SER_TOTAL).fetchall())
    orgs = sorted(totals)

    def dimension(sql: str, categories: list[str], *, rank: bool) -> dict:
        counts = {(org, cat): n for org, cat, n in con.execute(sql).fetchall()}
        cats = categories
        if rank:  # keep the categories present, most common first
            totals_by_cat: dict[str, int] = {}
            for (_org, cat), n in counts.items():
                totals_by_cat[cat] = totals_by_cat.get(cat, 0) + n
            cats = sorted(totals_by_cat, key=lambda c: -totals_by_cat[c])

        def cell(org: str, cat: str) -> int | None:
            n = counts.get((org, cat), 0)
            return n if (n == 0 or n >= threshold) else None

        return {
            "categories": cats,
            "institutions": orgs,
            "totals": totals,
            "matrix": {org: {c: cell(org, c) for c in cats} for org in orgs},
            "sql": sql,
        }

    return {
        "dimensions": {
            "succession_link": dimension(Q_SER_LINK, ["pred", "succ"], rank=False),
            "succession_type": dimension(Q_SER_TYPE, list("012345678"), rank=True),
        },
        "sql": [
            {"label": "Serials linked to a predecessor / successor", "sql": Q_SER_LINK},
            {
                "label": "Serials by succeeding-entry (785) relationship type",
                "sql": Q_SER_TYPE,
            },
        ],
    }


# Archives & manuscripts: leader/06 type-of-record t/d/f/p (manuscript text, music,
# maps, mixed materials) OR leader/08 bibliographic level c/d (collection & subunit).
# Broad on purpose — captures collection-level description, including some printed
# collections. Reused by every archives() query below (mirrors the serial-subset
# idiom). Built with concatenation, not f-strings, so regexp {n} braces stay literal.
_ARCH_WITH = (
    "WITH arch AS (\n"
    "  SELECT org, pod_record_id, substr(value, 7, 1) AS rtype\n"
    "  FROM records\n"
    "  WHERE field_tag = 'LDR' AND length(value) >= 8\n"
    "    AND (substr(value, 7, 1) IN ('t','d','f','p')\n"
    "         OR substr(value, 8, 1) IN ('c','d'))\n"
    ")\n"
)

Q_ARCH_TOTAL = _ARCH_WITH + "SELECT org, count(*) AS n FROM arch GROUP BY org"

Q_ARCH_TYPE = _ARCH_WITH + (
    "SELECT org, rtype AS category, count(*) AS n FROM arch GROUP BY org, rtype"
)

Q_ARCH_GENRE = _ARCH_WITH + (
    "SELECT a.org, lower(rtrim(trim(r.value), ' .')) AS category,\n"
    "       count(DISTINCT r.pod_record_id) AS n\n"
    "FROM arch a JOIN records r USING (org, pod_record_id)\n"
    "WHERE r.field_tag = '655' AND r.subfield_code = 'a' AND trim(r.value) <> ''\n"
    "GROUP BY a.org, category"
)

Q_ARCH_DECADE = _ARCH_WITH + (
    "SELECT a.org, (CAST(substr(r.value, 8, 4) AS INTEGER) // 10) * 10 AS decade,\n"
    "       count(*) AS n\n"
    "FROM arch a JOIN records r USING (org, pod_record_id)\n"
    "WHERE r.field_tag = '008' AND length(r.value) >= 11\n"
    "  AND regexp_matches(substr(r.value, 8, 4), '^[0-9]{4}$')\n"
    "  AND CAST(substr(r.value, 8, 4) AS INTEGER) BETWEEN 100 AND 2025\n"
    "GROUP BY a.org, decade ORDER BY a.org, decade"
)

Q_ARCH_LINK = _ARCH_WITH + (
    "SELECT org, count(*) AS n FROM arch\n"
    "WHERE (org, pod_record_id) IN\n"
    "      (SELECT org, pod_record_id FROM records\n"
    "       WHERE field_tag = '856' AND subfield_code = 'u')\n"
    "GROUP BY org"
)

# Classify 856 link hosts into a fixed taxonomy (not raw hostnames) so the chart
# axis stays constant as POD adds institutions, each with its own finding-aid host.
Q_ARCH_DEST = _ARCH_WITH + (
    ", links AS (\n"
    "  SELECT a.org, r.pod_record_id,\n"
    "         regexp_extract(lower(r.value), 'https?://([^/]+)', 1) AS host\n"
    "  FROM arch a JOIN records r USING (org, pod_record_id)\n"
    "  WHERE r.field_tag = '856' AND r.subfield_code = 'u' AND r.value LIKE 'http%'\n"
    ")\n"
    "SELECT org,\n"
    "  CASE\n"
    "    WHEN regexp_matches(host, 'findingaid|archives') THEN 'finding_aid'\n"
    "    WHEN host IN ('oac.cdlib.org','www.oac.cdlib.org')\n"
    "         OR regexp_matches(host, 'archivegrid|snaccooperative') THEN 'aggregator'\n"
    "    WHEN regexp_matches(host, '^(nrs|arks|purl|hdl|handle)\\.')\n"
    "         OR regexp_matches(host, 'doi\\.org$') THEN 'resolver'\n"
    "    WHEN regexp_matches(host, 'proquest|amdigital|gale|jstor|e-enlightenment')\n"
    "         THEN 'vendor'\n"
    "    WHEN regexp_matches(host, 'colenda|digital|repository|dspace|fedora|idn\\.duke')\n"
    "         THEN 'repository'\n"
    "    ELSE 'other'\n"
    "  END AS category,\n"
    "  count(DISTINCT pod_record_id) AS n\n"
    "FROM links GROUP BY org, category"
)


def archives(con: Connection, *, threshold: int = 10, **_: object) -> dict:
    """
    Archives & manuscripts (see ``_ARCH_WITH`` for the subset). Several views of a
    small-but-distinctive slice of each catalog, all counting archival *records*:

    - ``material_type``: counts by leader/06 code (rendered as a count heatmap).
    - ``genre``: each institution's *own* top 655 genre/form terms (LC class barely
      applies to archives, and the genre vocabulary is a ~5.8k-term long tail that is
      65% institution-specific, so a shared top-N would be sparse and unrepresentative).
    - ``start_decade``: 008 date1 by decade, for a normalized vintage view.
    - ``online_link``: per-org count/total of records with an 856 online link.
    - ``link_destination``: those links bucketed into a fixed host taxonomy.

    Heatmap dimensions share the ``{categories, institutions, totals, matrix, sql}``
    shape; ``totals`` is each institution's archival-record count, so shares are of
    all archival records. Counts below ``threshold`` are suppressed to null.
    """
    totals = dict(con.execute(Q_ARCH_TOTAL).fetchall())
    orgs = sorted(totals)

    def cell(counts: dict, org: str, cat: str) -> int | None:
        n = counts.get((org, cat), 0)
        return n if (n == 0 or n >= threshold) else None

    def dimension(
        sql: str, *, categories: list[str] | None = None, top_k: int | None = None
    ) -> dict:
        counts = {(org, cat): n for org, cat, n in con.execute(sql).fetchall()}
        if categories is None:  # rank present categories by consortium total
            by_cat: dict[str, int] = {}
            for (_org, cat), n in counts.items():
                by_cat[cat] = by_cat.get(cat, 0) + n
            cats = sorted(by_cat, key=lambda c: (-by_cat[c], c))
            if top_k is not None:
                cats = cats[:top_k]
        else:
            cats = categories  # fixed order and membership
        return {
            "categories": cats,
            "institutions": orgs,
            "totals": totals,
            "matrix": {o: {c: cell(counts, o, c) for c in cats} for o in orgs},
            "sql": sql,
        }

    starts: dict[str, list] = {}
    for org, decade, n in con.execute(Q_ARCH_DECADE).fetchall():
        starts.setdefault(org, []).append({"decade": decade, "count": n})
    linked = dict(con.execute(Q_ARCH_LINK).fetchall())

    # genre: each institution's own top terms, not a shared axis (long, divergent
    # tail). Suppress terms below threshold, then keep each org's top 12.
    genre_by_org: dict[str, list] = {}
    for org, term, n in con.execute(Q_ARCH_GENRE).fetchall():
        if n >= threshold:
            genre_by_org.setdefault(org, []).append((term, n))
    genre = []
    for o in orgs:
        top = sorted(genre_by_org.get(o, []), key=lambda tn: (-tn[1], tn[0]))[:12]
        genre.append(
            {
                "org": o,
                "total": totals[o],
                "values": [{"term": t, "count": n} for t, n in top],
            }
        )

    return {
        "dimensions": {
            "material_type": dimension(Q_ARCH_TYPE, top_k=10),
            "link_destination": dimension(
                Q_ARCH_DEST,
                categories=[
                    "finding_aid",
                    "aggregator",
                    "resolver",
                    "repository",
                    "vendor",
                    "other",
                ],
            ),
        },
        "genre": genre,
        "start_decade": [{"org": o, "values": starts.get(o, [])} for o in orgs],
        "online_link": [
            {"org": o, "count": linked.get(o, 0), "total": totals[o]} for o in orgs
        ],
        "sql": [
            {
                "label": "Archival records by material type (leader/06)",
                "sql": Q_ARCH_TYPE,
            },
            {"label": "Archival records by 655 genre/form term", "sql": Q_ARCH_GENRE},
            {
                "label": "Archival records by decade of first date (008)",
                "sql": Q_ARCH_DECADE,
            },
            {"label": "Archival records with an 856 online link", "sql": Q_ARCH_LINK},
            {"label": "856 link destinations, bucketed by host", "sql": Q_ARCH_DEST},
        ],
    }


# The bare host of every http 856 $u link. Reported as each institution's own top
# hosts (they're mostly institution-specific resolvers/proxies, so a shared axis
# would be diagonal). Raw hosts — proxies and resolvers are left as-is.
Q_LINK_HOSTS = """\
SELECT org, regexp_extract(lower(value), 'https?://([^/]+)', 1) AS host, count(*) AS n
FROM records
WHERE field_tag = '856' AND subfield_code = 'u' AND value LIKE 'http%'
GROUP BY org, host"""


def electronic(con: Connection, *, threshold: int = 10, **_: object) -> dict:
    """
    Where each institution's online (856) links point: its own top link hosts.
    Reports observed links rather than trying to *detect* electronic resources
    (which is heavily cataloging-practice dependent). ``total`` is the
    institution's whole 856 link count; hosts below ``threshold`` are dropped and
    each institution keeps its top 15.
    """
    totals: dict[str, int] = {}
    hosts: dict[str, list] = {}
    for org, host, n in con.execute(Q_LINK_HOSTS).fetchall():
        totals[org] = totals.get(org, 0) + n
        if host and n >= threshold:
            hosts.setdefault(org, []).append((host, n))
    orgs = sorted(totals)
    return {
        "hosts": [
            {
                "org": o,
                "total": totals[o],
                "values": [
                    {"host": h, "count": n}
                    for h, n in sorted(
                        hosts.get(o, []), key=lambda hn: (-hn[1], hn[0])
                    )[:15]
                ],
            }
            for o in orgs
        ],
        "sql": [{"label": "Top 856 link hosts per institution", "sql": Q_LINK_HOSTS}],
    }


# --- source of cataloging (MARC 040) -----------------------------------------

# 040 $a is the *original* cataloging agency, $d each *modifying* agency. Which
# codes mean "this POD member cataloged it" is not derivable from the data:
# members self-attribute with a mix of MARC Organization Codes (CSt, NjP, PU, RPB,
# MH, NcD) and OCLC symbols (STF, PUL, PAU, RBN, HLS, NDD), and some run a symbol
# per library (Harvard especially — its MH family accounts for only ~250k of its
# ~1.9m self-attributed records). Sub-unit codes are base + '-' + suffix (CSt-H,
# MH-L, NjP-G, PU-MED, RPB-JH), which the '-*' entries below cover.
#
# Trailing counts are $a occurrences at that institution in the 2026-08 lake, so
# the table can be reviewed against the data. Entries marked "?" are inferred from
# the symbol family plus near-exclusive use at that institution and are *not*
# confirmed by the institution — POD should ratify this mapping before these
# figures are treated as authoritative. A prefix rule would be wrong: H** is not
# exclusively Harvard (HMM is Brown's), so this is an explicit list.
#
# The '-*' sub-unit rule is safe by construction, not by luck: MARC Organization
# Codes are hierarchical on '-', so every 'BASE-…' code belongs to BASE's
# institution. Verified against the lake — RPB-JH, MH-L/HY/MU/FA/AR, NJP-G,
# PU-MED/L/CJS, CST-H/LAW/ES are all genuine sub-units, and 'PU-%' does not match
# 'PUL' (Princeton's symbol, claimed by its own exact entry).
#
# Left in "other" as too uncertain to attribute, listed so a reviewer can promote
# them: FLL 94k, BOH 84k, BHA 41k, TOZ 16k, SLR 11k, MCS 8k (Harvard); NDL 12k,
# NCS 14k (Duke); QQR 19k, PAULM 13k, PPA 11k (Penn); RIBRL 8k (Brown); HMM
# (harvard 18k / brown 15k — split too evenly to attribute either way). 'YNH'
# (144k at Harvard, half of it written '*YNH*') is *Yale's* symbol — a
# copy-cataloging signal, not self-attribution — and correctly stays in "other".
# Codes we can name with confidence: a member's MARC Organization Code (and its
# '-' sub-units) plus OCLC symbols whose owner is unambiguous from the name.
_SELF_CODES: dict[str, tuple[str, ...]] = {
    "brown": ("RPB", "RPB-*", "RBN", "RPJCB"),  # 117k, 5k, 155k, 18k
    "duke": ("NCD", "NCD-*", "NDD"),  # 2k, —, 279k
    "harvard": (
        "MH",  # 56k (+ MH-*: MH-L 79k, MH-HY 48k, MH-MU 28k, MH-FA 19k, MH-H 19k)
        "MH-*",
        "HLS",  # 714k Harvard Law School
        "HUL",  # 168k Harvard University Library
        "HMS",  # 137k Harvard Medical School
        "HBS",  # 38k Harvard Business School
        "DDO",  # 17k Dumbarton Oaks
    ),
    "penn": ("PU", "PU-*", "PAU"),  # 490k, 3k, 105k
    "princeton": ("NJP", "NJP-*", "PUL", "PULEA"),  # 533k, 29k, 205k, 20k
    "stanford": ("CST", "CST-*", "STF"),  # 718k, 190k, 224k
}

# Codes we *infer* belong to a member — they follow that institution's symbol
# family and are used almost exclusively there, but nobody has confirmed them.
# Reported as a separate `self_inferred` bucket rather than merged into `self`,
# because the difference is material: these move Harvard's self-cataloged share
# from 8.3% to 14.5%, and that figure invites comparison against peers. If POD
# ratifies them, move them into _SELF_CODES above; if POD rejects any, delete it.
_SELF_CODES_INFERRED: dict[str, tuple[str, ...]] = {
    "harvard": (
        "HVL",  # 270k
        "HHG",  # 122k
        "HMY",  # 121k
        "HMZ",  # 59k
        "HMG",  # 32k
        "HTV",  # 31k
        "HMU",  # 30k
        "HFL",  # 27k
    ),
}

# Merged view, for "which member is this code's?" — used by the `pod` bucket and
# the flow matrix, both of which care about attribution direction rather than how
# certain the attribution is.
_ALL_SELF_CODES: dict[str, tuple[str, ...]] = {
    org: codes + _SELF_CODES_INFERRED.get(org, ()) for org, codes in _SELF_CODES.items()
}

# Agency codes arrive noisy: ~1.2m of 155m values carry a trailing period, and
# 513k are wrapped in asterisks (the NOTIS-era '*YNH*' convention) — which, left
# alone, splits one agency into two categories and double-counts it as two
# distinct modifying agencies in $d. `trim(str, chars)` strips both ends, so this
# one expression subsumes whitespace, punctuation, asterisks, and a stray NBSP.
_CODE_NORM = "upper(trim(value, ' *.,;:' || chr(9) || chr(10) || chr(13) || chr(160)))"


# The probe that built _SELF_CODES in the first place, quoted in the guard's error
# so whoever hits it can act on it instead of rediscovering the technique. Note
# concentration alone is not sufficient to identify a member's own codes — it also
# surfaces single-subscriber vendor namespaces (LexisNexis at Penn, MiAaPQ at Duke),
# so the result needs a human, and ideally the member's own confirmation.
_SELF_CODE_PROBE = """\
SELECT org, upper(trim(value)) AS code, count(*) AS n
FROM records
WHERE field_tag = '040' AND subfield_code = 'a'
GROUP BY org, code
QUALIFY row_number() OVER (PARTITION BY org ORDER BY n DESC) <= 15
ORDER BY org, n DESC"""


def _assert_orgs_mapped(con: Connection) -> None:
    """
    Refuse to build if the lake holds an org that ``_SELF_CODES`` doesn't know.

    An unmapped org does not error on its own — it quietly reads as 0%
    self-cataloged, contributes nothing to ``pod``, and gets a row but no column in
    the flow matrix. That is a publishable-looking claim that a member does no
    original cataloging and shares nothing with the consortium, which is worse than
    a failed build: the extract is a manual offline job, so whoever runs it is
    whoever can fix the mapping.
    """
    rows = con.execute("SELECT DISTINCT org FROM record_meta").fetchall()
    orgs = {org for (org,) in rows}
    missing = sorted(orgs - set(_ALL_SELF_CODES))
    if not missing:
        return
    raise ValueError(
        "no cataloging-agency codes are mapped for: "
        + ", ".join(missing)
        + ".\nThese institutions would publish 0% self-cataloged, no "
        "intra-consortium\nflow, and no local-system coverage. Add them to "
        "queries._SELF_CODES (codes\nyou can confirm) or "
        "queries._SELF_CODES_INFERRED (codes you can only infer),\nthen re-run. "
        "To find the candidates:\n\n"
        + "\n".join(f"    {line}" for line in _SELF_CODE_PROBE.splitlines())
        + "\n\nMembers often self-attribute with an OCLC symbol rather than their "
        "MARC\nOrganization Code, so expect both (Duke's NcD appears on ~1.7k "
        "records,\nits NDD on 279k)."
    )


def _code_match_sql(column: str, codes: tuple[str, ...], indent: str) -> str:
    """OR-ed tests matching a code against exact entries and ``BASE-*`` families."""
    tests = [
        f"{column} LIKE '{code[:-1]}%'"
        if code.endswith("-*")
        else f"{column} = '{code}'"
        for code in codes
    ]
    return f"\n{indent}OR ".join(tests)


def _self_org_sql(column: str) -> str:
    """A CASE mapping a normalized 040 agency code to the POD org that owns it."""
    whens = [
        f"         WHEN {_code_match_sql(column, codes, ' ' * 14)}\n"
        f"              THEN '{org}'"
        for org, codes in _ALL_SELF_CODES.items()
    ]
    return "CASE\n" + "\n".join(whens) + "\n         END"


def _self_inferred_sql(column: str) -> str:
    """True when the code is one of the *unconfirmed* member attributions."""
    codes = tuple(c for codes in _SELF_CODES_INFERRED.values() for c in codes)
    if not codes:
        return "false"
    return _code_match_sql(column, codes, " " * 14)


# MARC 008/00-05 is "date entered on file" — when the record was created in the
# holding institution's system, written yymmdd, so the century has to be inferred.
# Two facts pin the pivot: machine-readable cataloging starts in the mid-1960s, and
# a lake cannot hold a record entered after its own snapshot. So a two-digit year at
# or below NOW_YEAR's is this century and anything above it is the last one.
#
# '000000' is a placeholder, not the year 2000. 141k records carry it — 53k at Duke,
# 57k at Stanford — and treated as a date it would inflate Duke's 2000 by 37%.
#
# Built by concatenation, not an f-string, so the regexp's {6} quantifier survives.
# Indented to sit at column 9, where it is interpolated into the SELECT below.
_ENTERED_YEAR = (
    "CASE WHEN regexp_matches(substr(value, 1, 6), '^[0-9]{6}$')\n"
    "              AND substr(value, 1, 6) <> '000000'\n"
    "              THEN CASE WHEN CAST(substr(value, 1, 2) AS INTEGER) <= "
    + str(NOW_YEAR % 100)
    + " THEN 2000\n"
    "                        ELSE 1900 END + CAST(substr(value, 1, 2) AS INTEGER)\n"
    "         END"
)

# The first year a date entered on file can plausibly mean anything: MARC's pilot
# ran from 1966. Earlier values (~2.5k records, scattered singly across 1927-1965)
# are keying errors, not history.
_ENTERED_MIN_YEAR = 1966


# One pass over the 040 slice, materialized so the five views below are cheap
# group-bys instead of five scans of the billions-of-rows EAV table (measured:
# ~139s + 5×0.05s here, versus well over 200s for self-contained queries; folding it
# all into one grouped mega-query is far worse — over 8 minutes). Rolled up to
# (org, year, code, org, bucket, depth) counts rather than one row per record, which
# is ~1.3m rows instead of 48m and drops pod_record_id entirely. The year is what
# costs: without it the table is ~224k rows and ~77s.
#
# $a is nominally non-repeatable, but ~7.4k records carry more than one — almost
# always a mangled subfield delimiter that glued $c/$d onto the end, e.g. one
# Harvard record's 040 reads $a='OL' $a='cOL' $a='dDLC'. The true value is always
# the lowest (field_seq, subfield_seq), which is what this picks. $d *is*
# repeatable and is counted as distinct agencies.
Q_CAT_SOURCE_TABLE = f"""\
CREATE OR REPLACE TEMP TABLE cataloging_source AS
WITH f AS (
  SELECT org, pod_record_id, subfield_code, field_seq, subfield_seq,
         {_CODE_NORM} AS code
  FROM records
  WHERE field_tag = '040'
),
present AS (
  SELECT DISTINCT org, pod_record_id FROM f
),
orig AS (
  SELECT org, pod_record_id, code
  FROM f
  WHERE subfield_code = 'a' AND code <> ''
  QUALIFY row_number() OVER (
    PARTITION BY org, pod_record_id ORDER BY field_seq, subfield_seq) = 1
),
mods AS (
  SELECT org, pod_record_id, count(DISTINCT code) AS mod_agencies
  FROM f
  WHERE subfield_code = 'd' AND code <> ''
  GROUP BY org, pod_record_id
),
-- When the record entered this institution's system. ~2.5k records carry two 008
-- fields; the first by field_seq is the record's own, so QUALIFY keeps the join
-- one-to-one rather than silently double-counting them.
entered AS (
  SELECT org, pod_record_id,
         {_ENTERED_YEAR} AS entered_year
  FROM records
  WHERE field_tag = '008'
  QUALIFY row_number() OVER (
    PARTITION BY org, pod_record_id ORDER BY field_seq) = 1
),
joined AS (
  SELECT m.org,
         e.entered_year,
         o.code AS source_code,
         {_self_org_sql("o.code")} AS source_org,
         {_self_inferred_sql("o.code")} AS inferred_self,
         coalesce(d.mod_agencies, 0) AS mod_agencies,
         p.pod_record_id IS NOT NULL AS has_040
  FROM record_meta m
  LEFT JOIN present p USING (org, pod_record_id)
  LEFT JOIN orig o USING (org, pod_record_id)
  LEFT JOIN mods d USING (org, pod_record_id)
  LEFT JOIN entered e USING (org, pod_record_id)
)
SELECT org, entered_year, source_code, source_org,
       CASE
         WHEN source_code IS NULL                            THEN 'none'
         WHEN source_code = 'DLC' OR source_code LIKE 'DLC-%' THEN 'lc'
         -- No 'oclc' bucket: OCoLC appears as the *original* agency on only 27k
         -- of 48m records (0.06%), because 040 credits the library that made the
         -- description, not the utility the record travelled through. Reporting a
         -- 0% OCLC bucket would imply OCLC plays no role here, when in fact
         -- 66-98% of these records carry an (OCoLC) number in 035. That channel
         -- signal belongs to 035, not 040, so OCoLC-in-$a falls to 'other'.
         WHEN source_org = org AND inferred_self             THEN 'self_inferred'
         WHEN source_org = org                               THEN 'self'
         WHEN source_org IS NOT NULL                         THEN 'pod'
         ELSE 'other'
       END AS bucket,
       -- "no 040 at all" is a different fact from "an 040 that names no
       -- modifying agency", and the gap is large (182k-933k records per
       -- institution carry an 040 with no $a), so they get separate buckets.
       CASE
         WHEN NOT has_040        THEN 'no_040'
         WHEN mod_agencies >= 10 THEN '10+'
         WHEN mod_agencies >= 5  THEN '5-9'
         WHEN mod_agencies >= 3  THEN '3-4'
         ELSE CAST(mod_agencies AS VARCHAR)
       END AS mod_depth,
       count(*) AS n
FROM joined
GROUP BY ALL"""

Q_CAT_MIX = """\
SELECT org, bucket AS category, sum(n) AS n
FROM cataloging_source
GROUP BY org, bucket"""

# How many of its *own* top agencies each institution contributes to the shared
# axis. The union of these, rather than a consortium-wide top-N, because ranking
# globally silently drops a small library's principal agencies: Brown's own RBN
# (6.8% of its records) and RPB (5.1%) are its #2 and #3 agencies but miss a global
# top-20 entirely, as do Harvard's HVL (270k) and HUL (168k). Adding institutions
# makes a global ranking worse — each new member dilutes it — whereas this scales,
# since every member brings its own rows. 12 each gives ~44 rows at current
# membership, about the same height as a global top-40 and the same ~59% coverage,
# but with every library actually represented.
_CAT_AGENCY_PER_ORG = 12

# Note the semi-join: `picked` chooses the codes, but the counts returned cover
# *every* institution for those codes — otherwise a code that is one library's top
# agency would read as zero everywhere else instead of showing its real spread.
Q_CAT_AGENCY = f"""\
WITH per AS (
  SELECT org, source_code, sum(n) AS n
  FROM cataloging_source
  WHERE source_code IS NOT NULL
  GROUP BY org, source_code
),
picked AS (
  SELECT DISTINCT source_code
  FROM per
  QUALIFY row_number() OVER (
    PARTITION BY org ORDER BY n DESC, source_code) <= {_CAT_AGENCY_PER_ORG}
)
SELECT p.org, p.source_code AS category, p.n
FROM per p
WHERE p.source_code IN (SELECT source_code FROM picked)"""

# The share denominator. Needed separately because Q_CAT_AGENCY deliberately
# returns only the displayed codes, and `_comparison_matrix` derives `totals` by
# summing the rows it is handed — which would make each cell a share of the
# selection rather than of everything the institution catalogs. Matching how
# heatmap.js treats `exclude`: dropping rows must not inflate the rest.
Q_CAT_AGENCY_TOTAL = """\
SELECT org, sum(n) AS n
FROM cataloging_source
WHERE source_code IS NOT NULL
GROUP BY org"""

# Asymmetric by design: rows are the institution *holding* the record, categories
# the POD member credited with cataloging it. Includes the diagonal (self).
Q_CAT_FLOW = """\
SELECT org, source_org AS category, sum(n) AS n
FROM cataloging_source
WHERE source_org IS NOT NULL
GROUP BY org, source_org"""

Q_CAT_MOD_DEPTH = """\
SELECT org, mod_depth AS category, sum(n) AS n
FROM cataloging_source
GROUP BY org, mod_depth"""

# The same provenance mix, cut by the year the record entered the institution's
# system. Rows with a NULL year come back too — they are reported as `unplaced`
# rather than dropped, so the timeline visibly accounts for every record.
Q_CAT_TIMELINE = """\
SELECT org, entered_year AS year, bucket, sum(n) AS n
FROM cataloging_source
GROUP BY org, entered_year, bucket"""

# Render order for the two fixed vocabularies (neither is worth ranking by count).
_CAT_BUCKETS = ("lc", "self", "self_inferred", "pod", "other", "none")
_MOD_DEPTH_BUCKETS = ("no_040", "0", "1", "2", "3-4", "5-9", "10+")


def cataloging_source(con: Connection, *, threshold: int = 10, **_: object) -> dict:
    """
    Source of cataloging, from MARC 040 — who made the metadata, rather than what
    the collections contain (the POD "040 analysis" ask).

    - ``per_org[].mix`` / ``.counts``: share and count of the institution's records
      by origin bucket — ``lc`` (DLC), ``self``, ``self_inferred``, ``pod``
      (another member), ``other``, ``none`` (an 040 with no $a, or no 040 at all).
      Denominator is every record the institution holds, so the shares sum to ~1.
    - ``dimensions.agency``: the union of each institution's own top
      ``_CAT_AGENCY_PER_ORG`` $a codes, on a shared axis.
    - ``dimensions.flow``: POD member credited × institution holding — asymmetric,
      and the diagonal is the self-cataloged count.
    - ``dimensions.mod_depth``: distinct 040 $d modifying agencies per record,
      keeping "no 040 field" separate from "040 naming no modifying agency".
    - ``timeline``: the same mix again, cut by the year the record entered the
      institution's system (008/00-05) — see :func:`_cataloging_timeline`.

    ``self`` depends on ``_SELF_CODES``, a curated mapping of agency codes to
    members; read it as "attributed to us," not "we did the original work". Codes
    that follow a member's symbol family but that nobody has confirmed live in
    ``_SELF_CODES_INFERRED`` and are reported separately as ``self_inferred``, so
    the uncertainty is visible in the chart rather than only in the prose. Members
    largely self-attribute with their OCLC symbol rather than their MARC
    Organization Code. There is deliberately no ``oclc`` bucket — see the CASE in
    ``Q_CAT_SOURCE_TABLE``; 040 records authorship, not distribution channel.

    ``flow`` and ``pod`` count confirmed and inferred attributions together: they
    describe the *direction* of copy cataloging, where excluding a probably-correct
    attribution would understate a member's outflow. So ``flow``'s diagonal equals
    ``self`` + ``self_inferred``, not ``self`` alone.

    Disclosure control: sub-``threshold`` mix buckets are folded into ``other``
    (never published as their own share), and matrix cells in ``1..threshold-1``
    are nulled. ``flow`` omits ``totals`` deliberately — its categories exhaust the
    total, so publishing both would let a suppressed cell be recovered by
    subtraction.
    """
    _assert_orgs_mapped(con)
    con.execute(Q_CAT_SOURCE_TABLE)

    mix = {(org, cat): n for org, cat, n in con.execute(Q_CAT_MIX).fetchall()}
    records: dict[str, int] = {}
    for (org, _cat), n in mix.items():
        records[org] = records.get(org, 0) + n

    def bucket_counts(org: str) -> dict[str, int]:
        """Counts per bucket, with sub-threshold buckets folded into ``other``."""
        counts = {b: mix.get((org, b), 0) for b in _CAT_BUCKETS}
        for bucket, count in counts.items():
            if bucket != "other" and 0 < count < threshold:
                counts["other"] += count
                counts[bucket] = 0
        return counts

    per_org = []
    for org in sorted(records):
        counts = bucket_counts(org)
        total = records[org]
        per_org.append(
            {
                "org": org,
                "records": total,
                "counts": counts,
                "mix": {
                    b: (round(n / total, 4) if total else 0.0)
                    for b, n in counts.items()
                },
            }
        )

    # Each dimension's SQL needs the materialization step in front of it, or the
    # query shown under the chart isn't runnable on its own — which is the whole
    # point of embedding it.
    ddl = {
        "label": "Per-record 040 summary, materialized once",
        "sql": Q_CAT_SOURCE_TABLE,
    }

    def dimension(
        sql: str,
        label: str,
        *,
        top_k: int | None = None,
        categories: list[str] | None = None,
    ) -> dict:
        dim = _comparison_matrix(
            con, sql, threshold=threshold, top_k=top_k, categories=categories
        )
        dim["sql"] = [ddl, {"label": label, "sql": sql}]
        return dim

    # top_k=None: the SQL already bounded the set to the union of each institution's
    # own top agencies, so Python only orders it (by consortium total, largest at
    # the top of the axis). The denominator then has to be restored, because
    # _comparison_matrix summed only the displayed codes.
    agency = dimension(
        Q_CAT_AGENCY,
        "Cataloging agencies (040 $a): each institution's own top "
        f"{_CAT_AGENCY_PER_ORG}, unioned",
        top_k=None,
    )
    agency["totals"] = dict(con.execute(Q_CAT_AGENCY_TOTAL).fetchall())
    agency["sql"].append(
        {
            "label": "Share denominator: records carrying an 040 $a",
            "sql": Q_CAT_AGENCY_TOTAL,
        }
    )

    flow = dimension(
        Q_CAT_FLOW,
        "Cataloging attributed to each POD member, by holding institution",
        # The full member roster *union* the orgs actually in this lake. The
        # roster alone covers a member credited as a source whose own records
        # aren't loaded; the union guarantees no org can get a row without a
        # column, so the matrix stays square even if _assert_orgs_mapped is
        # ever bypassed.
        categories=sorted(set(_ALL_SELF_CODES) | set(records)),
    )
    del flow["totals"]  # see the disclosure note above

    timeline = _cataloging_timeline(con, threshold=threshold, totals=records)
    timeline["sql"] = [
        ddl,
        {"label": "Provenance mix by year entered on file", "sql": Q_CAT_TIMELINE},
    ]

    return {
        "buckets": list(_CAT_BUCKETS),
        "per_org": per_org,
        "dimensions": {
            "agency": agency,
            "flow": flow,
            "mod_depth": dimension(
                Q_CAT_MOD_DEPTH,
                "Distinct modifying agencies (040 $d) per record",
                categories=list(_MOD_DEPTH_BUCKETS),
            ),
        },
        "timeline": timeline,
        "sql": [ddl, {"label": "Provenance mix by institution", "sql": Q_CAT_MIX}],
    }


def _cataloging_timeline(
    con: Connection, *, threshold: int, totals: dict[str, int]
) -> dict:
    """
    Provenance mix per institution per year, keyed on 008/00-05 — the year the
    record entered that institution's system.

    This is a record-arrival clock, not a cataloging clock; the two only coincide
    for the ``self``/``self_inferred`` buckets, where "the record appeared in our
    system" and "we cataloged it" are the same event. Even then the date survives
    only until the next migration: a reload restamps everything it touches, so a
    year holding several times its neighbours' volume is a load event and its shape
    says nothing about that year's cataloging. Publishing each year's *total*
    alongside the buckets is what makes those legible rather than invisible.

    Every record is accounted for. Those that cannot be placed on the timeline —
    no 008, an unparseable or placeholder date, a year outside
    ``_ENTERED_MIN_YEAR..NOW_YEAR``, or a year holding too few records to publish —
    are summed into ``unplaced``, so ``sum(year totals) + unplaced`` equals the
    institution's record count. Folding suppressed years in there rather than
    reporting them separately is deliberate: a published count of dropped years
    would let each one be recovered by subtraction.
    """
    rows = con.execute(Q_CAT_TIMELINE).fetchall()

    def in_range(year: int | None) -> bool:
        return year is not None and _ENTERED_MIN_YEAR <= year <= NOW_YEAR

    by_org: dict[str, dict[int | None, dict[str, int]]] = {}
    for org, year, bucket, n in rows:
        placed = year if in_range(year) else None
        counts = by_org.setdefault(org, {}).setdefault(
            placed, dict.fromkeys(_CAT_BUCKETS, 0)
        )
        counts[bucket] += n

    per_org = []
    for org in sorted(by_org):
        years = by_org[org]
        unplaced = sum(years.pop(None, {}).values())
        values: list[dict] = []
        placed_total = 0
        for year in sorted(y for y in years if y is not None):
            counts = years[year]
            total = sum(counts.values())
            if total < threshold:  # too thin to publish; see the docstring
                unplaced += total
                continue
            for bucket, n in list(counts.items()):
                if bucket != "other" and 0 < n < threshold:
                    counts["other"] += n
                    counts[bucket] = 0
            placed_total += total
            values.append({"year": year, "total": total, "counts": counts})
        per_org.append({"org": org, "unplaced": unplaced, "values": values})

        # Not a formality: the 008 join is the one place a record can be counted
        # twice (two 008 fields), and a duplicated record would inflate a year's
        # bar with nothing else to give it away.
        if placed_total + unplaced != totals.get(org, 0):
            raise ValueError(
                f"timeline for {org} covers {placed_total + unplaced} records but "
                f"the institution holds {totals.get(org, 0)} — the 008 join is "
                "duplicating or dropping records"
            )

    return {
        # The snapshot's own year is incomplete by construction — the lake is
        # harvested part-way through it — so the last point is not a real decline.
        "partial_year": NOW_YEAR,
        "per_org": per_org,
    }


# --- how records arrived (MARC 035 system control numbers) --------------------

# 035 $a is written "(ORGCODE)number": the number, and the *system it belongs to*.
# That makes it a record's travel history — which utilities, knowledge bases and
# vendor platforms it has passed through — which is a different question from 040's
# "who wrote the description". It is also far better populated: 99.3-100% of records
# carry an 035, against 86% with an 040 $a.
_NS_PREFIX = "upper(trim(regexp_extract(value, '^\\s*\\(([^)]{1,24})\\)', 1)))"

# Namespaces that denote a local integrated library system rather than a shared
# utility. Deliberately generic — these identify the *product*, not the library, so
# they are counted as "local" for whichever institution carries them rather than
# being mapped to an owner.
_LOCAL_ILS_NS = ("SIRSI", "PUVOYAGERBIBID")

# A deliberately small taxonomy of channels we can identify with confidence, rather
# than a hand-classification of all ~25k observed namespaces. The long tail is left
# to the raw-namespace heatmap below, which needs no curation to be honest.
#
# Channels are NOT mutually exclusive — a record routinely carries both an OCLC and
# an RLIN number (the RLG merger in 2006 gave RLIN records OCLC numbers), so these
# are coverage shares, not a partition, and they do not sum to 1.
#
# 'OCOLC%' matters: Stanford writes (OCoLC-M) and (OCoLC-I) from its Symphony era,
# 13.8m occurrences between them. Matching only the bare '(OCoLC)' reads Stanford as
# 10.7% OCLC when the real figure is 97.8%.
_CHANNEL_TESTS = {
    # the utility: (OCoLC), plus the OCoLC-M / -I / -P variants
    "oclc": "prefix LIKE 'OCOLC%'",
    # RLIN, the RLG-era union catalogue, whose org code is CStRLIN (RLG was
    # headquartered at Stanford). Kept separate from OCLC despite the 2006 merger —
    # a visible historical layer is the interesting part.
    "rlin": "prefix = 'CSTRLIN'",
    # Ex Libris' Alma Community Zone / Central KnowledgeBase — the modern
    # alternative route for electronic records, bypassing WorldCat entirely
    "alma_cz": "prefix IN ('EXLCZ', 'CKB')",
    # A number from a local ILS rather than a shared utility. Two forms: the
    # institution's own MARC/OCLC code as a namespace, or a generic ILS-product
    # namespace. The generic ones are NOT attributed to an institution — (SIRSI) is
    # what any Sirsi/Symphony library writes, and it is only unambiguous here
    # because Stanford is the sole Symphony site in this lake. Counting it as
    # "local" for whichever institution carries it stays correct as membership
    # grows, where attributing it to Stanford would not. Without this, Stanford
    # reads 3% local when its real local namespace, (SIRSI), covers 91%.
    "local_system": (f"{_self_org_sql('prefix')} = org OR prefix IN {_LOCAL_ILS_NS}"),
    # a number in *another* POD member's namespace — evidence of record sharing
    "pod_system": (
        f"{_self_org_sql('prefix')} IS NOT NULL AND {_self_org_sql('prefix')} <> org"
    ),
    # baseline: carries any parseable "(namespace)number" at all
    "any_system": "prefix <> ''",
}

_CHANNELS = tuple(_CHANNEL_TESTS)


def _channel_coverage_sql() -> str:
    """Per-institution count of records carrying each channel's system number."""
    flags = ",\n".join(
        f"         bool_or({test}) AS {name}" for name, test in _CHANNEL_TESTS.items()
    )
    counts = ",\n".join(
        f"         count(*) FILTER (WHERE {name}) AS {name}" for name in _CHANNEL_TESTS
    )
    picks = ",\n".join(
        f"       coalesce(c.{name}, 0) AS {name}" for name in _CHANNEL_TESTS
    )
    return (
        "WITH ns AS (\n"
        f"  SELECT org, pod_record_id, {_NS_PREFIX} AS prefix\n"
        "  FROM records\n"
        "  WHERE field_tag = '035' AND subfield_code = 'a'\n"
        "),\n"
        "flagged AS (\n"
        "  SELECT org, pod_record_id,\n"
        f"{flags}\n"
        "  FROM ns\n"
        "  GROUP BY org, pod_record_id\n"
        "),\n"
        "counted AS (\n"
        "  SELECT org,\n"
        f"{counts}\n"
        "  FROM flagged GROUP BY org\n"
        "),\n"
        "totals AS (SELECT org, count(*) AS records FROM record_meta GROUP BY org)\n"
        "SELECT t.org, t.records,\n"
        f"{picks}\n"
        "FROM totals t LEFT JOIN counted c USING (org)\n"
        "ORDER BY t.org"
    )


Q_CHANNEL_COVERAGE = _channel_coverage_sql()

# How many of its own top namespaces each institution contributes to the shared
# axis — same union-not-global-ranking reasoning as the 040 agency chart, and for
# the same reason: several namespaces are one library's alone (SIRSI at Stanford,
# PUVoyagerBibID at Penn) and a consortium-wide ranking would bury the smallest
# members' local systems.
_CHANNEL_NS_PER_ORG = 12

# A namespace also has to reach this share of an institution's records to earn a row.
# Without it the axis fills with rows that are visually blank: institutions with few
# distinct namespaces (Brown has a handful) contribute a "top 12" whose tail is a few
# hundred records — above the suppression threshold, but 0.006% of the collection.
_CHANNEL_NS_MIN_SHARE = 0.001

Q_CHANNEL_NAMESPACE = f"""\
WITH ns AS (
  SELECT org, pod_record_id, {_NS_PREFIX} AS prefix
  FROM records
  WHERE field_tag = '035' AND subfield_code = 'a'
),
per AS (
  SELECT org, prefix, count(DISTINCT pod_record_id) AS n
  FROM ns
  WHERE prefix <> ''
  GROUP BY org, prefix
),
sized AS (
  SELECT p.*, r.records
  FROM per p
  JOIN (SELECT org, count(*) AS records FROM record_meta GROUP BY org) r USING (org)
),
picked AS (
  SELECT DISTINCT prefix
  FROM sized
  WHERE n >= records * {_CHANNEL_NS_MIN_SHARE}
  QUALIFY row_number() OVER (
    PARTITION BY org ORDER BY n DESC, prefix) <= {_CHANNEL_NS_PER_ORG}
)
SELECT p.org, p.prefix AS category, p.n
FROM per p
WHERE p.prefix IN (SELECT prefix FROM picked)"""

# Share denominator: every record, including those with no 035 at all. Kept
# separate for the same reason as the 040 agency chart — `_comparison_matrix` would
# otherwise total only the displayed namespaces and inflate every cell.
Q_CHANNEL_TOTAL = """\
SELECT org, count(*) AS n FROM record_meta GROUP BY org"""


def record_channels(con: Connection, *, threshold: int = 10, **_: object) -> dict:
    """
    How records reached each institution, from the MARC 035 system control number —
    the record's distribution history rather than its authorship (which is
    :func:`cataloging_source`).

    - ``per_org[].coverage``: share of the institution's records carrying a system
      number from each channel in ``_CHANNELS``. **Not a partition** — a record
      commonly carries several, so these overlap and do not sum to 1.
    - ``dimensions.namespace``: the union of each institution's own top
      ``_CHANNEL_NS_PER_ORG`` raw 035 namespaces, as a share of all its records.

    Denominators are every record the institution holds (millions), so the coverage
    shares need no suppression; the namespace matrix nulls cells below ``threshold``.
    """
    # local_system / pod_system read the same agency-code mapping, so an unmapped
    # org would understate both here too
    _assert_orgs_mapped(con)

    channel_rows = con.execute(Q_CHANNEL_COVERAGE).fetchall()

    def cell(count: int, records: int) -> tuple[int | None, float | None]:
        """(count, share), or (None, None) when the count is too small to report.

        These channels overlap rather than partition, so there is no ``other``
        bucket to fold a small count into the way the 040 mix does — null is the
        only honest option, and it matches the repo's null-means-suppressed rule.
        A genuine zero stays 0. Real counts here run to millions, but a small
        member's ``pod_system`` can be a handful (Brown's is 13 today).
        """
        if 0 < count < threshold:
            return None, None
        return count, (round(count / records, 4) if records else 0.0)

    per_org = []
    for org, records, *counts in channel_rows:
        cells = {c: cell(n, records) for c, n in zip(_CHANNELS, counts)}
        per_org.append(
            {
                "org": org,
                "records": records,
                # counts alongside shares so the page never has to reconstruct them
                # by multiplying a 4-dp share back out
                "counts": {c: v[0] for c, v in cells.items()},
                "coverage": {c: v[1] for c, v in cells.items()},
            }
        )

    namespace = _comparison_matrix(
        con, Q_CHANNEL_NAMESPACE, threshold=threshold, top_k=None
    )
    namespace["totals"] = dict(con.execute(Q_CHANNEL_TOTAL).fetchall())
    namespace["sql"] = [
        {
            "label": "035 namespaces: each institution's own top "
            f"{_CHANNEL_NS_PER_ORG}, unioned",
            "sql": Q_CHANNEL_NAMESPACE,
        },
        {"label": "Share denominator: all records", "sql": Q_CHANNEL_TOTAL},
    ]

    return {
        "channels": list(_CHANNELS),
        "per_org": per_org,
        "dimensions": {"namespace": namespace},
        "sql": [
            {
                "label": "Records carrying each channel's system number",
                "sql": Q_CHANNEL_COVERAGE,
            }
        ],
    }


def coverage(con: Connection, **_: object) -> dict:
    """
    Per-institution metadata completeness: share of records carrying selected
    fields (ISBN, subjects, author, electronic access, physical description,
    classification). Denominators are large, so no suppression is needed.
    """
    rows = con.execute(Q_COVERAGE).fetchall()
    fields = ["isbn", "subjects", "author", "online", "phys_desc", "lc_classification"]
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

# The cross-institution comparison heatmaps (Languages, Place of publication,
# Format, LC classification). Each dimension supplies a query returning
# (org, category, n); the first three are coded categoricals read from a single
# MARC field, LC classification is assembled across several call-number slots.
_COMPARE_TOP_K = 15  # global top categories kept per dimension


def _dist_sql(expr: str, where: str) -> str:
    """A per-record coded categorical → (org, category, n)."""
    return (
        f"SELECT org, {expr} AS category, count(*) AS n\n"
        f"FROM records\n"
        f"WHERE {where}\n"
        f"  AND {expr} IS NOT NULL AND trim({expr}) <> ''\n"
        f"GROUP BY org, category"
    )


def _lc_class_sql(serials_only: bool = False) -> str:
    """
    One LC class letter per record: scan the call-number locations (_LC_CALLNUM)
    in priority order, keep only LC-shaped values, and take the first match — so
    non-LC schemes and records with no call number simply drop out. With
    ``serials_only`` the records are first restricted to serials (leader/07='s').
    """
    priority = "\n      ".join(
        f"WHEN {_lc_loc_cond(*loc)} THEN {i}" for i, loc in enumerate(_LC_LOCATIONS)
    )
    source = "records"
    if serials_only:
        source = (
            "records\n"
            "    JOIN (SELECT DISTINCT org, pod_record_id FROM records\n"
            "          WHERE field_tag = 'LDR' AND substr(value, 8, 1) = 's')\n"
            "      USING (org, pod_record_id)"
        )
    return (
        "WITH candidate AS (\n"
        "  SELECT org, pod_record_id,\n"
        "    upper(substr(trim(value), 1, 1)) AS category,\n"
        f"    CASE\n      {priority}\n    END AS priority\n"
        f"  FROM {source}\n"
        f"  WHERE {_LC_CALLNUM}\n"
        "),\n"
        "first_match AS (\n"
        "  SELECT org, category\n"
        "  FROM candidate\n"
        "  QUALIFY row_number() OVER "
        "(PARTITION BY org, pod_record_id ORDER BY priority) = 1\n"
        ")\n"
        "SELECT org, category, count(*) AS n\n"
        "FROM first_match\n"
        "GROUP BY org, category"
    )


def _compare_sql() -> dict[str, str]:
    return {
        "language": _dist_sql(
            "upper(trim(substr(value, 36, 3)))",
            "field_tag = '008' AND length(value) >= 38",
        ),
        "country": _dist_sql(
            _COUNTRY_EXPR, "field_tag = '008' AND length(value) >= 18"
        ),
        "record_type": _dist_sql(
            "substr(value, 7, 1)", "field_tag = 'LDR' AND length(value) >= 7"
        ),
        "classification": _lc_class_sql(),
        # LC class of just the serials — what the continuing resources are about
        "serial_classification": _lc_class_sql(serials_only=True),
        # publication status of serials (008/06): still published / ceased /
        # unknown — the "currency" of each institution's continuing resources
        "serial_status": _serial_status_sql(),
    }


def _serial_status_sql() -> str:
    """
    Serials (leader/07='s') counted by 008 publication-status code (char 06):
    'c' still published, 'd' ceased, 'u' status unknown. Other codes are dropped
    so the three shares sum to ~100%.
    """
    return (
        "WITH serial AS (\n"
        "  SELECT DISTINCT org, pod_record_id FROM records\n"
        "  WHERE field_tag = 'LDR' AND substr(value, 8, 1) = 's'\n"
        ")\n"
        "SELECT s.org, substr(r.value, 7, 1) AS category, count(*) AS n\n"
        "FROM serial s JOIN records r USING (org, pod_record_id)\n"
        "WHERE r.field_tag = '008' AND length(r.value) >= 7\n"
        "  AND substr(r.value, 7, 1) IN ('c', 'd', 'u')\n"
        "GROUP BY s.org, category"
    )


def comparison(con: Connection, *, threshold: int = 10, **_: object) -> dict:
    """
    Cross-institution comparison matrices for the heatmap views. For each
    dimension: the categories (ranked by total count across all institutions),
    every institution's count per category, each institution's dimension total
    (the denominator for a share), and the SQL that produced the raw counts.
    Most dimensions keep the top ``_COMPARE_TOP_K``; the LC-classification
    dimensions show every class (a bounded ~21-value set) so each institution's
    column sums to ~100%. Counts in ``1..threshold-1`` are suppressed to null so
    no small cell is exposed; a genuine zero stays 0. Category codes are labeled
    client-side.
    """
    return {
        "dimensions": {
            name: _comparison_matrix(
                con,
                sql,
                threshold=threshold,
                top_k=None if name in _COMPARE_ALL_CATEGORIES else _COMPARE_TOP_K,
            )
            for name, sql in _compare_sql().items()
        }
    }


# Dimensions that show every category rather than the top-k: the LC classes are
# a bounded set (~21 letters), so all of them fit and columns total ~100%.
_COMPARE_ALL_CATEGORIES = frozenset({"classification", "serial_classification"})


def _comparison_matrix(
    con: Connection,
    sql: str,
    *,
    threshold: int,
    top_k: int | None = _COMPARE_TOP_K,
    categories: list[str] | None = None,
) -> dict:
    """
    Shape flat ``(org, category, n)`` rows into the heatmap matrix. Categories are
    ranked by consortium total and capped at ``top_k`` unless ``categories`` pins an
    explicit set and order — for fixed vocabularies (an ordered bucket scale, a
    square institution × institution matrix) where ranking would scramble the axis
    and a category absent from the rows still needs its row.
    """
    rows = con.execute(sql).fetchall()

    orgs = sorted({org for org, _cat, _n in rows})
    totals: dict[str, int] = dict.fromkeys(orgs, 0)
    cat_totals: dict[str, int] = {}
    counts: dict[tuple[str, str], int] = {}
    for org, cat, n in rows:
        totals[org] += n
        cat_totals[cat] = cat_totals.get(cat, 0) + n
        counts[(org, cat)] = n

    if categories is None:
        ranked = [
            cat for cat, _ in sorted(cat_totals.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        categories = ranked if top_k is None else ranked[:top_k]

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
