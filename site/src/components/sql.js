import hljs from "npm:highlight.js/lib/core";
import sqlGrammar from "npm:highlight.js/lib/languages/sql";

hljs.registerLanguage("sql", sqlGrammar);

// A highlighted SQL <pre> block. Highlighting runs client-side using the token
// classes already in Observable Framework's theme, so it follows light/dark.
export function sqlBlock(code) {
  // Guard the empty case. highlight.js calls .replace() on whatever it is handed, so
  // an undefined query throws from deep inside the minified library ("can't access
  // property replace, e is undefined") with nothing pointing back to the caller.
  // Reachable whenever a page reads an artifact whose `sql` key a committed snapshot
  // predates, which is easy to do here — the site is always built from a snapshot
  // that can be older than the code.
  if (!code) return document.createComment("no sql");
  const el = document.createElement("code");
  el.className = "hljs language-sql";
  el.innerHTML = hljs.highlight(code, {language: "sql"}).value;
  const pre = document.createElement("pre");
  pre.style.overflowX = "auto";
  pre.style.fontSize = "13px";
  pre.style.lineHeight = "1.4";
  pre.append(el);
  return pre;
}
