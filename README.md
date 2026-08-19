# podlake-web

A public, client-side dashboard that showcases the consortial collection
analytics possible with [podlake](https://github.com/sul-dlss/podlake) for the
[POD](https://pod.stanford.edu/) community.

Live at <https://sul-dlss.github.io/podlake-web/>.

## Design

The podlake DuckLake holds hundreds of millions of record-level rows and is only
accessible to POD members. So this project splits in two along that boundary:

1. **`src/podlake_web/`** — a Python step that connects *read-only* to the private
   lake and compiles a handful of small, **aggregate-only** JSON artifacts (counts,
   distributions, percentages — never record identifiers, titles, or raw field
   values).
2. **`site/`** — an [Observable Framework](https://observablehq.com/framework/)
   app that reads *only* those artifacts and renders them. It is fully static and
   serverless: the built files deploy to GitHub Pages, with no database to reach.

The aggregate artifacts in `site/src/data/*.json` are **committed** — they are the
published snapshot the site is built from. That is what lets the public site build
without any access to the lake, and it is why refreshing the figures is a commit
rather than a query: see [Keeping the figures current](#keeping-the-figures-current).

Because only a POD-member host can reach the lake, that refresh runs there rather
than in CI: `podlake-web refresh` rebuilds and publishes, and
[podlake-deploy](https://github.com/sul-dlss/podlake-deploy) provisions the host and schedules it.

## Quickstart

Everything is a subcommand of `podlake-web`, the same way podlake exposes
`podlake sync-all`:

```sh
uv run podlake-web --help
```

**One prerequisite that is easy to miss: `podlake` must be checked out as a sibling
of this repo.** `pyproject.toml` depends on it by path (`../podlake`), so the whole
CLI fails to install without it — this is not optional, and it is why CI checks out
both repositories side by side:

```sh
git clone https://github.com/sul-dlss/podlake.git
git clone https://github.com/sul-dlss/podlake-web.git
cd podlake-web            # podlake/ and podlake-web/ are now siblings
```

You also need [uv](https://docs.astral.sh/uv/), and Node 20+ for the `site` and
`build` tasks.

`extract` needs an explicit `--catalog` naming the lake to read — a local
`.ducklake` file, an `s3://…/x.ducklake` object, or a `postgres:…` DSN — so it can
run anywhere the lake is reachable:

```sh
# one-time: install the site's npm deps (Python deps are handled by uv)
uv run podlake-web install

# 1. compile the public aggregate artifacts into site/src/data/*.json

# a local podlake checkout (data path defaults to the sibling lake-data/):
uv run podlake-web extract --catalog ../podlake/podlake.ducklake

# a lake published to S3 by `podlake publish`:
uv run podlake-web extract --catalog s3://my-bucket/podlake/podlake.ducklake

# a Postgres-catalog lake (S3 data path is required — it can't be derived):
uv run podlake-web extract \
  --catalog "postgres:host=… dbname=… user=… password=…" \
  --data-path s3://my-bucket/podlake/lake-data/

# 2. preview the dashboard (reads the artifacts from step 1)
uv run podlake-web site         # dev server at http://127.0.0.1:3000
uv run podlake-web build        # or: produce the static site in site/dist

# test
uv run pytest -q
```

Formatting and typing are not wrapped in a task: CI runs `ruff format --check .`,
`ruff check .` and `ty check .` as separate steps, so forgetting them locally costs
a red build rather than a broken main.

For file catalogs `--data-path` defaults to the catalog's sibling `lake-data/` (how
`podlake publish` lays a lake out); pass it explicitly to override. S3 access uses
DuckDB's credential chain (standard `AWS_*` env vars, shared config, or an assumed
role).

## Deployment

`.github/workflows/deploy.yml` deploys the site to GitHub Pages on every push to
`main`: it runs `npm run build` and publishes `site/dist`. **The build uses the
committed `site/src/data/*.json` snapshot — CI never touches the private lake.**
So a push that changes those artifacts is what updates the live figures.

The repository's **Settings → Pages → Source** must be set to **"GitHub Actions"**
(not "Deploy from a branch"); the workflow already handles the build and upload.

### Keeping the figures current

Because CI can't reach the lake, the refresh runs on a host that can. This repo
provides the command; **[sul-dlss/podlake-deploy](https://github.com/sul-dlss/podlake-deploy)**
provisions the host and schedules it.

```sh
# on the host — rebuild the artifacts, commit and push them
uv run podlake-web refresh --catalog /opt/app/pod/podlake/podlake.ducklake
```

Running it *on the host* rather than over SSH is what keeps it simple: a remotely
driven refresh would have to survive an hour-long job outliving its connection, a
forwarded SSH agent expiring with it, and a Duo prompt no script can answer. Under
cron, none of that arises. It pushes only when the numbers actually moved — every
artifact carries a `generated_at`, so a re-run always produces a diff, and that
isn't news.

**The schedule is not ours to set.** `refresh` must run *after* podlake has finished
syncing the lake, or it publishes a comparison in which some institutions are
updated and others aren't — wrong in a way that looks plausible. That ordering spans
two repositories, so `podlake-deploy` owns it as a single pipeline. Don't add a cron
entry for `refresh` on its own.

## Layout

```
src/podlake_web/
           The `podlake-web` CLI: aggregate queries (queries.py), disclosure
           control (suppress.py), the institution↔code map loader (codes.py), the
           extract/probe commands (build.py), and the repository tasks —
           check/site/build/refresh (tasks.py). Depends on the podlake checkout
           being a sibling of this repo.
tests/     pytest; builds small DuckLakes and throwaway git repos in tmpdirs, and
           never touches the private lake.
site/      Observable Framework app; pages read site/src/data/*.json.
tools/     registry-codes.js — a browser console script that proposes rows for
           institution-codes.csv from the WorldCat Registry.
docs/      POD analytics use cases and user stories that motivate the views,
           plus institution-codes.md on maintaining the code map.

institution-codes.csv   Which agency codes belong to which POD member. Curated
           by hand; every per-institution attribution depends on it.
```

## What is published

Every artifact and the disclosure-control parameters are described on the
dashboard's **About the data** page and in `site/src/data/manifest.json`, so the
full public surface can be reviewed before anything ships.
