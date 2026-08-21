/* ============================================================
   RKM CINEMA — application
   Vanilla JS SPA. No frameworks, no build step, no analytics.
   Data: /dashboard-data.json (generated) + /api/* (FastAPI backend)
   ============================================================ */
'use strict';

/* ---------------- helpers ---------------- */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[c]));

const fmtRating = (n) => (typeof n === 'number' ? n.toFixed(1) : String(n ?? ''));

const timeAgo = (iso) => {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (isNaN(then)) return '';
  const s = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (s < 60) return 'just now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hour${h === 1 ? '' : 's'} ago`;
  const d = Math.floor(h / 24);
  return d === 1 ? 'yesterday' : `${d} days ago`;
};

const debounce = (fn, ms) => {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
};

const seededShuffle = (arr, seed) => {
  const a = [...arr];
  let s = seed >>> 0;
  const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
};

const daySeed = () => {
  const d = new Date();
  return d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
};

const MIN = (a, b) => (a < b ? a : b);

/* ---------------- icons ---------------- */
const ICONS = {
  play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>',
  down: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12m0 0 5-5m-5 5-5-5"/><path d="M4 21h16"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/></svg>',
  gear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h.09a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v.09a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1z"/></svg>',
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="m4 12.5 5.5 5.5L20 6.5"/></svg>',
  town: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 19V5m0 14h16M6 8h4m-4 4h4m-4 4h4m4-8h4m-4 4h4m-4 4h4"/></svg>',
  film: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M7 4v16M17 4v16M3 9h4m0 3h14M7 12h4m0 3h4m-4 3h4"/></svg>',
  star: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.6 15 9l7 .7-5.2 4.7 1.5 6.9L12 17.8l-6.3 3.5 1.5-6.9L2 9.7 9 9z"/></svg>',
  spark: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2c.6 4.8 2.6 6.8 7.4 7.4-4.8.6-6.8 2.6-7.4 7.4-.6-4.8-2.6-6.8-7.4-7.4C9.4 8.8 11.4 6.8 12 2zM19 15c.3 2.4 1.3 3.4 3.7 3.7-2.4.3-3.4 1.3-3.7 3.7-.3-2.4-1.3-3.4-3.7-3.7 2.4-.3 3.4-1.3 3.7-3.7z"/></svg>',
  heart: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 21s-7.5-4.7-10-9.3C.6 8.6 2.6 5 6 5c2.1 0 3.6 1.2 4.5 2.6L12 9l1.5-1.4C14.4 6.2 15.9 5 18 5c3.4 0 5.4 3.6 4 6.7C19.5 16.3 12 21 12 21z"/></svg>',
  eye: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>',
};

/* ---------------- state ---------------- */
let DATA = null;
let STATUS = {};       // imdbId -> {state, service, progress, detail}
let INDEXER_ISSUE = null; // Radarr indexer outage message, if any
let LIB = null;
let SERVICES = {};     // service -> bool
let currentView = 'discover';
let searchSel = -1;
let modalEntry = null;
let heroOverride = localStorage.getItem('rkm_hero') || '';
let viewFilters = { type: 'all', done: 'all', sort: 'recent' };

const app = $('#app');

/* ---------------- api ---------------- */
async function getJSON(url) {
  // Delegates to the centralized API client (api.js).
  return API.getJSON(url);
}

async function refreshStatus(silent = false) {
  try {
    const d = await API.getStatus();
    STATUS = d.statuses || {};
    INDEXER_ISSUE = d.indexerIssue || null;
  } catch (e) {
    if (!silent) toast('Status unavailable', 'Could not reach the RKM API. ' + e.message, 'err');
  }
}

async function loadServices() {
  try {
    const d = await API.getConfig();
    SERVICES = d.services || {};
    if (typeof d.heroMode === 'string' && !heroOverride) heroOverride = d.heroMode;
  } catch (e) { /* keep previous */ }
}

async function loadLibrary() {
  try { LIB = await API.getLibrary(); } catch (e) { LIB = null; }
}

async function postDownload(entry) {
  return API.download(entry);
}

/* ---------------- toasts ---------------- */
function toast(title, sub = '', kind = 'ok', ms = 4200) {
  const box = $('#toasts');
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  const icon = kind === 'ok' ? ICONS.check : kind === 'err' ? ICONS.x : ICONS.spark;
  el.innerHTML = `<div class="t-ico">${icon}</div><div><div class="t-title">${esc(title)}</div>${sub ? `<div class="t-sub">${esc(sub)}</div>` : ''}</div>`;
  box.appendChild(el);
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => {
    el.classList.add('leaving');
    setTimeout(() => el.remove(), 260);
  }, ms);
}

/* ---------------- image fade-in ---------------- */
function img(entry, size = 'poster') {
  const src = size === 'backdrop' ? (entry.backdrop || entry.poster || '') : (entry.poster || '');
  if (!src) return `<div class="poster-ph" aria-hidden="true">🎬</div>`;
  return `<img class="img-load" src="${esc(src)}" alt="" loading="lazy" referrerpolicy="no-referrer" onload="this.classList.add('loaded')" onerror="this.outerHTML='<div class=poster-ph aria-hidden=true>🎬</div>'">`;
}

/* ---------------- status helpers ---------------- */
function st(entry) {
  const current = STATUS[entry.imdbId];
  if (current && current.state !== 'unknown') return current;
  const service = entry.type === 'tv' ? 'sonarr' : 'radarr';
  // When API is reachable and service is healthy, show actionable state
  if (SERVICES[service] === true) return { state: 'not_added', service };
  // When API is unreachable (SERVICES empty), don't show "unavailable" —
  // allow the user to attempt download; the backend will handle errors.
  if (Object.keys(SERVICES).length === 0) return { state: 'not_added', service };
  return current || { state: 'not_added', service };
}
const isDownloaded = (entry) => {
  const s = st(entry).state;
  return s === 'downloaded' || s === 'available';
};
const isBusy = (entry) => {
  const s = st(entry).state;
  return s === 'requested' || s === 'downloading';
};

const STATE_LABEL = {
  not_added: 'Not added', requested: 'Requested', downloading: 'Downloading',
  downloaded: 'Available', available: 'Available', unavailable: 'Unavailable', unknown: 'Unknown',
};

function dlStateMarkup(entry) {
  const s = st(entry);
  let cls = '', inner = '';
  if (s.state === 'downloading') {
    const p = Math.min(99, s.progress || 0);
    const speed = s.speed ? ` · ${s.speed} MB/s` : '';
    const eta = s.eta != null ? ` · ${fmtEta(s.eta)} left` : '';
    inner = `<span>Downloading ${p}%${speed}${eta}</span><span class="bar"><i style="width:${p}%"></i></span>`;
    cls = 'showing';
  } else if (s.state === 'downloaded') {
    inner = `<span>${ICONS.check} ${s.detail || 'Available in library'}</span>`;
    cls = 'showing ok';
  } else if (s.state === 'available') {
    inner = `<span>${ICONS.check} ${s.detail || 'Available in Plex'}</span>`;
    cls = 'showing ok';
  } else if (s.state === 'requested') {
    const warn = s.detail && s.detail.indexOf('indexers') > -1 ? 'warn' : '';
    inner = `<span>${ICONS.check} ${s.detail || 'Requested — search running'}</span>`;
    cls = `showing ${warn}`;
  }
  return `<div class="dl-state ${cls}" data-role="dlstate">${inner}</div>`;
}

