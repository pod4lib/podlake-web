/*
 * Collect each POD member's cataloging-agency codes from the WorldCat Registry.
 *
 * HOW TO RUN
 *   1. Open https://registry.worldcat.org/registry/xsl/search-advanced in Chrome.
 *   2. Search using the "Name:" field in the *fields* section — NOT the "Find
 *      similar Name or Alias matches" box at the top, which is a different endpoint
 *      (see learnSearchUrl). Use something broad enough to paginate, e.g.
 *      Name = University, so there is a "Next" link on the results.
 *   3. Open DevTools -> Console, paste this whole file, press Enter.
 *   4. It prints progress and downloads a CSV when finished (a few minutes).
 *
 * WHY A CONSOLE SCRIPT AND NOT A COMMAND
 *   registry.worldcat.org sits behind Cloudflare bot protection, so plain HTTP from
 *   Python gets a 403 interstitial no matter what headers you send. Automating it
 *   would mean shipping Playwright to drive a real browser — a permanent dependency
 *   for a job run once or twice a year, against an undocumented internal endpoint
 *   (see SEARCH ENDPOINT below) that can change without notice. Pasting this into a
 *   browser you already have needs nothing installed, and when it breaks the damage
 *   is one obviously-broken script rather than a broken build.
 *
 * SEARCH ENDPOINT
 *   The search results page is a client-rendered template: fetching it returns
 *   literal <%=total_record%> placeholders. The data comes from an XHR to the same
 *   path with getData=getData, where `offset` is a PAGE NUMBER (1-based), not a
 *   record index. That is discovered below by reading the page's own request rather
 *   than hard-coding it, so this keeps working if the parameter list shifts.
 *
 * WHAT IT PRODUCES
 *   One row per (institution, code): pod_institution, marc_code, oclc_code,
 *   registry_name, registry_url — with exactly one of marc_code/oclc_code filled. A
 *   registry entity holding both (Harvard's Ernst Mayr library is OCLC symbol HMZ
 *   and MARC code MH-Z) therefore yields two rows, sharing a registry_url so the
 *   reviewer can open the record the claim came from.
 *
 * IT PRODUCES NOISE ON PURPOSE
 *   A name search for Brown returns John Brown University; for Chicago it returns
 *   Loyola and UIC. Those are kept, because some of them are actually used in the
 *   lake (IAY, 2,198 records; MUU, 4,288) and silently dropping them would hide the
 *   very rows a reviewer needs to rule on. Pruning is a human step.
 */

// The formal name is not enough. A university's main cataloging profile is usually
// registered under the LIBRARY's name, so searching only "Massachusetts Institute of
// Technology" returns nine branch profiles with no codes at all and misses MYG
// entirely — MIT would end up mapped with zero codes, reading 0% self-cataloged.
// Add variants whenever a member comes back suspiciously empty.
const MEMBERS = {
  brown: ["Brown University", "Brown University Library", "Brown University Libraries"],
  chicago: ["University of Chicago", "University of Chicago Library", "University of Chicago Libraries"],
  columbia: ["Columbia University", "Columbia University Libraries", "Columbia Libraries"],
  cornell: ["Cornell University", "Cornell University Library", "Cornell Library"],
  dartmouth: ["Dartmouth College", "Dartmouth Library", "Dartmouth College Library"],
  duke: ["Duke University", "Duke University Libraries", "Duke Libraries"],
  harvard: ["Harvard University", "Harvard Library", "Harvard University Library"],
  jhu: ["Johns Hopkins University", "Johns Hopkins University Libraries", "Sheridan Libraries", "Milton S. Eisenhower Library"],
  mit: ["Massachusetts Institute of Technology", "MIT Libraries", "MIT"],
  penn: ["University of Pennsylvania", "Penn Libraries", "University of Pennsylvania Libraries"],
  princeton: ["Princeton University", "Princeton University Library", "Princeton Library"],
  stanford: ["Stanford University", "Stanford University Libraries", "Stanford Libraries"],
  yale: ["Yale University", "Yale University Library", "Yale Library"],
};

const THROTTLE_MS = 120; // be a good citizen; this is a free public service

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* Learn the search request from the page itself rather than hard-coding it: hook
 * XHR, click through to a second page of results, and keep the URL that produced. */
