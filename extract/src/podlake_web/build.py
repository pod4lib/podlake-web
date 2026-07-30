"""
``podlake-web extract`` — build the public Tier-1 aggregate artifacts.

Connects read-only to the podlake DuckLake (via podlake's own profile
resolution, so it reads whatever lake ``podlake config`` points at), runs each
Tier-1 aggregate query, and writes a JSON file per view plus a ``manifest.json``
describing the full published data surface for review.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import typer
from podlake import lake

from podlake_web import queries

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
        "Corpus totals and per-institution record/work counts.",
        queries.overview,
    ),
    (
        "overlap_histogram.json",
        "Works held by exactly N institutions (rarity curve).",
        queries.overlap_histogram,
    ),
    (
        "overlap_pairwise.json",
        "Shared works between each pair of institutions.",
        queries.overlap_pairwise,
    ),
    (
        "uniqueness.json",
        "Works held by a single institution alone.",
        queries.uniqueness,
    ),
    (
        "characterization.json",
        "Per-institution decade / language / country / subject / type distributions.",
        queries.characterization,
    ),
    (
        "coverage.json",
        "Per-institution share of records carrying selected MARC fields.",
        queries.coverage,
    ),
]


@app.command()
def extract(
    out: Path = typer.Option(DEFAULT_OUT, help="Directory to write artifacts into."),
    top_n: int = typer.Option(25, help="Max categories kept per distribution."),
    threshold: int = typer.Option(
        10, help="Cells with a count below this are folded into 'Other'."
    ),
) -> None:
    """Build the Tier-1 aggregate artifacts into OUT."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out.mkdir(parents=True, exist_ok=True)

    con = lake.connect(read_only=True)
    try:
        generated_at = datetime.now(UTC).isoformat()
        manifest = {
            "generated_at": generated_at,
            "suppression": {"top_n": top_n, "threshold": threshold},
            "artifacts": [],
        }
        for filename, description, fn in ARTIFACTS:
            data = fn(con, top_n=top_n, threshold=threshold)
            data["generated_at"] = generated_at
            path = out / filename
            path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
            logger.info("wrote %s", path)
            manifest["artifacts"].append({"file": filename, "description": description})
    finally:
        con.close()

    # the SQL behind the views, published verbatim for the "About the data" page
    queries_doc = {
        "generated_at": generated_at,
        "queries": queries.showcase(top_n=top_n, threshold=threshold),
    }
    (out / "queries.json").write_text(json.dumps(queries_doc, indent=2) + "\n")
    logger.info(
        "wrote %s (%d queries)", out / "queries.json", len(queries_doc["queries"])
    )
    manifest["artifacts"].append(
        {"file": "queries.json", "description": "The DuckDB SQL behind each view."}
    )

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