/* ---------------- card ---------------- */
function cardMarkup(entry, opts = {}) {
  const s = st(entry);
  const badges = [];
  if (entry.imdb) badges.push(`<span class="b imdb">★ ${fmtRating(entry.imdb)}</span>`);
  if (entry.rt) badges.push(`<span class="b rt">${entry.rt}%</span>`);
  badges.push(`<span class="b ${entry.type}">${entry.type === 'tv' ? 'TV' : 'MOVIE'}</span>`);
  if (s.state === 'downloaded') badges.push('<span class="b" style="color:var(--green)">●</span>');
  const dlBtn = downloadButton(entry, true);
  const action = `<div class="card-actions">
    <button class="btn btn-ghost btn-sm mini-btn" data-act="trailer" aria-label="Watch trailer for ${esc(entry.title)}">${ICONS.play} Trailer</button>
    ${dlBtn}
  </div>`;
  return `<article class="card" tabindex="0" role="button" aria-label="${esc(entry.title)} (${entry.year})" data-id="${esc(entry.imdbId)}">
    <div class="card-inner">
      <div class="imgbox">${img(entry)}</div>
      <div class="shade" aria-hidden="true"></div>
      <div class="badges">${badges.join('')}</div>
      ${action}
      ${dlStateMarkup(entry)}
    </div>
    <div class="card-info">
      <div class="ci-title">${esc(entry.title)}</div>
      <div class="ci-meta">${entry.year || ''} · ${entry.type === 'tv' ? 'TV Series' : 'Movie'}${entry.genres && entry.genres[0] ? ` · ${esc(entry.genres[0])}` : ''}</div>
    </div>
  </article>`;
}

/* ---------------- download button with states ---------------- */
function downloadButton(entry, mini = false) {
  const s = st(entry);
  const svc = entry.type === 'tv' ? 'Sonarr' : 'Radarr';
  let label = 'Download', cls = 'btn-gold', disabled = false;
  
  if (s.state === 'downloaded') { 
    label = 'Available'; 
    cls = 'btn-green'; 
    disabled = true; 
  }
  else if (s.state === 'available') {
    // Watch Now button for content that's downloaded AND in Plex
    if (s.plexUrl && s.embyUrl) {
      // Both Plex and Emby available - show dropdown
      label = 'Watch Now ▼';
      cls = 'btn-purple';
      // We'll handle the dropdown logic in the click handler via data-act="watchnow"
      return `<button class="btn ${cls} btn-sm mini-btn" data-act="watchnow" data-plex-url="${esc(s.plexUrl)}" data-emby-url="${esc(s.embyUrl)}" aria-label="Watch ${esc(entry.title)}">${ICONS.play} ${label}</button>`;
    } else if (s.plexUrl) {
      // Only Plex available
      label = 'Watch on Plex';
      cls = 'btn-purple';
      return `<button class="btn ${cls} btn-sm mini-btn" data-act="watch-plex" data-url="${esc(s.plexUrl)}" aria-label="Watch ${esc(entry.title)} on Plex">${ICONS.play} ${label}</button>`;
    } else if (s.embyUrl) {
      // Only Emby available
      label = 'Watch on Emby';
      cls = 'btn-purple';
      return `<button class="btn ${cls} btn-sm mini-btn" data-act="watch-emby" data-url="${esc(s.embyUrl)}" aria-label="Watch ${esc(entry.title)} on Emby">${ICONS.play} ${label}</button>`;
    } else {
      // Fallback to original behavior
      label = 'Available';
      cls = 'btn-green';
      disabled = true;
    }
  }
  else if (s.state === 'requested') { 
    label = 'Requested'; 
    cls = 'btn-blue'; 
    disabled = true; 
  }
  else if (s.state === 'downloading') { 
    label = `Downloading ${s.progress || 0}%`; 
    cls = 'btn-blue'; 
    disabled = true; 
  }
  else if (s.state === 'unavailable' || s.state === 'unknown') { 
    label = 'Unavailable'; 
    cls = 'btn-ghost'; 
    disabled = true; 
  }
  return `<button class="btn ${cls} btn-sm mini-btn" data-act="download" ${disabled ? 'disabled' : ''} aria-label="${esc(entry.title)}: add to ${svc}">${ICONS.down} ${label}</button>`;
}

/* ---------------- rows ---------------- */
function buildRows() {
  if (!DATA) return [];
  const entries = DATA.entries;
  const movies = entries.filter((e) => e.type === 'movie');
  const rows = [];

  const heroId = pickHero()?.imdbId;
  const rest = entries.filter((e) => e.imdbId !== heroId);

  // Tonight's Picks
  rows.push({ id: 'tonight', title: 'Tonight\u2019s Picks', icon: ICONS.town, items: seededShuffle(rest.length ? rest : entries, daySeed()) });

  // New to Your Watchlist
  const byAdded = [...entries].sort((a, b) => String(b.added || '').localeCompare(String(a.added || '')));
  rows.push({ id: 'new', title: 'New to Your Watchlist', icon: ICONS.spark, items: byAdded });

  // Highly Rated
  const top = entries.filter((e) => (e.imdb && e.imdb >= 7.8) || (e.rt && e.rt >= 88));
  if (top.length >= 2) rows.push({ id: 'top', title: 'Highly Rated', icon: ICONS.star, items: top });

  // Hidden Gems — strong scores, lower fame
  const gems = entries.filter((e) => (e.rt && e.rt >= 85) && (!e.imdb || e.imdb <= 8.3));
  if (gems.length >= 2) rows.push({ id: 'gems', title: 'Hidden Gems', icon: ICONS.heart, items: gems });

  // Critically Acclaimed
  const praised = entries.filter((e) => (e.imdb && e.imdb >= 8.0) && (e.rt && e.rt >= 88));
  if (praised.length >= 2) rows.push({ id: 'acclaim', title: 'Critically Acclaimed', icon: ICONS.check, items: praised });

  // category rows (top 3 categories by count)
  const cats = {};
  for (const e of entries) { const c = e.category || 'Other'; cats[c] = cats[c] || []; cats[c].push(e); }
  const sortedCats = Object.entries(cats).sort((a, b) => b[1].length - a[1].length);
  for (const [cat, items] of sortedCats.slice(0, 3)) {
    if (items.length >= 2) rows.push({ id: 'cat-' + cat, title: cat, icon: ICONS.film, items, filter: { type: 'all', category: cat } });
  }

  // Because You Like <director> (directors with 2+ titles)
  const dirs = {};
  for (const e of entries) { if (e.director) { dirs[e.director] = dirs[e.director] || []; dirs[e.director].push(e); } }
  for (const [dir, items] of Object.entries(dirs)) {
    if (items.length >= 2) rows.push({ id: 'dir-' + dir, title: `Because You Like ${dir}`, icon: ICONS.eye, items });
  }

  return rows.slice(0, 8);
}

function pickHero() {
  if (!DATA || !DATA.entries.length) return null;
  const e = DATA.entries;
  const mode = heroOverride || DATA.heroMode || 'auto';
  if (mode === 'newest') return [...e].sort((a, b) => String(b.added || '').localeCompare(String(a.added || '')))[0];
  if (mode === 'random') return seededShuffle(e, daySeed())[0];
  return [...e].sort((a, b) => (b.imdb || 0) - (a.imdb || 0))[0]; // auto: highest rated
}

