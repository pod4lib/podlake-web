# Electronic resources

Rather than try to *detect* which records are "electronic" (which is a judgment
that depends heavily on each institution's cataloging practice) this page
simply reports what is **observably linked**: the hostnames each institution
points to from its MARC `856` fields (online location & access). Each panel is
that library's own top link hosts, since they're largely institution-specific.

A few things to keep in mind:

- **Hosts are raw**, including link *infrastructure*. Several institutions'
  top host is their own persistent-ID resolver (Penn `hdl.library.upenn.edu`,
  Harvard `nrs.harvard.edu`, Stanford `purl.stanford.edu`) or an EZproxy
  (`login.proxy.lib.duke.edu`, `login.revproxy.brown.edu`), which stands in
  front of the real destination.
- `856` links are a **mixed bag**: subscribed e-resource platforms (EBSCO,
  Springer, Gale, Naxos…) alongside government-document PURLs, digitized
  public-domain books (HathiTrust, Google Books, archive.org), tables of contents
  (`catdir.loc.gov`), and finding aids.

So read this as "where each library sends people online," not a clean census of
licensed databases.

```js
const electronicFile = FileAttachment("./data/electronic.json");
const electronic = electronicFile.json();
import {provenance} from "./components/provenance.js";
import {orgLabel} from "./components/marc.js";
```

## Top link hosts by institution

```js
const hostPanels = electronic.hosts.map((o) => {
  const rows = o.values.map((v) => ({host: v.host, count: v.count}));
  return html`<figure style="margin: 0 0 0.5rem 0; max-width: 520px">
    <figcaption style="font-weight: 600; margin-bottom: 0.25rem">
      ${orgLabel(o.org)} <span style="font-weight: 400; color: var(--theme-foreground-muted)">· ${d3.format(",")(o.total)} links</span>
    </figcaption>
    ${Plot.plot({
      marginLeft: 230,
      width: 520,
      height: 30 + rows.length * 22,
      x: {label: null, tickFormat: "~s", grid: true},
      y: {label: null, domain: rows.map((r) => r.host)},
      marks: [
        Plot.barX(rows, {x: "count", y: "host", fill: "var(--theme-foreground-focus)", fillOpacity: 0.8}),
        Plot.text(rows, {x: "count", y: "host", text: (d) => d3.format(",")(d.count), dx: 3, textAnchor: "start", fontSize: 10}),
        Plot.ruleX([0]),
      ],
    })}
  </figure>`;
});
```

```js
html`<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 1rem 1.5rem">${hostPanels}</div>`
```

```js
provenance({sql: electronic.sql, dataUrl: await electronicFile.url(), dataName: "electronic.json"})
```
