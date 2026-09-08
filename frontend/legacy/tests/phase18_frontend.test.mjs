/* Phase 11 — frontend capability-driven rendering (spec §19/§20).
   Loads api.js + app.js in a minimal browser VM and asserts:
     - mediaIdOf / legacyStatusToResource normalization
     - st() derives state/capabilities/watch from the §18 resource
     - downloadButton / heroDownloadButton / modalDownloadButton branch on
       capabilities.can_download, can_watch and watch.{plex,emby}.available
       (never showing Download when can_watch; never provider-name branching)
     - _applyRequestResult updates RES without waiting for the poll
   Node-only. Exits non-zero on failure; prints TAP-ish PASS lines. */
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

function loadPhase11() {
  const sandbox = {
    console: { ...console, error: () => {}, warn: () => {}, log: () => {} },
    setTimeout: () => 0, clearTimeout: () => 0, setInterval: () => 0,
    Math, Date, JSON, parseInt, parseFloat, isFinite,
    encodeURIComponent, decodeURIComponent,
    localStorage: { getItem: () => '', setItem: () => {}, removeItem: () => {} },
    location: { hash: '#/discover' },
    fetch: async () => { throw new Error('no network'); },
  };
  // In a browser `window` IS the global object, so `window.API` and bare `API`
  // must collide. Self-reference window so api.js's `global.API = API` lands
  // where app.js reads it.
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
    + ' setLegacy(map){ LEGACY_STATUS = map; USES_RESOURCE_API = false; RES = {}; },'
    + ' st, downloadButton, heroDownloadButton, modalDownloadButton, cardMarkup,'
    + ' _applyRequestResult, canWatch, canDownload, mediaIdOf: API.mediaIdOf, _resFor'
    + ' };';
  run(appSrc); // init IIFE catches the failed fetch
  return { api: run('window.API'), get: (k) => run('globalThis.__rkm.' + k) };
}

const t = loadPhase11();
const entry = (o) => Object.assign({ imdbId: 'tt0133093', tmdbId: 603, type: 'movie', title: 'The Matrix', year: 1999 }, o);
const resource = (o) => Object.assign({
  id: 'movie:tmdb:603', title: 'The Matrix', year: 1999, type: 'movie', status: 'available',
  capabilities: { can_download: false, can_watch: true },
  watch: { plex: { available: true, url: 'https://plex/x' } },
  acquisition: { provider: 'radarr', status: 'available' },
}, o);
const legacy = (o) => Object.assign({ state: 'available', service: 'radarr', plexUrl: 'https://plex/x' }, o);

/* mediaIdOf */
ok('mediaIdOf: tmdb preferred', () => assert.strictEqual(t.api.mediaIdOf(entry()), 'movie:tmdb:603'));
ok('mediaIdOf: series imdb fallback', () => assert.strictEqual(t.api.mediaIdOf(entry({ tmdbId: 0, isSeries: true })), 'tv:imdb:tt0133093'));
ok('mediaIdOf: tvdb fallback', () => assert.strictEqual(t.api.mediaIdOf(entry({ tmdbId: 0, isSeries: true, imdbId: '', tvdbId: 789 })), 'tv:tvdb:789'));

/* legacyStatusToResource */
ok('legacy->resource: available -> can_watch + watch.plex', () => {
  const r = t.api.legacyStatusToResource(entry(), legacy());
  assert.strictEqual(r.capabilities.can_watch, true);
  assert.strictEqual(r.capabilities.can_download, false);
  assert.strictEqual(r.watch.plex.url, 'https://plex/x');
  assert.strictEqual(r.status, 'available');
});
ok('legacy->resource: not_added -> can_download', () => {
  const r = t.api.legacyStatusToResource(entry(), { state: 'not_added', service: 'radarr' });
  assert.strictEqual(r.capabilities.can_download, true);
  assert.strictEqual(r.capabilities.can_watch, false);
});

/* st() from §18 resource (resource API path) */
ok('st: maps resource status/capabilities/watch', () => {
  t.get('setRes')({ 'movie:tmdb:603': resource() });
  const s = t.get('st')(entry());
  assert.strictEqual(s.state, 'available');
  assert.strictEqual(s.capabilities.can_watch, true);
  assert.strictEqual(s.capabilities.can_download, false);
  assert.strictEqual(s.watch.plex.url, 'https://plex/x');
  assert.strictEqual(s.plexUrl, 'https://plex/x');
  assert.strictEqual(s.acquisition.provider, 'radarr');
});

