# Publication era

How are each institution's holdings are distributed over time? This chart
visualizes the decade of publication (from the MARC 008 date). Only plausible
years (1450–2030) are counted.

```js
import {provenance} from "./components/provenance.js";
const decadeFile = FileAttachment("./data/publication_decade.json");
const decadeData = decadeFile.json();
```

```js
const orgs = decadeData.per_org.map((r) => r.org).sort();
const org = view(Inputs.select(orgs, {label: "Institution", value: orgs[0]}));
```

```js
const decades = (decadeData.per_org.find((r) => r.org === org) ?? {values: []})
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

```js
provenance({sql: decadeData.sql, dataUrl: await decadeFile.url(), dataName: "publication_decade.json"})
```
