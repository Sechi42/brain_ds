import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const here = path.dirname(fileURLToPath(import.meta.url));
const uiRoot = path.resolve(here, '..');

const LIMITS = {
  [path.resolve(uiRoot, 'assets/viewer.bundle.js')]:  { raw: 60 * 1024, gz: 20 * 1024 },
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
