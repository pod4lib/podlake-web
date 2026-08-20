# Tier 2 — planning notes (NOT scheduled)

**Status:** exploratory. Captured so the design isn't lost, but **deferred** — do
not execute yet. See "Sequencing" below.

## Sequencing / current direction

The near-term priority is **not** Tier 2. It is to confirm that the Tier‑1
"each institution within the whole" visualizations and presentation hold up:

1. Verify Tier 1 on the **full dataset** once it is built (a full extract +
   rebuild). Watch the two heavy queries (`coverage`'s per-record group-by and
   the `pairwise` self-join), the 13×N chart/heatmap rendering, suppression
   against real long tails, and artifact sizes.
2. Refine the existing views (Overview, Overlap & rarity, Collections, Metadata
   quality) based on how they read at full scale.

**Open strategic question that should be settled before scheduling Tier 2:**
is comparing one institution against *specific others* actually the most
valuable next step, or is deepening the "institution within the whole" framing
(each library seen against the consortium aggregate — what Tier 1 already does)
the better investment? The POD user stories ask for both; the "within the whole"
angle is simpler, safer to publish, and may cover most of the need. Tier 2 below
is documented as an option, not a commitment.

## What Tier 2 would be

Client-side "my institution vs. selected partners": for any subset of
institutions, show overlap (works all hold), uniqueness (works only I hold within
the group), and the rarity curve for that group — computed live in the browser,
no server, no record-level data exposed. This is the docs' "comparative
collection analysis" (e.g. overlap with ReCap or a chosen set of partners).

The key realization: this UX is about **counts and proportions**, not lists of
titles. That distinction drives the whole design.

## Encoding options

The browser needs, per work (`goldrush_key`), which institutions hold it. Three
ways to represent that:

1. **Per-work membership table** — one row per work: `(work_id, N-bit mask)`.
   ~10M works today, likely 30–50M+ at full IPLC scale → tens of millions of
   rows, ~50–150 MB compressed. Overlap *counts* scan every row, so DuckDB-WASM's
   range reads don't help much. Closest to record-level → largest disclosure
   exposure. **Not preferred.**

2. **Mask histogram (recommended workhorse)** — for counts we don't need per-work
   rows at all, only "how many works have each holding pattern." With N
   institutions there are ≤ 2^N possible masks (far fewer populated), so the
   entire dataset is a table of **≤ (2^N − 1) rows: `(mask, work_count)`** — a few
   KB to tens of KB. Every subset count is a bitwise predicate summed over it:
   - overlap with set S: Σ counts where `(mask & S) == S`
   - unique to me within S: counts where `mask & S == {me}`
   - held by exactly k of S; rarity curve for S; etc.

   Instant, fully client-side, needs no server and **not even DuckDB-WASM** (plain
   JS over a tiny file). Being an aggregate (counts per holding-pattern), it
   inherits Tier‑1's disclosure story.

3. **Per-institution roaring bitmaps** — bitwise-AND across selected institutions
   + popcount. Compact/fast, could support drill-to-list, but ~10–40 MB and needs
   a bitmap library. Overkill for counts-only.

## Recommendation

- **Mask histogram** as the Tier‑2 workhorse — the whole comparative-counts story
  in tens of KB, client-side, no backend.
- **Dimensional cubes** as a fast-follow (`mask × decade`, `mask × language`,
  `mask × format`): still aggregate, still small (sparse), and they unlock views
  like "our uniquely-held pre-1900 material vs. the group." **This is where
  DuckDB-WASM earns its place** — ship a modest Parquet cube, run arbitrary subset
  predicates in the browser.
- **Drill-to-list** ("show me those 312 titles") is inherently record-level →
  **Tier 3**, gated. The histogram deliberately stops at counts.

## Extract sketch

A new query assigns each institution a bit position, `bit_or`s membership per
work, then groups to `(mask, count)`, plus a small legend mapping bit →
institution:

```sql
WITH orgs AS (
  SELECT org, row_number() OVER (ORDER BY org) - 1 AS bit
  FROM (SELECT DISTINCT org FROM record_meta)
),
mem AS (
  SELECT goldrush_key, bit_or(1 << o.bit) AS mask
  FROM record_meta m JOIN orgs o USING (org)
  GROUP BY goldrush_key
)
SELECT mask, count(*) AS works FROM mem GROUP BY mask
```

Output: `masks.json` = `{ legend: [{bit, org}], masks: [{mask, works}] }` (tiny).

## Disclosure control for rare masks

A pattern like "held only by {small college}, 3 works" could be sensitive.
Proposed fix: fold sub-threshold masks into their *held-by-N* bucket — preserves
the rarity curve while hiding the specific institution set. Same review gate as
Tier 1: POD signs off on the published surface first.

## Open decisions (settle before scheduling)

1. Is Tier 2 the right next focus at all, vs. deepening "within the whole"? (see
   Sequencing).
2. Counts-only for v1 (drill-to-list punted to Tier 3)? Recommended: yes.
3. Rare-mask disclosure approach + POD review.
4. Histogram-first vs. cubes-first. Recommended: histogram first.
5. Scale unknown — distinct-work count at full IPLC. Known once the full lake is
   built; nothing here is at risk until far past current size.
