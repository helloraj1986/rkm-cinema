/* Phase 26 — in-app Jellyfin playback wiring.
   Loads api.js + app.js in a minimal browser VM and asserts:
     - st() surfaces watch.jellyfin.item_id as jellyfinItemId
     - cardMarkup renders "Play in RKM" (data-act="play" + data-jf-item) as the
       primary action when Jellyfin is the available source with a native id,
       with the Jellyfin deep-link kept beside it
     - playInRkmMarkup renders a button only when item_id is present
     - modalDownloadButton prepends data-role="play-jellyfin" for jellyfin-only
   Node-only. Exits non-zero on failure. */
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, '..');
let failures = 0;

function ok(name, fn) {
  try { fn(); console.log('PASS  ' + name); }
  catch (e) { failures++; console.log('FAIL  ' + name + '\n      ' + (e && e.message)); }
}

function makeEl() {
  return {
    querySelector: () => makeEl(), querySelectorAll: () => [], addEventListener: () => {},
    removeEventListener: () => {}, appendChild: () => {}, before: () => {}, remove: () => {},
    focus: () => {}, scrollIntoView: () => {}, setAttribute: () => {}, getAttribute: () => null,
    classList: { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false },
    style: {}, dataset: {}, innerHTML: '', value: '', textContent: '', disabled: false, className: '',
  };
}

function load() {
  const sandbox = {
    console: { ...console, error: () => {}, warn: () => {}, log: () => {} },
    setTimeout: () => 0, clearTimeout: () => 0, setInterval: () => 0,
    Math, Date, JSON, parseInt, parseFloat, isFinite,
    encodeURIComponent, decodeURIComponent,
    localStorage: { getItem: () => '', setItem: () => {}, removeItem: () => {} },
    location: { hash: '#/discover' },
    fetch: async () => { throw new Error('no network'); },
  };
  sandbox.window = sandbox;
  sandbox.window.addEventListener = () => {};
  sandbox.window.scrollTo = () => {};
  sandbox.window.open = () => {};
  sandbox.document = { querySelector: () => makeEl(), querySelectorAll: () => [], createElement: () => makeEl(), addEventListener: () => {}, removeEventListener: () => {}, body: { appendChild: () => {}, style: {} }, documentElement: makeEl() };
  sandbox.requestAnimationFrame = () => 0;
  const ctx = vm.createContext(sandbox);
  const run = (code) => vm.runInContext(code, ctx, { timeout: 3000 });

  run(readFileSync(path.join(root, 'api.js'), 'utf8'));
  const appSrc = readFileSync(path.join(root, 'app.js'), 'utf8')
    + '\n; globalThis.__rkm = {'
    + ' setRes(map, flag=true){ RES = map; USES_RESOURCE_API = flag; },'
    + ' st, cardMarkup, modalDownloadButton, playInRkmMarkup, canWatch, libraryCard'
    + ' };';
  run(appSrc);
  return { api: run('window.API'), get: (k) => run('globalThis.__rkm.' + k) };
}

const t = load();
const entry = (o) => Object.assign({ imdbId: 'tt0133093', tmdbId: 603, type: 'movie', title: 'The Matrix', year: 1999 }, o);
const JF_ID = '53756c83d38f47afbb1fd721dd089711';
const jfResource = () => ({
  id: 'movie:tmdb:603', title: 'The Matrix', year: 1999, type: 'movie', status: 'available',
  capabilities: { can_download: false, can_watch: true },
  watch: { jellyfin: { available: true, url: 'http://jf/web/index.html#/details?id=' + JF_ID, error: null, item_id: JF_ID } },
  acquisition: { provider: 'radarr', status: 'available' },
});

ok('st: exposes watch.jellyfin.item_id as jellyfinItemId', () => {
  t.get('setRes')({ 'movie:tmdb:603': jfResource() });
  const s = t.get('st')(entry());
  assert.strictEqual(s.jellyfinItemId, JF_ID);
  assert.strictEqual(s.watch.jellyfin.item_id, JF_ID);
});

ok('cardMarkup: jellyfin+id -> Play in RKM (data-act=play) primary, Jellyfin deep-link kept', () => {
  t.get('setRes')({ 'movie:tmdb:603': jfResource() });
  const html = t.get('cardMarkup')(entry());
  assert.ok(/data-act="play"/.test(html), 'expected Play in RKM button');
  assert.ok(new RegExp('data-jf-item="' + JF_ID + '"').test(html));
  assert.ok(/Play in RKM/.test(html));
  // Secondary Jellyfin deep-link preserved.
  assert.ok(/data-act="watch-jellyfin"/.test(html));
  // Not a Download.
  assert.ok(!/data-act="download"/.test(html));
});

ok('cardMarkup: jellyfin available WITHOUT id -> deep-link only, no Play in RKM', () => {
  t.get('setRes')({ 'movie:tmdb:603': {
    ...jfResource(),
    watch: { jellyfin: { available: true, url: 'http://jf/x', error: null } },
  } });
  const html = t.get('cardMarkup')(entry());
  assert.ok(/data-act="watch-jellyfin"/.test(html));
  assert.ok(!/data-act="play"/.test(html), 'no in-app play without a native item id');
});

ok('playInRkmMarkup: empty without item_id', () => {
  assert.strictEqual(t.get('playInRkmMarkup')({ available: true, url: 'http://jf/x' }, entry()), '');
  assert.strictEqual(t.get('playInRkmMarkup')(null, entry()), '');
});

ok('playInRkmMarkup: button with data-jf-item when id present', () => {
  const html = t.get('playInRkmMarkup')({ available: true, url: 'http://jf/x', item_id: JF_ID }, entry());
  assert.ok(/data-role="play-jellyfin"/.test(html));
  assert.ok(new RegExp('data-jf-item="' + JF_ID + '"').test(html));
  assert.ok(/Play in RKM/.test(html));
});

ok('modalDownloadButton: jellyfin-only watch -> Play in RKM first', () => {
  t.get('setRes')({ 'movie:tmdb:603': jfResource() });
  const s = t.get('st')(entry());
  const html = t.get('modalDownloadButton')(entry(), s);
  assert.ok(/data-role="play-jellyfin"/.test(html));
  assert.ok(new RegExp('data-jf-item="' + JF_ID + '"').test(html));
  // deep-link stays
  assert.ok(/Watch on Jellyfin/.test(html));
});

ok('libraryCard (Library view): Play in RKM + Jellyfin deep-link when item_id present', () => {
  const html = t.get('libraryCard')({
    title: '500 Days of Summer', year: 2009, type: 'movie', item_id: JF_ID,
    jellyfinUrl: 'http://jf/web/index.html#/details?id=' + JF_ID,
  });
  assert.ok(/data-act="play"/.test(html), 'expected Play in RKM on Library cards');
  assert.ok(new RegExp('data-jf-item="' + JF_ID + '"').test(html));
  assert.ok(/Play in RKM/.test(html));
  // deep-link button still present
  assert.ok(/data-act="watch-jellyfin"/.test(html));
});

ok('libraryCard: no item_id -> no Play in RKM', () => {
  const html = t.get('libraryCard')({ title: 'X', year: 2000, type: 'movie' });
  assert.ok(!/data-act="play"/.test(html));
});

process.exit(failures ? 1 : 0);