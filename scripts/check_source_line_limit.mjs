#!/usr/bin/env node
/**
 * Enforce Phase 2 max 400 lines for hand-written application source files.
 * Usage: node scripts/check_source_line_limit.mjs [relative-root...]
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const MAX = 400;
const roots = process.argv.slice(2);
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const targets = roots.length
  ? roots.map((r) => path.join(repoRoot, r))
  : [path.join(repoRoot, 'mobile/linas-ai/src')];

const EXT = new Set(['.ts', '.tsx', '.js', '.jsx', '.py']);
const IGNORE_DIRS = new Set(['node_modules', '.git', 'dist', 'build', '__pycache__']);

/** @type {string[]} */
const offenders = [];

/**
 * @param {string} filePath
 */
function checkFile(filePath) {
  const ext = path.extname(filePath);
  if (!EXT.has(ext)) return;
  const text = fs.readFileSync(filePath, 'utf8');
  const lines = text.split(/\r?\n/).length;
  if (lines > MAX) {
    offenders.push(`${path.relative(repoRoot, filePath)}: ${lines} lines`);
  }
}

/**
 * @param {string} dir
 */
function walk(dir) {
  if (!fs.existsSync(dir)) return;
  const st = fs.statSync(dir);
  if (st.isFile()) {
    checkFile(dir);
    return;
  }
  for (const name of fs.readdirSync(dir)) {
    if (IGNORE_DIRS.has(name)) continue;
    walk(path.join(dir, name));
  }
}

for (const t of targets) walk(t);

if (offenders.length) {
  console.error(`Source files exceed ${MAX} lines:`);
  for (const o of offenders) console.error(`  ${o}`);
  process.exit(1);
}
console.log(`OK: no source files over ${MAX} lines in checked roots`);
