# podlake-web

A public, client-side dashboard that showcases the consortial collection
analytics possible with [podlake](https://github.com/sul-dlss/podlake) — overlap
and rarity, collection characterization, and metadata quality across the
[POD](https://pod.stanford.edu/) community.

## Why it is built this way

The podlake DuckLake holds hundreds of millions of record-level rows and **cannot
be made public**. So this project splits cleanly in two:

1. **`extract/`** — a Python step that connects *read-only* to the private lake
   and compiles a handful of small, **aggregate-only** JSON artifacts (counts,
   distributions, percentages — no record ids, work keys, titles, or raw field
   values). Small cells are suppressed so nothing can finger an individual
   holding. This is the only thing that touches the lake.
2. **`site/`** — an [Observable Framework](https://observablehq.com/framework/)
   app that reads *only* those artifacts and renders them. It is fully static and
   serverless: deploy the built files to S3 or GitHub Pages, no database to reach.

This is **Tier 1**. The same extract framework is the spine for later tiers:

- **Tier 2** — a compact, non-identifying work-membership extract queried
  client-side with DuckDB-WASM for "my institution vs. selected partners"
  comparisons.
- **Tier 3** — record-level work (last-copy lists, list upload, text search,
  external matching) served through *gated* tools against the private lake, never
  from this public site.

## Quickstart

Build the aggregates from a lake, then run the site. `extract` takes an explicit
`--catalog` naming the lake to read — a local `.ducklake` file, an
`s3://…/x.ducklake` object, or a `postgres:…` DSN — so it can run anywhere the
lake is reachable, not just next to it:

```sh
# 1. compile the public artifacts from the lake
cd extract

# a local podlake checkout (data path defaults to the sibling lake-data/):
uv run podlake-web extract --catalog ../../podlake/podlake.ducklake

# a lake published to S3 by `podlake publish`:
uv run podlake-web extract --catalog s3://my-bucket/podlake/podlake.ducklake

# a Postgres-catalog lake (S3 data path is required — it can't be derived):
uv run podlake-web extract \
  --catalog "postgres:host=… dbname=… user=… password=…" \
  --data-path s3://my-bucket/podlake/lake-data/
# all three write site/src/data/*.json

# 2. preview the dashboard
cd ../site
npm install
npm run dev                            # or: npm run build  -> site/dist
```

For file catalogs `--data-path` defaults to the catalog's sibling `lake-data/`
(how `podlake publish` lays a lake out); pass it explicitly to override. S3
access uses DuckDB's credential chain (standard `AWS_*` env vars, shared config,
or an assumed role).

`make extract CATALOG=…` (and `DATA_PATH=…` when needed) and `make site` wrap
these. The generated `site/src/data/*.json` are gitignored — they are rebuilt
from the lake, so a deploy runs `extract` before `build`.

## Layout

```
extract/   Python: aggregate queries (queries.py), disclosure control
           (suppress.py), and the `podlake-web extract` CLI (build.py).
site/      Observable Framework app; pages read site/src/data/*.json.
docs/      POD analytics use cases and user stories that motivate the views.
```

## What is published

Every artifact and the disclosure-control parameters are described on the
dashboard's **About the data** page and in `site/src/data/manifest.json`, so the
full public surface can be reviewed before anything ships.
