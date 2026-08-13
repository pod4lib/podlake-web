# Completeness

Completeness is the share of records that carry a given descriptive MARC field.
It is a proxy for record quality, but really is not the same thing as quality.
So it is important not to read too much into these values. A record can be
complete but inaccurate, or sparse but perfectly fit for its material.

```js
import {provenance} from "./components/provenance.js";
import {coverageHeatmap} from "./components/heatmap.js";
const coverageFile = FileAttachment("./data/coverage.json");
const coverage = coverageFile.json();
```

```js
const fieldLabels = {
  isbn: "ISBN (020)",
  subjects: "Subjects (6xx)",
  author: "Author (1xx)",
  online: "Online access (856)",
  phys_desc: "Physical description (300)",
  lc_classification: "LC classification",
};
// coverage.json holds shares, not counts, so the count shown in each cell is
// derived — the same figure the chart is already coloring by, made concrete
const covPerOrg = coverage.per_org.map((o) => ({
  org: o.org,
  coverage: o.coverage,
  counts: Object.fromEntries(coverage.fields.map((f) => [f, Math.round(o.coverage[f] * o.records)])),
}));
// order fields by mean coverage across institutions (most-covered on top)
const fieldOrder = coverage.fields
  .map((f) => ({field: f, mean: d3.mean(coverage.per_org, (o) => o.coverage[f])}))
  .sort((a, b) => b.mean - a.mean)
  .map((d) => d.field);
```

## Completeness by field

Share of each institution's records that carry the field.

```js
coverageHeatmap(covPerOrg, fieldOrder, (f) => fieldLabels[f] ?? f, {
  marginLeft: 220,
  legendLabel: "records with the field",
  width,
})
```

```js
provenance({sql: coverage.sql, dataUrl: await coverageFile.url(), dataName: "coverage.json"})
```