/* ---------------- views ---------------- */
const VIEWS = {
  discover: renderDiscover,
  movies: () => renderGrid('movies'),
  tv: () => renderGrid('tv'),
  watchlist: renderWatchlist,
  downloaded: renderDownloaded,
  library: renderLibraryView,
};

function renderHeader() {
  const pillState = SERVICES.radarr ? '' : SERVICES.sonarr ? '' : 'err';
  const updated = DATA?.updated ? `Updated ${timeAgo(DATA.updated)}` : 'No data yet';
  const nav = [['discover', 'Discover'], ['movies', 'Movies'], ['tv', 'TV Shows'], ['watchlist', 'Watchlist'], ['downloaded', 'Downloaded']];
  const navHtml = nav.map(([id, label]) =>
    `<button data-nav="${id}" class="${currentView === id ? 'active' : ''}" aria-current="${currentView === id ? 'page' : 'false'}">${label}</button>`).join('');

  document.querySelector('header')?.remove();
  const h = document.createElement('header');
  h.className = 'header';
  h.innerHTML = `
    <a class="brand" href="#/discover" aria-label="RKM Cinema home">
      <span class="mark"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></span>
      <span class="word">RKM<small>CINEMA</small></span>
    </a>
    <nav class="nav" aria-label="Primary">${navHtml}</nav>
    <div class="header-right">
      <div class="search-wrap" id="searchWrap">
        <span class="search-ico">${ICONS.search}</span>
        <input class="search-input" id="searchInput" type="search" placeholder="Search movies, shows, actors\u2026" autocomplete="off" aria-label="Search movies, shows, actors" role="combobox" aria-expanded="false" aria-controls="searchResults">
        <button class="search-clear" id="searchClear" aria-label="Clear search">✕</button>
        <div class="search-results" id="searchResults" role="listbox" style="display:none"></div>
      </div>
      <span class="status-pill ${pillState}" id="statusPill" title="${esc(updated)}"><span class="dot" aria-hidden="true"></span><span class="txt" id="statusTxt">${esc(updated)}</span></span>
      <button class="icon-btn" id="refreshBtn" title="Refresh status" aria-label="Refresh status">${ICONS.refresh}</button>
      <button class="icon-btn" id="gearBtn" title="Settings" aria-label="Settings" aria-haspopup="dialog">${ICONS.gear}</button>
    </div>
    ${INDEXER_ISSUE ? `<div class="indexer-banner" role="status">⚠ ${esc(INDEXER_ISSUE)}</div>` : ''}`;
  app.before(h);

  // mobile bottom navigation (hidden on desktop via CSS)
  const NAV_ITEMS = [
    ['discover', 'Discover', ICONS.spark],
    ['movies', 'Movies', ICONS.film],
    ['tv', 'TV', ICONS.town],
    ['watchlist', 'Watchlist', ICONS.heart],
    ['downloaded', 'Saved', ICONS.check],
  ];
  document.querySelector('.bottom-nav')?.remove();
  const bn = document.createElement('nav');
  bn.className = 'bottom-nav';
  bn.setAttribute('aria-label', 'Primary mobile');
  bn.innerHTML = NAV_ITEMS.map(([id, label, ic]) =>
    `<button data-nav="${id}" class="${currentView === id ? 'active' : ''}" aria-current="${currentView === id ? 'page' : 'false'}">
       <span class="bn-ico">${ic}</span>${label}</button>`).join('');
  document.body.appendChild(bn);
}

function renderFooter() {
  document.querySelector('footer')?.remove();
  const f = document.createElement('footer');
  f.className = 'footer shell';
  f.innerHTML = `<span><b>RKM Cinema</b> — your private streaming discovery · Tailnet-only</span>
    <span id="footerGen">Generated ${DATA?.generatedAt ? new Date(DATA.generatedAt).toLocaleString() : ''}</span>`;
  app.appendChild(f);
}

/* ---------- discover ---------- */
function renderDiscover() {
  const hero = pickHero();
  const rows = buildRows();
  let html = '';
  if (hero) html += heroMarkup(hero);
  html += `<div class="shell">`;
  for (const row of rows) html += rowMarkup(row);
  html += libraryStripMarkup();
  html += `</div>`;
  app.innerHTML = html;
}

function heroMarkup(e) {
  const s = st(e);
  const meta = [e.year, e.lang, e.cert, e.runtime ? fmtRuntime(e.runtime) : ''].filter(Boolean);
  const genres = (e.genres || []).slice(0, 3);
  const scores = [];
  if (e.imdb) scores.push(`<span class="score imdb">${ICONS.star} ${fmtRating(e.imdb)} IMDb</span>`);
  if (scores.length === 0 && e.imdb === 0) scores.push('<span class="score missing">IMDb n/a</span>');
  const back = e.backdrop || e.poster || '';
  const bg = back
    ? `<img class="himg" src="${esc(back)}" alt="" onload="this.classList.add('loaded')" referrerpolicy="no-referrer">`
    : `<div class="ph">🎬</div>`;
  const ds = dlStateMarkup(e);
  return `<section class="hero" aria-label="Featured: ${esc(e.title)}">
    <div class="hero-bg">${bg}</div>
    <div class="hero-shade1" aria-hidden="true"></div>
    <div class="hero-shade2" aria-hidden="true"></div>
    <div class="hero-glow" aria-hidden="true"></div>
    <div class="hero-body">
      <span class="hero-eyebrow">Featured pick</span>
      <h1 class="hero-title">${esc(e.title)}</h1>
      <div class="hero-meta">${meta.map((m) => `<span class="chip">${esc(m)}</span>`).join('')}${genres.map((g) => `<span class="chip">${esc(g)}</span>`).join('')}</div>
      <div class="hero-scores">${scores.join('')}${e.rt ? `<span class="score rt">${e.rt}% RT</span>` : ''}</div>
      <p class="hero-overview">${esc(e.overview)}</p>
      <div class="hero-actions">
        <button class="btn btn-ghost" data-act="trailer" data-hero="1" data-id="${esc(e.imdbId)}" aria-label="Watch trailer for ${esc(e.title)}">${ICONS.play} Watch Trailer</button>
        ${heroDownloadButton(e, s)}
        <div class="dl-panel" id="heroDlPanel" style="display:none"></div>
      </div>
    </div>
  </section>`;
}

function heroDownloadButton(e, s) {
  let label, cls = 'btn-gold', disabled = false;
  if (s.state === 'available') {
    // Show Watch on Plex/Emby for available content.
    if (s.plexUrl && s.embyUrl) {
      return `<span class="hero-watch-group">
        <a class="btn btn-purple" target="_blank" rel="noopener" data-watchplex href="${esc(s.plexUrl)}">${ICONS.play} Plex</a>
        <a class="btn btn-purple" target="_blank" rel="noopener" data-watchebmy href="${esc(s.embyUrl)}">${ICONS.play} Emby</a>
      </span>`;
    } else if (s.plexUrl) {
      return `<a class="btn btn-purple" target="_blank" rel="noopener" data-watchplex href="${esc(s.plexUrl)}">${ICONS.play} Watch on Plex</a>`;
    } else if (s.embyUrl) {
      return `<a class="btn btn-purple" target="_blank" rel="noopener" data-watchebmy href="${esc(s.embyUrl)}">${ICONS.play} Watch on Emby</a>`;
    }
    label = 'Available'; cls = 'btn-green'; disabled = true;
  }
  else if (s.state === 'downloaded') { label = 'Available'; cls = 'btn-green'; disabled = true; }
  else if (s.state === 'requested') { label = 'Requested'; cls = 'btn-blue'; disabled = true; }
  else if (s.state === 'downloading') { label = `Downloading ${s.progress || 0}%`; cls = 'btn-blue'; disabled = true; }
  else if (s.state === 'unavailable' || s.state === 'unknown') { label = 'Unavailable'; cls = 'btn-ghost'; disabled = true; }
  else label = 'Download';
  return `<button class="btn ${cls}" id="heroDownload" data-act="download" data-hero="1" data-id="${esc(e.imdbId)}" ${disabled ? 'disabled' : ''} aria-label="${esc(e.title)}: add to ${e.type === 'tv' ? 'Sonarr' : 'Radarr'}">${ICONS.down} ${label}</button>`;
}

