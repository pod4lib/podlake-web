# Overlap & rarity

How much of the collective collection is widely held versus rare? This is the
question behind shared-print, preservation, and "last copy" decisions: a title
held by only one institution is a candidate for preservation, while a title held
by many is a safe candidate to store or weed.

```js
const histogram = FileAttachment("./data/overlap_histogram.json").json();
const uniqueness = FileAttachment("./data/uniqueness.json").json();
const pairwise = FileAttachment("./data/overlap_pairwise.json").json();
```

## Works held by _N_ institutions

The rarity curve: how many distinct works are held by exactly one institution,
by two, and so on. The left end is the rare/unique material; the right end is
the widely-duplicated core.

```js
Plot.plot({
  marginLeft: 60,
  x: {label: "institutions holding the work", tickFormat: (d) => d, ticks: histogram.held_by.length},
  y: {label: "works", grid: true, tickFormat: "~s"},
  marks: [
    Plot.barY(histogram.held_by, {x: "institutions", y: "works", fill: "var(--theme-foreground-focus)", tip: true}),
    Plot.ruleY([0]),
  ],
})
```

## Works held by a single institution

Each institution's uniquely-held works — material that would disappear from the
consortium if that copy were lost.

```js
Plot.plot({
  marginLeft: 90,
  height: 40 + uniqueness.per_org.length * 28,
  x: {label: "uniquely-held works", grid: true, tickFormat: "~s"},
  y: {label: null},
  marks: [
    Plot.barX(uniqueness.per_org, {x: "unique_works", y: "org", fill: "var(--theme-foreground-focus)", sort: {y: "-x"}, tip: true}),
    Plot.ruleX([0]),
  ],
})
```

## Shared works between institutions

The number of works each pair of institutions both hold. The diagonal is each
institution's own total; off-diagonal cells are the overlap that drives
comparative collection analysis.

```js
const cells = (() => {
  const insts = pairwise.institutions;
  const shared = new Map(pairwise.pairs.map((p) => [`${p.a}|${p.b}`, p.shared]));
  const out = [];
  for (const a of insts)
    for (const b of insts) {
      let value;
      if (a === b) value = pairwise.works[a];
      else {
        const key = a < b ? `${a}|${b}` : `${b}|${a}`;
        value = shared.get(key) ?? 0;
      }
      out.push({a, b, value});
    }
  return out;
})();
```

```js
Plot.plot({
  marginLeft: 90,
  marginBottom: 90,
  aspectRatio: 1,
  color: {scheme: "blues", type: "sqrt", legend: true, label: "shared works"},
  x: {label: null, tickRotate: -30},
  y: {label: null},
  marks: [
    Plot.cell(cells, {x: "b", y: "a", fill: "value"}),
    Plot.text(cells, {x: "b", y: "a", text: (d) => d3.format(".2s")(d.value), fill: "white"}),
  ],
})
```
