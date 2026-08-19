// A collapsible "Behind this chart" panel shown under each visualization: the
// DuckDB query (or queries) that produced the derived data, a link to download
// that data, and a link to the Python that shapes it (suppression, share
// matrices, place roll-ups — none of which are expressible in the SQL alone).

import {html} from "npm:htl";
import {sqlBlock} from "./sql.js";

// Deep links into the repo on GitHub. These are the one class of link Observable's
// build cannot check for us — `npm run build` validates internal links only — so a
// path change here fails silently on the live site. Grep for the old path when
// moving Python around.
const GITHUB_BASE = "https://github.com/sul-dlss/podlake-web/blob/main";
const DEFAULT_SOURCE = "src/podlake_web/queries.py";

// sql: a string, or [{label?, sql}]. dataUrl/dataName: the derived JSON to link.
export function provenance({sql, dataUrl, dataName, source = DEFAULT_SOURCE} = {}) {
  const queries = typeof sql === "string" ? [{sql}] : (sql ?? []);
  const sourceName = source.split("/").pop();
  return html`<details class="card" style="margin-top: 2rem;">
    <summary style="cursor: pointer; font-weight: 600;">Behind this chart</summary>
    <p style="max-width: 640px; margin: 0.75rem 0 1rem;">
      The DuckDB ${queries.length > 1 ? "queries" : "query"} that produced the
      data. The raw counts are then shaped in Python — suppression, shares,
      roll-ups — in <a href=${`${GITHUB_BASE}/${source}`}>${sourceName}</a>.${dataUrl
        ? html` Download the derived data: <a href=${dataUrl} download=${dataName}>${dataName}</a>.`
        : ""}
    </p>
    ${queries.map(
      (q) => html`<div style="margin-bottom: 0.75rem;">
        ${q.label
          ? html`<div style="font-size: 0.85rem; color: var(--theme-foreground-muted); margin-bottom: 0.25rem;">${q.label}</div>`
          : ""}
        ${sqlBlock(q.sql)}
      </div>`
    )}
  </details>`;
}