/* downloadButton — capability driven */
ok('downloadButton: AVAILABLE(can_watch) -> Watch, NO Download', () => {
  t.get('setRes')({ 'movie:tmdb:603': resource({ watch: { plex: { available: true, url: 'https://plex/x' } } }) });
  const btn = t.get('downloadButton')(entry(), true);
  assert.ok(!/data-act="download"/.test(btn), 'must not show Download button');
  assert.ok(/data-act="watch-plex"/.test(btn), 'should show Watch on Plex');
  assert.ok(/Watch on Plex/.test(btn));
});
ok('downloadButton: AVAILABLE both providers -> Watch Now dropdown', () => {
  t.get('setRes')({ 'movie:tmdb:603': resource({ watch: { plex: { available: true, url: 'https://p' }, emby: { available: true, url: 'https://e' } } }) });
  const btn = t.get('downloadButton')(entry(), true);
  assert.ok(/data-act="watchnow"/.test(btn));
  assert.ok(!/data-act="download"/.test(btn));
});
ok('downloadButton: NOT_ADDED(can_download, !can_watch) -> Download', () => {
  t.get('setRes')({ 'movie:tmdb:603': resource({ status: 'not_added', capabilities: { can_download: true, can_watch: false }, watch: {}, acquisition: null }) });
  const btn = t.get('downloadButton')(entry(), true);
  assert.ok(/data-act="download"/.test(btn), 'should show Download');
  assert.ok(!/disabled/.test(btn));
});
ok('downloadButton: can_watch but no live link -> disabled Available, never Download', () => {
  t.get('setRes')({ 'movie:tmdb:603': resource({ watch: { plex: { available: false, url: null } } }) });
  const btn = t.get('downloadButton')(entry(), true);
  assert.ok(!/data-act="download"/.test(btn), 'link outage is a capability problem, not status');
  assert.ok(/disabled/.test(btn));
});
ok('downloadButton: REQUESTED -> disabled Requested', () => {
  t.get('setRes')({ 'movie:tmdb:603': resource({ status: 'requested', capabilities: { can_download: true, can_watch: false }, watch: {} }) });
  const btn = t.get('downloadButton')(entry(), true);
  assert.ok(/Requested/.test(btn));
  assert.ok(/disabled/.test(btn));
  assert.ok(!/data-act="download"/.test(btn));
});
ok('downloadButton: DOWNLOADING -> progress + disabled', () => {
  t.get('setRes')({ 'movie:tmdb:603': resource({ status: 'downloading', capabilities: { can_download: true, can_watch: false }, progress: 72, speed: 8.4 }) });
  const btn = t.get('downloadButton')(entry(), true);
  assert.ok(/Downloading 72%/.test(btn));
  assert.ok(/disabled/.test(btn));
});

/* hero + modal buttons */
ok('heroDownloadButton: can_watch -> watch link group', () => {
  t.get('setRes')({ 'movie:tmdb:603': resource({ watch: { plex: { available: true, url: 'https://p' }, emby: { available: true, url: 'https://e' } } }) });
  const s = t.get('st')(entry());
  const html = t.get('heroDownloadButton')(entry(), s);
  assert.ok(/data-watchplex/.test(html) && /data-watchebmy/.test(html));
  assert.ok(!/data-act="download"/.test(html));
});
ok('modalDownloadButton: can_download -> Download action', () => {
  t.get('setRes')({ 'movie:tmdb:603': resource({ status: 'not_added', capabilities: { can_download: true, can_watch: false }, watch: {} }) });
  const s = t.get('st')(entry());
  const html = t.get('modalDownloadButton')(entry(), s);
  assert.ok(/data-role="download"/.test(html));
  assert.ok(/Download/.test(html));
});

/* _applyRequestResult updates RES (optimistic) */
ok('_applyRequestResult: requested -> RES patched as requested', () => {
  t.get('setRes')({});
  t.get('_applyRequestResult')(entry(), { state: 'requested', message: 'added', service: 'radarr' });
  const s = t.get('st')(entry());
  assert.strictEqual(s.state, 'requested');
  assert.ok(t.get('canWatch')(entry()) === false);
});

/* legacy fallback path still renders */
ok('legacy fallback: /api/status available -> can_watch resource', () => {
  t.get('setLegacy')({ tt0133093: legacy() });
  const s = t.get('st')(entry());
  assert.strictEqual(s.state, 'available');
  assert.strictEqual(s.capabilities.can_watch, true);
  assert.strictEqual(s.watch.plex.url, 'https://plex/x');
});

/* card markup features: in-Plex orange tick + hover actions (feature #3) */
ok('cardMarkup: in-Plex card -> orange tick + Watch on Plex + Trailer, no "Available in Plex" text', () => {
  t.get('setRes')({ 'movie:tmdb:603': resource({ watch: { plex: { available: true, url: 'https://p' } } }) });
  const html = t.get('cardMarkup')(entry());
  assert.ok(/class="b plex-check"/.test(html), 'shows bright in-Plex tick');
  assert.ok(/Watch on Plex/.test(html), 'hover Watch on Plex button');
  assert.ok(/card-actions stacked/.test(html), 'stacked action layout for two buttons');
  assert.ok(/data-act="trailer"/.test(html), 'hover Trailer button present');
  assert.ok(!/data-role="dlstate"/.test(html), 'no "Available in Plex" state-text line on in-Plex card (replaced by the tick)');
});
ok('cardMarkup: not-added card -> Download action, no in-Plex tick', () => {
  t.get('setRes')({ 'movie:tmdb:603': resource({ status: 'not_added', capabilities: { can_download: true, can_watch: false }, watch: {} }) });
  const html = t.get('cardMarkup')(entry());
  assert.ok(!/plex-check/.test(html), 'no in-Plex tick');
  assert.ok(/data-act="download"/.test(html), 'Download action rendered');
});

console.log('\n' + (failures === 0 ? 'ALL PASS' : failures + ' FAILURES'));
process.exit(failures === 0 ? 0 : 1);