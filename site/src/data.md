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
The queries are nothing fancier than SQL over two tables: `record_meta` (one row
per record, with its Gold Rush match key `goldrush_key`) and `records` (a tall
table, one row per MARC subfield, so any field or subfield is a plain `WHERE`
clause).

The SQL is only half the story — the raw counts are then shaped in Python
(small-cell suppression, the comparison share matrices, the place roll-ups). All
of that lives in the extract:
[`extract/src/podlake_web`](https://github.com/sul-dlss/podlake-web/tree/main/extract/src/podlake_web).
To run queries like these against the lake yourself, see
[Query it yourself](./query).
