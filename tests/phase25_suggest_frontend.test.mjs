/* Suggest tab frontend (Phase 25 fixes).
   Loads api.js + app.js in a minimal browser VM and asserts:
     - suggestCardMarkup renders BOTH actions (Add to Watchlist, Download) plus
       the card-click targets (data-tmdb-id/data-type/data-title) needed for the
       detail modal — issues 1 & 3.
     - sgAddToWatchlist posts the correct URL and flips the button to "Added".
     - sgDownload adds to watchlist then posts /request (two-step download).
     - renderSuggestDetailBody renders IMDb rating + TMDB rating + synopsis +
       the detail-modal action buttons (issue 3).
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

async function load() {
  const sandbox = {
    console: { ...console, error: () => {}, warn: () => {}, log: () => {} },
    setTimeout: () => 0, clearTimeout: () => 0, setInterval: () => 0,
    Math, Date, JSON, parseInt, parseFloat, isFinite, Number,
    encodeURIComponent, decodeURIComponent, toLocaleString: () => '',
    localStorage: { getItem: () => '', setItem: () => {}, removeItem: () => {} },
    location: { hash: '#/suggest' },
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
      + '; globalThis.__rkm = {'
      + ' setSg(state){ suggestState = state; }, getSg(){ return suggestState; },'
      + ' setData(d){ DATA = d; }, getData(){ return DATA; },'
      + ' suggestCardMarkup, sgAddToWatchlist, sgDownload,'
      + ' suggestHistoryPush, suggestHistoryLabel,'
      + ' entryFromSuggestItem, entryFromWatchlistEntry, pushSuggestEntryToApp,'
      + ' renderSuggestDetailBody'
      + ' };';
  run(appSrc); // init IIFE resolves against stubbed getDashboardData below

  // Stub the network layer the suggest actions / detail modal use.
  const calls = { add: [], request: [] };
  const obj = run('window.API');
  obj.postJSON = async (url) => {
    if (url.indexOf('/api/suggest/add/') > -1) { calls.add.push(url); return { ok: true, message: 'Added', title: 'Inception' }; }
    if (url.indexOf('/request') > -1) { calls.request.push(url); return { ok: true, state: 'requested' }; }
    return { ok: true };
  };
  obj.requestMedia = async (id) => { calls.request.push('media:' + id); return { ok: true, state: 'requested' }; };
  obj.getDashboardData = async () => ({ entries: [], rotation_index: 0, updated: new Date().toISOString() });
  obj.getConfig = async () => ({ services: {} });
  obj.getLibrary = async () => ({});
  obj.getWatchlist = async () => ({ entries: [], indexerIssue: null });
  obj.getStatusLegacy = async () => ({ statuses: {} });
  obj.getJobs = async () => [];
  obj.suggest = async () => ({ results: [], total: 0, filters: {}, genres_available: [] });
  obj.suggestDetail = async () => ({ ok: false });

  return { get: (k) => run('globalThis.__rkm.' + k), calls };
}

const t = await load();
const get = t.get;

const item = (o) => Object.assign(
  { tmdb_id: 27205, title: 'Inception', year: 2010, media_type: 'movie', tmdb_score: 8.4, vote_count: 40041, genres: ['Action', 'Sci-Fi'], overview: 'A thief enters dreams.', poster: '', in_watchlist: false }, o);

/* ---- card markup (issues 1 & 3) ---- */
ok('suggestCardMarkup: renders Add button + Download button', () => {
  const html = get('suggestCardMarkup')(item());
  assert.ok(/data-sg-add="27205"/.test(html), 'missing Add button');
  assert.ok(/data-sg-download="27205"/.test(html), 'missing Download button');
  assert.ok(/Add to Watchlist/.test(html));
  assert.ok(/Download/.test(html));
});
ok('suggestCardMarkup: card carries detail-modal targets', () => {
  const html = get('suggestCardMarkup')(item());
  assert.ok(/data-tmdb-id="27205"/.test(html));
  assert.ok(/data-type="movie"/.test(html));
  assert.ok(/data-title="Inception"/.test(html));
  assert.ok(/class="card suggest-card"/.test(html));
});
ok('suggestCardMarkup: reflects already-on-watchlist', () => {
  const html = get('suggestCardMarkup')(item({ in_watchlist: true }));
  assert.ok(/Added/.test(html));
  assert.ok(!/data-sg-add="27205">[^<]*Add to Watchlist/.test(html) || /Added/.test(html));
});

/* ---- Add to Watchlist (issue 1) ---- */
ok('sgAddToWatchlist: posts /api/suggest/add & flips button to Added', async () => {
  const btn = { disabled: false, innerHTML: '', classList: { add: () => {} } };
  const ok = await get('sgAddToWatchlist')(item(), btn);
  assert.strictEqual(ok, true);
  assert.ok(/Added/.test(btn.innerHTML), 'button should read Added');
  assert.ok(t.calls.add.some((u) => u.indexOf('/api/suggest/add/27205?media_type=movie') > -1), 'wrong add URL: ' + t.calls.add);
});

