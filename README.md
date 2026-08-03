# podlake-web

A public, client-side dashboard that showcases the consortial collection
analytics possible with [podlake](https://github.com/sul-dlss/podlake) for the
[POD](https://pod.stanford.edu/) community.

Live at <https://sul-dlss.github.io/podlake-web/>.

## Design

The podlake DuckLake holds hundreds of millions of record-level rows and is only
accessible to POD members. So this project has two components:

1. **`extract/`** — a Python step that connects *read-only* to the private lake
   and compiles a handful of small, **aggregate-only** JSON artifacts (counts,
   distributions, percentages — never record identifiers, titles, or raw field
   values).
2. **`site/`** — an [Observable Framework](https://observablehq.com/framework/)
   app that reads *only* those artifacts and renders them. It is fully static and
   serverless: the built files deploy to GitHub Pages, with no database to reach.

The aggregate artifacts in `site/src/data/*.json` are **committed** — they are the
published snapshot the site is built from. Refreshing the figures means re-running
`extract` against the lake and committing the updated JSON.

## Quickstart

The `Makefile` wraps the common tasks. `extract` needs an explicit `CATALOG`
naming the lake to read — a local `.ducklake` file, an `s3://…/x.ducklake`
object, or a `postgres:…` DSN — so it can run anywhere the lake is reachable:

```sh
# one-time: install the site's npm deps (extract's Python deps are handled by uv)
cd site && npm install && cd ..

# 1. compile the public aggregate artifacts into site/src/data/*.json

# a local podlake checkout (data path defaults to the sibling lake-data/):
make extract CATALOG=../../podlake/podlake.ducklake

# a lake published to S3 by `podlake publish`:
make extract CATALOG=s3://my-bucket/podlake/podlake.ducklake

# a Postgres-catalog lake (S3 data path is required — it can't be derived):
make extract CATALOG="postgres:host=… dbname=… user=… password=…" \
             DATA_PATH=s3://my-bucket/podlake/lake-data/

# 2. preview the dashboard (reads the artifacts from step 1)
make site            # dev server at http://127.0.0.1:3000
make build           # or: produce the static site in site/dist

# lint, type-check, and test the extract step
make check
```

For file catalogs `DATA_PATH` defaults to the catalog's sibling `lake-data/` (how
`podlake publish` lays a lake out); pass it explicitly to override. S3 access uses
DuckDB's credential chain (standard `AWS_*` env vars, shared config, or an assumed
role).

## Deployment

`.github/workflows/deploy.yml` deploys the site to GitHub Pages on every push to
`main`: it runs `npm run build` and publishes `site/dist`. **The build uses the
committed `site/src/data/*.json` snapshot — CI never touches the private lake.**
So updating the live figures is a two-step commit: `make extract CATALOG=…`, then
commit the changed artifacts.

The repository's **Settings → Pages → Source** must be set to **"GitHub Actions"**
(not "Deploy from a branch"); the workflow already handles the build and upload.

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
