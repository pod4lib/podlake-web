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
    {name: "Archives & manuscripts", path: "/archives"},
    {name: "Electronic resources", path: "/electronic"},
    {name: "Completeness", path: "/completeness"},
    {name: "Source of cataloging", path: "/cataloging-source"},
    {name: "Original cataloging over time", path: "/original-cataloging"},
    {name: "How records arrived", path: "/record-channels"},
    {name: "About the data", path: "/data"},
  ],
  // Bump Observable Plot's default label size (10px presentation attribute on
  // the root <svg>) for more legible axis, tick, and legend text everywhere.
  // Plain rule beats the presentation attribute; marks with an explicit
  // fontSize (e.g. heatmap cell labels) keep their own size.
  // Global CSS: bump Plot's default label size, and style the alpha-preview
  // banner that the script below inserts into the sidebar.
  head:
    "<style>" +
    'svg[class^="plot-"] { font-size: 13px; }' +
    "#observablehq-sidebar .alpha-banner {" +
    " margin: 0.5rem 0.75rem 0.75rem; padding: 0.5rem 0.6rem;" +
    " background: #b45309; color: #fff; border-radius: 6px;" +
    " font-size: 0.75rem; line-height: 1.4;" +
    " }" +
    "#observablehq-sidebar .alpha-banner strong { text-transform: uppercase; letter-spacing: 0.05em; }" +
    "</style>" +
    "<script>addEventListener('DOMContentLoaded',()=>{" +
    "const nav=document.querySelector('#observablehq-sidebar');" +
    "if(!nav||nav.querySelector('.alpha-banner'))return;" +
    "const d=document.createElement('div');d.className='alpha-banner';" +
    "d.innerHTML='<strong>Alpha preview</strong> — podlake is under active development; the data and visualizations here are exploratory, may be wrong, and will change.';" +
    "const firstOl=nav.querySelector('ol');" +
    "firstOl.insertAdjacentElement('afterend', d);" +
    "});</script>",
  header: "podlake — consortial collection analytics",
  footer:
    'Built from <a href="https://pod.stanford.edu/">POD</a> MARC data with ' +
    '<a href="https://ducklake.select/">DuckLake</a>. ' +
    "All figures are aggregates; no record-level data is published.",
  toc: false,
  pager: true,
};
