# How records arrived

[Source of cataloging](./cataloging-source) asks who *wrote* a record. This page
asks how it *travelled* — a different question, answered by a different field.

MARC `035` holds system control numbers, written `(ORGCODE)number`: the number, and
the system the number belongs to. Records accumulate these as they move between
union catalogues, knowledge bases and vendor platforms, so the set of namespaces on
a record is a rough itinerary. It is also much better populated than the cataloging
source — **99.3% to 100%** of records carry an `035`, against 86% with an `040 $a`.

Two things to keep in mind:

- **These channels overlap.** A record routinely carries several system numbers, so
  the shares below are *coverage* and do not sum to 100%. That overlap is often the
  history: RLG merged into OCLC in 2006, so a great many records legitimately carry
  both an RLIN and an OCLC number.
- **A system number means the record passed through, not that it originated there.**
  An OCLC number says the record exists in WorldCat, not that OCLC created it —
  which is exactly why the `040` page shows almost no OCLC authorship while nearly
  every record here has an OCLC number.

```js
import {orgLabel, channelLabel, namespaceLabel} from "./components/marc.js";
import {shareHeatmap} from "./components/heatmap.js";
import {provenance} from "./components/provenance.js";
const channelFile = FileAttachment("./data/record_channels.json");
const channels = channelFile.json();
```

## Which systems each library's records have been through

Share of each institution's records carrying a control number from each system.
"Any system number" is the baseline — essentially every record has one.

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

Four things stand out.

**Nearly everything went through OCLC — except at Duke.** Five of the six libraries
sit between 95% and 98%. Duke is at 66%, and the gap is filled by the Ex Libris
Community Zone: about 45% of Duke's records carry a `(EXLCZ)` or `(CKB)` number.
Duke is sourcing a large share of its records, mostly electronic, straight from Ex
Libris rather than through WorldCat. That is the same fact appearing as Duke's
unusually large "some other agency" band on the cataloging-source page, seen from
the other side — and no other member does this at any scale.

**RLIN is still visible in three catalogues.** Princeton (30%), Penn (23%) and
Stanford (17%) carry substantial RLIN numbers; Brown, Duke and Harvard essentially
none. RLIN closed in 2006, so this is a durable trace of how these catalogues were
built rather than anything about current practice.

**Harvard is the outlier on local identifiers**, at 8% against 52–97% everywhere
else. Read that as a data-contribution difference rather than a cataloging one: it
reflects whether an institution exports its local record number into `035`, not
anything about the records themselves.

**Direct member-to-member identifiers are almost nonexistent** — under 1%
everywhere. Records travel between these libraries through the utilities, not
laterally, which is the same story the cataloging-source flow matrix tells with
different evidence.

```js
provenance({sql: channels.sql, dataUrl: await channelFile.url(), dataName: "record_channels.json"})
```

## The namespaces themselves

The raw `035` namespaces, uncategorized: the union of each institution's own twelve
most common, so a system that matters to one library isn't ranked away by the
others. Cells are a share of all that institution's records.

This is where the channel taxonomy above stops and the detail begins — local
systems (`SIRSI`, `PUVoyagerBibID`), vendor platforms (`MiAaPQ`, `VaAlASP`,
`UkMbAM-D`), special-collections databases (`CotsenDB` at Princeton, `DASH` at
Harvard), and other libraries' union catalogues. Unrecognized codes pass through
raw rather than being dropped or guessed at.

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
