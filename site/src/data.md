# About the data

This dashboard is deliberately built to be **safe to publish**. The underlying
podlake DuckLake holds hundreds of millions of record-level rows and is **not**
public. What this site loads instead is a small set of pre-computed
**aggregates** — counts, distributions, and percentages — with no record
identifiers, work keys, titles, or raw field values.

```js
const manifest = FileAttachment("./data/manifest.json").json();
```

## What is published

```js
Inputs.table(manifest.artifacts, {
  columns: ["file", "description"],
  header: {file: "File", description: "What it contains"},
  width: {file: 220},
  rows: 20,
})
```

## How small values are protected

Even aggregates can leak information when a cell is tiny (for example, "one work
in a rare language uniquely held by one institution" could point at a specific
item). To prevent that:

- Long-tail categories are capped at the top **${manifest.suppression.top_n}**
  per institution; everything else is grouped into **Other**.
- Any category with fewer than **${manifest.suppression.threshold}** records is
  also folded into **Other**, so no small count is ever reported on its own.
- Totals and the **Other** bucket aggregate many records and reveal nothing
  about an individual one.

Aggregates were last rebuilt from the lake on
**${manifest.generated_at.slice(0, 10)}**.

## How it is built

A read-only extract step queries the private lake and writes these JSON files;
the static site reads only those files. Nothing here can reach back into the
lake. Deeper, record-level analysis (last-copy lists, text search, external
matching against HathiTrust or the public domain) is handled separately through
gated tools, not this public site.

## The queries behind these views

These are the actual DuckDB queries that produce the figures above — nothing
fancier than SQL over two tables. `record_meta` has one row per record (with its
consortial work key, `goldrush_key`); `records` is a tall table with one row per
MARC subfield (`org, pod_record_id, field_tag, field_seq, ind1, ind2,
subfield_code, subfield_seq, value`), so any field or subfield is a plain `WHERE`
clause. If they spark an idea for a view we're missing, that's exactly the point
— **coming soon**, you'll be able to run queries like these against the lake
right in your browser with DuckDB-WASM.

```js
import hljs from "npm:highlight.js/lib/core";
import sqlGrammar from "npm:highlight.js/lib/languages/sql";
hljs.registerLanguage("sql", sqlGrammar);
```

```js
const queries = FileAttachment("./data/queries.json").json();
```

```js
function sqlCard(q) {
  const code = document.createElement("code");
  code.className = "hljs language-sql";
  code.innerHTML = hljs.highlight(q.sql, {language: "sql"}).value;
  return html`<div class="card" style="margin: 1rem 0;">
    <h3 style="margin-top: 0;">${q.title}</h3>
    <p style="max-width: 640px;">${q.note}</p>
    <pre style="overflow-x: auto; font-size: 13px; line-height: 1.4;">${code}</pre>
  </div>`;
}
```

```js
html`${queries.queries.map(sqlCard)}`
```
