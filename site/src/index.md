# Overview

The podlake site site provides a view into the MARC records collected as part
of the [POD](https://pod.stanford.edu/) project. It provides some initial
insight into what the participating institutions hold, where they overlap, and
how their metadata compares.

But the true goal of the site is to illustrate the types of analyses that can
be done with [the data](./data). Each visualization has a "Behind this chart"
section which contains the SQL query that was used to query the project's data
lake, which POD members have full access to.


```js
import {provenance} from "./components/provenance.js";
import {orgLabel} from "./components/marc.js";
const overviewFile = FileAttachment("./data/overview.json");
const overview = overviewFile.json();
```

<div class="grid grid-cols-3">
  <div class="card">
    <h2>Titles</h2>
    <span class="big">${d3.format(",")(overview.totals.titles)}</span>
    distinct titles (grouped by Gold Rush key)
  </div>
  <div class="card">
    <h2>Records</h2>
    <span class="big">${d3.format(",")(overview.totals.records)}</span>
    MARC bibliographic records
  </div>
  <div class="card">
    <h2>Institutions</h2>
    <span class="big">${overview.totals.institutions}</span>
    contributing partners
  </div>
</div>

## Records by institution

```js
Plot.plot({
  width,
  marginLeft: 90,
  height: 40 + overview.per_org.length * 28,
  x: {label: "records", grid: true, tickFormat: "~s"},
  y: {label: null},
  marks: [
    Plot.barX(overview.per_org.map((o) => ({...o, org: orgLabel(o.org)})), {
      x: "records",
      y: "org",
      fill: "var(--theme-foreground-focus)",
      sort: {y: "-x"},
      tip: true,
    }),
    Plot.ruleX([0]),
  ],
})
```

```js
Inputs.table(
  overview.per_org.map((o) => ({
    institution: orgLabel(o.org),
    records: o.records,
    titles: o.titles,
    "last synced": o.last_sync ? o.last_sync.slice(0, 10) : "—",
  })),
  {sort: "records", reverse: true, rows: 20}
)
```

```js
provenance({sql: overview.sql, dataUrl: await overviewFile.url(), dataName: "overview.json"})
```
