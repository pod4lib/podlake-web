# Publication era

How each institution's holdings are distributed over time, by decade of
publication (from the MARC 008 date). Only plausible years (1450–2030) are
counted.

```js
const characterization = FileAttachment("./data/characterization.json").json();
```

```js
const orgs = characterization.publication_decade.per_org.map((r) => r.org).sort();
const org = view(Inputs.select(orgs, {label: "Institution", value: orgs[0]}));
```

```js
const decades = (characterization.publication_decade.per_org.find((r) => r.org === org) ?? {values: []})
  .values.filter((d) => typeof d.decade === "number")
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