async function learnSearchUrl() {
  const captured = [];
  const open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (m, u, ...rest) {
    captured.push(u);
    return open.call(this, m, u, ...rest);
  };
  const next = [...document.querySelectorAll("a")].find((a) => /^next$/i.test(a.textContent.trim()));
  if (!next) {
    throw new Error(
      "Run a search that returns more than one page first (e.g. Name = Harvard University), " +
        "so the script can observe the request the page makes."
    );
  }
  next.click();
  for (let i = 0; i < 40 && !captured.length; i++) await sleep(250);
  XMLHttpRequest.prototype.open = open;
  if (!captured.length) throw new Error("No search request observed — the page may have changed.");

  /* The advanced-search page offers TWO searches that hit /find with different
   * parameters, and only one of them is the one we want:
   *
   *   "Find similar Name or Alias matches" (the box at the top)
   *        -> relevancy_nameAlias=…      relevancy-ranked, ignores the fields below
   *   "Name:" (in the fields section)
   *        -> oclcAccountName=…          what this script drives
   *
   * Seeding from the first one is quiet and disastrous: the script sets
   * oclcAccountName, that endpoint ignores it, and all 13 institutions re-run the
   * original relevancy query — producing an identical row count for every member
   * and a CSV that looks plausible. Refuse instead. */
  const params = new URL(captured[0], location.origin).searchParams;
  if (!params.has("oclcAccountName")) {
    throw new Error(
      "seeded from the wrong search. The captured request uses " +
        `[${[...params.keys()].join(", ")}]. Run a search using the "Name:" field ` +
        'in the fields section (not "Find similar Name or Alias matches" at the ' +
        "top), page to a second page of results, then re-run this script."
    );
  }
  return captured[0];
}

/* Build a name search from the observed template.
 *
 * Every other search field is explicitly cleared. The template is whatever search
 * you happened to run to seed the script, and if that had a filter set — State,
 * Country, Institution Type — it would silently persist into all 13 lookups. A
 * Connecticut-filtered seed makes Cornell return zero rows, which looks like
 * "Cornell has no codes" rather than "you left a filter on". */
const searchUrl = (template, name, page) => {
  const u = new URL(template, location.origin);
  for (const field of [
    "institutionAlias", "instType", "country", "city", "subdivision",
    "postalCode", "regID", "oclcSymbol", "ISIL", "marcOrgCode", "blCode",
  ]) {
    u.searchParams.set(field, "");
  }
  u.searchParams.set("oclcAccountName", name);
  u.searchParams.set("offset", String(page));
  return u.toString();
};

/* The detail page embeds `var JSON_Obj = {...}` holding a typed identifiers array.
 * Brace-balance rather than regex the closing brace: the blob contains nested
 * objects and quoted braces in address fields. */
function extractJsonObj(html) {
  const k = html.indexOf("JSON_Obj");
  if (k < 0) return null;
  const start = html.indexOf("{", k);
  let depth = 0, inStr = false, esc = false;
  for (let i = start; i < html.length; i++) {
    const c = html[i];
    if (esc) { esc = false; continue; }
    if (c === "\\") { esc = true; continue; }
    if (c === '"') { inStr = !inStr; continue; }
    if (inStr) continue;
    if (c === "{") depth++;
    else if (c === "}" && --depth === 0) {
      try { return JSON.parse(html.slice(start, i + 1)); } catch { return null; }
    }
  }
  return null;
}

/* Never let a failure look like an empty result set.
 *
 * This originally did `await res.json().catch(() => [])`, which turns a 429, a
 * Cloudflare challenge, or any HTML error page into "this institution has no
 * codes" — silently, and only for whichever members happened to be in flight when
 * the throttling started. Reporting "cornell: 0 code rows" for a member that plainly
 * has codes is worse than crashing, because the CSV looks complete. */
