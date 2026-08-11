# About the data

This dashboard is deliberately built to be **safe to publish**. The underlying
podlake DuckLake holds hundreds of millions of record-level rows and is only
available to POD members. What this site loads instead is a small set of
pre-computed **aggregates** — counts, distributions, and percentages — with no
record identifiers, Gold Rush keys, titles, or raw field values.

```js
const manifest = FileAttachment("./data/manifest.json").json();
```

## What is published

```js
Inputs.table(manifest.artifacts, {
  columns: ["file", "description"],
  header: {file: "File", description: "What it contains"},
  width: {file: 220},
  rows: 20,
})
```

Aggregates were last rebuilt from the lake on
**${manifest.generated_at.slice(0, 10)}**.

A read-only extract step queries the private lake and writes these JSON files;
the static site reads only those files.

## The queries behind the views

Every chart on this site has a **Behind this chart** panel showing the exact
DuckDB query that produced its data, plus a link to download that derived data.
The queries are nothing fancier than SQL over the two tables described below; the
raw counts are then shaped in Python (small-cell suppression, the comparison
share matrices, the place roll-ups), all of it in the extract:
[`extract/src/podlake_web`](https://github.com/sul-dlss/podlake-web/tree/main/extract/src/podlake_web).

## The institution code mapping

Several views need to know **which institution a MARC agency code belongs to** — is
`NDD` Duke? is `RPB` Brown? — and the records do not say. Codes appear in `040 $a`
(the agency credited with the cataloging) and as `035 $a` namespaces (the systems a
record passed through), but nothing ties a code to a POD member.

So the extract carries a hand-curated list, and **POD has not ratified it.** Treat
every figure that rests on it as *attribution practice* rather than fact. Two
properties of the data make the list unavoidable rather than merely convenient:

- Members mostly self-attribute with an **OCLC symbol, not their MARC Organization
  Code**. Duke's `NcD` appears on about 1,700 records; its `NDD` on 279,000.
- One member can use **many symbols**. Harvard's work is spread across `MH` and its
  sub-units (`MH-L`, `MH-HY`, …) plus `HLS`, `HUL`, `HMS`, `HBS` and others.

Codes that follow a member's symbol family but that nobody has confirmed are kept
apart in `_SELF_CODES_INFERRED` and reported separately as **"inferred"** wherever
they appear, so the unratified part of a figure stays visible instead of being folded
in. Codes too uncertain to attribute are left unattributed rather than guessed at.

| What | Where | Used for |
| --- | --- | --- |
| `_SELF_CODES` | `queries.py` | Codes confidently belonging to a member |
| `_SELF_CODES_INFERRED` | `queries.py` | Codes only inferred — reported separately |
| `_LOCAL_ILS_NS` | `queries.py` | Generic ILS namespaces (`SIRSI`, `PUVoyagerBibID`) that mean "local" for *whichever* library carries them, since they name a system rather than an institution |
| `_CHANNEL_TESTS` | `queries.py` | The `035` channel categories themselves |
| `NAMESPACE` | `components/marc.js` | Display names for raw codes — cosmetic only; an unmapped code still charts, just bare |

All of the above live in
[`queries.py`](https://github.com/sul-dlss/podlake-web/blob/main/extract/src/podlake_web/queries.py)
except the last, in
[`marc.js`](https://github.com/sul-dlss/podlake-web/blob/main/site/src/components/marc.js).
`_SELF_CODES` carries a comment recording each code's occurrence count and which
entries are unconfirmed, so the list can be reviewed against the data.

**Adding an institution to POD means revisiting these.** Only the first fails loudly:
the extract refuses to build when the lake holds an institution missing from
`_SELF_CODES`, because that member would otherwise publish a plausible-looking 0%
self-cataloged and no consortium sharing rather than an error. The rest degrade
quietly — a member arriving by a route no category covers simply doesn't appear in
the `035` taxonomy, and an unlabelled namespace shows its raw code.

Views that depend on the mapping: [Source of cataloging](./cataloging-source) (the
"this institution", "inferred", and "another POD member" buckets, and the whole
intra-consortium flow matrix), [Original cataloging over time](./original-cataloging)
(entirely), and [How records arrived](./record-channels) (the "a local library
system" and "another POD member's system" rows).

## Querying the lake yourself

The dashboard shows aggregates. To work at the **record level** — reconstruct
records, pull specific fields, run your own cross-tabulations — you can query the
lake directly with [DuckDB](https://duckdb.org/) on your own machine. Same data,
full SQL, no limits.

<div class="note">

**Access.** The shared POD lake is private, so querying it needs read-only
credentials issued to authorized partners (a self-serve, per-user signed-key app
is planned — for now access is arranged manually). You can also build and query
your **own** lake with [podlake](https://github.com/sul-dlss/podlake); everything
below works exactly the same against it.

</div>

### Install DuckDB

DuckDB is a single self-contained binary — no server to run.

```sh
# macOS / Linux command line
curl https://install.duckdb.org | sh      # or: brew install duckdb

# or from Python
pip install duckdb                          # then: import duckdb
```

Start an interactive session with `duckdb`, or the built-in web UI with
`duckdb -ui`.

### Attach the lake (read-only)

Attaching **read-only** guarantees your session can't modify the lake. Always go
through the DuckLake catalog — reading the Parquet files directly would ignore
snapshots and deletions and give wrong answers.

For a **published lake in a private S3 bucket**, register your read-only
credentials, then attach:

```sql run=false
INSTALL ducklake; INSTALL httpfs;

CREATE SECRET pod (
  TYPE s3,
  KEY_ID 'your-read-only-key-id',
  SECRET 'your-read-only-secret',
  REGION 'us-west-2'
);

ATTACH 'ducklake:s3://your-bucket/pod/podlake.ducklake' AS podlake
  (DATA_PATH 's3://your-bucket/pod/lake-data/', READ_ONLY, OVERRIDE_DATA_PATH true);
USE podlake;
```

For a **local lake** you built with podlake:

```sql run=false
INSTALL ducklake;
ATTACH 'ducklake:podlake.ducklake' AS podlake (DATA_PATH './lake-data/', READ_ONLY);
USE podlake;
```

### The schema

Two tables, joined on `(org, pod_record_id)`.

**`record_meta`** — one row per bibliographic record:

| column | meaning |
|---|---|
| `org` | contributing institution (e.g. `stanford`) |
| `pod_record_id` | the record's stable id, `org`-prefixed |
| `goldrush_key` | Gold Rush match key — records sharing one are treated as the same *title* (this powers overlap, rarity, and uniqueness) |

**`records`** — tall/EAV, one row per MARC **subfield**. Reassemble a record by
grouping on `pod_record_id` and ordering by `field_seq, subfield_seq`:

| column | meaning |
|---|---|
| `org`, `pod_record_id` | join back to `record_meta` |
| `field_tag` | MARC tag: `LDR` (leader), `001`–`009` (control fields), `245` / `650` / … (data fields) |
| `field_seq` | position of this field in the record — also disambiguates repeated tags |
| `ind1`, `ind2` | the two indicators (data fields only; `NULL` on the leader and control fields) |
| `subfield_code` | subfield letter (`a`, `b`, …); `NULL` for the leader and control fields |
| `subfield_seq` | position of the subfield within its field |
| `value` | the subfield's text — or, for `LDR` / `00X`, the entire fixed-field string |

How MARC maps onto this layout:

- The **leader** is `field_tag = 'LDR'`; its fixed positions live in `value` —
  type of record is character 7, bibliographic level is character 8.
- **Control fields** (`001`–`009`) likewise carry their data in `value` with a
  `NULL` `subfield_code`. The workhorse is `008`, whose fixed positions hold the
  date the record was created (chars 1–6, `yymmdd`), the publication date (8–11),
  country of publication (16–18), and language (36–38). DuckDB `substr` is
  **1-indexed**, so those become `substr(value, 1, 6)`, `substr(value, 8, 4)`,
  `substr(value, 16, 3)`, `substr(value, 36, 3)`.
- **Data fields** (`010`+) carry indicators and one row per subfield.

A short field cheat-sheet: `245` title, `1xx` author/creator, `6xx` subjects,
`050` / `090` LC call number, `008` the fixed field above, `856 $u`
electronic-access link, `040 $a` original cataloging agency and `040 $d` each
modifying agency, `035 $a` system control numbers written `(ORGCODE)number`.

### Record-level examples

These only make sense with direct access (the public dashboard never exposes
them), and they show why the tall layout is handy:

```sql run=false
-- all titles (245 $a)
SELECT value FROM records WHERE field_tag = '245' AND subfield_code = 'a' LIMIT 20;

-- pull several fields per record as columns (conditional aggregation)
SELECT pod_record_id,
  max(value) FILTER (WHERE field_tag = '245' AND subfield_code = 'a') AS title,
  max(value) FILTER (WHERE field_tag = '100' AND subfield_code = 'a') AS author
FROM records
WHERE field_tag IN ('245', '100')
GROUP BY pod_record_id
LIMIT 20;

-- reconstruct one record in order (leader first, then fields/subfields)
SELECT field_tag, ind1, ind2, subfield_code, value
FROM records
WHERE pod_record_id = 'stanford:12345'
ORDER BY field_seq, subfield_seq;

-- records at one institution carrying an electronic-access link (856)
SELECT count(*) FROM records
WHERE org = 'stanford' AND field_tag = '856' AND subfield_code = 'u';
```

### Tips

- **Filter by `org`** when you can — the lake is partitioned by organization, so
  it prunes whole partitions.
- **Use `record_meta`** for anything title-level (counts, overlap, uniqueness);
  it's far smaller than `records`.
- Pin a snapshot for reproducibility with `FROM records AT (VERSION => N)`.
- Reach for `LIMIT` while exploring — `records` has hundreds of millions of rows.

<div class="note">

**Coming later.** A hosted web app with authenticated users and per-user signed
keys would let people run these queries without installing anything or handling
credentials by hand. That's a separate build; this page is the zero-infra path
that works today.

</div>
