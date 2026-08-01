# Collections

Characterizing what each institution collects. **Language**, **place of
publication**, and **format** are compared across all institutions as a share of
each one's records — so collection size doesn't dominate — with the selected
institution's column outlined. **Publication era** and **subjects** profile the
selected institution on its own. Only the most common values are shown; small
cells are suppressed.

```js
import {recordTypeLabel, languageLabel, placeLabel, lcClassLabel} from "./components/marc.js";
const characterization = FileAttachment("./data/characterization.json").json();
const overview = FileAttachment("./data/overview.json").json();
const comparison = FileAttachment("./data/comparison.json").json();
```

```js
const org = view(
  Inputs.select(
    overview.per_org.map((o) => o.org).sort(),
    {label: "Institution", value: overview.per_org.map((o) => o.org).sort()[0]}
  )
);
```

```js
// Per-institution values for a characterization section (era, subjects).
const forOrg = (section) =>
  (characterization[section].per_org.find((r) => r.org === org) ?? {values: []}).values;

// Cross-institution comparison rows: {org, category (labeled), share, count}.
function compareRows(dim, label) {
  const d = comparison.dimensions[dim];
  const rows = [];
  for (const o of d.institutions)
    for (const c of d.categories) {
      const n = d.matrix[o][c];
      rows.push({org: o, category: label(c), share: n == null ? null : n / d.totals[o], count: n});
    }
  // categories arrive sorted by consortium total (largest first → top of the y axis)
  return {rows, categories: d.categories.map(label), institutions: d.institutions};
}

// Share heatmap (category × institution) for a comparison dimension, with the
// `selected` institution's column outlined. `selected` is passed in (not closed
// over) so the calling cell re-renders when the institution changes.
function shareHeatmap(dim, label, selected, {marginLeft = 155} = {}) {
  const {rows, categories, institutions} = compareRows(dim, label);
  const maxShare = d3.max(rows, (d) => d.share ?? 0);
  return Plot.plot({
    marginLeft,
    marginBottom: 60,
    height: 55 + categories.length * 34,
    x: {label: null, domain: institutions, tickRotate: -30},
    y: {label: null, domain: categories},
    color: {
      scheme: "blues",
      legend: true,
      label: "share of records",
      domain: [0, maxShare],
      tickFormat: ".0%",
      // suppressed cells (too few to report) — a faint tint, not solid black
      unknown: "color-mix(in srgb, var(--theme-foreground) 12%, transparent)",
    },
    marks: [
      Plot.cell(rows, {x: "org", y: "category", fill: "share", tip: true}),
      Plot.text(rows, {
        x: "org",
        y: "category",
        text: (d) => (d.share == null ? "" : (d.share * 100).toFixed(0) + "%"),
        fill: (d) => (d.share > maxShare * 0.55 ? "white" : "black"),
        fontSize: 12,
      }),
      Plot.cell(
        rows.filter((d) => d.org === selected),
        {x: "org", y: "category", fill: "none", stroke: "var(--theme-foreground)", strokeWidth: 2}
      ),
    ],
  });
}
```

## Publication era

Records by decade of publication (from the MARC 008 date) for **${org}**. Only
plausible years (1450–2030) are counted.

```js
const decades = forOrg("publication_decade")
  .filter((d) => typeof d.decade === "number")
  .sort((a, b) => a.decade - b.decade);
```

```js
Plot.plot({
  marginLeft: 60,
  x: {label: "decade", tickFormat: "d"},
  y: {label: "records", grid: true, tickFormat: "~s"},
  marks: [
    Plot.areaY(decades, {x: "decade", y: "count", fill: "var(--theme-foreground-focus)", fillOpacity: 0.3, curve: "step"}),
    Plot.lineY(decades, {x: "decade", y: "count", stroke: "var(--theme-foreground-focus)", curve: "step"}),
    Plot.ruleY([0]),
  ],
})
```

## Languages

Share of each institution's records in each of the consortium's most common
languages.

```js
shareHeatmap("language", languageLabel, org)
```

## Place of publication

```js
shareHeatmap("country", placeLabel, org)
```

## Format (MARC record type)

```js
shareHeatmap("record_type", recordTypeLabel, org, {marginLeft: 205})
```

## LC classification

Share of each institution's call-numbered records (MARC 050 / 090) in each
Library of Congress class — a shared, controlled scheme, so it compares cleanly
across institutions. Only records carrying an LC call number are counted.

```js
shareHeatmap("classification", lcClassLabel, org, {marginLeft: 210})
```
