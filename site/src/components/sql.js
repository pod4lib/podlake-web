import hljs from "npm:highlight.js/lib/core";
import sqlGrammar from "npm:highlight.js/lib/languages/sql";
import {html} from "npm:htl";

hljs.registerLanguage("sql", sqlGrammar);

// A highlighted SQL <pre> block. Highlighting runs client-side using the token
// classes already in Observable Framework's theme, so it follows light/dark.
export function sqlBlock(code) {
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

// A titled card wrapping one showcase query ({title, note, sql}).
export function sqlCard(q) {
  return html`<div class="card" style="margin: 1rem 0;">
    <h3 style="margin-top: 0;">${q.title}</h3>
    <p style="max-width: 640px;">${q.note}</p>
    ${sqlBlock(q.sql)}
  </div>`;
}
