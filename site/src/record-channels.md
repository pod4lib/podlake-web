# How records arrived

[Source of cataloging](./cataloging-source) asks who *wrote* a record. This page
asks how it *travelled* which is answered by a different field.

MARC `035` holds system control numbers, written `(ORGCODE)number`: the number, and
the system the number belongs to. Records accumulate these as they move between
union catalogues, knowledge bases and vendor platforms, so the set of namespaces on
a record is a rough itinerary. It is also much better populated than the cataloging
source: **99.3% to 100%** of records carry an `035`, against 86% with an `040 $a`.

Two things to keep in mind:

- **These channels overlap.** A record routinely carries several system numbers, so
  the shares below are *coverage* and do not sum to 100%. That overlap is often the
  history: RLG merged into OCLC in 2006, so a great many records legitimately carry
  both an RLIN and an OCLC number.
- **A system number means the record passed through, not that it originated there.**
  An OCLC number says the record exists in WorldCat, not that OCLC created it —
  which is exactly why the `040` page shows almost no OCLC authorship while nearly
  every record here has an OCLC number.

The two charts below are the same field seen at two resolutions. The first sorts
namespaces into a handful of categories, so one question *has this record been
through OCLC?* can be put to every library and answered on comparable terms. The
second drops the categories and shows the namespace strings as they were written.
Neither is a summary of the other, and **their numbers will not always agree**; the
list under the second chart says exactly where they diverge and why.

```js
import {orgLabel, channelLabel, namespaceLabel} from "./components/marc.js";
import {shareHeatmap} from "./components/heatmap.js";
import {provenance} from "./components/provenance.js";
const channelFile = FileAttachment("./data/record_channels.json");
const channels = channelFile.json();
```

## Which systems each library's records have been through

Share of each institution's records carrying a control number from each system.
"Any system number" is the baseline, essentially every record has one.

```js
const chanRows = channels.per_org.flatMap((o) =>
  channels.channels.map((c) => ({
    org: orgLabel(o.org),
    channel: channelLabel(c),
    share: o.coverage[c],
    records: o.counts[c],
  }))
);
const chanOrder = channels.channels.map(channelLabel);
```

```js
Plot.plot({
  marginLeft: 230,
  marginBottom: 60,
  height: 55 + chanOrder.length * 40,
  x: {label: null, domain: channels.per_org.map((o) => orgLabel(o.org)), tickRotate: -30},
  y: {label: null, domain: chanOrder},
  color: {
    scheme: "blues",
    legend: true,
    label: "share of records",
    domain: [0, 1],
    tickFormat: ".0%",
    // too few to report renders as a faint tint, matching the other heatmaps
    unknown: "color-mix(in srgb, var(--theme-foreground) 12%, transparent)",
  },
  marks: [
    Plot.cell(chanRows, {
      x: "org",
      y: "channel",
      fill: "share",
      channels: {records: {value: "records", label: "records"}},
      tip: {format: {fill: ".1%", records: ","}},
    }),
    Plot.text(chanRows, {
      x: "org",
      y: "channel",
      dy: -6,
      text: (d) => (d.share == null ? "" : (d.share * 100).toFixed(0) + "%"),
      fill: (d) => (d.share > 0.55 ? "white" : "black"),
      fontSize: 12,
    }),
    Plot.text(chanRows, {
      x: "org",
      y: "channel",
      dy: 8,
      text: (d) => (d.records == null ? "" : d3.format("~s")(d.records)),
      fill: (d) => (d.share > 0.55 ? "white" : "black"),
      fillOpacity: 0.65,
      fontSize: 9.5,
    }),
  ],
})
```

```js
provenance({sql: channels.sql, dataUrl: await channelFile.url(), dataName: "record_channels.json"})
```

## The namespaces themselves

The raw `035` namespaces, uncategorized: the union of each institution's own twelve
most common — a namespace must also reach 0.1% of that institution's records to earn
a row — so a system that matters to one library isn't ranked away by the others.
Cells are a share of all that institution's records, the same denominator as the
chart above, which makes the two directly comparable.

Three ways they differ, each of them a reason both charts exist:

- **One category can be several namespaces.** `OCLC / WorldCat` above matches
  `(OCoLC)` together with its variants. Five libraries write only `(OCoLC)`, so their
  two figures agree; Stanford also writes `(OCoLC-M)` and `(OCoLC-I)`, which is why
  it reads 98% above and 11%, 91% and 63% across three separate rows here.
- **One category can be a different namespace at each library.** `A local library
  system` is `RPB` at Brown, `NCD` at Duke, `MH` at Harvard, `PU` at Penn, `NJP` at
  Princeton, and `SIRSI` at Stanford — an institution's own code in five cases and an
  ILS product name in the sixth. The category is what makes those one comparable row;
  only the raw view shows what that row is made of.
- **The categories are not exhaustive.** Nothing above collects vendor platforms,
  special-collections databases, or other libraries' union catalogues, so ProQuest,
  Adam Matthew Digital, the University of Toronto and the rest appear only here.

Unrecognized codes pass through raw rather than being dropped or guessed at.

Two rows of the first chart — `A local library system` and `Another POD member's
system` — rest on a hand-curated map of namespace codes to institutions that POD has
not ratified. See [the institution code mapping](./data#the-institution-code-mapping)
for what it contains and what adding a member would change.

```js
shareHeatmap(channels, "namespace", namespaceLabel, {
  marginLeft: 330,
  legendLabel: "share of records",
  rowHeight: 30,
})
```

```js
provenance({sql: channels.dimensions.namespace.sql, dataUrl: await channelFile.url(), dataName: "record_channels.json"})
```