function rowMarkup(row) {
  if (!row.items.length) return '';
  const filter = row.filter ? ` data-filter='${esc(JSON.stringify(row.filter))}'` : '';
  return `<div class="shell">
    <div class="row-head">
      <h2><span class="swatch" aria-hidden="true"></span>${row.icon || ''} ${esc(row.title)}</h2>
      <button class="row-more" data-view="go"${filter} aria-label="See all in ${esc(row.title)}">See all ${'›'}</button>
    </div>
    <div class="row">${row.items.map((e) => cardMarkup(e)).join('')}</div>
  </div>`;
}

/* ---------- grid views (movies / tv) ---------- */
function renderGrid(kind) {
  const entries = DATA.entries.filter((e) => e.type === (kind === 'tv' ? 'tv' : 'movie'));
  const title = kind === 'tv' ? 'TV Shows' : 'Movies';
  const genres = [...new Set(entries.flatMap((e) => e.genres || []))].sort();
  const gSel = `<label class="sr-only" for="gfilter">Filter by genre</label>
    <select class="select" id="gfilter" aria-label="Filter by genre"><option value="">All genres</option>${genres.map((g) => `<option value="${esc(g)}">${esc(g)}</option>`).join('')}</select>`;
  const inner = entries.length
    ? `<div class="grid" id="grid">${entries.map((e) => cardMarkup(e)).join('')}</div>`
    : emptyState(kind === 'tv' ? 'No TV series yet' : 'No movies yet', `Your ${title.toLowerCase()} will appear here as the recommendation engine adds them.`);
  app.innerHTML = `<div class="view shell">
    <div class="view-head">
      <div><h1>${title}</h1><div class="sub">${entries.length} title${entries.length === 1 ? '' : 's'}</div></div>
      <div class="controls">${gSel}</div>
    </div>
    ${inner}
  </div>`;
  const sel = $('#gfilter');
  if (sel) sel.addEventListener('change', () => {
    const v = sel.value;
    $$('#grid .card').forEach((c) => {
      const entry = entryById(c.dataset.id);
      const show = !v || (entry.genres || []).includes(v);
      c.style.display = show ? '' : 'none';
    });
  });
}

/* ---------- watchlist ---------- */
function renderWatchlist() {
  const all = DATA.entries;
  const chips = [['all', 'All'], ['movie', 'Movies'], ['tv', 'TV Shows'], ['downloaded', 'Downloaded'], ['not', 'Not Downloaded']];
  const chipHtml = chips.map(([k, l]) => `<button class="chip ${viewFilters.type === k ? 'active' : ''}" data-chip="${k}">${l}</button>`).join('');
  let list = all.filter((e) => {
    if (viewFilters.type === 'movie' && e.type !== 'movie') return false;
    if (viewFilters.type === 'tv' && e.type !== 'tv') return false;
    if (viewFilters.type === 'downloaded' && !isDownloaded(e) && !isBusy(e)) return false;
    if (viewFilters.type === 'not' && (isDownloaded(e) || isBusy(e))) return false;
    return true;
  });
  if (viewFilters.sort === 'rating') list = [...list].sort((a, b) => (b.imdb || 0) - (a.imdb || 0));
  else if (viewFilters.sort === 'release') list = [...list].sort((a, b) => (b.year || 0) - (a.year || 0));
  else if (viewFilters.sort === 'title') list = [...list].sort((a, b) => a.title.localeCompare(b.title));
  else list = [...list].sort((a, b) => String(b.added || '').localeCompare(String(a.added || '')));

  const sortSel = `<label class="sr-only" for="wsort">Sort by</label>
    <select class="select" id="wsort" aria-label="Sort by">
      <option value="recent">Sort: Recently Added</option>
      <option value="rating">Sort: Rating</option>
      <option value="release">Sort: Release Date</option>
      <option value="title">Sort: Title</option>
    </select>`;
  const inner = list.length
    ? `<div class="grid" id="grid">${list.map((e) => cardMarkup(e)).join('')}</div>`
    : emptyState('Nothing here yet', viewFilters.type === 'downloaded' ? 'Downloaded titles will collect here when you grab something from Radarr or Sonarr.' : 'Your watchlist is empty — the daily recommendation engine will bring fresh picks.');
  app.innerHTML = `<div class="view shell">
    <div class="view-head">
      <div><h1>Watchlist</h1><div class="sub">${list.length} of ${all.length} titles</div></div>
      <div class="controls">${chipHtml}${sortSel}</div>
    </div>
    ${inner}
    ${libraryStripMarkup()}
  </div>`;
  $('#wsort').value = viewFilters.sort;
  $('#wsort').addEventListener('change', (e) => { viewFilters.sort = e.target.value; renderWatchlist(); });
  $$('#grid .card').forEach((c) => c.addEventListener('keydown', gridKeyNav));
}

/* ---------- downloaded ---------- */
function renderDownloaded() {
  const list = DATA.entries.filter((e) => isDownloaded(e) || isBusy(e));
  const inner = list.length
    ? `<div class="grid" id="grid">${list.map((e) => cardMarkup(e)).join('')}</div>`
    : emptyState('Nothing downloaded yet', 'Click Download on any title and it will flow in here automatically.');
  app.innerHTML = `<div class="view shell">
    <div class="view-head">
      <div><h1>Downloaded</h1><div class="sub">${list.length} title${list.length === 1 ? '' : 's'} in your library pipeline</div></div>
    </div>
    ${inner}
  </div>`;
}

/* ---------- library view ---------- */
function renderLibraryView() {
  const counts = LIB?.counts || { movie: 0, show: 0 };
  const inner = LIB?.available
    ? `<div class="lib-strip">
        <div class="lib-card hl"><div class="k">Movies</div><div class="v">${counts.movie || 0} <small>films</small></div></div>
        <div class="lib-card hl"><div class="k">TV Shows</div><div class="v">${counts.show || 0} <small>series</small></div></div>
        <div class="lib-card"><div class="k">Server</div><div class="v" style="font-size:18px; padding-top:8px">${esc(LIB.server || '')}</div></div>
      </div>
      ${LIB.recent && LIB.recent.length ? `<div class="row-head"><h2><span class="swatch" aria-hidden="true"></span> Recently Added to Library</h2></div><div class="row">${LIB.recent.map((r) => libraryCard(r)).join('')}</div>` : ''}`
    : emptyState('Library unavailable', 'Connect Plex or Emby in your .env and it will appear here automatically.');
  app.innerHTML = `<div class="view shell">
    <div class="view-head"><div><h1>My Library</h1><div class="sub">Your media server at a glance</div></div></div>
    ${inner}
  </div>`;
}

