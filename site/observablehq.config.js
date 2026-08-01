export default {
  title: "podlake",
  root: "src",
  pages: [
    {name: "Overview", path: "/"},
    {name: "Overlap & rarity", path: "/overlap"},
    {name: "Collections", path: "/collections"},
    {name: "Metadata quality", path: "/quality"},
    {name: "About the data", path: "/data"},
    {name: "Query it yourself", path: "/query"},
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
