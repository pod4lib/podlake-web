.PHONY: extract site build check

# Compile the public aggregate artifacts from the lake into site/src/data.
# Point CATALOG at the lake to read: a local .ducklake path, an
# s3://…/x.ducklake URI, or a postgres:… DSN. For a Postgres catalog also set
# DATA_PATH (the s3://… prefix holding the Parquet data).
#   make extract CATALOG=../../podlake/podlake.ducklake
#   make extract CATALOG=s3://my-bucket/podlake/podlake.ducklake
#
# `?=` defers to the environment, so both may be exported instead of passed on
# the command line (a command-line value still wins over an exported one).
CATALOG ?=
DATA_PATH ?=
extract:
# Checked here rather than left to the CLI: an empty CATALOG still satisfies the
# required --catalog option, so it reaches DuckDB as a relative path and fails with
# "Could not read from file .../extract: Is a directory" — which reads like a broken
# lake rather than an unset variable.
	@test -n "$(CATALOG)" || { \
	  echo "make extract: CATALOG is not set."; \
	  echo "  Pass the lake to read — a local .ducklake path, an s3://…/x.ducklake"; \
	  echo "  URI, or a postgres:… DSN (which also needs DATA_PATH):"; \
	  echo "    make extract CATALOG=../../podlake/podlake.ducklake"; \
	  exit 1; \
	}
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
