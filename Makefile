.PHONY: extract site build check

# Compile the public aggregate artifacts from the lake into site/src/data.
# Point CATALOG at the lake to read: a local .ducklake path, an
# s3://…/x.ducklake URI, or a postgres:… DSN. For a Postgres catalog also set
# DATA_PATH (the s3://… prefix holding the Parquet data).
#   make extract CATALOG=../../podlake/podlake.ducklake
#   make extract CATALOG=s3://my-bucket/podlake/podlake.ducklake
CATALOG ?=
DATA_PATH ?=
extract:
	cd extract && uv run podlake-web extract --catalog "$(CATALOG)" \
		$(if $(DATA_PATH),--data-path "$(DATA_PATH)",)

# Preview the dashboard locally (expects artifacts to exist; run `make extract` first).
site:
	cd site && npm run dev

# Produce the static site in site/dist.
build:
	cd site && npm run build

# Lint, type-check, and test the extract step.
check:
	cd extract && uv run ruff format --check . && uv run ruff check . && uv run ty check . && uv run pytest -q
