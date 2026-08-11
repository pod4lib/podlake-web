# Source of cataloging

Every other view here asks what is *in* the collections. This one asks who made the
**metadata**, from MARC `040` — the field that records which agency did the original
cataloging (`$a`) and which agencies have modified the record since (`$d`).

Read the numbers as **attribution practice**, not as cataloging labor. Three things
matter before anything below means much:

- **"This institution" undercounts original cataloging.** A member cataloging in
  OCLC Connexion often ends up with someone else's code in `$a`. And members
  self-attribute inconsistently: Duke's MARC Organization Code `NcD` appears on
  about 1,700 of its records while its OCLC symbol `NDD` appears on 279,000, and
  Harvard spreads its work across a dozen per-library symbols (`HLS`, `HVL`,
  `HUL`, `HMS`…) plus the `MH` family. The mapping from codes to members is
  **curated by hand and has not yet been ratified by POD** — see
  [the institution code mapping](./data#the-institution-code-mapping) for the codes
  we attribute, the ones we only *infer* (reported separately as "inferred"
  everywhere below), and the ones we judged too uncertain to attribute at all.
- **This field says nothing about how a record was *distributed*.** `OCoLC` appears
  as the original agency on 26,780 records out of 48 million (0.06%), so there is no
  "OCLC" category below — a record that came through WorldCat is credited to the
  *library* that made it, via that library's OCLC symbol. That is not evidence that
  OCLC is uninvolved: between 66% and 98% of these records carry an `(OCoLC)`
  control number in MARC `035`, which is where the distribution channel is actually
  recorded. Authorship and channel are different questions, and this page answers
  only the first.
- **About 1.6% of `$a` values are free text, not codes** — `Harvard Univ. Library`,
  `Princeton Univ. Libr.`, `RETROCON/NYGG (COO)`. Those land in "some other agency"
  even when they name a member, so they slightly depress "this institution".
- **`$d` practice varies enormously.** Between 12% and 45% of records carry no
  modifying agency at all depending on the institution, which says more about each
  ILS's habits than about how much the records have been edited.

```js
import {orgLabel, agencyLabel, sourceBucketLabel, modDepthLabel} from "./components/marc.js";
import {shareHeatmap} from "./components/heatmap.js";
import {provenance} from "./components/provenance.js";
const catFile = FileAttachment("./data/cataloging_source.json");
const cat = catFile.json();
```

```js
// Semantic, not decorative: blues for outside authorities, greens for cataloging
// done inside the consortium (darkest = confirmed as this library's own, lighter =
// inferred, lightest = another member), amber for the commercial/other long tail,
// grey for absent.
const BUCKET_COLOR = {
  lc: "#1d4e89",
  self: "#1f5f43",
  self_inferred: "#4f9c76",
  pod: "#a8d5bd",
  other: "#d9a03c",
  none: "#9aa0a6",
};
const institutions = cat.per_org.map((o) => orgLabel(o.org));
const mixRows = cat.per_org.flatMap((o) =>
  cat.buckets.map((b) => ({
    org: orgLabel(o.org),
    key: b, // raw bucket key, kept for the color lookup
    bucket: sourceBucketLabel(b),
    share: o.mix[b],
    records: o.counts[b],
  }))
);
```

## Where each library's records come from

Share of every record the institution holds, by the agency credited in `040 $a`.
"No 040 field" is kept visible rather than dropped, so each bar is the whole
collection. The dominant band almost everywhere is **some other agency** — mostly
commercial suppliers and other libraries' original cataloging, broken out in the
next chart.

```js
Plot.plot({
  marginLeft: 90,
  marginBottom: 40,
  height: 60 + institutions.length * 44,
  x: {label: "share of records", grid: true, domain: [0, 1], tickFormat: ".0%"},
  y: {label: null, domain: institutions},
  color: {
    domain: cat.buckets.map(sourceBucketLabel),
    range: cat.buckets.map((b) => BUCKET_COLOR[b]),
    legend: true,
  },
  marks: [
    Plot.barX(mixRows, {
      x: "share",
      y: "org",
      fill: "bucket",
      channels: {records: {value: "records", label: "records"}},
      tip: {format: {x: ".1%", fill: true, y: true, records: ","}},
    }),
    // stackX so the label sits at the midpoint of its own segment, not the
    // cumulative total; only wide-enough segments get a label
    Plot.text(
      mixRows,
      Plot.stackX({
        x: "share",
        y: "org",
        text: (d) => (d.share >= 0.07 ? (d.share * 100).toFixed(0) + "%" : ""),
        // pick label contrast from the segment's own lightness rather than
        // assuming white works — the "another member" and "no agency" fills are pale
        fill: (d) => (d3.lab(BUCKET_COLOR[d.key]).l > 60 ? "black" : "white"),
        fontSize: 11,
      })
    ),
    Plot.ruleX([0]),
  ],
})
```

```js
provenance({sql: cat.sql, dataUrl: await catFile.url(), dataName: "cataloging_source.json"})
```

## How that mix has changed

The bar above is the whole of each collection at once. Cutting it by the year each
record entered the catalog (`008/00-05`) shows the mix moving. Panels keep their own
vertical scale, so a panel's height is that library's intake curve and the bands are
its composition.

<div class="note">

**The Library of Congress band is not a picture of LC's cataloging.** The horizontal
axis dates the record in the *holding* library's system, so an LC record cataloged in
1975 and loaded by Penn in 1986 sits in 1986. Read the blue band as "LC copy arriving
here", never as "LC's output that year" — this data has no clock for that. (The one
that would is `010 $a`: an LCCN encodes the year LC assigned it. Different field,
different chart.) The same caveat applies to the "another POD member" band.

