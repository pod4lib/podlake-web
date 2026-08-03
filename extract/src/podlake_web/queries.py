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
# clamped out; bump when the lake is refreshed well beyond it.
NOW_YEAR = 2025

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
    con: Connection, sql: str, *, threshold: int, top_k: int | None = _COMPARE_TOP_K
) -> dict:
    rows = con.execute(sql).fetchall()

    orgs = sorted({org for org, _cat, _n in rows})
    totals: dict[str, int] = dict.fromkeys(orgs, 0)
    cat_totals: dict[str, int] = {}
    counts: dict[tuple[str, str], int] = {}
    for org, cat, n in rows:
        totals[org] += n
        cat_totals[cat] = cat_totals.get(cat, 0) + n
        counts[(org, cat)] = n

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
