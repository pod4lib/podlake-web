# Archives & manuscripts

Archives and manuscript materials are a small but distinctive slice of these
catalogs — roughly 0.5–2.3% of each institution's records, but hundreds of
thousands of records in absolute terms. They are identified here from the MARC
leader: **type of record** (position 06) `t` manuscript text, `d`/`f` manuscript
music/maps, `p` mixed materials; **or bibliographic level** (position 08) `c`
collection / `d` subunit. That is a deliberately broad net — it includes
collection-level description of some printed material, not only manuscripts.

Unlike the general collection, these materials are rarely shelf-classified, so
the views below lean on *what the material is* (genre/form) and *how it is made
findable* rather than LC class. As with electronic resources, several of these
signals reflect **cataloging practice** as much as what an institution holds.

```js
import {recordTypeLabel} from "./components/marc.js";
import {shareHeatmap, countHeatmap} from "./components/heatmap.js";
import {provenance} from "./components/provenance.js";
const archivesFile = FileAttachment("./data/archives.json");
const archives = archivesFile.json();
const cap = (s) => (s.length ? s.charAt(0).toUpperCase() + s.slice(1) : s);
```

## Scale & material type

How much archival material each institution holds, and of what kind (leader/06),
as **record counts** — cells are on a square-root color scale so both large
(Harvard) and small (Brown) holdings stay legible. Harvard and Penn dominate;
"mixed material" is the classic multi-format archival collection.

```js
countHeatmap(archives.dimensions.material_type, recordTypeLabel, {marginLeft: 230, colorLabel: "archival records"})
```

```js
provenance({sql: archives.dimensions.material_type.sql, dataUrl: await archivesFile.url(), dataName: "archives.json"})
```

## Genre & form of material

What *kinds* of things the archives contain, from the MARC `655` genre/form
heading — the vocabulary that actually characterizes special collections. We use
this instead of LC classification because archives are seldom shelf-classified
(LC-class coverage of this subset swings from 8% at Harvard to 71% at Penn).

Genre/form is a **long tail** — ~5,800 distinct terms, 65% of them used by a
single institution — so rather than force a shared axis (which would be sparse
and Harvard-skewed), each panel below shows that institution's *own* top dozen
forms. The vocabularies aren't reconciled across libraries and subdivisions are
kept intact, because that's exactly where the distinctive strengths show — Arabic
and Sanskrit manuscripts, posters, broadsides, scrapbooks.

```js
const genrePanels = archives.genre.map((o) => {
  const rows = o.values.map((v) => ({term: cap(v.term), count: v.count}));
  return html`<figure style="margin: 0 0 0.5rem 0; max-width: 460px">
    <figcaption style="font-weight: 600; margin-bottom: 0.25rem">
      ${o.org} <span style="font-weight: 400; color: var(--theme-foreground-muted)">· ${d3.format(",")(o.total)} archival records</span>
    </figcaption>
    ${Plot.plot({
      marginLeft: 185,
      width: 480,
      height: 30 + rows.length * 22,
      x: {label: null, tickFormat: "~s", grid: true},
      y: {label: null, domain: rows.map((r) => r.term)},
      marks: [
        Plot.barX(rows, {x: "count", y: "term", fill: "var(--theme-foreground-focus)", fillOpacity: 0.8}),
        Plot.text(rows, {x: "count", y: "term", text: (d) => d3.format(",")(d.count), dx: 3, textAnchor: "start", fontSize: 10}),
        Plot.ruleX([0]),
      ],
    })}
  </figure>`;
});
```

```js
html`<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(440px, 1fr)); gap: 1rem 1.5rem">${genrePanels}</div>`
```

```js
provenance({sql: [archives.sql[1]], dataUrl: await archivesFile.url(), dataName: "archives.json"})
```

## Vintage: when the material dates from

The decade each archival record's material *begins* (MARC 008 date1), as a share
of the institution's dated archival records, so collection size drops out and the
shapes can be compared. The axis runs from ~100 AD to the present: most material
is modern (so the recent end dominates), but the deep tail is real — medieval
manuscripts around the 1400s, and Duke's documentary papyri back in the first few
centuries AD. Old material is dated to the century, so expect round-number
clusters; dates are frequently estimated, so treat this as broad-brush. (The 008
can't record BC dates, so ~100 AD is the practical floor.)

```js
const archVintage = archives.start_decade.flatMap((o) => {
  const total = d3.sum(o.values, (d) => d.count);
  return o.values.map((d) => ({org: o.org, decade: d.decade, share: total ? d.count / total : 0}));
});
```

```js
// drag right to zoom past the sparse deep-history tail into the modern era
const startYear = view(Inputs.range([100, 2000], {step: 10, value: 100, label: "Start year"}));
```

```js
Plot.plot({
  width,
  marginLeft: 55,
  x: {label: "decade of first date", tickFormat: "d", domain: [startYear, 2025]},
  y: {label: "share of archival records", grid: true, tickFormat: ".0%"},
  color: {legend: true},
  marks: [
    Plot.lineY(archVintage, {
      filter: (d) => d.decade >= startYear,
      x: "decade",
      y: "share",
      stroke: "org",
      curve: "catmull-rom",
      tip: true,
    }),
    Plot.ruleY([0]),
  ],
})
```

```js
provenance({sql: [archives.sql[2]], dataUrl: await archivesFile.url(), dataName: "archives.json"})
```

## Finding-aid links

Archival records increasingly point to an **online finding aid** — a fuller guide
to the collection than the catalog record itself. First, how many of each
institution's archival records carry any online link (`856`):

```js
const linkShare = archives.online_link
  .map((o) => ({org: o.org, share: o.total ? o.count / o.total : 0, count: o.count}))
  .sort((a, b) => b.share - a.share);
```

```js
Plot.plot({
  marginLeft: 90,
  height: 55 + linkShare.length * 34,
  x: {label: "share with an online link", grid: true, tickFormat: ".0%", domain: [0, 1]},
  y: {label: null, domain: linkShare.map((d) => d.org)},
  marks: [
    Plot.barX(linkShare, {x: "share", y: "org", fill: "var(--theme-foreground-focus)", fillOpacity: 0.75}),
    Plot.text(linkShare, {x: "share", y: "org", text: (d) => d3.format(".0%")(d.share), dx: 4, textAnchor: "start"}),
    Plot.ruleX([0]),
  ],
})
```

Because "finding aid" is not reliably flagged in the record, we don't trust a
label — instead we classify each link's **host** into a fixed set of destination
types. This keeps the chart stable as POD adds institutions (each brings its own
finding-aid host, which still lands in the same bucket). Persistent-ID resolvers
(`nrs`, `arks`, `purl`, `hdl`) are kept separate because they hide whether the
target is a finding aid or a digitized object.

```js
const destLabel = (c) =>
  ({
    finding_aid: "Finding-aid platform",
    aggregator: "Aggregator (OAC, ArchiveGrid)",
    resolver: "Persistent-ID resolver",
    repository: "Digital repository",
    vendor: "Vendor / licensed",
    other: "Other",
  })[c] ?? c;
```

```js
shareHeatmap(archives, "link_destination", destLabel, {marginLeft: 220, legendLabel: "share of archival records"})
```

```js
provenance({sql: [archives.sql[3], archives.sql[4]], dataUrl: await archivesFile.url(), dataName: "archives.json"})
```