</div>

```js
import {html} from "npm:htl";
const lastFullYear = cat.timeline.partial_year - 1;
const mixOrgs = cat.timeline.per_org.map((o) => orgLabel(o.org));
const mixCols = mixOrgs.length <= 6 ? 2 : mixOrgs.length <= 12 ? 3 : 4;
const mixYearRows = d3.group(
  cat.timeline.per_org.flatMap((o) =>
    o.values
      // the snapshot year is only partly harvested, so its drop is an artifact
      .filter((v) => v.year <= lastFullYear)
      .flatMap((v) =>
        cat.buckets.map((b) => ({
          org: orgLabel(o.org),
          year: v.year,
          bucket: sourceBucketLabel(b),
          n: v.counts[b],
        }))
      )
  ),
  (d) => d.org
);
const mixYearColor = {
  domain: cat.buckets.map(sourceBucketLabel),
  range: cat.buckets.map((b) => BUCKET_COLOR[b]),
};
```

```js
Plot.legend({color: mixYearColor})
```

```js
html`<div class=${`grid grid-cols-${mixCols}`}>${mixOrgs.map(
  (org) => html`<div class="card">${Plot.plot({
    title: org,
    width: Math.max(230, Math.floor(width / mixCols) - 60),
    height: 170,
    marginLeft: 52,
    x: {label: null, tickFormat: "d", grid: true, domain: [1966, lastFullYear]},
    y: {label: null, grid: true, tickFormat: "~s"},
    color: mixYearColor,
    marks: [
      Plot.areaY(mixYearRows.get(org), {
        x: "year",
        y: "n",
        fill: "bucket",
        // stack in the published bucket order rather than by magnitude, so the
        // bands sit in the same position in every panel and can be compared
        order: cat.buckets.map(sourceBucketLabel),
        tip: {format: {x: "d", y: ",", fill: true, org: false}},
      }),
      Plot.ruleY([0]),
    ],
  })}</div>`
)}</div>`
```

