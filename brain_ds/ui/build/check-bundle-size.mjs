import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const here = path.dirname(fileURLToPath(import.meta.url));
const uiRoot = path.resolve(here, '..');

// Budgets rebased 2026-07-12: the committed bundle is 156,821 bytes raw / 45,721 gz.
// Keep the established modest, rounded headroom so future UI work stays intentional.
const LIMITS = {
  [path.resolve(uiRoot, 'assets/viewer.bundle.js')]:  { raw: 160 * 1024, gz: 48 * 1024 },
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