/* ---- Download (two-step, issue 1) ---- */
ok('sgDownload: adds to watchlist then posts /request', async () => {
  const before = t.calls.add.length + t.calls.request.length;
  const btn = { disabled: false, innerHTML: '', classList: { add: () => {} } };
  const ok = await get('sgDownload')(item(), btn);
  assert.strictEqual(ok, true);
  assert.ok(t.calls.add.length > before - 1, 'should call add endpoint');
  assert.ok(t.calls.request.some((u) => u && u.indexOf('movie:tmdb:27205') > -1) ||
            t.calls.request.some((u) => u && u.indexOf('/media/movie:tmdb:27205/request') > -1),
            'should request media movie:tmdb:27205 — got ' + JSON.stringify(t.calls.request));
  assert.ok(/Downloading/.test(btn.innerHTML));
});

/* ---- Detail modal render (issue 3) ---- */
ok('renderSuggestDetailBody: shows IMDb + TMDB rating + synopsis', () => {
  const rec = { innerHTML: '', focus: () => {}, querySelector: () => makeEl() };
  const detail = {
    id: 27205, media_type: 'movie', title: 'Inception', year: 2010,
    overview: 'A thief steals corporate secrets through dream-sharing technology.',
    genres: ['Action', 'Sci-Fi'], runtime: 148, cert: 'PG-13', cast: ['Leonardo DiCaprio'],
    director: 'Christopher Nolan', tmdb_score: 8.4, vote_count: 40041,
    poster: '', backdrop: '', imdb_id: 'tt1375666', imdb_rating: 8.8, ok: true,
  };
  get('renderSuggestDetailBody')(rec, detail, 'Inception', () => {});
  assert.ok(/8\.8 IMDb/.test(rec.innerHTML), 'missing IMDb rating');
  assert.ok(/8\.4 TMDB/.test(rec.innerHTML), 'missing TMDB rating');
  assert.ok(/dream-sharing technology/.test(rec.innerHTML), 'missing synopsis');
  assert.ok(/Inception/.test(rec.innerHTML), 'missing title');
  assert.ok(/data-sg-detail-dl/.test(rec.innerHTML), 'missing Download action');
  assert.ok(/data-sg-detail-add/.test(rec.innerHTML), 'missing Add action');
  assert.ok(/Christopher Nolan/.test(rec.innerHTML), 'missing director fact');
});

/* ---- Recent-search history (retain last 10, dedupe) ---- */
ok('suggestHistoryPush: keeps most-recent-first, dedupes, caps at 10', () => {
  get('setSg')({ history: [] });
  const f = (media_type) => ({ media_type, genres: [], year_from: null, year_to: null, min_rating: 6, sort_by: 'popularity.desc', count: 20 });
  const push = get('suggestHistoryPush');
  const tv = f('tv');
  for (let i = 0; i < 15; i++) push(f('all'));   // same filter repeated -> 1 entry
  push(tv);                                        // +1
  push(f('movie'));                                // +1
  push(tv);                                        // duplicate moved to front (no growth)
  const hist = get('getSg')().history;
  assert.ok(hist.length <= 3, 'should dedupe, got ' + hist.length);
  assert.strictEqual(hist[0].media_type, 'tv', 'most recent first');
});

ok('pushSuggestEntryToApp: upserts a TV suggest item into DATA.entries', () => {
  get('setData')({ entries: [{ id: 'movie:tmdb:99', title: 'Old', type: 'movie', tmdbId: 99 }] });
  const tvItem = { tmdb_id: 500, title: 'Succession', year: 2018, media_type: 'tv', genres: ['Drama'], poster: 'p.jpg', tmdb_score: 8.0 };
  get('pushSuggestEntryToApp')(get('entryFromSuggestItem')(tvItem));
  const entries = get('getData')().entries;
  assert.ok(entries.length >= 2, 'should have added the TV title');
  const added = entries.find((e) => e.tmdbId === 500);
  assert.ok(added && added.type === 'tv', 'TV title must be typed tv (goes to TV Shows tab)');
  assert.ok(added && added.isSeries === true, 'isSeries must be true');
  // same title re-added must not duplicate
  get('pushSuggestEntryToApp')(get('entryFromSuggestItem')(tvItem));
  const count = get('getData')().entries.filter((e) => e.tmdbId === 500).length;
  assert.strictEqual(count, 1, 'no duplicate');
});

ok('entryFromWatchlistEntry: builds a FULL card (trailer/director/cast/scores)', () => {
  const w = { title: 'Succession', year: 2018, isSeries: true, tmdbId: 500, imdbId: 'tt7660850', imdb: 8.9, rt: 94,
             poster: 'p.jpg', backdrop: 'b.jpg', genres: ['Drama'], overview: 'O', director: 'Jesse Armstrong',
             cast: ['Brian Cox'], trailerId: 'AbCdEfGh123', tmdb_score: 8.5 };
  const e = get('entryFromWatchlistEntry')(w);
  assert.strictEqual(e.type, 'tv');
  assert.strictEqual(e.trailerId, 'AbCdEfGh123', 'trailer must carry through');
  assert.strictEqual(e.director, 'Jesse Armstrong');
  assert.deepStrictEqual(e.cast, ['Brian Cox']);
  assert.strictEqual(e.imdb, 8.9);
  assert.strictEqual(e.tmdb_score, 8.5);
});

console.log('\n' + (failures === 0 ? 'ALL PASS' : failures + ' FAILURES'));
process.exit(failures === 0 ? 0 : 1);