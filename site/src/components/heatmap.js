// Cross-institution comparison heatmaps, shared by the Collections pages.
// Each reads a dimension of data/comparison.json (a category × institution
// matrix with per-institution totals) and colors cells by each institution's
// share of records, so collection size doesn't dominate.

import * as Plot from "npm:@observablehq/plot";
import * as d3 from "npm:d3";
import {orgLabel} from "./marc.js";

// A cell carries two stacked labels — a percentage over a record count — so its
// width is set by the text, not by whatever space happens to be left over. At
// 12px, "100%" is ~30px wide; the count below it, in the compact form below, is
// ~26px. MIN_CELL is those plus padding, and is a floor: the grid grows to fill
// the container when there is room and scrolls when there isn't, rather than
// shrinking cells until neighbouring labels collide.
const MIN_CELL = 54;
// Cells grow to fill the page, but not without limit: past this a chart with
// short row labels ends up with cells far larger than one with long labels on the
// next page, which reads as two unrelated charts rather than one system.
const MAX_CELL = 72;
// One row height for every heatmap on the site, so a cell means the same thing on
// every page. Callers used to override this per chart — 30 to squeeze a long axis
// in, 66 to pad a three-row one out — which made otherwise identical charts look
// unrelated.
const CELL_HEIGHT = 34;
// Named because the plot height has to be derived from them: Plot divides the
// space *inside* the margins among the rows, so `55 + n * CELL_HEIGHT` (the old
// formula) silently made cells shorter the fewer rows there were — a 3-row chart
// came out at 18px against a 21-row chart's 29px. Height is built up from the
// cell instead, so every heatmap's rows are exactly CELL_HEIGHT tall.
const MARGIN_TOP = 20;
const MARGIN_BOTTOM = 60;
const MARGIN_RIGHT = 20;
const plotHeight = (rows) => MARGIN_TOP + MARGIN_BOTTOM + rows * CELL_HEIGHT;

// Counts share a cell with the percentage, so they have to be short: d3's ","
// gives "4,635,414" (~44px, wider than the cell), while this gives "4.6M".
// Under 1000 the value is already short enough to show exactly.
const countFormat = (n) => (n == null ? "" : n < 1000 ? String(n) : d3.format(".2~s")(n));

// Cell width, and the plot width that follows from it, for `n` columns inside a
// container `available` px wide. Below MIN_CELL the plot overflows and gets a
// scroller (see `scrollable`) instead of squeezing the cells.
function geometry(n, available, marginLeft) {
  const room = available - marginLeft - MARGIN_RIGHT;
  const cell = Math.min(MAX_CELL, Math.max(MIN_CELL, room / n));
  return {cell, width: marginLeft + MARGIN_RIGHT + n * cell};
}

// Once the columns outgrow the page the grid scrolls sideways rather than
// compressing. Known limitation: the row labels live in the same SVG, so they
// scroll away with the cells — pinning them means splitting the y axis into its
// own element, which isn't worth it until this actually triggers.
function scrollable(figure, width, available) {
  if (width <= available) return figure;
  const div = document.createElement("div");
  div.style.overflowX = "auto";
  div.style.maxWidth = "100%";
  div.append(figure);
  return div;
}

// {org, category (labeled), share, count} rows for a comparison dimension.
// `exclude` drops those raw category codes from the display; shares still divide
// by each institution's full dimension total, so the remaining values stay
// "share of the whole" (e.g. hide the dominant Monograph row without inflating
// the rest).
export function compareRows(comparison, dim, label, exclude = []) {
  const d = comparison.dimensions[dim];
  const drop = new Set(exclude);
  const categories = d.categories.filter((c) => !drop.has(c));
  const rows = [];
  for (const o of d.institutions)
    for (const c of categories) {
      const n = d.matrix[o][c];
      rows.push({org: orgLabel(o), category: label(c), share: n == null ? null : n / d.totals[o], count: n});
    }
  // categories arrive sorted by consortium total (largest first → top of the y axis)
  return {rows, categories: categories.map(label), institutions: d.institutions.map(orgLabel)};
}