function libraryCard(r) {
  const thumb = r.thumb
    ? `<img src="${esc('/api/plex/thumb?path=' + encodeURIComponent(r.thumb) + '&width=500')}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display='none'">`
    : '';
  const plexUrl = r.plexUrl || (LIB?.urls?.plex ? LIB.urls.plex + '/search' : '');
  let embyUrl = r.embyUrl || '';
  if (!embyUrl && LIB?.urls?.emby) {
    embyUrl = `${LIB.urls.emby.replace(/\/web\/index\.html$/, '')}/web/index.html#!/search/${encodeURIComponent(r.title || '')}`;
  }
  return `<div class="card" tabindex="0" role="button" aria-label="${esc(r.title)}">
    <div class="card-inner" style="--card-aspect: 2/3">
      <div class="imgbox">${thumb || '<div class="poster-ph">🎬</div>'}</div>
      <div class="shade"></div>
      <div class="badges"><span class="b ${r.type}">${r.type === 'tv' ? 'TV' : 'MOVIE'}</span></div>
      <div class="watchnow" style="position:absolute; left:50%; bottom:12px; transform:translateX(-50%); z-index:5; display:flex; gap:8px;">
        ${plexUrl ? `<button class="btn btn-purple btn-sm mini-btn" data-act="watch-plex" data-url="${esc(plexUrl)}">${ICONS.play} Plex</button>` : ''}
        ${embyUrl ? `<button class="btn btn-gold btn-sm mini-btn" data-act="watch-emby" data-url="${esc(embyUrl)}">${ICONS.play} Emby</button>` : ''}
      </div>
    </div>
    <div class="card-info"><div class="ci-title">${esc(r.title)}</div><div class="ci-meta">${r.year || ''}</div></div>
  </div>`;
}

function libraryStripMarkup() {
  if (LIB?.available) return '';
  return `<div class="row-head">
    <h2><span class="swatch" aria-hidden="true"></span> My Library</h2>
    <button class="row-more" data-view="library">Open ${'›'}</button>
  </div>
  <div class="row"><div class="empty" style="margin:0; padding:46px 20px; border-style:dashed">
    <div class="ec">📚</div><h3>Library preview</h3>
    <p>Connect Plex or Emby in .env (PLEX_URL, PLEX_TOKEN or EMBY_URL, EMBY_API_KEY) and your library counts and recent additions appear here.</p>
  </div></div>`;
}

/* ---------- empty state ---------- */
function emptyState(title, sub) {
  return `<div class="empty"><div class="ec">🎞️</div><h3>${esc(title)}</h3><p>${esc(sub)}</p></div>`;
}

