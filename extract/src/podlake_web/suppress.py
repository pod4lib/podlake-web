"""
Disclosure-control helpers for the published aggregates.

Everything the extract publishes is a count/distribution, never a record. The
one residual risk is a *small* cell — e.g. "1 work in Tibetan uniquely held by
X" — which could finger a specific holding. These helpers fold every cell below
a threshold into an aggregated ``Other`` bucket, so a count in ``1..threshold-1``
is never exposed on its own. Totals and the ``Other`` bucket itself are exempt
(they aggregate many records and reveal nothing about an individual one).
"""

from __future__ import annotations

OTHER = "Other"


def bucket_top_n(
    rows: list[dict],
    *,
    n: int,
    threshold: int,
    label_key: str = "category",
    count_key: str = "count",
    other_label: str = OTHER,
) -> list[dict]:
    """
    Keep the top ``n`` rows by count and fold the rest — plus any cell whose
    count is below ``threshold`` — into a single ``other_label`` bucket.

    Guarantees no surviving cell (other than ``other_label``) has a count in
    ``1..threshold-1``, and bounds the output to ``n + 1`` rows. Returns a new
    list sorted by count descending with ``other_label`` last (only if > 0).
    """
    ordered = sorted(rows, key=lambda r: r[count_key], reverse=True)
    kept: list[dict] = []
    other = 0
    for i, row in enumerate(ordered):
        count = row[count_key]
        if i < n and count >= threshold:
            kept.append({label_key: row[label_key], count_key: count})
        else:
            other += count
    if other:
        kept.append({label_key: other_label, count_key: other})
    return kept


def fold_small(
    rows: list[dict],
    *,
    threshold: int,
    label_key: str = "category",
    count_key: str = "count",
    other_label: str = OTHER,
) -> list[dict]:
    """
    Fold only the sub-``threshold`` cells into ``other_label`` (no top-n cap).
    Used for distributions where every above-threshold bucket is worth keeping
    (e.g. a publication-decade histogram).
    """
    return bucket_top_n(
        rows,
        n=len(rows),
        threshold=threshold,
        label_key=label_key,
        count_key=count_key,
        other_label=other_label,
    )


def small_cells(
    rows: list[dict],
    *,
    threshold: int,
    label_key: str = "category",
    count_key: str = "count",
    other_label: str = OTHER,
) -> list[dict]:
    """
    Return any rows (other than ``other_label``) whose count is in
    ``1..threshold-1`` — i.e. cells that leaked through suppression. A correct
    extract yields an empty list; used by tests to assert the invariant.
    """
    return [
        row
        for row in rows
        if row.get(label_key) != other_label and 0 < row[count_key] < threshold
    ]
