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
    // Section links injected under the active page in the sidebar (see the script
    // below). Indented past the page links, smaller and dimmer, so they read as
    // subordinate; the active one gets a rule down its left edge.
    "#observablehq-sidebar .section-nav { list-style: none; margin: 0.15rem 0 0.4rem; padding: 0; }" +
    "#observablehq-sidebar .section-nav a {" +
    " display: block; padding: 3px 12px 3px 24px; margin-left: 12px;" +
    " font-size: 14px; line-height: 1.35; text-decoration: none;" +
    " color: var(--theme-foreground-muted);" +
    " border-left: 2px solid var(--theme-foreground-faintest, rgba(128,128,128,0.25));" +
    " }" +
    "#observablehq-sidebar .section-nav a:hover {" +
    " color: var(--theme-foreground); background: var(--theme-background-alt);" +
    " }" +
    "#observablehq-sidebar .section-nav a.current {" +
    " color: var(--theme-foreground-focus); border-left-color: var(--theme-foreground-focus);" +
    " }" +
    "</style>" +
    "<script>addEventListener('DOMContentLoaded',()=>{" +
    "const nav=document.querySelector('#observablehq-sidebar');" +
    "if(!nav||nav.querySelector('.alpha-banner'))return;" +
    "const d=document.createElement('div');d.className='alpha-banner';" +
    "d.innerHTML='<strong>Alpha preview</strong> — podlake is under active development; the data and visualizations here are exploratory, may be wrong, and will change.';" +
    "const firstOl=nav.querySelector('ol');" +
    "firstOl.insertAdjacentElement('afterend', d);" +
    "});</script>" +
    // Sidebar section links for the current page. Built at load from the page's
    // own <h2 id> elements rather than listed in `pages` above, so headings can
    // be added, renamed or reordered without a config edit and the anchors can
    // never drift from the markdown. Nested inside the active <li> — an <ol> may
    // only contain <li>, so it cannot be a sibling of one.
    "<script>addEventListener('DOMContentLoaded',()=>{" +
    "const nav=document.querySelector('#observablehq-sidebar');" +
    "const active=nav&&nav.querySelector('.observablehq-link-active');" +
    "const main=document.querySelector('#observablehq-main');" +
    "if(!nav||!active||!main||active.querySelector('.section-nav'))return;" +
    "const hs=[...main.querySelectorAll('h2[id]')];" +
    // one section is the whole page, so a sub-nav would just restate the title
    "if(hs.length<2)return;" +
    "const ol=document.createElement('ol');ol.className='section-nav';" +
    "const links=hs.map(h=>{" +
    "const li=document.createElement('li');const a=document.createElement('a');" +
    "a.href='#'+h.id;a.textContent=h.textContent;li.append(a);ol.append(li);return a;});" +
    "active.append(ol);" +
    // mark whichever section the reader is currently in, the way the framework's
    // own right-hand toc does
    "const sync=()=>{" +
    "let i=0;hs.forEach((h,j)=>{if(h.getBoundingClientRect().top<120)i=j;});" +
    "links.forEach((a,j)=>a.classList.toggle('current',j===i));};" +
    // `load` and `hashchange` as well as `scroll`: arriving on a URL that already
    // carries a hash jumps the page without necessarily firing a scroll event
    // after this handler has run, which would otherwise leave the wrong section
    // marked on exactly the links people bookmark and share.
    "addEventListener('scroll',sync,{passive:true});" +
    "addEventListener('hashchange',sync);addEventListener('load',sync);sync();" +
    "});</script>",
  header: "podlake — consortial collection analytics",
  footer:
    'Built from <a href="https://pod.stanford.edu/">POD</a> MARC data with ' +
    '<a href="https://ducklake.select/">DuckLake</a>. ' +
    "All figures are aggregates; no record-level data is published.",
  toc: false,
  pager: true,
};
