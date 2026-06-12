import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const here = path.dirname(fileURLToPath(import.meta.url));
const uiRoot = path.resolve(here, '..');

// Budgets rebased 2026-06-12: the minified bundle sits at ~106KB raw / ~32KB gz
// after the reader tabs + BRD panel + live-sync features; the old 60KB budget
// predated them and was never enforced in CI. ~25% headroom over current size.
const LIMITS = {
  [path.resolve(uiRoot, 'assets/viewer.bundle.js')]:  { raw: 136 * 1024, gz: 40 * 1024 },
  [path.resolve(uiRoot, 'assets/viewer.bundle.css')]: { raw: 15 * 1024, gz:  4 * 1024 },
};
let failed = false;
for (const [path, { raw, gz }] of Object.entries(LIMITS)) {
  const buf = readFileSync(path);
  const rawSz = buf.length;
  const gzSz = gzipSync(buf).length;
  const okRaw = rawSz <= raw, okGz = gzSz <= gz;
  console.log(`${path}  raw=${rawSz}/${raw} ${okRaw?'OK':'FAIL'}  gz=${gzSz}/${gz} ${okGz?'OK':'FAIL'}`);
  if (!okRaw || !okGz) failed = true;
}
process.exit(failed ? 1 : 0);
