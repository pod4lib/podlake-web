# Overlap & rarity

How much of the collective collection is widely held versus rare? This is the
question behind shared-print, preservation, and "last copy" decisions: a title
held by only one institution is a candidate for preservation, while a title held
by many is a safe candidate to store or weed.

<div class="note">

**How records are grouped into titles.** Each institution contributes many
individual MARC records for the same book. To count *titles* rather than raw
records, records are collapsed using the [Gold Rush match
key](https://github.com/co-alliance/coalliance-matchkey) developed by the
[Colorado Alliance of Research Libraries](https://coalliance.org/). The key is
a normalized fingerprint derived from a record's title, author, publication
year, edition, publisher, pagination, material type, and carrier (print vs.
electronic). Records that generate the same key are treated as one title. The
key is roughly *manifestation*-level: because it captures edition and carrier,
a print book and its e-book edition count as two distinct titles.

</div>

```js
import {provenance} from "./components/provenance.js";
import {countHeatmap} from "./components/heatmap.js";
import {orgLabel} from "./components/marc.js";
const histogramFile = FileAttachment("./data/overlap_histogram.json");
const histogram = histogramFile.json();
const uniquenessFile = FileAttachment("./data/uniqueness.json");
const uniqueness = uniquenessFile.json();
const pairwiseFile = FileAttachment("./data/overlap_pairwise.json");
const pairwise = pairwiseFile.json();
```

## Titles held by _N_ institutions

The rarity curve: how many distinct titles are held by exactly one institution,
by two, and so on. The left end is the rare/unique material; the right end is
the widely-duplicated core.

```js
Plot.plot({
  width,
  marginLeft: 60,
  x: {label: "institutions holding the title", tickFormat: (d) => d, ticks: histogram.held_by.length},
  y: {label: "titles", grid: true, tickFormat: "~s"},
  marks: [
    Plot.barY(histogram.held_by, {x: "institutions", y: "titles", fill: "var(--theme-foreground-focus)", tip: true}),
    Plot.ruleY([0]),
  ],
})
```

```js
provenance({sql: histogram.sql, dataUrl: await histogramFile.url(), dataName: "overlap_histogram.json"})
```

## Titles held by a single institution

Each institution's uniquely-held titles. This is material that would disappear
from the consortium if that copy were lost.

```js
Plot.plot({
  width,
  marginLeft: 90,
  height: 40 + uniqueness.per_org.length * 28,
  x: {label: "uniquely-held titles", grid: true, tickFormat: "~s"},
  y: {label: null},
  marks: [
    Plot.barX(uniqueness.per_org.map((o) => ({...o, org: orgLabel(o.org)})), {x: "unique_titles", y: "org", fill: "var(--theme-foreground-focus)", sort: {y: "-x"}, tip: true}),
    Plot.ruleX([0]),
  ],
})
```

```js
provenance({sql: uniqueness.sql, dataUrl: await uniquenessFile.url(), dataName: "uniqueness.json"})
```

## Which collections are most alike

Which pairs of libraries actually resemble each other? **How you measure decides
the answer**, so the control below switches between three measures of the same
underlying numbers. They disagree sharply, and the disagreement is the point.

- **Shared titles** is the raw count of titles both libraries hold. It is mostly a
  ranking of *size* — the largest collections top it because they are largest, and
  Harvard appears in six of the eight highest pairs.
- **Jaccard similarity** divides that count by the two libraries' combined titles,
  so scale drops out and what is left is how far their collecting coincides. Harvard
  leaves the top eight entirely; same-sized peers take over.
- **Containment** asks a different question in a different direction: what share of
  *this* library's titles the other one also holds. It is not symmetric, and it
  favours the small library in a lopsided pair — which is exactly what a shared-print
  or last-copy conversation needs to know.

```js
const measure = view(
  Inputs.select(
    new Map([
      ["Jaccard similarity — shared ÷ combined titles", "jaccard"],
      ["Containment — share of this library's titles the other also holds", "containment"],
      ["Shared titles — raw count", "shared"],
    ]),
    {label: "Measure", value: "jaccard"}
  )
);
```

```js
const titles = pairwise.titles;
// shared is published once per unordered pair; look it up either way round
const sharedTitles = (() => {
  const m = new Map(pairwise.pairs.map((p) => [`${p.a}|${p.b}`, p.shared]));
  return (a, b) => (a === b ? titles[a] : m.get(a < b ? `${a}|${b}` : `${b}|${a}`) ?? 0);
})();
const MEASURES = {
  jaccard: {
    // symmetric: the union is the same set whichever way round you read the pair
    directional: false,
    of: (a, b) => sharedTitles(a, b) / (titles[a] + titles[b] - sharedTitles(a, b)),
    format: (v) => (v == null ? "" : d3.format(".1%")(v)),
    tickFormat: ".0%",
    colorLabel: "shared ÷ combined titles",
    axisLabel: "Jaccard similarity",
  },
  containment: {
    // directional: a's share of a is not b's share of b, so both orderings appear
    directional: true,
    of: (a, b) => sharedTitles(a, b) / titles[a],
    format: (v) => (v == null ? "" : d3.format(".0%")(v)),
    tickFormat: ".0%",
    colorLabel: "share of this library's titles",
    axisLabel: "share of the first library's titles also held by the second",
  },
  shared: {
    directional: false,
    of: (a, b) => sharedTitles(a, b),
    format: (v) => (v == null ? "" : d3.format(",")(v)),
    tickFormat: "~s",
    colorLabel: "shared titles",
    axisLabel: "shared titles",
  },
};
const m = MEASURES[measure];
```

```js
// every pair, ordered both ways only when the measure is directional
const rankedPairs = (() => {
  const insts = pairwise.institutions;
  const out = [];
  for (const a of insts)
    for (const b of insts) {
      if (a === b) continue;
      if (!m.directional && b < a) continue; // one row per unordered pair
      out.push({
        pair: m.directional ? `${orgLabel(a)} → ${orgLabel(b)}` : `${orgLabel(a)} · ${orgLabel(b)}`,
        value: m.of(a, b),
        shared: sharedTitles(a, b),
      });
    }
  return out.sort((x, y) => y.value - x.value).slice(0, 15);
})();
```

The fifteen closest pairs on the measure selected above.

```js
Plot.plot({
  width,
  marginLeft: 210,
  // room for the value label that sits past the end of the longest bar — the top
  // bar reaches the axis maximum, so without this its label is clipped
  marginRight: 60,
  height: 55 + rankedPairs.length * 30,
  // zero-based deliberately: these values are genuinely small and close together,
  // and a clipped axis would turn a few points of difference into apparent structure
  x: {label: m.axisLabel, grid: true, tickFormat: m.tickFormat, domain: [0, d3.max(rankedPairs, (d) => d.value)]},
  y: {label: null, domain: rankedPairs.map((d) => d.pair)},
  marks: [
    Plot.barX(rankedPairs, {
      x: "value",
      y: "pair",
      fill: "var(--theme-foreground-focus)",
      fillOpacity: 0.8,
      channels: {shared: {value: "shared", label: "shared titles"}},
      tip: {format: {x: m.tickFormat, y: true, shared: ","}},
    }),
    Plot.text(rankedPairs, {x: "value", y: "pair", text: (d) => m.format(d.value), dx: 4, textAnchor: "start"}),
    Plot.ruleX([0]),
  ],
})
```

Every pair, as a matrix. With **Containment** selected the matrix is asymmetric —
read a row across for what share of that library's titles each other library also
holds. The diagonal is blank throughout: a collection contains all of itself, and
plotting that would flatten every other cell.

```js
// shaped as a {categories, institutions, matrix} dimension so it can share the
// heatmap component, and so its cells match every other heatmap on the site
// rather than being forced square by an aspectRatio
const pairDimension = (() => {
  const insts = pairwise.institutions;
  const matrix = {};
  // countHeatmap indexes matrix[x][y] — `institutions` is the x axis and
  // `categories` the y — so the OUTER key is the column and the inner one the row.
  // Containment is normalised by the row library, so that the prose instruction
  // "read a row across" is literally what the cells do; getting these two the
  // wrong way round transposes the matrix and silently inverts every asymmetric
  // reading (a small library's high containment shows up against it instead).
  for (const col of insts) {
    matrix[col] = {};
    for (const row of insts) matrix[col][row] = col === row ? null : m.of(row, col);
  }
  return {categories: insts, institutions: insts, matrix};
})();
```

```js
// linear rather than the component's default sqrt: every cell is the same measure
// on one scale, and the scale auto-fits the data — Jaccard peaks near 20%, so a
// 0–100% ramp would render the whole matrix near-white
countHeatmap(pairDimension, orgLabel, {
  marginLeft: 90,
  colorLabel: m.colorLabel,
  colorType: "linear",
  valueFormat: m.format,
  colorTickFormat: m.tickFormat,
  // only the asymmetric measure needs the axes spelled out; for the symmetric
  // ones which axis is which makes no difference to the reading
  xLabel: m.directional ? "also held by →" : null,
  yLabel: m.directional ? "↓ share of this library's titles" : null,
  width,
})
```

<div class="note">

**Two things limit how far "alike" can be pushed.** Jaccard peaks at about 20%
here, because 29.7M titles are held by exactly one institution — the collective
collection is mostly long tail, so even the closest pair overlaps on a fifth of
their combined holdings. And because the Gold Rush key is roughly
manifestation-level, this measures *edition-level* co-holding: two libraries buying
the same works in different editions or formats read as dissimilar. Treat it as a
floor on how alike two collections are.

</div>

```js
provenance({sql: pairwise.sql, dataUrl: await pairwiseFile.url(), dataName: "overlap_pairwise.json"})
```
