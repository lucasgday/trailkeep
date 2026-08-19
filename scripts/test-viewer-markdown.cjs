#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const files = [path.join(root, "viewer.html"), path.join(root, "docs", "index.html")];

function renderer(source) {
  const start = source.indexOf("function renderMarkdown");
  const end = source.indexOf("/* ---------- parse .md ---------- */", start);
  assert(start >= 0 && end > start, "renderMarkdown source was not found");
  return new Function(`
    const escapeHtml = value => String(value ?? "")
      .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;").replace(/'/g,"&#039;");
    const T = key => key === "table_region" ? "Table" : key;
    ${source.slice(start, end)}
    return renderMarkdown;
  `)();
}

const emptyHeaderTable = [
  "| | |",
  "|---|---|",
  "| **ven-46** | backfill de Kitt — 764 ventas |",
  "| **ven-11** | Ver en Kitt |",
].join("\n");

const alignedTable = [
  "| Name | Count |",
  "|:---|---:|",
  "| Alpha | 2 |",
].join("\n");

const escapedPipesTable = [
  "| Key | Value |",
  "|---|---|",
  "| one | a \\| b and `c|d` |",
].join("\n");

let expectedEmpty = "";
for (const file of files) {
  const renderMarkdown = renderer(fs.readFileSync(file, "utf8"));
  const empty = renderMarkdown(emptyHeaderTable);
  assert.match(empty, /class="md-table-wrap"/);
  assert.match(empty, /<table>/);
  assert.doesNotMatch(empty, /<thead>/, "an all-empty header should not create a blank band");
  assert.strictEqual((empty.match(/<tr>/g) || []).length, 2);
  assert.match(empty, /<strong>ven-46<\/strong>/);
  assert.match(empty, /backfill de Kitt — 764 ventas/);

  const aligned = renderMarkdown(alignedTable);
  assert.match(aligned, /<thead>/);
  assert.match(aligned, /scope="col" class="md-align-right"/);
  assert.match(aligned, /scope="col">Name<\/th>/);

  const escaped = renderMarkdown(escapedPipesTable);
  assert.strictEqual((escaped.match(/<td/g) || []).length, 2);
  assert.match(escaped, /a \| b and <code>c\|d<\/code>/);

  const plain = renderMarkdown("one | two");
  assert.doesNotMatch(plain, /<table>/);
  assert.match(plain, /<p>one \| two<\/p>/);

  const unsafe = renderMarkdown("| Name |\n|---|\n| <script>alert(1)</script> |");
  assert.doesNotMatch(unsafe, /<script>/);
  assert.match(unsafe, /&lt;script&gt;/);

  if (!expectedEmpty) expectedEmpty = empty;
  else assert.strictEqual(empty, expectedEmpty, "viewer and demo table output drifted");
}

console.log("Viewer Markdown tables: ok");
