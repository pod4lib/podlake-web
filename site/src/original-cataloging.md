# Original cataloging over time

[Source of cataloging](./cataloging-source) asks *who* made each record's metadata.
This page asks *when* and (for the subset of records a library made itself) those
two questions together are the closest this data comes to measuring a library's own
cataloging output.

The time comes from MARC `008/00-05`, **date entered on file**: the day the record was
created in the holding library's system. On its own that is a record-*arrival* clock;
for copy cataloging it dates the copying, not the cataloging. But where `040 $a`
credits the library holding the record, arrival and authorship are the same event.

Three things to hold onto before reading anything below:

- **"Credited to this library" is not the same as "cataloged by this library."** The
  attribution comes from [a hand-curated map of agency codes to
  members](./data#the-institution-code-mapping), and a library cataloging in OCLC
  Connexion often ends up with someone else's code in `$a`. Every figure here is a
  **floor**: the map holds only codes somebody has confirmed, so a library's retired
  or unrecorded codes go uncounted, and adding one raises its line. Nothing here
  distinguishes "did little original cataloging" from "has codes we don't know yet".
- **A reload restamps every record it touches.** The tallest years are almost always
  system migrations and retrospective-conversion projects, not bursts of cataloging.
  The date is only ever as old as the last system the records passed through.
- **Volume of intake is not effort.** A year of large vendor loads looks like a
  productive year until you divide through, which is what the second chart does.

```js
import {html} from "npm:htl";
import {orgLabel, sourceBucketLabel} from "./components/marc.js";
import {provenance} from "./components/provenance.js";
const catFile = FileAttachment("./data/cataloging_source.json");
const cat = catFile.json();
```

```js
// Same semantic palette as the Source of cataloging page: blues for outside
// authorities, greens for cataloging done inside the consortium, amber for the
// commercial tail, grey for absent.
const BUCKET_COLOR = {
  lc: "#1d4e89",
  self: "#1f5f43",
  pod: "#a8d5bd",
  other: "#d9a03c",
  none: "#9aa0a6",
};
// everything credited to the library holding the record
const ORIGINAL = ["self"];
const lastFullYear = cat.timeline.partial_year - 1;
const tlRows = cat.timeline.per_org.flatMap((o) =>
  o.values
    // the snapshot year is only partly harvested, so its drop is an artifact
    .filter((v) => v.year <= lastFullYear)
    .map((v) => {
      const original = ORIGINAL.reduce((sum, b) => sum + v.counts[b], 0);
      return {
        org: orgLabel(o.org),
        year: v.year,
        total: v.total,
        original,
        share: v.total ? original / v.total : 0,
        counts: v.counts,
      };
    })
);
const tlByOrg = d3.group(tlRows, (d) => d.org);
const tlOrgs = [...tlByOrg.keys()];
const tlX = {label: "year the record entered the catalog", tickFormat: "d", grid: true};
const tlYears = [1966, lastFullYear];
const unplaced = cat.timeline.per_org.reduce((sum, o) => sum + o.unplaced, 0);
const unplacedShare = unplaced / cat.per_org.reduce((sum, o) => sum + o.records, 0);

// Every chart here is one panel per member, because POD is meant to grow: a chart
// that overlays N libraries stops working somewhere around a dozen, while a grid of
// panels just reflows. Columns scale with the roster so the panels stay legible
// rather than shrinking indefinitely.
const tlCols = tlOrgs.length <= 6 ? 2 : tlOrgs.length <= 12 ? 3 : 4;
const panelWidth = Math.max(230, Math.floor(width / tlCols) - 60);
const panelGrid = (render, height = 170) =>
  html`<div class=${`grid grid-cols-${tlCols}`}>${tlOrgs.map(
    (org) => html`<div class="card">${render(org, tlByOrg.get(org), height)}</div>`
  )}</div>`;
```

## How much, and when

One panel per library, **each on its own vertical scale**. Compare *shapes*
across panels, not heights; the axis labels carry the magnitudes. Hover over
a year for the records credited, the total that arrived, and the share.

```js
panelGrid((org, rows, height) =>
  Plot.plot({
    title: org,
    width: panelWidth,
    height,
    marginLeft: 52,
    x: {...tlX, label: null, domain: tlYears},
    y: {label: null, grid: true, tickFormat: "~s"},
    marks: [
      Plot.areaY(rows, {x: "year", y: "original", fill: BUCKET_COLOR.self, fillOpacity: 0.85}),
      Plot.lineY(rows, {x: "year", y: "original", stroke: BUCKET_COLOR.self}),
      Plot.ruleY([0]),
      Plot.tip(
        rows,
        Plot.pointerX({
          x: "year",
          y: "original",
          channels: {
            entered: {value: "total", label: "of records entered"},
            portion: {value: "share", label: "share"},
          },
          format: {x: "d", y: ",", entered: ",", portion: ".1%", org: false, counts: false},
        })
      ),
    ],
  })
)
```

## As a share of what arrived

The same records divided through by everything that entered that year. This is the
comparable view: it removes both collection size and the sheer volume of a load
year, so a rise here means the library really was cataloging more of what it took in,
not merely taking in more.

Because a share is bounded and already size-independent, **these panels share one
vertical scale**, unlike the ones above: heights mean the same thing everywhere and
can be read across. Each panel greys in every other library, so you get the
cross-library comparison without the six-way line tangle.

```js
const shareMax = d3.max(tlRows, (d) => d.share);
```

```js
panelGrid(
  (org, rows, height) =>
    Plot.plot({
      title: org,
      width: panelWidth,
      height,
      marginLeft: 46,
      x: {...tlX, label: null, domain: tlYears},
      y: {label: null, grid: true, domain: [0, shareMax], tickFormat: ".0%"},
      marks: [
        // every library, faint — the context this panel's line is read against
        Plot.lineY(tlRows, {
          x: "year",
          y: "share",
          z: "org",
          stroke: "var(--theme-foreground)",
          strokeOpacity: 0.16,
          strokeWidth: 1,
        }),
        Plot.lineY(rows, {x: "year", y: "share", stroke: BUCKET_COLOR.self, strokeWidth: 1.75}),
        Plot.ruleY([0]),
        Plot.tip(
          rows,
          Plot.pointerX({
            x: "year",
            y: "share",
            channels: {
              records: {value: "original", label: "records credited"},
              intake: {value: "total", label: "of records entered"},
            },
            format: {x: "d", y: ".1%", records: ",", intake: ",", org: false, counts: false},
          })
        ),
      ],
    }),
  150
)
```

## What is left out

${d3.format(",")(unplaced)} records — ${d3.format(".1%")(unplacedShare)} of the
corpus — carry no usable date and are absent from every chart here: no `008`, an
unparseable one, the placeholder `000000` (which is *not* the year 2000, and would
distort it badly if taken literally), or a year before 1966,
when MARC did not yet exist. Years holding too few records to publish are folded in
with them, so that a suppressed year cannot be recovered by subtraction.

${cat.timeline.partial_year} is also left off: the lake is harvested part-way through
it, so its apparent collapse is an artifact of the snapshot rather than anything about
cataloging.

```js
provenance({sql: cat.timeline.sql, dataUrl: await catFile.url(), dataName: "cataloging_source.json"})
```
