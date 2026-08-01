# Completeness

Completeness is the share of records that carry a given descriptive MARC field.
It is a proxy for record quality, but really is not the same thing as quality.
So it is important not to read too much into these values. A record can be
complete but inaccurate, or sparse but perfectly fit for its material.

```js
import {provenance} from "./components/provenance.js";
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
const covRows = coverage.per_org.flatMap((o) =>
  coverage.fields.map((f) => ({
    org: o.org,
    field: fieldLabels[f] ?? f,
    coverage: o.coverage[f],
  }))
);
// order fields by mean coverage across institutions (most-covered on top)
const fieldOrder = coverage.fields
  .map((f) => ({label: fieldLabels[f] ?? f, mean: d3.mean(coverage.per_org, (o) => o.coverage[f])}))
  .sort((a, b) => b.mean - a.mean)
  .map((d) => d.label);
```

## Completeness by field

Share of each institution's records that carry the field.

```js
Plot.plot({
  marginLeft: 220,
  marginBottom: 60,
  height: 55 + fieldOrder.length * 40,
  x: {label: null, tickRotate: -30},
  y: {label: null, domain: fieldOrder},
  color: {scheme: "blues", legend: true, label: "records with the field", domain: [0, 1], tickFormat: ".0%"},
  marks: [
    Plot.cell(covRows, {x: "org", y: "field", fill: "coverage", tip: true}),
    Plot.text(covRows, {
      x: "org",
      y: "field",
      text: (d) => d3.format(".0%")(d.coverage),
      fill: (d) => (d.coverage > 0.55 ? "white" : "black"),
      fontSize: 12,
    }),
  ],
})
```

```js
provenance({sql: coverage.sql, dataUrl: await coverageFile.url(), dataName: "coverage.json"})
```
