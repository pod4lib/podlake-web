.PHONY: extract site build check

# Compile the public aggregate artifacts from the lake into site/src/data.
# Run this where the podlake lake is reachable (see podlake for configuration).
extract:
	cd extract && uv run podlake-web extract

# Preview the dashboard locally (expects artifacts to exist; run `make extract` first).
site:
	cd site && npm run dev

# Produce the static site in site/dist.
build:
	cd site && npm run build

# Lint, type-check, and test the extract step.
check:
	cd extract && uv run ruff format --check . && uv run ruff check . && uv run ty check . && uv run pytest -q
