# About the data

This dashboard is deliberately built to be **safe to publish**. The underlying
podlake DuckLake holds hundreds of millions of record-level rows and is only
available to POD members. What this site loads instead is a small set of
pre-computed **aggregates** — counts, distributions, and percentages — with no
record identifiers, Gold Rush keys, titles, or raw field values.

```js
import {html} from "npm:htl";
import {orgLabel} from "./components/marc.js";
import {provenance} from "./components/provenance.js";
const manifest = FileAttachment("./data/manifest.json").json();
const catFile = FileAttachment("./data/cataloging_source.json");
const cat = catFile.json();
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
The queries are nothing fancier than SQL over the two tables described under [the
schema](#the-schema); the raw counts are then shaped in Python (small-cell
suppression, the comparison share matrices, the place roll-ups), all of it in the
extract:
[`src/podlake_web`](https://github.com/pod4lib/podlake-web/tree/main/src/podlake_web).

## Querying the lake yourself

The dashboard shows aggregates. To work at the **record level** — reconstruct
records, pull specific fields, run your own cross-tabulations — you can query the
lake directly with [DuckDB](https://duckdb.org/) on your own machine. Same data,
full SQL, no limits.

<div class="note">

**Access.** The shared POD lake is private, so querying it needs read-only
credentials issued to authorized partners (a self-serve, per-user signed-key app
is planned — for now access is arranged manually). You can also build and query
your **own** lake with [podlake](https://github.com/pod4lib/podlake); everything
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

## The institution code mapping

MARC `040 $a` and `035` identify a cataloging agency by code, and nothing in the
record says which POD member a code belongs to — so the mapping is curated by hand in
[`institution-codes.csv`](https://github.com/pod4lib/podlake-web/blob/main/institution-codes.csv).

It matters only where a view asks **who catalogued a record**: the "this institution"
and "another POD member" shares on [Source of cataloging](./cataloging-source) and its
intra-consortium flow matrix, all of [Original cataloging over
time](./original-cataloging), and the "a local library system" / "another POD member's
system" rows on [How records arrived](./record-channels). Every other per-institution
figure — counts, overlap, subject and language distributions, classification, formats
— keys on `org`, the lake's own record of which member contributed the record, and is
unaffected by the map.
[`tools/registry-codes.js`](https://github.com/pod4lib/podlake-web/blob/main/tools/registry-codes.js)
proposes rows from the [WorldCat Registry](https://registry.worldcat.org/) and a
person decides what to keep;
[docs/institution-codes.md](https://github.com/pod4lib/podlake-web/blob/main/docs/institution-codes.md)
covers maintaining it.

**Every figure built on it is a floor.** The map holds only codes somebody has
confirmed, so retired or unrecorded codes go uncounted — nothing here distinguishes
"did little original cataloging" from "has codes we don't know about yet".

Below is the map exactly as this snapshot used it, split by namespace because the two
follow different rules. Most of these codes are branch libraries that rarely or never
appear in `040 $a`; being listed does not imply the institution uses it.

```js
const codeMap = cat.code_map ?? {listed: [], sql: null};
const codeRows = (kind) =>
  codeMap.listed
    .filter((r) => r.kind === kind)
    .map((r) => ({
      institution: orgLabel(r.org),
      code: r.code,
      "registry name": r.registry_name,
    }))
    .sort(
      (a, b) =>
        a.institution.localeCompare(b.institution) || a.code.localeCompare(b.code)
    );
// Full width, or the registry names truncate — they are the field you read to judge
// whether a row belongs to that institution.
const codeTable = (rows) =>
  rows.length
    ? html`<div class="grid grid-cols-1">${Inputs.table(rows, {
        rows: 12,
        width: {institution: 110, code: 150},
      })}</div>`
    : html`<div class="note">This snapshot predates the published map — re-running the
        extract fills this in.</div>`;
```

**MARC Organization Codes.** Hierarchical on the hyphen, so a listed code also covers
its sub-units without the file enumerating them: `CtY` counts `CtY-BR` (Yale's
Beinecke) too. The hyphen is required rather than a nicety — `PU-L` is Penn's Biddle
Law Library and `PUL` is Princeton University Library, and LC's own registry publishes
`PU-L` normalized to `pul`, which conflates the two.

```js
codeTable(codeRows("marc"))
```

**OCLC symbols.** A separate namespace, and opaque — `AS#`, `4H7`, `YU#` — so these
are matched exactly. A shared prefix between two symbols means nothing, and no
sub-unit rule applies.

```js
codeTable(codeRows("oclc"))
```

Case is not significant in either namespace; agency codes are written every which way
in real records, so both sides are upper-cased before comparing.

Two smaller maps live in the extract rather than here: `_LOCAL_ILS_NS`, the generic ILS
namespaces (`SIRSI`, `PUVoyagerBibID`) that mean "local" for whichever library carries
them, and `_CHANNEL_TESTS`, the `035` channel categories. Display names for raw codes
are in `components/marc.js` and are cosmetic — an unmapped code still charts, just
bare.

**Adding an institution means updating the CSV.** The extract refuses to build for an
institution it has no codes for, rather than publishing a plausible-looking 0%
self-cataloged.
