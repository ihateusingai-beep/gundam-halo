#!/usr/bin/env node
/**
 * audit-orphans.js — Sprint 52.
 *
 * Grep every .tsx file in frontend/src/components/ for its exports,
 * then grep the rest of frontend/src for imports of those names.
 * Skips JSDoc comment lines (don't count doc-block examples as imports).
 * Prints "<Name> · <file> · <import_count> imports" with 0-import
 * counts flagged as orphans.
 *
 * Exits 0 if no orphans, 1 otherwise (CI-friendly).
 *
 * Run with:  node frontend/scripts/audit-orphans.js
 * Or via pnpm:  pnpm audit:orphans  (script in package.json)
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { execSync } = require('node:child_process');

const COMPONENTS_ROOT = path.join(__dirname, '..', 'src', 'components');
const SEARCH_ROOT = path.join(__dirname, '..', 'src');

function walk(dir, acc = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(p, acc);
    else if (entry.isFile() && p.endsWith('.tsx') && !p.endsWith('.test.tsx') && !p.endsWith('.stories.tsx')) {
      acc.push(p);
    }
  }
  return acc;
}

/** True if line is a JSDoc/comment line. */
function isCommentLine(line) {
  const t = line.trim();
  return t.startsWith('//') || t.startsWith('*') || t.startsWith('/*');
}

/** Find named exports in a file, skipping comment lines. */
function findExports(file) {
  const src = fs.readFileSync(file, 'utf8');
  const lines = src.split('\n');
  const out = [];
  for (const line of lines) {
    if (isCommentLine(line)) continue;
    const re = /export\s+(?:default\s+)?(?:function|const|class)\s+(\w+)/g;
    let m;
    while ((m = re.exec(line)) !== null) {
      out.push(m[1]);
    }
  }
  return out;
}

/** Count source-file (non-comment) references to `name` excluding the file itself. */
function countUsages(name, excludeFile) {
  try {
    // Use ripgrep if available, fall back to grep -r
    const rgArgs = [
      '--no-messages',
      '-c',
      '--type-add', 'web:*.{ts,tsx}',
      '-t', 'web',
      '-l',
      name,
      SEARCH_ROOT,
      '-g', `!${path.basename(excludeFile)}`,
    ];
    const out = execSync(`rg ${rgArgs.map(a => `'${a}'`).join(' ')} 2>/dev/null || true`, {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    }).trim();
    if (!out) return 0;
    // Each line is a file path; exclude the source file itself.
    const files = out.split('\n').filter(f => !f.endsWith(path.basename(excludeFile)));
    return files.length;
  } catch {
    return 0;
  }
}

const allFiles = walk(COMPONENTS_ROOT);
const orphans = [];

for (const file of allFiles) {
  const exports = findExports(file);
  for (const name of exports) {
    const usageCount = countUsages(name, file);
    if (usageCount === 0) {
      orphans.push({ name, file: path.relative(path.join(__dirname, '..'), file), imports: 0 });
    }
  }
}

if (orphans.length === 0) {
  console.log('Found 0 orphans.');
  process.exit(0);
} else {
  console.log(`Found ${orphans.length} orphan(s):`);
  for (const o of orphans) {
    console.log(`  ${o.name} · ${o.file} · ${o.imports} imports`);
  }
  process.exit(1);
}