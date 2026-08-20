"""
The institution ↔ agency-code map, loaded from ``institution-codes.csv``.

MARC ``040 $a`` and ``035`` namespaces identify a *cataloging agency* by code. The
records never say which POD member a code belongs to, and it cannot be derived:
members mostly self-attribute with an OCLC symbol rather than their MARC
Organization Code (Duke writes ``NDD`` on 301k records and ``NcD`` on ~2k), and one
member may use dozens of codes across its libraries. So the mapping is curated by
hand, in a CSV at the repository root rather than in this source file, so that the
people whose judgement it encodes can read and amend it, and so a change arrives as
a reviewable diff. ``tools/registry-codes.js`` generates candidate rows from the
WorldCat Registry; a human decides what to keep.

Columns: ``pod_institution``, ``marc_code``, ``oclc_code``, ``registry_name``, and
optionally ``registry_url``. Exactly one of the two code columns is filled — the two
are different namespaces and the distinction matters (see FAMILIES below). One
registry entity holding both therefore appears as two rows.

Comparison is **case-insensitive**. The codes are stored in the registry's display
form (``CtY``, ``NcD``, ``MH-Ar``) because that is readable and carries the code's
structure, but records are written every which way: ``DLC`` appears as DLC, dLC,
Dlc, dlc, DlC and DLc across 10.6m records in this corpus, ``NjP`` in seven forms.
Both sides are upper-cased at comparison time.

Hyphens, by contrast, are **significant**, and must not be normalized away even
though LC's own registry does exactly that — it publishes ``PU-L`` with
``normalized: pul``. ``PU-L`` is Penn's Biddle Law Library; ``PUL`` is Princeton
University Library. Conflating them moves 210k Princeton records to Penn.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

# The map lives at the repo root, next to the README: it is curated input that POD
# members need to find, not an implementation detail. codes.py sits at
# src/podlake_web/, hence two parents up.
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "institution-codes.csv"

REQUIRED_COLUMNS = {"pod_institution", "marc_code", "oclc_code"}


@dataclass(frozen=True)
class Code:
    """One (institution, code) claim, with the code upper-cased for comparison."""

    org: str
    code: str
    is_marc: bool
    registry_name: str = ""


def load(path: Path | None = None) -> tuple[Code, ...]:
    """Read and validate the map. Raises ValueError on anything malformed."""
    path = path or DEFAULT_PATH
    if not path.exists():
        raise ValueError(
            f"the institution code map is missing: {path}\n"
            "Every per-institution attribution depends on it. Generate candidates "
            "with tools/registry-codes.js and curate them into that file."
        )
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{path} has no rows")
    missing_columns = REQUIRED_COLUMNS - set(rows[0])
    if missing_columns:
        raise ValueError(f"{path} is missing column(s): {sorted(missing_columns)}")

    codes: list[Code] = []
    for line, row in enumerate(rows, start=2):  # start=2: line 1 is the header
        marc = (row.get("marc_code") or "").strip()
        oclc = (row.get("oclc_code") or "").strip()
        org = (row.get("pod_institution") or "").strip()
        where = f"{path}:{line}"
        if not org:
            raise ValueError(f"{where}: no pod_institution")
        # Both-or-neither is the one shape that cannot be interpreted: a row with
        # both filled would silently pick one namespace, and an empty row would
        # look like a mapping while matching nothing.
        if bool(marc) == bool(oclc):
            raise ValueError(
                f"{where}: fill exactly one of marc_code / oclc_code "
                f"(got marc_code={marc!r}, oclc_code={oclc!r})"
            )
        codes.append(
            Code(
                org=org,
                code=(marc or oclc).upper(),
                is_marc=bool(marc),
                registry_name=(row.get("registry_name") or "").strip(),
            )
        )
    _validate(tuple(codes), path)
    return tuple(codes)


def _validate(codes: tuple[Code, ...], path: Path) -> None:
    """
    Fail on mechanical breakage only — never on judgement.

    Whether a given code really belongs to a member is the curator's call and is
    not checkable here. What *is* checkable is that the file cannot mis-credit a
    member by construction: no code claimed by two institutions, and no family
    rule reaching into another institution's codes.
    """
    claimed: dict[tuple[bool, str], set[str]] = {}
    for c in codes:
        claimed.setdefault((c.is_marc, c.code), set()).add(c.org)
    contested = {k: v for k, v in claimed.items() if len(v) > 1}
    if contested:
        detail = "; ".join(
            f"{'MARC' if is_marc else 'OCLC'} {code} claimed by {sorted(orgs)}"
            for (is_marc, code), orgs in sorted(contested.items())
        )
        raise ValueError(f"{path}: a code cannot belong to two institutions — {detail}")

    # See FAMILIES in expand_sql(): a listed MARC base also matches BASE-<child>.
    # That must not reach another institution's code.
    owners = {c.code: c.org for c in codes}
    for base in (c for c in codes if c.is_marc):
        for code, org in owners.items():
            if (
                code != base.code
                and code.startswith(base.code + "-")
                and org != base.org
            ):
                raise ValueError(
                    f"{path}: {base.org}'s MARC family {base.code}-* would also match "
                    f"{org}'s {code}; list the child explicitly for {org} or remove "
                    f"the conflict"
                )


def orgs(codes: tuple[Code, ...]) -> set[str]:
    return {c.org for c in codes}


def match_sql(column: str, codes: tuple[Code, ...], indent: str = "") -> str:
    """
    OR-ed SQL tests matching ``column`` against these codes.

    FAMILIES. MARC Organization Codes are hierarchical on the hyphen: a code of the
    form ``BASE-SUFFIX`` denotes a sub-unit of ``BASE``. So a listed MARC code also
    matches its children, and ``CtY`` covers ``CtY-BR`` (Yale's Beinecke) without
    the file having to enumerate every library. That keeps the map maintainable —
    Yale, Harvard and Columbia between them have dozens of sub-units, and new ones
    appear without warning. Verified against this corpus: every ``BASE-`` child
    present is claimed by the base's owner, and ``_validate`` above re-checks that
    on every load.

    The hyphen is required, not optional, and that is the whole safety property. A
    bare prefix rule would make Penn's ``PU`` match Princeton's ``PUL`` and
    ``PULEA``, and Columbia's ``NNC`` match ``NNCORM`` — all real codes in this
    corpus belonging to other institutions.

    Expansion applies to MARC codes ONLY. OCLC symbols are not hierarchical: they
    are opaque strings from a different namespace (``AS#``, ``4H7``, ``YU#``), and
    a shared prefix between two of them means nothing. Expanding those would
    invent relationships that do not exist.
    """
    tests: list[str] = []
    for c in codes:
        tests.append(f"{column} = '{c.code}'")
        if c.is_marc:
            tests.append(f"{column} LIKE '{c.code}-%'")
    if not tests:
        return "false"
    return f"\n{indent}OR ".join(tests)


def org_case_sql(column: str, codes: tuple[Code, ...]) -> str:
    """A CASE mapping a normalized agency code to the POD institution that owns it."""
    by_org: dict[str, list[Code]] = {}
    for c in codes:
        by_org.setdefault(c.org, []).append(c)
    whens = [
        f"         WHEN {match_sql(column, tuple(owned), ' ' * 14)}\n"
        f"              THEN '{org}'"
        for org, owned in by_org.items()
    ]
    return "CASE\n" + "\n".join(whens) + "\n         END"