/* ---------- modal ---------- */
function openModal(entry) {
  modalEntry = entry;
  const s = st(entry);
  const meta = [entry.year, entry.lang, entry.cert, entry.runtime ? fmtRuntime(entry.runtime) : ''].filter(Boolean);
  const genres = (entry.genres || []).slice(0, 4);
  const facts = [];
  if (entry.director) facts.push(['Director', entry.director]);
  if (entry.cast && entry.cast.length) facts.push(['Starring', entry.cast.slice(0, 5).join(' · ')]);
  if (entry.type === 'tv') facts.push(['Format', 'TV Series']);
  if (entry.added) facts.push(['Added', entry.added]);

  const back = entry.backdrop || entry.poster || '';
  const bg = back ? `<img src="${esc(back)}" alt="" referrerpolicy="no-referrer">` : '<div class="ph">🎬</div>';
  const scores = [];
  if (entry.imdb) scores.push(`<span class="score imdb">${ICONS.star} ${fmtRating(entry.imdb)} IMDb</span>`);
  if (entry.tmdbScore) scores.push(`<span class="score tmdb">${fmtRating(entry.tmdbScore * 10)}% TMDB</span>`);
  if (entry.rt) scores.push(`<span class="score rt">${entry.rt}% Rotten Tomatoes</span>`);

  const overlay = document.createElement('div');
  overlay.className = 'overlay';
  overlay.innerHTML = `<div class="modal" role="dialog" aria-modal="true" aria-label="${esc(entry.title)} details">
    <div class="modal-back">
      ${bg}
      <div class="shade" aria-hidden="true"></div>
      <div class="poster-float">${entry.poster ? `<img src="${esc(entry.poster)}" alt="" referrerpolicy="no-referrer">` : '<div class="ph">🎬</div>'}</div>
      <button class="modal-x" data-role="close" aria-label="Close">${ICONS.x}</button>
    </div>
    <div class="modal-content">
      <h2 class="modal-title">${esc(entry.title)}</h2>
      <div class="modal-meta">${meta.map((m) => `<span class="chip">${esc(m)}</span>`).join('')}${genres.map((g) => `<span class="chip">${esc(g)}</span>`).join('')}</div>
      <div class="modal-scores">${scores.join('') || '<span class="score missing">No rating data yet</span>'}</div>
      <p class="modal-overview">${esc(entry.overview || 'No synopsis available yet.')}</p>
      ${facts.length ? `<div class="modal-facts">${facts.map(([k, v]) => `<div class="fact"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join('')}</div>` : ''}
      <div class="modal-actions">
        ${trailerButton(entry)}
        ${modalDownloadButton(entry, s)}
        <div class="dl-panel" id="modalDlPanel" style="display:none"></div>
      </div>
      <div class="trailer-wrap" id="trailerWrap" style="display:none"></div>
      <div class="trailer-note" id="trailerNote"></div>
    </div>
  </div>`;
  document.body.appendChild(overlay);
  requestAnimationFrame(() => overlay.classList.add('show'));
  document.body.style.overflow = 'hidden';

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) { closeModal(); return; }
    const trailerBtn = e.target.closest('[data-role="trailer"]');
    const dlBtn = e.target.closest('[data-role="download"]');
    if (trailerBtn) { e.preventDefault(); loadTrailer(); return; }
    if (dlBtn) { e.preventDefault(); if (modalEntry) doDownload(modalEntry, { in: 'modal' }); return; }
  });
  overlay.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });
  $$('[data-role="close"]', overlay).forEach((b) => b.addEventListener('click', closeModal));
  const firstBtn = $('button', overlay);
  if (firstBtn) firstBtn.focus();
}

function closeModal() {
  const ov = $('.overlay');
  if (!ov) return;
  ov.classList.remove('show');
  document.body.style.overflow = '';
  setTimeout(() => ov.remove(), 220);
  modalEntry = null;
}

function trailerButton(entry) {
  if (entry.trailerId) {
    return `<button class="btn btn-ghost" data-role="trailer" aria-label="Watch the official trailer for ${esc(entry.title)}">${ICONS.play} Watch Trailer</button>`;
  }
  return `<a class="btn btn-ghost" href="${esc(entry.trailerUrl)}" target="_blank" rel="noopener" aria-label="Search YouTube for ${esc(entry.title)} trailer">${ICONS.search} Search YouTube</a>`;
}

function modalDownloadButton(entry, s) {
  const svc = entry.type === 'tv' ? 'Sonarr' : 'Radarr';
  if (s.state === 'available') {
    if (s.plexUrl && s.embyUrl) {
      return `<div class="modal-watch-group">
        <a class="btn btn-purple" target="_blank" rel="noopener" data-role="watchplex" href="${esc(s.plexUrl)}">${ICONS.play} Watch on Plex</a>
        <a class="btn btn-purple" target="_blank" rel="noopener" data-role="watchemby" href="${esc(s.embyUrl)}">${ICONS.play} Watch on Emby</a>
      </div>`;
    } else if (s.plexUrl) {
      return `<a class="btn btn-purple" data-role="watchplex" target="_blank" rel="noopener" href="${esc(s.plexUrl)}">${ICONS.play} Watch on Plex</a>`;
    } else if (s.embyUrl) {
      return `<a class="btn btn-purple" data-role="watchemby" target="_blank" rel="noopener" href="${esc(s.embyUrl)}">${ICONS.play} Watch on Emby</a>`;
    }
    return `<button class="btn btn-green" data-role="download" disabled>${ICONS.check} Available in Plex</button>`;
  }
  let label = `Download`, cls = 'btn-gold', disabled = false;
  if (s.state === 'downloaded') { label = `Available in library`; cls = 'btn-green'; disabled = true; }
  else if (s.state === 'requested') { label = `Requested`; cls = 'btn-blue'; disabled = true; }
  else if (s.state === 'downloading') { label = `Downloading ${s.progress || 0}%`; cls = 'btn-blue'; disabled = true; }
  else if (s.state === 'unavailable' || s.state === 'unknown') { label = 'Unavailable'; cls = 'btn-ghost'; disabled = true; }
  return `<button class="btn ${cls}" data-role="download" ${disabled ? 'disabled' : ''} aria-label="Add ${esc(entry.title)} to ${svc}">${ICONS.down} ${label}</button>`;
}

/* trailer lazy-load: iframe only created on demand */
function loadTrailer() {
  const wrap = $('#trailerWrap');
  const note = $('#trailerNote');
  if (!wrap || !modalEntry) return;
  if (wrap.dataset.loaded) return;
  if (!modalEntry.trailerId) return;
  wrap.dataset.loaded = '1';
  wrap.style.display = 'block';
  wrap.innerHTML = `<iframe src="${esc(modalEntry.trailerUrl)}" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen title="Official trailer: ${esc(modalEntry.title)}"></iframe>`;
  note.textContent = modalEntry.trailerTitle ? `Trailer: ${modalEntry.trailerTitle}` : '';
}

/* ---------------- interactions ---------------- */
async function doDownload(entry, opts = {}) {
  const svc = entry.type === 'tv' ? 'Sonarr' : 'Radarr';
  const sizeCls = opts.in === 'hero' || opts.in === 'modal' ? '' : ' btn-sm';
  const where = opts.in === 'hero' ? ['#heroDownload', '#heroDlPanel'] : opts.in === 'modal' ? ['[data-role="download"]', '#modalDlPanel'] : [`[data-id="${entry.imdbId}"] [data-act="download"]`, `[data-id="${entry.imdbId}"] [data-role="dlstate"]`];
  const btn = where[0] ? $(where[0]) : null;
  const panel = where[1] ? $(where[1]) : null;

  const paint = (label, cls, disabled) => {
    if (btn) { btn.innerHTML = `${ICONS.down} ${label}`; btn.className = `btn ${cls}${sizeCls}`; btn.disabled = !!disabled; }
  };
  paint(`Adding to ${svc}\u2026`, 'btn-gold', true);

  try {
    const res = await postDownload(entry);
    STATUS[entry.imdbId] = { state: res.state || 'requested', service: entry.type === 'tv' ? 'sonarr' : 'radarr', detail: res.message };
    toast(res.message || `${entry.title} added to ${svc}`, entry.type === 'tv' ? 'Episodes will start downloading shortly.' : 'Your download will begin shortly.', 'ok');
    paint(`✓ Added to ${svc}`, 'btn-green', true);
    if (panel && panel.dataset.role === 'dlstate') { panel.className = 'dl-state showing ok'; panel.innerHTML = `<span>${ICONS.check} Requested — search running</span>`; }
    setTimeout(() => refreshStatus(true).then(renderMinimal), 2500);
  } catch (e) {
    toast('Download failed', e.message || 'Could not reach the download service.', 'err', 6000);
    paint('Failed — Retry', 'btn-danger', false);
    STATUS[entry.imdbId] = { state: 'unavailable', service: entry.type === 'tv' ? 'sonarr' : 'radarr' };
  }
  if (opts.in !== 'hero' && opts.in !== 'modal') rerenderDownloadButtons(entry);
}

function rerenderDownloadButtons(entry) {
  const s = st(entry);
  // update any visible card download buttons for this entry
  $$(`[data-id="${entry.imdbId}"] [data-act="download"]`).forEach((b) => {
    const label = s.state === 'downloaded' ? 'Available' : s.state === 'available' ? 'Available' : s.state === 'requested' ? 'Requested' : s.state === 'downloading' ? `Downloading ${s.progress || 0}%` : 'Download';
    b.innerHTML = `${ICONS.down} ${label}`;
    b.className = `btn ${s.state === 'downloaded' || s.state === 'available' ? 'btn-green' : s.state === 'requested' || s.state === 'downloading' ? 'btn-blue' : 'btn-gold'} btn-sm mini-btn`;
    b.disabled = s.state !== 'not_added';
  });
}

/* only rebuild markup for entries whose state changed */
let lastStatusKey = '';
function renderMinimal() {
  const key = JSON.stringify(Object.values(STATUS).map((s) => s.state + (s.progress || ''))) + '|' + (INDEXER_ISSUE || '');
  if (key === lastStatusKey) return;
  lastStatusKey = key;
  render();
}

function render() {
  renderHeader();
  VIEWS[currentView]();
  renderFooter();
  wireSearchKeys();   // header is rebuilt every render — re-wire controls
  window.scrollTo({ top: 0 });
}

/* ---------------- search ---------------- */
const searchWrap = () => $('#searchWrap');
let searchResults = [];
let searchTimer = null;

function openSearch() {
  searchWrap()?.classList.add('open');
  $('#searchResults').style.display = 'block';
  $('#searchInput').setAttribute('aria-expanded', 'true');
  searchSel = -1;
  $('#searchInput').focus();
}

function closeSearch() {
  searchWrap()?.classList.remove('open');
  const r = $('#searchResults');
  if (r) r.style.display = 'none';
  $('#searchInput').setAttribute('aria-expanded', 'false');
  $('#searchInput').value = '';
  $('#searchClear').classList.remove('show');
}

async function runSearch(q) {
  const box = $('#searchResults');
  q = q.trim();
  if (!q) { box.innerHTML = ''; box.style.display = 'none'; return; }
  box.style.display = 'block';
  box.innerHTML = `<div class="sr-empty">Searching\u2026</div>`;
  let local = [], live = [];
  try {
    const d = await API.search(q);
    local = d.watchlist || [];
    live = d.tmdb || [];
  } catch (e) { /* fall through */ }
  // local fallback search (works offline)
  if (!local.length && !live.length && DATA) {
    local = DATA.entries.filter((e) => {
      const hay = [e.title, e.director, e.category, e.year, (e.cast || []).join(' '), (e.genres || []).join(' ')].join(' ').toLowerCase();
      return hay.includes(q.toLowerCase());
    }).map((e) => ({ title: e.title, year: e.year, type: e.type, imdbId: e.imdbId, tmdbId: e.tmdbId, poster: e.poster, inWatchlist: true, director: e.director, snippet: e.overview }));
  }
  searchResults = [...local, ...live];
  const lh = local.map((r, i) => searchItem(r, i)).join('');
  const lh2 = live.length ? `<div class="sr-group">Live results (TMDB)</div>` + live.map((r, i) => searchItem(r, i + local.length)).join('') : '';
  box.innerHTML = local.length || live.length
    ? `<div class="sr-group">${local.length ? 'Watchlist' : ''}</div>${lh}${lh2}`
    : `<div class="sr-empty">No matches for “${esc(q)}” — try a title, actor or director.</div>`;
}

function searchItem(r, idx) {
  const badge = r.inWatchlist ? '<span class="b" style="color:var(--green)">In watchlist</span>' : '';
  return `<div class="sr-item" data-idx="${idx}" role="option" aria-selected="false" tabindex="-1">
    <img src="${esc(r.poster || '')}" alt="" onerror="this.style.visibility='hidden'">
    <div class="si-main">
      <div class="si-title">${esc(r.title)} <span style="color:var(--muted);font-weight:400">${r.year ? '(' + esc(r.year) + ')' : ''}</span></div>
      <div class="si-meta">${r.type === 'tv' ? 'TV Series' : 'Movie'}${r.director ? ' · ' + esc(r.director) : ''}${r.cast && r.cast.length ? ' · ' + esc(r.cast.join(', ')) : ''}</div>
    </div>
    <button class="btn btn-gold btn-sm" data-search-dl data-idx="${idx}" aria-label="Download ${esc(r.title)}">${ICONS.down} Download</button>
  </div>`;
}

function searchActivate() {
  const item = searchResults[searchSel];
  if (!item) return;
  closeSearch();
  const entry = entryById(item.imdbId) || {
    imdbId: item.imdbId, tmdbId: item.tmdbId, title: item.title, year: item.year,
    type: item.type, poster: item.poster || '', overview: item.overview || '', cast: [], director: '', genres: [],
    trailerId: '', trailerTitle: '', trailerUrl: `https://www.youtube.com/results?search_query=${encodeURIComponent(item.title + ' trailer')}`, added: '', rt: null, imdb: null,
  };
  openModal(entry);
}

