# Collections

Characterizing what each institution collects — by era, language, place of
publication, format, and subject. Pick an institution to explore its profile.
Long tails are grouped into **Other**, and any category too small to report is
folded into it as well.

```js
const characterization = FileAttachment("./data/characterization.json").json();
const overview = FileAttachment("./data/overview.json").json();
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
const forOrg = (section) =>
  (characterization[section].per_org.find((r) => r.org === org) ?? {values: []}).values;
```

## Publication era

Records by decade of publication (from the MARC 008 date). Only plausible years
(1450–2030) are counted.

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

<div class="grid grid-cols-2">
<div>

## Top languages

```js
Plot.plot({
  marginLeft: 60,
  height: 300,
  x: {label: "records", tickFormat: "~s"},
  y: {label: null},
  marks: [
    Plot.barX(forOrg("language"), {x: "count", y: "category", sort: {y: "-x", limit: 12}, fill: "var(--theme-foreground-focus)", tip: true}),
    Plot.ruleX([0]),
  ],
})
```

</div>
<div>

## Format (MARC record type)

```js
Plot.plot({
  marginLeft: 120,
  height: 300,
  x: {label: "records", tickFormat: "~s"},
  y: {label: null},
  marks: [
    Plot.barX(forOrg("record_type").map((d) => ({...d, category: recordTypeLabel(d.category)})), {
      x: "count",
      y: "category",
      sort: {y: "-x", limit: 12},
      fill: "var(--theme-foreground-focus)",
      tip: true,
    }),
    Plot.ruleX([0]),
  ],
})
```

</div>
</div>

## Top subjects

The most common subject headings (MARC 650 $a) in this institution's records.

```js
Plot.plot({
  marginLeft: 220,
  height: 40 + Math.min(forOrg("subject").length, 25) * 22,
  x: {label: "records", grid: true, tickFormat: "~s"},
  y: {label: null},
  marks: [
    Plot.barX(forOrg("subject"), {x: "count", y: "category", sort: {y: "-x", limit: 25}, fill: "var(--theme-foreground-focus)", tip: true}),
    Plot.ruleX([0]),
  ],
})
```

```js
// MARC leader position 06 (type of record) — the common values.
function recordTypeLabel(code) {
  const labels = {
    a: "Language material",
    c: "Notated music",
    d: "Manuscript music",
    e: "Cartographic",
    f: "Manuscript cartographic",
    g: "Projected medium",
    i: "Nonmusical sound",
    j: "Musical sound",
    k: "Two-dimensional image",
    m: "Computer file",
    o: "Kit",
    p: "Mixed material",
    r: "Three-dimensional object",
    t: "Manuscript language material",
    Other: "Other",
  };
  return labels[code] ?? code;
}
```
