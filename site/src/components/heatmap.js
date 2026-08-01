// Cross-institution comparison heatmaps, shared by the Collections pages.
// Each reads a dimension of data/comparison.json (a category × institution
// matrix with per-institution totals) and colors cells by each institution's
// share of records, so collection size doesn't dominate.

import * as Plot from "npm:@observablehq/plot";
import * as d3 from "npm:d3";

// {org, category (labeled), share, count} rows for a comparison dimension.
export function compareRows(comparison, dim, label) {
  const d = comparison.dimensions[dim];
  const rows = [];
  for (const o of d.institutions)
    for (const c of d.categories) {
      const n = d.matrix[o][c];
      rows.push({org: o, category: label(c), share: n == null ? null : n / d.totals[o], count: n});
    }
  // categories arrive sorted by consortium total (largest first → top of the y axis)
  return {rows, categories: d.categories.map(label), institutions: d.institutions};
}

// Share heatmap (category × institution) for a comparison dimension. Suppressed
// cells (too few to report) render as a faint tint rather than solid black.
export function shareHeatmap(comparison, dim, label, {marginLeft = 155} = {}) {
  const {rows, categories, institutions} = compareRows(comparison, dim, label);
  const maxShare = d3.max(rows, (d) => d.share ?? 0);
  return Plot.plot({
    marginLeft,
    marginBottom: 60,
    height: 55 + categories.length * 34,
    x: {label: null, domain: institutions, tickRotate: -30},
    y: {label: null, domain: categories},
    color: {
      scheme: "blues",
      legend: true,
      label: "share of records",
      domain: [0, maxShare],
      tickFormat: ".0%",
      unknown: "color-mix(in srgb, var(--theme-foreground) 12%, transparent)",
    },
    marks: [
      Plot.cell(rows, {
        x: "org",
        y: "category",
        fill: "share",
        tip: {format: {fill: ".0%"}},
      }),
      Plot.text(rows, {
        x: "org",
        y: "category",
        text: (d) => (d.share == null ? "" : (d.share * 100).toFixed(0) + "%"),
        fill: (d) => (d.share > maxShare * 0.55 ? "white" : "black"),
        fontSize: 12,
      }),
    ],
  });
}