The LC band is the one trend all six libraries share: **the Library of Congress
supplied between a third and two-thirds of everything these catalogs took in during
the 1970s, and between 2% and 14% of what they took in since 2020.**

| Share of intake credited to LC | 1970s | 1990s | 2020–25 |
| --- | --- | --- | --- |
| Brown | 62% | 35% | 14% |
| Duke | 56% | 30% | 2% |
| Harvard | 59% | 18% | 13% |
| Penn | 38% | 25% | 8% |
| Princeton | 67% | 32% | 13% |
| Stanford | 34% | 24% | 9% |

The amber band takes up the slack almost exactly: "some other agency" runs 21–37% of
intake in the 1970s and 50–80% since 2020 — the shift from a catalog built on a single
national backbone to one assembled from many suppliers. Again, that is a statement
about **what these libraries loaded**, not about how much cataloging LC did.

The grey band moves for a different reason: records carrying no `040 $a` at all. It is
erratic rather than trending — Stanford's runs 37% in the 1970s and effectively 0%
since 2010, while Duke's goes the other way, 3% in the 1980s to 44% since 2020, the
signature of large vendor loads with no cataloging-source field.

```js
provenance({sql: cat.timeline.sql, dataUrl: await catFile.url(), dataName: "cataloging_source.json"})
```

## Which agencies those are

There are 25,217 distinct agency codes in `040 $a`, so this has to be a selection.
It is the **union of each institution's own twelve most common** codes, not a
consortium-wide top-N — because ranking globally drops a small library's principal
agencies. Brown's own `RBN` and `RPB` are its #2 and #3 agencies, together 12% of
its records, and neither makes a consortium top-20; nor do Harvard's `HVL`
(270,000 records) or `HUL` (168,000), because Harvard's work is spread thinly
across a dozen symbols. Unioning also means the axis keeps working as POD grows:
each new member brings its own rows rather than competing for shared ones.

Cells are that institution's share of its records carrying an `$a` — **of all of
them, not just the rows shown** — so the columns deliberately sum to 55–65% rather
than 100%: the remainder is the 25,000-code tail. A code that is one library's
mainstay and absent elsewhere reads as a single bright cell in a row of real zeros. The Library of Congress is the largest single source everywhere.
After that the pattern is mostly **local**: each library's own symbol lights up its
own column (`CSt` at Stanford, `NjP` at Princeton, `PU` at Penn, `HLS` at Harvard,
`NDD` at Duke, `RBN` at Brown), and so do the vendors it buys from — ProQuest at
Duke, LexisNexis at Penn, Naxos at Penn and Stanford, Adam Matthew at Duke and Penn.

Codes are shown uppercased because that is the normal form the extract compares
on; unrecognized codes pass through raw rather than being dropped.

```js
shareHeatmap(cat, "agency", agencyLabel, {
  marginLeft: 300,
  legendLabel: "share of records with an 040 $a",
  rowHeight: 30,
})
```

```js
provenance({sql: cat.dimensions.agency.sql, dataUrl: await catFile.url(), dataName: "cataloging_source.json"})
```

## Cataloging done inside the consortium

Restricting `040 $a` to the six members' own codes gives the flow of cataloging
*between* POD libraries. First, how much of each library's collection is credited
to itself. The lighter part of each bar is attribution we **inferred** rather than
confirmed — almost all of it Harvard's, where it is the difference between a 8%
and a 15% self-cataloging rate:

```js
Plot.plot({
  marginLeft: 90,
  marginBottom: 40,
  height: 55 + cat.per_org.length * 30,
  x: {label: "share of records credited to this institution", grid: true, tickFormat: ".0%"},
  y: {label: null, domain: [...cat.per_org]
        .sort((a, b) => (b.mix.self + b.mix.self_inferred) - (a.mix.self + a.mix.self_inferred))
        .map((o) => orgLabel(o.org))},
  color: {
    domain: ["self", "self_inferred"].map(sourceBucketLabel),
    range: [BUCKET_COLOR.self, BUCKET_COLOR.self_inferred],
    legend: true,
  },
  marks: [
    Plot.barX(
      cat.per_org.flatMap((o) =>
        ["self", "self_inferred"].map((b) => ({
          org: orgLabel(o.org),
          bucket: sourceBucketLabel(b),
          share: o.mix[b],
          records: o.counts[b],
        }))
      ),
      {
        x: "share",
        y: "org",
        fill: "bucket",
        channels: {records: {value: "records", label: "records"}},
        tip: {format: {x: ".1%", fill: true, y: true, records: ","}},
      }
    ),
    Plot.ruleX([0]),
  ],
})
```

Then whose cataloging each library *holds*. This matrix is **not symmetric** — the
number of Harvard-cataloged records at Princeton is a different figure from the
number of Princeton-cataloged records at Harvard, and that asymmetry is the whole
point. Read a column down to see who supplies a library, and a row across to see
where a library's cataloging travels. The diagonal (self-cataloging, shown above)
is left out because it is an order of magnitude larger and would flatten
everything else. Unlike the bar above, this matrix counts confirmed and inferred
attributions together — it is about the direction cataloging travels, and dropping
a probably-correct attribution would understate a member's outflow.

```js
const flowCells = (() => {
  const d = cat.dimensions.flow;
  const out = [];
  for (const holder of d.institutions)
    for (const source of d.categories) {
      if (holder === source) continue; // the diagonal is a different scale
      out.push({
        holder: orgLabel(holder),
        source: orgLabel(source),
        count: d.matrix[holder][source],
      });
    }
  return out;
})();
const maxFlow = d3.max(flowCells, (d) => d.count ?? 0);
```

```js
Plot.plot({
  marginLeft: 100,
  marginBottom: 80,
  aspectRatio: 1,
  x: {label: "held by →", tickRotate: -30},
  y: {label: "↓ cataloged by"},
  color: {
    scheme: "greens",
    legend: true,
    label: "records",
    type: "sqrt",
    domain: [0, maxFlow],
    unknown: "color-mix(in srgb, var(--theme-foreground) 12%, transparent)",
  },
  marks: [
    Plot.cell(flowCells, {
      x: "holder",
      y: "source",
      fill: "count",
      tip: {format: {fill: (d) => d3.format(",")(d)}},
    }),
    Plot.text(flowCells, {
      x: "holder",
      y: "source",
      text: (d) => (d.count == null ? "" : d3.format(".2s")(d.count)),
      fill: (d) => (d.count > maxFlow * 0.55 ? "white" : "black"),
      fontSize: 11,
    }),
  ],
})
```

```js
provenance({sql: cat.dimensions.flow.sql, dataUrl: await catFile.url(), dataName: "cataloging_source.json"})
```

## When that cataloging happened

Crossing `040 $a` with the record's creation date (`008/00-05`) dates each library's
own cataloging, and shows how much of it is really a conversion project stamped with
one year. That has its own page: **[Original cataloging over time](./original-cataloging)**.

## How many hands have touched each record

Count of *distinct* agencies in `040 $d`, as a share of all the institution's
records. "No 040 field" is kept separate from "None" — a record with no `040` at
all is a different thing from one whose `040` simply credits no modifying agency,
and the gap is large (between 182,000 and 933,000 records per institution carry an
`040` that names no original agency).

The spread is wide — Stanford and Brown carry long modification chains while Duke,
Harvard, and Penn leave far more records untouched — but this is a **practice**
signal first: some systems append a modifying agency on every save and others
never do.

```js
shareHeatmap(cat, "mod_depth", modDepthLabel, {
  marginLeft: 130,
  legendLabel: "share of records",
})
```

```js
provenance({sql: cat.dimensions.mod_depth.sql, dataUrl: await catFile.url(), dataName: "cataloging_source.json"})
```