// The shared cell grid behind every heatmap on the site: percentage over count in
// each cell, sequential blues, suppressed cells (too few to report) as a faint
// tint rather than solid black. Callers differ only in where the rows come from
// and whether the color scale runs to the largest value present or to a fixed
// 100% — so those are arguments, and the geometry and formatting are not.
function cellHeatmap({
  rows,
  categories,
  institutions,
  marginLeft,
  legendLabel,
  colorDomain,
  // cells at or above this share of the scale get white text instead of black
  lightTextAbove,
  width: available,
}) {
  const {width} = geometry(institutions.length, available, marginLeft);
  const figure = Plot.plot({
    width,
    marginLeft,
    marginRight: MARGIN_RIGHT,
    marginTop: MARGIN_TOP,
    marginBottom: MARGIN_BOTTOM,
    height: plotHeight(categories.length),
    x: {label: null, domain: institutions, tickRotate: -30},
    y: {label: null, domain: categories},
    color: {
      scheme: "blues",
      legend: true,
      label: legendLabel,
      domain: colorDomain,
      tickFormat: ".0%",
      unknown: "color-mix(in srgb, var(--theme-foreground) 12%, transparent)",
    },
    marks: [
      Plot.cell(rows, {
        x: "org",
        y: "category",
        fill: "share",
        channels: {count: {value: "count", label: "records"}},
        tip: {format: {fill: ".1%", count: ","}},
      }),
      // percentage (top line) and raw count (smaller, dimmer, below)
      Plot.text(rows, {
        x: "org",
        y: "category",
        dy: -6,
        text: (d) => (d.share == null ? "" : (d.share * 100).toFixed(0) + "%"),
        fill: (d) => (d.share > lightTextAbove ? "white" : "black"),
        fontSize: 12,
      }),
      Plot.text(rows, {
        x: "org",
        y: "category",
        dy: 8,
        text: (d) => countFormat(d.count),
        fill: (d) => (d.share > lightTextAbove ? "white" : "black"),
        fillOpacity: 0.65,
        fontSize: 9.5,
      }),
    ],
  });
  return scrollable(figure, width, available);
}

// Share heatmap (category × institution) for a comparison dimension.
export function shareHeatmap(
  comparison,
  dim,
  label,
  {
    marginLeft = 155,
    exclude = [],
    legendLabel = "share of records",
    // Plot's own default, so a caller that forgets to pass Framework's `width`
    // gets the old size rather than a broken chart
    width = 640,
  } = {}
) {
  const {rows, categories, institutions} = compareRows(comparison, dim, label, exclude);
  const maxShare = d3.max(rows, (d) => d.share ?? 0);
  return cellHeatmap({
    rows,
    categories,
    institutions,
    marginLeft,
    legendLabel,
    width,
    colorDomain: [0, maxShare],
    lightTextAbove: maxShare * 0.55,
  });
}

// Coverage heatmap over a {per_org: [{org, coverage, counts}], keys} shape, where
// the values are overlapping coverage rather than a partition of a total — so the
// color scale is a fixed 0–100% and rows are free to sum past 100%.
export function coverageHeatmap(perOrg, keys, label, {marginLeft = 155, legendLabel = "share of records", width = 640} = {}) {
  const rows = perOrg.flatMap((o) =>
    keys.map((k) => ({org: orgLabel(o.org), category: label(k), share: o.coverage[k], count: o.counts[k]}))
  );
  return cellHeatmap({
    rows,
    categories: keys.map(label),
    institutions: perOrg.map((o) => orgLabel(o.org)),
    marginLeft,
    legendLabel,
    width,
    colorDomain: [0, 1],
    lightTextAbove: 0.55,
  });
}

// Count heatmap (category × institution) colored by raw count on a sqrt scale, so
// large and small institutions are both legible — for views where absolute scale
// is the point (e.g. archival material by type). Takes a single dimension object
// ({categories, institutions, matrix}), not the whole comparison. Suppressed cells
// (null) render as a faint tint.
export function countHeatmap(
  dimension,
  label,
  {
    marginLeft = 155,
    colorLabel = "records",
    width: available = 640,
    // sqrt by default so a dominant cell doesn't flatten the rest; callers whose
    // values are already on a comparable scale can ask for linear
    colorType = "sqrt",
    scheme = "blues",
    // the x axis is institutions in every use but the pairwise matrices, where
    // both axes are institutions and this is just orgLabel again
    institutionLabel = orgLabel,
    // normally unlabelled — the prose says what the axes are. The asymmetric
    // matrices need them, because which axis is which is the whole point.
    xLabel = null,
    yLabel = null,
  } = {}
) {
  const {categories, institutions, matrix} = dimension;
  const cats = categories.map(label);
  const insts = institutions.map(institutionLabel);
  const rows = [];
  for (const o of institutions)
    for (const c of categories) rows.push({org: institutionLabel(o), category: label(c), count: matrix[o][c]});
  const maxCount = d3.max(rows, (d) => d.count ?? 0);
  const {width} = geometry(insts.length, available, marginLeft);
  const figure = Plot.plot({
    width,
    marginLeft,
    marginRight: MARGIN_RIGHT,
    marginTop: MARGIN_TOP,
    marginBottom: MARGIN_BOTTOM,
    height: plotHeight(categories.length),
    x: {label: xLabel, domain: insts, tickRotate: -30},
    y: {label: yLabel, domain: cats},
    color: {
      scheme,
      legend: true,
      label: colorLabel,
      type: colorType,
      domain: [0, maxCount],
      unknown: "color-mix(in srgb, var(--theme-foreground) 12%, transparent)",
    },
    marks: [
      Plot.cell(rows, {
        x: "org",
        y: "category",
        fill: "count",
        tip: {format: {fill: (d) => d3.format(",")(d)}},
      }),
      Plot.text(rows, {
        x: "org",
        y: "category",
        text: (d) => countFormat(d.count),
        fill: (d) => (d.count > maxCount * 0.5 ? "white" : "black"),
        fontSize: 11,
      }),
    ],
  });
  return scrollable(figure, width, available);
}
