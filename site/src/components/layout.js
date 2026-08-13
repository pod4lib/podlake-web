// Small-multiples layout. Plot needs a pixel width, but the number of columns it
// should divide by is decided by CSS, so the two have to be derived from the same
// breakpoints or the panels come out the wrong size.

// Framework's grid.css applies a column count by container query, not by the
// class alone: `grid-cols-4` is four columns only at ≥1080px and falls back to
// two below that, and both it and `grid-cols-2` collapse to one below 640px.
// Asking for four columns at a 1072px container therefore renders two — so
// sizing panels at width/4 leaves each one filling half its card. This returns
// the count the CSS will actually apply.
//
// Keep in sync with node_modules/@observablehq/framework/dist/style/grid.css.
export function gridCols(n, width) {
  const wanted = n <= 6 ? 2 : n <= 12 ? 3 : 4;
  if (wanted === 4) return width >= 1080 ? 4 : width >= 640 ? 2 : 1;
  if (wanted === 3) return width >= 720 ? 3 : 1;
  return width >= 640 ? 2 : 1;
}

// Width for a plot inside a `.card` in one of those grids. The allowance covers
// the 1rem grid gap plus the card's own padding and border; the floor only binds
// on a phone, where the grid is one column anyway.
export function panelWidth(cols, width, {chrome = 60, min = 230} = {}) {
  return Math.max(min, Math.floor(width / cols) - chrome);
}

// Column count and exact track width for a hand-rolled panel grid (the genre and
// link-host small multiples, which are bare <figure>s rather than `.card`s).
// `repeat(auto-fit, minmax(Npx, 1fr))` alone isn't enough: it sizes the *tracks*
// but the plot inside still needs a pixel width, and if that width is a constant
// the panel leaves a dead strip in every track. This returns both, so the two
// agree and the panels actually fill the row.
export function autoGrid(width, {min = 440, gap = 24} = {}) {
  const cols = Math.max(1, Math.floor((width + gap) / (min + gap)));
  return {cols, panel: Math.floor((width - gap * (cols - 1)) / cols)};
}
