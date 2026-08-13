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
  // Global CSS: bump Plot's default label size, widen and enlarge the prose,
  // and style the alpha-preview banner that the script below inserts into the
  // sidebar. These rules override the framework's own stylesheet by source
  // order — `head` is emitted after the theme <link>.
  head:
    "<style>" +
    'svg[class^="plot-"] { font-size: 13px; }' +
    // The framework caps the whole content area at 1440px, which on a desktop
    // display leaves a few hundred pixels unused on either side — very visible
    // now that the heatmaps grow to fill whatever they are given. Raised rather
    // than removed: past ~1900px the wide charts stop gaining anything and the
    // prose is stranded beside an enormous empty gutter.
    ":root { --observablehq-max-width: 1920px; }" +
    // Bigger body type than the framework's 17px, and prose that flows to fill
    // the content area instead of sitting in a fixed 640px column beside the
    // full-width charts. The framework caps every text element at 640/600px;
    // dropping the cap lets text and charts share one right edge, so the page
    // reads as one column of content rather than a narrow column with a wide
    // gutter. The remaining bound is `--observablehq-max-width` above, which
    // keeps lines from running the full width of a very large display.
    // `font-size` only, so the framework's 1.5 line-height and serif family
    // still apply; the sidebar and charts set their own sizes and are
    // unaffected.
    "body { font-size: 20px; }" +
    // One right margin for everything, text and charts alike. It goes on <main>
    // rather than on the individual elements because the framework's reactive
    // `width` — which every chart is sized from — is that element's
    // *contentRect*, so padding here shrinks `width` too and the charts inherit
    // the same margin automatically. Setting it per-element instead would inset
    // the prose while leaving every chart to subtract the margin by hand.
    "main { padding-right: 3rem; }" +
    // With the margin handled above, prose flows to the full content width
    // instead of the framework's fixed 640/600px column, so text and charts
    // share one right edge and the page reads as a single column of content.
    "p, table, figure, figcaption, h1, h2, h3, h4, h5, h6, .katex-display," +
    " blockquote, ol, ul, .note, .tip, .warning, .caution," +
    " #observablehq-footer nav {" +
    " max-width: none;" +
    " }" +
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
