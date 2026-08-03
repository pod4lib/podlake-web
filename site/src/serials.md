# Serials

Serials and other continuing resources, identified from the MARC leader's
bibliographic level (position 07 = `s`). Every institution's serial holdings
grow along the same historical curve, so these views instead look for what makes
each collection *different*: how current it is, how far back it reaches, and
what its serials are about.

```js
import {lcClassLabel, serialStatusLabel, successionLinkLabel, successionTypeLabel, orgLabel} from "./components/marc.js";
import {shareHeatmap} from "./components/heatmap.js";
import {provenance} from "./components/provenance.js";
const comparisonFile = FileAttachment("./data/comparison.json");
const comparison = comparisonFile.json();
const timelineFile = FileAttachment("./data/serials_timeline.json");
const timeline = timelineFile.json();
const successionFile = FileAttachment("./data/serials_succession.json");
const succession = successionFile.json();
```

## Active serials over time

How many of an institution's serials were *being published* in a given year?
This chart contains serial counts in every year from its start to its end (from
the dates in the MARC 008 field), with titles still published running to
${timeline.now_year}. Serials with an unknown start or an undetermined end
can't be placed on the timeline and are omitted.

```js
const serialOrgs = timeline.active.map((r) => r.org).sort();
const serialOrg = view(Inputs.select(serialOrgs, {label: "Institution", value: serialOrgs[0], format: orgLabel}));
```

```js
const active = (timeline.active.find((r) => r.org === serialOrg) ?? {values: []})
  .values.slice()
  .sort((a, b) => a.year - b.year);
```

```js
Plot.plot({
  marginLeft: 60,
  x: {label: "year", tickFormat: "d"},
  y: {label: "active serials", grid: true, tickFormat: "~s"},
  marks: [
    Plot.areaY(active, {x: "year", y: "count", fill: "var(--theme-foreground-focus)", fillOpacity: 0.3}),
    Plot.lineY(active, {x: "year", y: "count", stroke: "var(--theme-foreground-focus)"}),
    Plot.ruleY([0]),
  ],
})
```

```js
provenance({sql: [timeline.sql[0]], dataUrl: await timelineFile.url(), dataName: "serials_timeline.json"})
```

## Currency: still published, ceased, or unknown

The publication status recorded in the 008 (character 06) is a measure of how
*living* each serial collection is. Columns sum to ~100\% since serials without
one of these three status codes are omitted.

```js
// re-order categories to the semantic still-published → ceased → unknown
const statusOrdered = {
  dimensions: {
    serial_status: {
      ...comparison.dimensions.serial_status,
      categories: ["c", "d", "u"].filter((c) =>
        comparison.dimensions.serial_status.categories.includes(c)
      ),
    },
  },
};
```

```js
shareHeatmap(statusOrdered, "serial_status", serialStatusLabel, {marginLeft: 150, legendLabel: "share of serials", rowHeight: 66})
```

```js
provenance({sql: comparison.dimensions.serial_status.sql, dataUrl: await comparisonFile.url(), dataName: "comparison.json"})
```

## Vintage: when the serials began

The decade each serial *started* publishing, as a share of the institution's
serials (so collection size drops out and the shapes can be compared directly).
A curve pushed to the right holds mostly recent serials; a fatter left tail means
deeper historical runs. Only serials with a numeric start year (1700–2025) are
counted.

```js
const vintage = timeline.start_decade.flatMap((o) => {
  const total = d3.sum(o.values, (d) => d.count);
  return o.values.map((d) => ({org: orgLabel(o.org), decade: d.decade, share: total ? d.count / total : 0}));
});
```

```js
Plot.plot({
  marginLeft: 55,
  x: {label: "decade of first publication", tickFormat: "d"},
  y: {label: "share of serials", grid: true, tickFormat: ".0%"},
  color: {legend: true},
  marks: [
    Plot.lineY(vintage, {x: "decade", y: "share", stroke: "org", curve: "catmull-rom", tip: true}),
    Plot.ruleY([0]),
  ],
})
```

```js
provenance({sql: [timeline.sql[1]], dataUrl: await timelineFile.url(), dataName: "serials_timeline.json"})
```

## Succession: how serial titles change

Serials rarely keep one identity forever. A journal is renamed, two newsletters
merge into one, an annual review splits into separate series, or a publication
absorbs another. Catalogers record these events directly on the record with two
**linking-entry** fields: **`780`** points *backward* to the title a serial
**continues** (its predecessor), and **`785`** points *forward* to the title it
**became** (its successor). Together they stitch separate catalog records into a
single lineage. So a run you might think of as one long-lived journal is often
several records chained by these links.

Reconstructing the full chains (title A → B → C) is genuinely hard: it means
matching each linked title back to its own record. So these two charts take the
low-hanging fruit instead and show *how often* the links appear, and *what
kind* of change they record. Two things to keep in mind while reading them:

- A single lineage appears as **several** linked records, not one, so these
  count links, not distinct histories.
- Whether a link is present reflects **cataloging thoroughness** as much as the
  underlying history. A missing link doesn't prove a title never changed.

### Serials that are part of a lineage

The share of each institution's serials that carry a predecessor (`780`) or
a successor (`785`) link, i.e. that are documented as part of a title's larger
history. The two rows are **independent** (a serial can have both a predecessor
and a successor), so they do not sum to 100%.

```js
shareHeatmap(succession, "succession_link", successionLinkLabel, {marginLeft: 240, legendLabel: "share of serials", rowHeight: 66})
```

```js
provenance({sql: succession.dimensions.succession_link.sql, dataUrl: await successionFile.url(), dataName: "serials_succession.json"})
```

### How serials transform

Among the serials that *were* succeeded by another title, the kind of change
recorded (read from the `785` field's second indicator). Each cell is a share
of all that institution's serials, so a column roughly totals its "continued by
a later title" figure above.

```js
shareHeatmap(succession, "succession_type", successionTypeLabel, {marginLeft: 190, legendLabel: "share of serials"})
```

```js
provenance({sql: succession.dimensions.succession_type.sql, dataUrl: await successionFile.url(), dataName: "serials_succession.json"})
```

## Serials by LC classification

The subject mix *within* each institution's serials: of the serials that carry
an LC call number, the share in each Library of Congress class (so a column adds
up to ~100\%). Same first-LC-match logic as the
[LC classification](./lc-classification) page, restricted to serial records.

```js
shareHeatmap(comparison, "serial_classification", lcClassLabel, {marginLeft: 210, legendLabel: "share of serials"})
```

```js
provenance({sql: comparison.dimensions.serial_classification.sql, dataUrl: await comparisonFile.url(), dataName: "comparison.json"})
```
