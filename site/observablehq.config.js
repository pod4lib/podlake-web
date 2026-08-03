export default {
  title: "podlake",
  root: "src",
  pages: [
    {name: "Overview", path: "/"},
    {name: "Overlap & rarity", path: "/overlap"},
    {name: "Publication era", path: "/publication-era"},
    {name: "Languages", path: "/languages"},
    {name: "Place of publication", path: "/place-of-publication"},
    {name: "Format", path: "/format"},
    {name: "LC classification", path: "/lc-classification"},
    {name: "Serials", path: "/serials"},
    {name: "Completeness", path: "/completeness"},
    {name: "About the data", path: "/data"},
  ],
  // Bump Observable Plot's default label size (10px presentation attribute on
  // the root <svg>) for more legible axis, tick, and legend text everywhere.
  // Plain rule beats the presentation attribute; marks with an explicit
  // fontSize (e.g. heatmap cell labels) keep their own size.
  head: '<style>svg[class^="plot-"] { font-size: 13px; }</style>',
  header: "podlake — consortial collection analytics",
  footer:
    'Built from <a href="https://pod.stanford.edu/">POD</a> MARC data with ' +
    '<a href="https://ducklake.select/">DuckLake</a>. ' +
    "All figures are aggregates; no record-level data is published.",
  toc: false,
  pager: true,
};
