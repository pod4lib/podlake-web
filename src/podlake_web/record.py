"""
Reconstitute a full MARC record from the tall/EAV ``records`` table.

This is a **record-level** helper for local, authorized exploration of a lake —
the deliberate opposite of :mod:`podlake_web.queries`, which only ever emits
aggregates. It is *not* used by the public site build; reconstructing a record
needs direct read access to the private lake.

    from podlake_web import record, source
    con = source.connect("…/podlake.ducklake")
    print(record.to_text(con, "stanford", "stanford:12345"))
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb

Connection = duckdb.DuckDBPyConnection


@dataclass
class Field:
    """One MARC field. Control fields (LDR, 00X) carry ``value`` and no
    subfields; data fields carry indicators and ordered ``(code, value)``
    subfields."""

    tag: str
    value: str | None = None
    ind1: str | None = None
    ind2: str | None = None
    subfields: list[tuple[str, str]] = field(default_factory=list)

    @property
    def is_control(self) -> bool:
        return not self.subfields


def reconstitute(con: Connection, org: str, pod_record_id: str) -> list[Field]:
    """
    Rebuild one record's fields, in original order, from its EAV rows. Fields
    are grouped by ``field_seq`` and subfields ordered by ``subfield_seq``, so
    repeated tags and subfield order are preserved. Returns [] for an unknown id.
    """
    rows = con.execute(
        "SELECT field_tag, field_seq, ind1, ind2, subfield_code, subfield_seq, value "
        "FROM records WHERE org = ? AND pod_record_id = ? "
        "ORDER BY field_seq, subfield_seq",
        [org, pod_record_id],
    ).fetchall()

    fields: dict[int, Field] = {}
    order: list[int] = []
    for tag, fseq, ind1, ind2, code, _sseq, value in rows:
        f = fields.get(fseq)
        if f is None:
            f = Field(tag=tag, ind1=ind1, ind2=ind2)
            fields[fseq] = f
            order.append(fseq)
        if code is None:
            f.value = value  # control field / leader
        else:
            f.subfields.append((code, value))
    return [fields[s] for s in order]


def to_text(con: Connection, org: str, pod_record_id: str) -> str:
    """Reconstitute a record and render it as human-readable MARC."""
    return format_marc(reconstitute(con, org, pod_record_id))


def format_marc(fields: list[Field]) -> str:
    """Render fields as MARC-ish text: ``245 10  $aTitle $bsubtitle``."""
    lines = []
    for f in fields:
        if f.is_control:
            lines.append(f"{f.tag}      {f.value or ''}")
        else:
            indicators = f"{f.ind1 or ' '}{f.ind2 or ' '}"
            body = " ".join(f"${code}{value}" for code, value in f.subfields)
            lines.append(f"{f.tag} {indicators}  {body}")
    return "\n".join(lines)
