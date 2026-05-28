import esbuild from 'esbuild';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const watch = process.argv.includes('--watch');
const here = path.dirname(fileURLToPath(import.meta.url));
const uiRoot = path.resolve(here, '..');

const common = {
  entryPoints: ['src/main.ts'],
  // CSS side bundle output path: assets/viewer.bundle.css (generated from src/main.css import)
  absWorkingDir: uiRoot,
  bundle: true,
  format: 'iife',
  globalName: 'BrainDsViewer',
  target: ['es2020'],
  charset: 'utf8',
  logLevel: 'info',
  legalComments: 'none',
  treeShaking: true,
};
const build = await esbuild.context({
  ...common,
  outfile: path.resolve(uiRoot, 'assets/viewer.bundle.js'),
  minify: !watch,
  sourcemap: watch ? 'inline' : false,
});
if (watch) { await build.watch(); }
else { await build.rebuild(); await build.dispose(); }
