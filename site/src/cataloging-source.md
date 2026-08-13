# Source of cataloging

Every other view here asks what is *in* the collections. This one asks who made the
**metadata**, from MARC `040` — the field that records which agency did the original
cataloging (`$a`) and which agencies have modified the record since (`$d`).

Read the numbers as **attribution practice**, not as cataloging labor. Three things
matter before anything below means much:

- **"This institution" undercounts original cataloging.** A member cataloging in
  OCLC Connexion often ends up with someone else's code in `$a`. And members
  self-attribute inconsistently: some write their MARC Organization Code, most write
  an OCLC symbol, and a large library may use a different one per branch. The
  mapping from codes to members is
  **curated by hand** from the WorldCat Registry and reviewed by a person — see
  [the institution code mapping](./data#the-institution-code-mapping) for what it
  holds and how it is maintained. A code nobody has confirmed is simply absent,
  which makes every figure below a floor rather than an estimate.
- **This field says nothing about how a record was *distributed*.** `OCoLC` is
  almost never the original agency, so there is no "OCLC" category below — a record
  that came through WorldCat is credited to the *library* that made it, via that
  library's OCLC symbol. That is not evidence OCLC is uninvolved; the distribution
  channel is recorded in MARC `035`, which is [a different
  page](./record-channels). Authorship and channel are different questions, and this
  page answers only the first.
- **Some `$a` values are free text rather than codes** — `Harvard Univ. Library`,
  `Princeton Univ. Libr.`, `RETROCON/NYGG (COO)`. Those land in "some other agency"
  even when they name a member, so they depress "this institution".
- **`$d` practice varies enormously** between institutions, which says more about
  each ILS's habits than about how much the records have been edited.

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
// lighter = another member), amber for the commercial/other long tail,
// grey for absent.
const BUCKET_COLOR = {
  lc: "#1d4e89",
  self: "#1f5f43",
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

The `035` page covers where records *travelled*; this is who is credited with making
them, cut by year. The bands are read as a share of that year's intake, so a band can
narrow either because a library took in more of other kinds of record or because it
was credited with less.

## Which agencies those are

There are tens of thousands of distinct agency codes in `040 $a`, so this has to be a
selection. It is the **union of each institution's own twelve most common** codes, not
a consortium-wide top-N — because ranking globally drops a small library's principal
agencies, and buries a large library whose work is spread thinly across many symbols.
Unioning also means the axis keeps working as POD grows: each new member brings its
own rows rather than competing for shared ones.

Cells are that institution's share of its records carrying an `$a` — **of all of
them, not just the rows shown** — so the columns do not sum to 100%: the remainder is
the long tail of codes no institution ranks highly. A code that is one library's
mainstay and absent elsewhere reads as a single bright cell in a row of real zeros.

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

Restricting `040 $a` to POD members' own codes gives the flow of cataloging
*between* these libraries. First, how much of each library's collection is credited
to itself. Read each bar as a **floor**: it counts only codes somebody has confirmed
against a registry, so a library whose retired or unrecorded codes are missing reads
lower than its real output.

```js
Plot.plot({
  marginLeft: 90,
  marginBottom: 40,
  height: 55 + cat.per_org.length * 30,
  x: {label: "share of records credited to this institution", grid: true, tickFormat: ".0%"},
  y: {label: null, domain: [...cat.per_org]
        .sort((a, b) => b.mix.self - a.mix.self)
        .map((o) => orgLabel(o.org))},
  marks: [
    Plot.barX(
      cat.per_org.map((o) => ({
        org: orgLabel(o.org),
        share: o.mix.self,
        records: o.counts.self,
      })),
      {
        x: "share",
        y: "org",
        fill: BUCKET_COLOR.self,
        channels: {records: {value: "records", label: "records"}},
        tip: {format: {x: ".1%", y: true, records: ","}},
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
everything else. Like the bar above, it can only count codes the map knows, so a
thin row may mean unrecorded codes rather than little sharing.

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
and the gap between them is substantial at every institution.

Read this as a **practice** signal first: some systems append a modifying agency on
every save and others never do, so the spread says more about ILS habits than about
how heavily records have been edited.

```js
shareHeatmap(cat, "mod_depth", modDepthLabel, {
  marginLeft: 130,
  legendLabel: "share of records",
})
```

```js
provenance({sql: cat.dimensions.mod_depth.sql, dataUrl: await catFile.url(), dataName: "cataloging_source.json"})
```
