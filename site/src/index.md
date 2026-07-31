# Overview

A window into the collective collection described by [POD](https://pod.stanford.edu/) —
what the participating institutions hold, where they overlap, and how their
metadata compares. Everything here is an **aggregate**: counts and distributions
compiled from the shared catalog, never individual records. See
[About the data](./data) for exactly what is published.

```js
const overview = FileAttachment("./data/overview.json").json();
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
  marginLeft: 90,
  height: 40 + overview.per_org.length * 28,
  x: {label: "records", grid: true, tickFormat: "~s"},
  y: {label: null},
  marks: [
    Plot.barX(overview.per_org, {
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
    institution: o.org,
    records: o.records,
    titles: o.titles,
    "last synced": o.last_sync ? o.last_sync.slice(0, 10) : "—",
  })),
  {sort: "records", reverse: true, rows: 20}
)
```
