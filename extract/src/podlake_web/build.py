"""
``podlake-web extract`` — build the public Tier-1 aggregate artifacts.

Connects read-only to an explicitly-named podlake DuckLake (a local
``.ducklake`` file, an ``s3://…/x.ducklake`` object, or a ``postgres:…`` DSN),
runs each Tier-1 aggregate query, and writes a JSON file per view plus a
``manifest.json`` describing the full published data surface for review.
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import typer

from podlake_web import queries, source

logger = logging.getLogger(__name__)

app = typer.Typer(add_completion=False, help=__doc__)


@app.callback()
def _main() -> None:
    """Build public Tier-1 analytics extracts from a podlake DuckLake."""


# The default output dir is the sibling Observable Framework data dir:
# podlake-web/site/src/data (build.py lives at podlake-web/extract/src/podlake_web).
DEFAULT_OUT = Path(__file__).resolve().parents[3] / "site" / "src" / "data"

# filename, human description, query function
ARTIFACTS = [
    (
        "overview.json",
        "Corpus totals and per-institution record/title counts.",
        queries.overview,
    ),
    (
        "overlap_histogram.json",
        "Titles held by exactly N institutions (rarity curve).",
        queries.overlap_histogram,
    ),
    (
        "overlap_pairwise.json",
        "Shared titles between each pair of institutions.",
        queries.overlap_pairwise,
    ),
    (
        "uniqueness.json",
        "Titles held by a single institution alone.",
        queries.uniqueness,
    ),
    (
        "publication_decade.json",
        "Per-institution distribution of records by decade of publication.",
        queries.publication_decade,
    ),
    (
        "serials_timeline.json",
        "Per-institution count of serials actively published in each year.",
        queries.serials_timeline,
    ),
    (
        "serials_succession.json",
        "Per-institution serial succession: lineage links and transition types.",
        queries.serials_succession,
    ),
    (
        "archives.json",
        "Per-institution archives & manuscripts: material type, genre/form, vintage, finding-aid links.",
        queries.archives,
    ),
    (
        "electronic.json",
        "Per-institution top hosts linked from 856 fields.",
        queries.electronic,
    ),
    (
        "coverage.json",
        "Per-institution share of records carrying selected MARC fields.",
        queries.coverage,
    ),
    (
        "cataloging_source.json",
        (
            "Per-institution source of cataloging (MARC 040): provenance mix, "
            "intra-consortium flow, modification depth, and the mix by year the "
            "record entered the catalog (MARC 008/00-05)."
        ),
        queries.cataloging_source,
    ),
    (
        "record_channels.json",
        (
            "Per-institution distribution channels from MARC 035 system control "
            "numbers: OCLC, RLIN, Alma Community Zone, local and vendor namespaces."
        ),
        queries.record_channels,
    ),
    (
        "comparison.json",
        "Cross-institution matrices: language, place, format, LC classification.",
        queries.comparison,
    ),
]


CATALOG_OPTION = typer.Option(
    ...,
    "--catalog",
    help=(
        "The DuckLake catalog to read: a local .ducklake path, an "
        "s3://…/x.ducklake URI, or a postgres:… DSN."
    ),
)

DATA_PATH_OPTION = typer.Option(
    None,
    "--data-path",
    help=(
        "Where the lake's Parquet data lives. Defaults to the catalog's "
        "sibling lake-data/ for file catalogs; required for a Postgres catalog."
    ),
)


def _require_data_path_for_postgres(catalog: str, data_path: str | None) -> None:
    if data_path is None and source.is_postgres(catalog):
        raise typer.BadParameter(
            "--data-path is required when --catalog is a Postgres DSN",
            param_hint="--data-path",
        )


@app.command()
def probe(
    catalog: str = CATALOG_OPTION,
    data_path: str = DATA_PATH_OPTION,
    out: Path = typer.Option(
        None, "--out", help="Write the CSV here instead of standard output."
    ),
) -> None:
    """
    Print the cataloging-agency codes each institution uses, as CSV.

    This is the query behind ``queries._SELF_CODES`` — run it when onboarding a
    member, or when the extract refuses to build because an institution is
    unmapped. It is a command rather than a snippet to copy out of the source
    because a transcribed copy drifts: the version in circulation ranked on
    ``upper(trim(value))`` while the extract matched on ``_CODE_NORM``, so it
    reported one code as two rows and nobody noticed.

    Columns: ``n`` is occurrences of the code at that institution,
    ``pct_of_org`` its share of that institution's records, and
    ``pct_at_this_org`` how much of the code's *consortium-wide* use sits at this
    one institution. Sort by the last of these — a code used almost only at one
    member is the shape worth reviewing. It is not proof, though: single-subscriber
    vendor namespaces look identical. Settle a MARC Organization Code against
    id.loc.gov/vocabulary/organizations/<code>.json and an OCLC symbol against
    OCLC's member directory (searching by *institution name* returns every symbol
    that institution owns).
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _require_data_path_for_postgres(catalog, data_path)

    con = source.connect(catalog, data_path, read_only=True)
    try:
        rows = con.execute(queries._SELF_CODE_PROBE)
        header = [d[0] for d in rows.description]
        records = rows.fetchall()
    finally:
        con.close()

    if out is None:
        writer = csv.writer(sys.stdout)
        writer.writerow(header)
        writer.writerows(records)
        return
    with out.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(records)
    logger.info("wrote %s (%d rows)", out, len(records))


@app.command()
def extract(
    catalog: str = CATALOG_OPTION,
    data_path: str = DATA_PATH_OPTION,
    out: Path = typer.Option(DEFAULT_OUT, help="Directory to write artifacts into."),
    threshold: int = typer.Option(
        10, help="Counts below this are suppressed (folded into 'Other' or blanked)."
    ),
) -> None:
    """Build the Tier-1 aggregate artifacts into OUT."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out.mkdir(parents=True, exist_ok=True)

    _require_data_path_for_postgres(catalog, data_path)

    con = source.connect(catalog, data_path, read_only=True)
    try:
        generated_at = datetime.now(UTC).isoformat()
        manifest = {
            "generated_at": generated_at,
            "suppression": {"threshold": threshold},
            "artifacts": [],
        }
        for filename, description, fn in ARTIFACTS:
            data = fn(con, threshold=threshold)
            data["generated_at"] = generated_at
            path = out / filename
            path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
            logger.info("wrote %s", path)
            manifest["artifacts"].append({"file": filename, "description": description})
    finally:
        con.close()

    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    logger.info(
        "wrote %s (%d artifacts)", out / "manifest.json", len(manifest["artifacts"])
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
