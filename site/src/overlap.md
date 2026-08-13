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

## Shared titles between institutions

The number of titles each pair of institutions both hold. The diagonal is left
blank: an institution's own total sits on a far larger scale and would flatten
the contrast between the pairwise cells.

```js
// shaped as a {categories, institutions, matrix} dimension so it can share the
// heatmap component, and so its cells match every other heatmap on the site
// rather than being forced square by an aspectRatio
const sharedDimension = (() => {
  const insts = pairwise.institutions;
  const shared = new Map(pairwise.pairs.map((p) => [`${p.a}|${p.b}`, p.shared]));
  const matrix = {};
  for (const b of insts) {
    matrix[b] = {};
    for (const a of insts) {
      // the diagonal is the org's own total, an order of magnitude larger; null
      // renders as the same faint tint used for suppressed cells elsewhere
      const key = a < b ? `${a}|${b}` : `${b}|${a}`;
      matrix[b][a] = a === b ? null : shared.get(key) ?? 0;
    }
  }
  return {categories: insts, institutions: insts, matrix};
})();
```

```js
// linear rather than the component's default sqrt: these are all counts of the
// same thing on one comparable scale, so the raw contrast is the story
countHeatmap(sharedDimension, orgLabel, {
  marginLeft: 90,
  colorLabel: "shared titles",
  colorType: "linear",
  width,
})
```

```js
provenance({sql: pairwise.sql, dataUrl: await pairwiseFile.url(), dataName: "overlap_pairwise.json"})
```