async function getJson(url, what) {
  for (let attempt = 1; attempt <= 4; attempt++) {
    const res = await fetch(url);
    if (res.ok) {
      const text = await res.text();
      try {
        return JSON.parse(text);
      } catch {
        // an HTML body from a 200 means an interstitial, not data
        throw new Error(`${what}: expected JSON, got ${text.slice(0, 80)}`);
      }
    }
    if (res.status === 429 || res.status >= 500) {
      const wait = 2000 * attempt;
      console.warn(`${what}: HTTP ${res.status}, retrying in ${wait}ms`);
      await sleep(wait);
      continue;
    }
    throw new Error(`${what}: HTTP ${res.status}`);
  }
  throw new Error(`${what}: still failing after 4 attempts — stop and resume later`);
}

async function collect() {
  // Every request below is a relative path, so the wrong tab sends them all to the
  // wrong host and they fail as 404/500 rather than as anything self-explanatory.
  // www.oclc.org's member directory looks similar and is the easy mistake.
  if (location.hostname !== "registry.worldcat.org") {
    throw new Error(
      `run this on registry.worldcat.org, not ${location.hostname} — open ` +
        "https://registry.worldcat.org/registry/xsl/search-advanced and search first"
    );
  }
  const template = await learnSearchUrl();
  // Print the shape once, so a failing run is diagnosable without guesswork.
  const t = new URL(template, location.origin);
  console.log(
    `search endpoint: ${t.pathname} params=[${[...t.searchParams.keys()].join(",")}]`
  );
  const rows = [];
  const seenRow = new Set();

  for (const [org, names] of Object.entries(MEMBERS)) {
    let found = 0;
    // Deduplicate per institution, not globally. A registry entity can legitimately
    // come back under two members' searches, and a global set would credit it to
    // whichever ran first and silently give the other nothing.
    const seenId = new Set();
    for (const name of names) {
      for (let page = 1; page <= 30; page++) {
        const list = await getJson(searchUrl(template, name, page), `${org} search "${name}" p${page}`);
        if (!Array.isArray(list) || !list.length) break;
        for (const r of list) {
          if (seenId.has(r.identifier)) continue;
          seenId.add(r.identifier);
          const html = await (await fetch("/registry/Institutions/" + r.identifier)).text();
          const obj = extractJsonObj(html) || {};
          const ids = obj.identifiers || [];
          const val = (t) => {
            const hit = ids.find((x) => x.type === t);
            return hit ? String(hit.value).trim() : "";
          };
          const nl = r.nameLocation || {};
          const label = [nl.institutionName, nl.institutionAlias].filter(Boolean).join(" — ");
          const url = location.origin + "/registry/Institutions/" + r.identifier;
          // an entity with no codes cannot contribute a mapping row
          for (const [col, code] of [["marc", val("marcOrgCode")], ["oclc", val("oclcSymbol")]]) {
            if (!code) continue;
            const key = org + "|" + col + "|" + code;
            if (seenRow.has(key)) continue;
            seenRow.add(key);
            rows.push([org, col === "marc" ? code : "", col === "oclc" ? code : "", label, url]);
            found++;
          }
          await sleep(THROTTLE_MS);
        }
        if (list.length < 10) break;
        await sleep(THROTTLE_MS);
      }
    }
    console.log(`${org}: ${found} code rows`);
    // Zero is a real signal and always worth investigating: either the member's
    // profile is registered under a name none of the variants match (the reason
    // "Massachusetts Institute of Technology" alone finds nothing — the codes live
    // on "MIT Libraries"), or requests are being throttled and getJson above should
    // have thrown. Never treat it as "this member has no codes".
    if (!found) {
      console.warn(
        `  ${org}: NO codes found. Add a name variant above — try the library's own ` +
          `name rather than the university's. Confirm by searching the registry UI ` +
          `for one code you expect and seeing what institutionName it reports.`
      );
    }
  }
  return rows;
}

const esc = (s) => (/[",\n]/.test(s) ? '"' + String(s).replace(/"/g, '""') + '"' : String(s));

collect().then((rows) => {
  rows.sort((a, b) => a[0].localeCompare(b[0]) || (a[1] + a[2]).localeCompare(b[1] + b[2]));
  const csv =
    "pod_institution,marc_code,oclc_code,registry_name,registry_url\n" +
    rows.map((r) => r.map(esc).join(",")).join("\n") +
    "\n";
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = "institution_codes-candidates.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  console.log(`Done: ${rows.length} rows downloaded as institution_codes-candidates.csv`);
});
