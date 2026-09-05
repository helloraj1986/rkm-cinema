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
    + ` setRes(map, flag=true){ RES = map; USES_RESOURCE_API = flag; },`
    + ` setLib(all, watch){ LIBALL = all || []; LIBWATCH = watch || []; LIB = { available: true, counts: { movie: (all||[]).length, show: 0 }, recent: (all||[]).slice(0,2), server: 'Jellyfin', urls: { jellyfin: 'http://jellyfin/web/index.html' } }; },`
    + ' st, cardMarkup, modalDownloadButton, playInRkmMarkup, playbackMarkup, canWatch, libraryCard, reportProgress, continueWatchingRowMarkup, fullLibraryGridMarkup'
    + ' };';
  run(appSrc);
  return { api: run('window.API'), get: (k) => run('globalThis.__rkm.' + k), run };
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

/* ---- Watched / progress markers ---- */
ok('playbackMarkup: fully played -> watched tick', () => {
  const html = t.get('playbackMarkup')({ played: true, playback_position: 0, runtime: 9000 });
  assert.ok(/watched-tick/.test(html));
  assert.ok(!/resume-bar/.test(html));
});
ok('playbackMarkup: partially watched -> resume bar with %', () => {
  const html = t.get('playbackMarkup')({ played: false, playback_position: 4500, runtime: 9000 });
  assert.ok(/resume-bar/.test(html));
  assert.ok(/resume-fill/.test(html));
  assert.ok(/width:50%/.test(html));   // 4500/9000
  assert.ok(/50%/.test(html));
});
ok('playbackMarkup: no progress -> empty', () => {
  assert.strictEqual(t.get('playbackMarkup')({ played: false, playback_position: 0, runtime: 0 }), '');
  assert.strictEqual(t.get('playbackMarkup')(null), '');
});
ok('libraryCard: partial watch renders resume bar', () => {
  const html = t.get('libraryCard')({
    title: 'Half Seen', year: 2001, type: 'movie', item_id: 'm1',
    played: false, playback_position: 3000, runtime: 6000,
  });
  assert.ok(/resume-bar/.test(html));
  assert.ok(/width:50%/.test(html));
});
ok('libraryCard: watched renders watched tick', () => {
  const html = t.get('libraryCard')({
    title: 'Done', year: 2002, type: 'movie', item_id: 'm2', played: true,
  });
  assert.ok(/watched-tick/.test(html));
});
ok('cardMarkup: jellyfin watch with position -> resume bar', () => {
  t.get('setRes')({ 'movie:tmdb:603': {
    ...jfResource(),
    watch: { jellyfin: { available: true, item_id: JF_ID, url: 'http://jf/x',
                         played: false, playback_position: 3000, runtime: 6000 } },
  } });
  const html = t.get('cardMarkup')(entry());
  assert.ok(/resume-bar/.test(html));
  assert.ok(/width:50%/.test(html));
});

/* ---- playback progress reporting (so Jellyfin UserData moves) ---- */
ok('reportProgress: POSTs ticks to /api/jellyfin/progress', () => {
  t.run('window.__fetchLog = []; window.fetch = (url, opts) => { window.__fetchLog.push({ url, opts }); return Promise.resolve({ ok: true }); };');
  t.get('reportProgress')('m1', 120, 'timeupdate');
  // reportProgress is fire-and-forget; the capture is synchronous at assignment.
  const hit = t.run('JSON.stringify(window.__fetchLog)');
  const log = JSON.parse(hit);
  assert.strictEqual(log.length, 1);
  assert.strictEqual(log[0].url, '/api/jellyfin/progress');
  assert.strictEqual(log[0].opts.method, 'POST');
  const body = JSON.parse(log[0].opts.body);
  assert.strictEqual(body.item_id, 'm1');
  assert.strictEqual(body.event, 'timeupdate');
  assert.strictEqual(body.position_ticks, 1200000000); // 120s * 1e7
});

/* ---- Continue Watching + full library grid (item 3) ---- */
ok('continueWatchingRowMarkup: renders in-progress items as Play-in-RKM cards', () => {
  t.get('setLib')(
    // LIBALL/all
    [ { title: 'Half Seen', year: 2001, type: 'movie', item_id: 'm1', played: false, playback_position: 3000, runtime: 6000 },
      { title: 'Fresh', year: 2002, type: 'movie', item_id: 'm2', played: false, playback_position: 0, runtime: 7000 } ],
    // LIBWATCH/watch (only in-progress)
    [ { title: 'Half Seen', year: 2001, type: 'movie', item_id: 'm1', played: false, playback_position: 3000, runtime: 6000 } ]
  );
  const html = t.get('continueWatchingRowMarkup')();
  assert.ok(/Continue Watching/.test(html), 'heading present');
  assert.ok(new RegExp('data-jf-item="m1"').test(html), 'Play-in-RKM button for in-progress item');
  assert.ok(/resume-bar/.test(html), 'resume bar shown');
  assert.ok(!/data-jf-item="m2"/.test(html), 'not-started item excluded');
});

ok('continueWatchingRowMarkup: empty when nothing in progress', () => {
  t.get('setLib')([], []);
  assert.strictEqual(t.get('continueWatchingRowMarkup')(), '');
});

ok('fullLibraryGridMarkup: renders the full poster wall grid', () => {
  t.get('setLib')([
    { title: 'A', year: 2001, type: 'movie', item_id: 'a1', played: false, playback_position: 0, runtime: 6000 },
    { title: 'B', year: 2002, type: 'tv', item_id: 'b1', played: true, playback_position: 0, runtime: 0 },
  ], []);
  const html = t.get('fullLibraryGridMarkup')();
  assert.ok(/Full Library/.test(html));
  assert.ok(/2 titles/.test(html));
  assert.ok(/class="grid"/.test(html));
  assert.ok(new RegExp('data-jf-item="a1"').test(html));
  assert.ok(new RegExp('data-jf-item="b1"').test(html));
  assert.ok(/watched-tick/.test(html), 'watched B shows a tick');
});

process.exit(failures ? 1 : 0);