/* ---------------- app-level event delegation ---------------- */
app.addEventListener('click', (e) => {
  const card = e.target.closest('.card');
  const actBtn = e.target.closest('[data-act]');
  const heroBtn = e.target.closest('[data-hero]');
  const viewGo = e.target.closest('[data-view]');
  const chip = e.target.closest('[data-chip]');
  const srItem = e.target.closest('.sr-item');

  // search result row -> open it
  if (srItem && !e.target.closest('[data-search-dl]')) {
    e.preventDefault(); e.stopPropagation();
    searchSel = +srItem.dataset.idx;
    searchActivate();
    return;
  }

  if (actBtn) {
       e.preventDefault();
       e.stopPropagation();
       const id = actBtn.closest('[data-id]')?.dataset.id;
       const entry = heroBtn ? pickHero() : id ? entryById(id) : modalEntry;
       if (actBtn.dataset.act === 'trailer') {
         // Play trailer in-app (modal iframe), never open a new YouTube tab.
         e.preventDefault();
         if (modalEntry) { loadTrailer(); }
         else if (entry) { openModal(entry); requestAnimationFrame(() => loadTrailer()); }
         return;
       } else if (actBtn.dataset.act === 'download') {
         if (entry) doDownload(entry, { in: heroBtn ? 'hero' : (modalEntry ? 'modal' : 'card') });
       } else if (actBtn.dataset.act === 'watch-plex') {
         if (actBtn.dataset.url) {
           window.open(actBtn.dataset.url, '_blank');
         }
       } else if (actBtn.dataset.act === 'watch-emby') {
         if (actBtn.dataset.url) {
           window.open(actBtn.dataset.url, '_blank');
         }
       } else if (actBtn.dataset.act === 'watchnow') {
         // Handle Watch Now dropdown - for simplicity, we'll open Plex first if both available
         // In a full implementation, this would show a dropdown menu
         if (entry) {
           const plexUrl = actBtn.dataset.plexUrl;
           const embyUrl = actBtn.dataset.embyUrl;
           if (plexUrl) {
             window.open(plexUrl, '_blank');
           } else if (embyUrl) {
             window.open(embyUrl, '_blank');
           }
         }
       }
       return;
     }
  if (card) {
    const entry = entryById(card.dataset.id);
    if (entry) openModal(entry);
    return;
  }
  if (viewGo) {
    e.preventDefault();
    const filter = viewGo.dataset.filter;
    if (filter) { try { viewFilters = JSON.parse(filter); } catch (err) { /* ignore */ } currentView = 'movies'; }
    else currentView = viewGo.dataset.view;
    location.hash = '#/' + currentView;
    return;
  }
  if (chip) {
    viewFilters.type = chip.dataset.chip;
    renderWatchlist();
    return;
  }
});

document.addEventListener('click', (e) => {
  if (!e.target.closest('.search-wrap')) closeSearch();
});

app.addEventListener('keydown', (e) => {
  const card = e.target.closest('.card');
  if (card && (e.key === 'Enter' || e.key === ' ')) {
    e.preventDefault();
    openModal(entryById(card.dataset.id));
  }
});

function gridKeyNav(e) {
  if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
    const cards = $$('#grid .card');
    const i = cards.indexOf(e.target);
    const n = e.key === 'ArrowRight' ? i + 1 : i - 1;
    if (cards[n]) cards[n].focus();
  }
}

/* ---------------- header events ---------------- */
document.addEventListener('click', (e) => {
  const navBtn = e.target.closest('[data-nav]');
  if (!navBtn) return;
  currentView = navBtn.dataset.nav;
  location.hash = '#/' + currentView;
});

document.addEventListener('click', (e) => {
  const dl = e.target.closest('[data-search-dl]');
  if (!dl) return;
  e.preventDefault(); e.stopPropagation();
  const item = searchResults[+dl.dataset.idx];
  if (!item) return;
  const entry = entryById(item.imdbId) || {
    imdbId: item.imdbId, tmdbId: item.tmdbId, title: item.title, year: item.year,
    type: item.type, poster: item.poster || '', overview: item.overview || '', cast: [], director: '', genres: [],
    trailerId: '', trailerTitle: '', trailerUrl: `https://www.youtube.com/results?search_query=${encodeURIComponent(item.title + ' trailer')}`, added: '', rt: null, imdb: null,
  };
  doDownload(entry, { in: 'card' });
});

/* keyboard on search input */
function wireSearchKeys() {
  const input = $('#searchInput');
  if (!input) return;
  input.addEventListener('input', debounce((e) => {
    const v = e.target.value;
    const clear = $('#searchClear');
    if (clear) clear.classList.toggle('show', !!v);
    if (v) openSearch();
    runSearch(v);
  }, 180));
  input.addEventListener('keydown', (e) => {
    const box = $('#searchResults');
    const items = $$('.sr-item', box);
    if (e.key === 'ArrowDown') { e.preventDefault(); searchSel = Math.min(searchSel + 1, Math.max(searchResults.length - 1, 0)); paintSearchSel(items); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); searchSel = Math.max(searchSel - 1, -1); paintSearchSel(items); }
    else if (e.key === 'Enter') { e.preventDefault(); searchActivate(); }
    else if (e.key === 'Escape') { closeSearch(); }
  });
  const clear = $('#searchClear');
  if (clear) clear.addEventListener('click', () => { const i = $('#searchInput'); if (i) i.value = ''; clear.classList.remove('show'); runSearch(''); });
  const refresh = $('#refreshBtn');
  if (refresh) refresh.addEventListener('click', async (e) => {
    const b = e.currentTarget;
    b.classList.add('spin');
    await refreshStatus(true); await loadServices(); await loadLibrary();
    b.classList.remove('spin');
    render();
    toast('Refreshed', 'Status and library info are up to date.', 'ok', 2500);
  });
  const gear = $('#gearBtn');
  if (gear) gear.addEventListener('click', toggleSettings);
}

