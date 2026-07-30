# Metadata quality

How completely is each institution's collection described? This scorecard shows
the share of records carrying selected MARC fields — a proxy for how
discoverable and reusable the metadata is, and a way to spot enrichment
opportunities across the consortium.

```js
const coverage = FileAttachment("./data/coverage.json").json();
```

```js
const fieldLabels = {
  isbn: "ISBN (020)",
  subjects: "Subjects (6xx)",
  author: "Author (1xx)",
  online: "Online access (856)",
  phys_desc: "Physical description (300)",
  classification: "Classification (050/082/090)",
};
const rows = coverage.per_org.flatMap((o) =>
  coverage.fields.map((f) => ({
    institution: o.org,
    field: fieldLabels[f] ?? f,
    coverage: o.coverage[f],
  }))
);
```

## Coverage by field

```js
Plot.plot({
  marginLeft: 220,
  height: 60 + coverage.fields.length * 42,
  x: {label: "records with the field", percent: true, domain: [0, 100], grid: true},
  y: {label: null},
  color: {legend: true, label: "institution", scheme: "category10"},
  fy: {label: null},
  marks: [
    Plot.barX(rows, {
      x: (d) => d.coverage * 100,
      y: "institution",
      fy: "field",
      fill: "institution",
      tip: true,
    }),
    Plot.ruleX([0]),
  ],
})
```

## Scorecard

```js
Inputs.table(
  coverage.per_org.map((o) => ({
    institution: o.org,
    ...Object.fromEntries(
      coverage.fields.map((f) => [fieldLabels[f] ?? f, o.coverage[f]])
    ),
  })),
  {
    format: Object.fromEntries(
      coverage.fields.map((f) => [fieldLabels[f] ?? f, (v) => d3.format(".0%")(v)])
    ),
  }
)
```
