# Maintaining `institution-codes.csv`

Which MARC agency code belongs to which POD member. The records don't say, and it
can't be derived, so this is a curated file. This is the process for changing it.

It affects only the views that ask *who catalogued a record* — the `self` and `pod`
buckets and flow matrix from `040 $a`, the original-cataloging timeline, and the
`local_system` / `pod_system` channels from `035`. Everything else per-institution
keys on `org` in `record_meta` and is unaffected.

## When you need to touch it

- **A member joins POD.** The extract refuses to build for an unmapped institution
  rather than publishing a plausible-looking 0% self-cataloged for it, so this is
  forced rather than optional.
- **A member tells you about a code.** Retired codes are the common case: they appear
  in old records but in no current registry, so only the member can confirm them.
- **A self-attribution figure looks too low.** Those figures are floors. A library
  whose codes are missing is indistinguishable from one that does little original
  cataloging.

## The file

One row per (institution, code). Exactly one of `marc_code` / `oclc_code` is filled —
they're different namespaces and the distinction is load-bearing.

| column | |
| --- | --- |
| `pod_institution` | the `org` as it appears in the lake |
| `marc_code` | MARC Organization Code, or empty |
| `oclc_code` | OCLC symbol, or empty |
| `registry_name` | the registry's own name for the entity, for a human reading the row |
| `registry_url` | link to the record the claim came from |

Codes are stored in the registry's display form (`CtY`, `NcD`, `MH-Ar`). Comparison
upper-cases both sides, so case in the file is cosmetic. Hyphens are **not**
cosmetic — see below.

`podlake_web.codes` validates the file on load and fails the build on mechanical
breakage: a code claimed by two institutions, both or neither code column filled, or
a MARC family reaching into another institution's codes. It never validates
judgement; whether a code really belongs to a member is yours to decide.

## Proposing rows

`tools/registry-codes.js` is a browser console script — paste it into a
[WorldCat Registry](https://registry.worldcat.org/registry/xsl/search-advanced) tab
and it downloads candidate rows. Read its header comment before running it; the two
mistakes that produce quietly wrong output are documented there.

It isn't part of `podlake-web` on purpose. The registry sits behind bot protection,
so a program would need a headless browser — a permanent dependency, driving an
undocumented internal endpoint, for a job run once or twice a year. A console script
needs nothing installed, and when it breaks it breaks visibly instead of taking the
build with it.

The script only proposes. Most of what it returns is noise — a search for Brown
returns John Brown University; one for Chicago returns Loyola and UIC — and some of
that noise is *used in the lake*, so it can't be filtered automatically without
hiding the rows that most need a decision.

Regenerating overwrites; git is the undo. Note that hand-added rows (a retired code a
member confirmed) have no registry backing and will not come back, so check the diff.

## Two things that will bite you

**Search by library name, not just the institution's.** A university's cataloging
profile is usually registered under the *library's* name. Searching
`Massachusetts Institute of Technology` returns branch profiles with no codes at all;
the codes live on `MIT Libraries`. Same for `Dartmouth Library`. A member coming back
with zero codes almost always means a missing name variant, not a member that does no
original cataloging — the script warns when this happens.

**Don't normalize away hyphens.** MARC codes are hierarchical on the hyphen, so a
listed `CtY` also covers `CtY-BR`, and that expansion is why the file doesn't have to
enumerate every branch library. But the hyphen is required, not a nicety: `PU-L` is
Penn's Biddle Law Library and `PUL` is Princeton University Library. LC's own registry
publishes `PU-L` with `normalized: pul`, which conflates the two — following that
would move Princeton's records to Penn.

## Checking your work

`make probe CATALOG=…` dumps every agency code each institution actually uses, with
how concentrated each is. Sort by `pct_at_this_org`: a code used almost exclusively at
one member is worth a look. It isn't proof — single-subscriber vendor namespaces look
identical — but it's how you find codes the registries don't know about.

The **About the data** page renders the map as published — two tables, one per
namespace — so the effect of an edit is visible after the next extract.