function paintSearchSel(items) {
  items.forEach((el, i) => { el.classList.toggle('sel', i === searchSel); el.setAttribute('aria-selected', i === searchSel); });
  if (items[searchSel]) items[searchSel].scrollIntoView({ block: 'nearest' });
}

function entryById(id) {
  return DATA?.entries.find((e) => e.imdbId === id) || null;
}

/* ---------------- settings ---------- */
function toggleSettings() {
  const ex = $('#settingsPanel');
  if (ex) { ex.remove(); return; }
  const services = [
    ['Radarr', SERVICES.radarr], ['Sonarr', SERVICES.sonarr], ['TMDB', SERVICES.tmdb],
    ['Plex', SERVICES.plex], ['Jellyfin', SERVICES.jellyfin],
  ];
  const s = document.createElement('div');
  s.id = 'settingsPanel';
  s.className = 'overlay show';
  s.style.display = 'block';
  s.innerHTML = `<div class="modal" style="max-width:520px">
    <div class="modal-content" style="padding:28px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">
        <h2 style="font-size:20px;font-weight:800">Settings</h2>
        <button class="icon-btn" data-role="close" aria-label="Close settings">${ICONS.x}</button>
      </div>
      <div class="modal-facts" style="margin-bottom:14px">
        ${services.map(([n, ok]) => `<div class="fact"><div class="k">${n}</div><div class="v" style="color:${ok ? 'var(--green)' : 'var(--muted)'}">${ok ? 'Connected' : 'Not configured'}</div></div>`).join('')}
      </div>
      <label class="k" style="display:block;font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);margin-bottom:6px">Hero pick</label>
      <select class="select" id="heroSel" style="width:100%;margin-bottom:18px">
        <option value="">Auto (highest rated)</option>
        <option value="newest">Newest addition</option>
        <option value="random">Random pick</option>
      </select>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="btn btn-ghost btn-sm" id="libLink">Open My Library</button>
        <button class="btn btn-ghost btn-sm" id="refreshSvc">Refresh services</button>
      </div>
      <p style="font-size:12px;color:var(--faint);margin-top:18px">API keys and URLs stay server-side in .env — the browser only talks to /api.</p>
    </div>
  </div>`;
  document.body.appendChild(s);
  s.addEventListener('click', (e) => { if (e.target === s) s.remove(); });
  $$('[data-role="close"]', s).forEach((b) => b.addEventListener('click', () => s.remove()));
  const sel = $('#heroSel');
  const cur = heroOverride || DATA?.heroMode || 'auto';
  sel.value = (cur === 'auto' ? '' : cur);
  sel.addEventListener('change', () => {
    heroOverride = sel.value;
    if (heroOverride) localStorage.setItem('rkm_hero', heroOverride); else localStorage.removeItem('rkm_hero');
    render();
    s.remove();
  });
  $('#libLink').addEventListener('click', () => { s.remove(); currentView = 'library'; location.hash = '#/library'; });
  $('#refreshSvc').addEventListener('click', async () => {
    $('#refreshSvc').textContent = 'Refreshing\u2026';
    await Promise.all([loadServices(), loadLibrary()]);
    await refreshStatus(true);
    $('#refreshSvc').textContent = 'Refresh services';
    s.remove();
    render();
    toast('Services refreshed', 'Status updated.', 'ok');
  });
}

/* ---------------- router ---------------- */
function route() {
  const h = (location.hash || '#/discover').replace(/^#\//, '').replace(/\/+$/, '');
  currentView = VIEWS[h] ? h : 'discover';
  render();
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const settings = $('#settingsPanel');
    if (settings) { settings.remove(); return; }
    closeModal();
    closeSearch();
  }
});

window.addEventListener('hashchange', route);

/* ---------------- helpers ---------------- */
function fmtEta(sec) {
  if (sec == null || sec < 0 || !isFinite(sec)) return '';
  if (sec < 90) return `${Math.round(sec)}s`;
  const m = Math.round(sec / 60);
  if (m < 90) return `${m}m`;
  const h = Math.floor(m / 60), mm = m % 60;
  return h >= 24 ? `${Math.floor(h / 24)}d ${h % 24}h` : `${h}h ${mm}m`;
}
function fmtRuntime(min) {
  if (!min) return '';
  const h = Math.floor(min / 60), m = min % 60;
  return h ? `${h}h ${m}m` : `${m}m`;
}

/* ---------------- init ---------------- */
(async function init() {
  // toast container
  const t = document.createElement('div');
  t.className = 'toasts';
  t.id = 'toasts';
  document.body.appendChild(t);

  try {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    // minimum skeleton so the page never flashes empty
    app.innerHTML = skeleton();
    const dataP = API.getDashboardData();
    const [d] = await Promise.all([dataP, loadServices()]);
    DATA = d;
    await refreshStatus(true);
    await loadLibrary();
    route();           // renders header + view (render() wires header controls)
    // periodic status refresh — 15s keeps download progress feeling live
    setInterval(() => refreshStatus(true).then(renderMinimal), 15 * 1000);
  } catch (e) {
    app.innerHTML = `<div class="empty" style="margin:80px auto;max-width:500px">
      <div class="ec">🎬</div>
      <h3>RKM Cinema could not load</h3>
      <p>${esc(e.message)}</p>
      <p style="margin-top:14px"><button class="btn btn-gold" onclick="location.reload()">Retry</button></p>
    </div>`;
    console.error(e);
  } finally {
    updateStatusPill();
  }
})();

function updateStatusPill() {
  const pill = $('#statusPill');
  const txt = $('#statusTxt');
  if (!pill || !txt) return;
  txt.textContent = DATA?.updated ? `Updated ${timeAgo(DATA.updated)}` : 'No data';
  const stale = DATA?.updated && (Date.now() - new Date(DATA.updated).getTime()) > 26 * 60 * 60 * 1000;
  pill.classList.toggle('stale', !!stale);
  setTimeout(() => { if (pill) pill.title = `Next refresh: ${nextRefresh(DATA?.refreshCron)}`; }, 50);
}

function nextRefresh(cronExpr) {
  try {
    const parts = (cronExpr || '0 18 * * *').trim().split(/\s+/);
    const cronS = parseInt(parts[1] ?? '18', 10), cronM = parseInt(parts[0] ?? '0', 10);
    const now = new Date();
    const next = new Date(now); next.setHours(cronS, cronM, 0, 0);
    if (next <= now) next.setDate(next.getDate() + 1);
    return next.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch (e) { return 'daily'; }
}

function skeleton() {
  const rows = [0, 1, 2].map(() => `<div class="shell">
    <div class="row-head"><h2 style="opacity:.4" class="sk" margin="6px 0">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</h2></div>
    <div class="row">${[0, 1, 2, 3, 4, 5].map(() => `<div class="card sk sk-rounded" style="width:200px;height:300px;border:none"></div>`).join('')}</div>
  </div>`).join('');
  return `<section class="hero"><div class="hero-bg"><div class="ph sk"></div></div>
    <div class="hero-shade1"></div><div class="hero-shade2"></div></section>${rows}`;
}

/* expose a few internals for debug/devtools */
window.RKM = { get state() { return { DATA, STATUS, LIB, SERVICES, view: currentView }; } };