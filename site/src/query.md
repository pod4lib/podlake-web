# Query it yourself

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

## 1. Install DuckDB

DuckDB is a single self-contained binary — no server to run.

```sh
# macOS / Linux command line
curl https://install.duckdb.org | sh      # or: brew install duckdb

# or from Python
pip install duckdb                          # then: import duckdb
```

Start an interactive session with `duckdb`, or the built-in web UI with
`duckdb -ui`.

## 2. Attach the lake (read-only)

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

## 3. The shape of the data

Two tables:

- **`record_meta`** — one row per record: `org`, `pod_record_id`, and
  `goldrush_key` (the Gold Rush match key that powers overlap and
  uniqueness).
- **`records`** — tall/EAV, one row per MARC subfield: `org, pod_record_id,
  field_tag, field_seq, ind1, ind2, subfield_code, subfield_seq, value`. The
  leader is `field_tag = 'LDR'`; control fields (00X) put their data in `value`
  with a `NULL` subfield_code. Any field or subfield is a plain `WHERE` clause.

## 4. The queries behind the dashboard

Every chart on this site is one of these — run them yourself and modify away:

```js
import {sqlCard} from "./components/sql.js";
const queries = FileAttachment("./data/queries.json").json();
```

```js
html`${queries.queries.map(sqlCard)}`
```

## 5. Going deeper: record-level queries

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

-- records at one institution carrying a IIIF/electronic-access link (856)
SELECT count(*) FROM records
WHERE org = 'stanford' AND field_tag = '856' AND subfield_code = 'u';
```

## Tips

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
