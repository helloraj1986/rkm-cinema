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
let RES = {};        // media_id -> §18 resource {status, capabilities, watch, acquisition, progress}
let LEGACY_STATUS = {}; // imdbId -> legacy /api/status entry (fallback only)
let USES_RESOURCE_API = false; // true once /api/watchlist resolves on this image
let INDEXER_ISSUE = null; // *arr indexer outage message, if any
let LIB = null;
let LIBALL = [];     // full library (poster-wall grid) {title,item_id,type,played,position,runtime,...}
let LIBWATCH = [];   // "Continue Watching" in-progress items
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
  // Primary: Phase 10 resource API (spec §17). Each entry arrives as one
  // complete §18 object carrying status + capabilities + watch, so the
  // frontend renders off it and never reconstructs state (§19).
  try {
    const d = await API.getWatchlist();
    RES = {};
    for (const e of d.entries || []) RES[e.id] = e;
    INDEXER_ISSUE = d.indexerIssue || null;
    USES_RESOURCE_API = true;
    LEGACY_STATUS = {};
    return;
  } catch (e) {
    // Fallback: legacy /api/status (still-running pre-Phase-10 image). Keep the
    // old per-title path so the site stays live until the next redeploy.
    if (!silent) toast('Status unavailable', 'Could not reach the RKM API. ' + e.message, 'err');
  }
  try {
    const d = await API.getStatusLegacy();
    LEGACY_STATUS = d.statuses || {};
    INDEXER_ISSUE = d.indexerIssue || null;
    USES_RESOURCE_API = false;
    RES = {};
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
  try {
    const d = await API.getLibraryItems();
    LIBALL = (d && d.items) || [];
  } catch (e) { LIBALL = []; }
  try {
    const d = await API.getContinueWatching();
    LIBWATCH = (d && d.items) || [];
  } catch (e) { LIBWATCH = []; }
}

async function postDownload(entry) {
  // Canonical request path (§15/§17): POST /api/media/{media_id}/request.
  // Falls back to the legacy /api/download on a still-running old image.
  if (USES_RESOURCE_API) {
    return API.requestMedia(API.mediaIdOf(entry));
  }
  return API.downloadLegacy(entry);
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
/* Resolve the canonical §18 resource for a watchlist entry. Primary source is
   the resource API (RES keyed by media_id); falls back to the legacy /api/status
   map (LEGACY_STATUS keyed by imdbId) so pre-Phase-10 images keep working. */
function _resFor(entry) {
  if (USES_RESOURCE_API) return RES[API.mediaIdOf(entry)] || null;
  const legacy = LEGACY_STATUS[entry.imdbId];
  if (legacy) return API.legacyStatusToResource(entry, legacy);
  return null;
}

function st(entry) {
  const r = _resFor(entry);
  if (r) {
    return {
      state: r.status,
      service: (r.acquisition && r.acquisition.provider) || (entry.type === 'tv' ? 'sonarr' : 'radarr'),
      detail: r.detail || '',
      progress: r.progress != null ? r.progress : undefined,
      speed: r.speed != null ? r.speed : undefined,
      eta: r.eta != null ? r.eta : undefined,
      qbitState: r.qbitState || '',
      qbitName: r.qbitName || '',
      capabilities: r.capabilities || { can_download: false, can_watch: false },
      watch: r.watch || {},
      plexUrl: ((r.watch && r.watch.plex) || {}).url || '',
      embyUrl: ((r.watch && r.watch.emby) || {}).url || '',
      jellyfinUrl: ((r.watch && r.watch.jellyfin) || {}).url || '',
      // Native item id for in-app playback via /api/jellyfin/stream.
      jellyfinItemId: ((r.watch && r.watch.jellyfin) || {}).item_id || '',
      acquisition: r.acquisition || null,
    };
  }
  const service = entry.type === 'tv' ? 'sonarr' : 'radarr';
  // When API is reachable and service is healthy, show actionable state.
  if (SERVICES[service] === true) return { state: 'not_added', service, capabilities: { can_download: true, can_watch: false }, watch: {} };
  // When API is unreachable (SERVICES empty), don't show "unavailable" —
  // allow the user to attempt download; the backend will handle errors.
  if (Object.keys(SERVICES).length === 0) return { state: 'not_added', service, capabilities: { can_download: true, can_watch: false }, watch: {} };
  return { state: 'not_added', service, capabilities: { can_download: true, can_watch: false }, watch: {} };
}

const canWatch = (entry) => !!(st(entry).capabilities && st(entry).capabilities.can_watch);
const canDownload = (entry) => st(entry).state === 'not_added' && !!(st(entry).capabilities && st(entry).capabilities.can_download);

const isDownloaded = (entry) => {
  const s = st(entry);
  const own = s.capabilities && s.capabilities.can_watch;
  return !!own || s.state === 'downloaded' || s.state === 'available';
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

  // "In Plex" = already available to watch → show a bright-orange tick badge
  // (top-right) instead of the old "Available in Plex" text, and reveal Watch
  // on Plex + Trailer buttons on hover.
  const inPlex = (s.state === 'available' || s.state === 'downloaded');
  const plex = (s.watch && s.watch.plex) ? s.watch.plex : null;
  const emby = (s.watch && s.watch.emby) ? s.watch.emby : null;
  const jellyfin = (s.watch && s.watch.jellyfin) ? s.watch.jellyfin : null;
  const plexAvail = !!(plex && plex.available);
  const embyAvail = !!(emby && emby.available);
  const jfAvail = !!(jellyfin && jellyfin.available);

  const plexTick = inPlex
    ? `<span class="b plex-check" role="img" aria-label="Available in Plex" title="Available in Plex">${ICONS.check}</span>`
    : '';
  // Watched / resume marker from the Jellyfin watch entry (when carried).
  const jfPlay = playbackMarkup(s.watch && s.watch.jellyfin);

  let dlBtn;
  if (inPlex) {
    if (plexAvail) {
      dlBtn = `<a class="btn btn-gold mini-btn" data-act="watch-plex" data-url="${esc(plex.url || '')}" aria-label="Watch on Plex">${ICONS.play} Watch on Plex</a>`;
    } else if (embyAvail) {
      dlBtn = `<a class="btn btn-purple mini-btn" data-act="watch-emby" data-url="${esc(emby.url || '')}" aria-label="Watch on Emby">${ICONS.play} Watch on Emby</a>`;
    } else if (jfAvail && jellyfin.item_id) {
      // In-app playback is the primary action; keep the Jellyfin deep-link beside it.
      dlBtn = `<span class="jf-qrow">
        <button class="btn btn-gold mini-btn" data-act="play" data-jf-item="${esc(jellyfin.item_id)}" data-resume="${esc(jellyfin.playback_position || 0)}" aria-label="Play ${esc(entry.title)} in RKM">${ICONS.play} Play in RKM</button>
        <a class="btn btn-ghost mini-btn" data-act="watch-jellyfin" data-url="${esc(jellyfin.url || '')}" aria-label="Open in Jellyfin">${ICONS.play} Jellyfin</a>
      </span>`;
    } else if (jfAvail) {
      dlBtn = `<a class="btn btn-blue mini-btn" data-act="watch-jellyfin" data-url="${esc(jellyfin.url || '')}" aria-label="Watch on Jellyfin">${ICONS.play} Watch on Jellyfin</a>`;
    } else {
      dlBtn = `<button class="btn btn-green mini-btn" disabled>${ICONS.check} Available</button>`;
    }
  } else {
    dlBtn = downloadButton(entry, true);
  }

  const trailerBtn = `<button class="btn btn-ghost mini-btn" data-act="trailer" aria-label="Watch trailer for ${esc(entry.title)}">${ICONS.play} Trailer</button>`;
  const action = `<div class="card-actions${inPlex ? ' stacked' : ''}">${dlBtn}${trailerBtn}</div>`;

  return `<article class="card" tabindex="0" role="button" aria-label="${esc(entry.title)} (${entry.year})" data-id="${esc(entry.tmdbId)}">
    <div class="card-inner">
      <div class="imgbox">${img(entry)}</div>
      <div class="shade" aria-hidden="true"></div>
      <div class="badges">${badges.join('')}</div>
      ${plexTick}
      ${jfPlay}
      ${action}
      ${inPlex ? '' : dlStateMarkup(entry)}
    </div>
    <div class="card-info">
      <div class="ci-title">${esc(entry.title)}</div>
      <div class="ci-meta">${entry.year || ''} · ${entry.type === 'tv' ? 'TV Series' : 'Movie'}${entry.genres && entry.genres[0] ? ` · ${esc(entry.genres[0])}` : ''}</div>
    </div>
  </article>`;
}

/* ---------------- download button with states ---------------- */
// Phase 11: the button is capability/watch-driven (spec §19/§20). We branch on
// resource capabilities {can_download,can_watch} and watch.{plex,emby}.available —
// never on provider names or reconstructed state.
function _watchButtons(entry, s, svc, mini) {
  const plex = (s.watch && s.watch.plex && s.watch.plex.available) ? s.watch.plex : null;
  const emby = (s.watch && s.watch.emby && s.watch.emby.available) ? s.watch.emby : null;
  const jf = (s.watch && s.watch.jellyfin && s.watch.jellyfin.available) ? s.watch.jellyfin : null;
  const sm = mini ? 'btn-sm mini-btn' : '';
  const avail = [plex, emby, jf].filter(Boolean);
  if (!avail.length) return null;
  if (avail.length === 1) {
    if (plex) {
      return `<button class="btn btn-purple ${sm}" data-act="watch-plex" data-url="${esc(plex.url || '')}" aria-label="Watch ${esc(entry.title)} on Plex">${ICONS.play} Watch on Plex</button>`;
    }
    if (emby) {
      return `<button class="btn btn-purple ${sm}" data-act="watch-emby" data-url="${esc(emby.url || '')}" aria-label="Watch ${esc(entry.title)} on Emby">${ICONS.play} Watch on Emby</button>`;
    }
    return `<button class="btn btn-purple ${sm}" data-act="watch-jellyfin" data-url="${esc(jf.url || '')}" aria-label="Watch ${esc(entry.title)} on Jellyfin">${ICONS.play} Watch on Jellyfin</button>`;
  }
  // Multiple providers available — show the Watch Now dropdown trigger.
  return `<button class="btn btn-purple ${sm}" data-act="watchnow" data-plex-url="${esc(plex ? plex.url : '')}" data-emby-url="${esc(emby ? emby.url : '')}" data-jellyfin-url="${esc(jf ? jf.url : '')}" aria-label="Watch ${esc(entry.title)}">${ICONS.play} Watch Now ▼</button>`;
}

function downloadButton(entry, mini = false) {
  const s = st(entry);
  const caps = s.capabilities || { can_download: false, can_watch: false };
  const svc = (entry.type === 'tv' ? 'Sonarr' : 'Radarr');
  const sm = mini ? 'btn-sm mini-btn' : '';

  // WATCH path — driven purely by capability.can_watch + watch links (§19/§20).
  if (caps.can_watch) {
    const w = _watchButtons(entry, s, svc, mini);
    if (w) return w;
    // capability says watch is possible but no live link right now (link outage
    // is a capability problem, never status): show a disabled Available (§10).
    return `<button class="btn btn-green ${sm}" disabled>${ICONS.check} Available</button>`;
  }

  // DOWNLOAD / progress path — driven by capability.can_download + state.
  if (s.state === 'downloaded') {
    return `<button class="btn btn-green ${sm}" disabled>${ICONS.check} Available</button>`;
  }
  if (s.state === 'requested') {
    return `<button class="btn btn-blue ${sm}" disabled>${ICONS.check} Requested</button>`;
  }
  if (s.state === 'downloading') {
    return `<button class="btn btn-blue ${sm}" disabled>${ICONS.down} Downloading ${s.progress || 0}%</button>`;
  }
  // not_added / ambiguous / unavailable: only offer Download when the backend
  // says the user can request it (capability.can_download).
  if (caps.can_download) {
    return `<button class="btn btn-gold ${sm}" data-act="download" aria-label="${esc(entry.title)}: add to ${svc}">${ICONS.down} Download</button>`;
  }
  return `<button class="btn btn-ghost ${sm}" disabled>Unavailable</button>`;
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
  suggest: renderSuggest,
  movies: () => renderGrid('movies'),
  tv: () => renderGrid('tv'),
  watchlist: renderWatchlist,
  downloaded: renderDownloaded,
  library: renderLibraryView,
};

function renderHeader() {
  const pillState = SERVICES.radarr ? '' : SERVICES.sonarr ? '' : 'err';
  const updated = DATA?.updated ? `Updated ${timeAgo(DATA.updated)}` : 'No data yet';
  const nav = [['discover', 'Discover'], ['movies', 'Movies'], ['tv', 'TV Shows'], ['watchlist', 'Watchlist'], ['downloaded', 'Downloaded'], ['suggest', 'Suggest']];
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
    ['suggest', 'Suggest', ICONS.search],
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
  html += continueWatchingRowMarkup();
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
  const caps = s.capabilities || { can_download: false, can_watch: false };
  // WATCH path — capability.can_watch + watch links (§19/§20).
  if (caps.can_watch) {
    const plex = (s.watch && s.watch.plex && s.watch.plex.available) ? s.watch.plex : null;
    const emby = (s.watch && s.watch.emby && s.watch.emby.available) ? s.watch.emby : null;
    if (plex && emby) {
      return `<span class="hero-watch-group">
        <a class="btn btn-purple" target="_blank" rel="noopener" data-watchplex href="${esc(plex.url || '')}">${ICONS.play} Plex</a>
        <a class="btn btn-purple" target="_blank" rel="noopener" data-watchebmy href="${esc(emby.url || '')}">${ICONS.play} Emby</a>
      </span>`;
    } else if (plex) {
      return `<a class="btn btn-purple" target="_blank" rel="noopener" data-watchplex href="${esc(plex.url || '')}">${ICONS.play} Watch on Plex</a>`;
    } else if (emby) {
      return `<a class="btn btn-purple" target="_blank" rel="noopener" data-watchebmy href="${esc(emby.url || '')}">${ICONS.play} Watch on Emby</a>`;
    }
    return `<button class="btn btn-green" id="heroDownload" data-act="download" data-hero="1" data-id="${esc(e.imdbId)}" disabled>${ICONS.check} Available</button>`;
  }
  // DOWNLOAD / progress path — capability.can_download + state.
  if (s.state === 'downloaded') return `<button class="btn btn-green" id="heroDownload" data-hero="1" data-id="${esc(e.imdbId)}" disabled>${ICONS.check} Available</button>`;
  if (s.state === 'requested') return `<button class="btn btn-blue" id="heroDownload" data-hero="1" data-id="${esc(e.imdbId)}" disabled>${ICONS.check} Requested</button>`;
  if (s.state === 'downloading') return `<button class="btn btn-blue" id="heroDownload" data-hero="1" data-id="${esc(e.imdbId)}" disabled>${ICONS.down} Downloading ${s.progress || 0}%</button>`;
  if (caps.can_download) {
    return `<button class="btn btn-gold" id="heroDownload" data-act="download" data-hero="1" data-id="${esc(e.imdbId)}" aria-label="${esc(e.title)}: add to ${e.type === 'tv' ? 'Sonarr' : 'Radarr'}">${ICONS.down} Download</button>`;
  }
  return `<button class="btn btn-ghost" id="heroDownload" data-hero="1" data-id="${esc(e.imdbId)}" disabled>Unavailable</button>`;
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

/* ---------- suggest ---------- */
const SUGGEST_GENRES = [
  'Action','Adventure','Animation','Comedy','Crime','Documentary','Drama',
  'Family','Fantasy','History','Horror','Music','Mystery','Romance','Sci-Fi',
  'Thriller','War','Western','Kids','Reality','Talk','War & Politics',
];
let suggestState = {
  results: [],
  loading: false,
  filters: { media_type: 'all', genres: [], year_from: null, year_to: null, min_rating: 6.0, sort_by: 'popularity.desc', count: 20 },
  history: suggestHistoryLoad(),
};

/* ---------- suggest: recent-search history (last 10, persisted) ---------- */
const SUGGEST_HISTORY_KEY = 'rkm_suggest_history';
function suggestHistoryLoad() {
  try { return JSON.parse(localStorage.getItem(SUGGEST_HISTORY_KEY) || '[]'); }
  catch (e) { return []; }
}
function suggestHistorySave() {
  try { localStorage.setItem(SUGGEST_HISTORY_KEY, JSON.stringify(suggestState.history || [])); }
  catch (e) { /* storage may be unavailable — non-fatal */ }
}
function suggestHistoryPush(filters) {
  const snap = JSON.stringify(filters);
  suggestState.history = [filters, ...(suggestState.history || []).filter((h) => JSON.stringify(h) !== snap)].slice(0, 10);
  suggestHistorySave();
}
function suggestHistoryLabel(f) {
  const parts = [];
  if (f.media_type === 'movie') parts.push('Movies');
  else if (f.media_type === 'tv') parts.push('TV');
  else parts.push('All');
  if (f.genres && f.genres.length) parts.push(f.genres.slice(0, 2).join(', ') + (f.genres.length > 2 ? ' +' : ''));
  if (f.year_from || f.year_to) parts.push((f.year_from || '…') + '–' + (f.year_to || '…'));
  if (f.min_rating) parts.push(f.min_rating + '\u2605');
  parts.push(f.count ? f.count + ' results' : '');
  return parts.filter(Boolean).join(' \u00b7 ');
}

/* Build a display entry (same shape as dashboard-data.json) from a suggest item
   so a freshly-added title appears immediately in the Movies/TV/Watchlist grids
   without waiting for the dashboard to be regenerated. */
function entryFromSuggestItem(item) {
  return {
    id: (item.media_type === 'tv' ? 'tv' : 'movie') + ':tmdb:' + item.tmdb_id,
    title: item.title, year: item.year,
    type: item.media_type === 'tv' ? 'tv' : 'movie',
    isSeries: item.media_type === 'tv',
    tmdbId: item.tmdb_id, imdbId: item.imdb_id || '',
    poster: item.poster || '', backdrop: item.backdrop || '',
    genres: item.genres || [], overview: item.overview || '',
    tmdb_score: item.tmdb_score || 0,
    category: (item.genres && item.genres[0]) || 'Other',
    added: new Date().toISOString().slice(0, 10),
  };
}
/* Map a full enriched WatchlistEntry (the shape /api/suggest/add returns in
   `entry`, and exactly what's persisted to watchlist.json) onto a card-shaped
   entry so the grid card looks complete (poster, trailer, director, cast,
   scores) instead of a thin stub. */
function entryFromWatchlistEntry(w) {
  if (!w) return null;
  const isSeries = !!w.isSeries;
  // The persisted WatchlistEntry schema stores the synopsis under `snippet` /
  // `tmdb_overview` (NOT `overview`) and the TMDB score under `tmdb_score`
  // (snake_case). The dashboard generator (`rebuild_dashboard.py`) normalizes
  // these before writing `/dashboard-data.json`; here we must do the same so a
  // freshly-added Suggest card matches an existing dashboard card (synopsis +
  // scores in the detail modal).
  const overview = w.overview || w.snippet || w.tmdb_overview || '';
  const tmdbScore = Number(w.tmdbScore || w.tmdb_score || 0);
  return {
    id: (isSeries ? 'tv' : 'movie') + ':tmdb:' + w.tmdbId,
    title: w.title, year: w.year,
    type: isSeries ? 'tv' : 'movie',
    isSeries,
    tmdbId: w.tmdbId, imdbId: w.imdbId || '', imdb: w.imdb || 0, rt: w.rt || 0,
    poster: w.poster || '', backdrop: w.backdrop || '',
    genres: w.genres || [], overview,
    director: w.director || '', cast: w.cast || [],
    trailerId: w.trailerId || '',
    tmdbScore,                  // what openModal()/hero read (camelCase)
    tmdb_score: tmdbScore,      // what suggest badges read (snake_case)
    runtime: w.runtime || 0,
    category: w.category || 'Other',
    added: w.added || new Date().toISOString().slice(0, 10),
  };
}
/* Upsert a card-shaped entry (from resp.entry or a suggest item) into the app's
   data source so it appears in Movies/TV/Watchlist grids on next render (e.g.
   navigation). No render() here — that would rebuild the view / close a modal. */
function pushSuggestEntryToApp(entry) {
  if (!DATA || !Array.isArray(DATA.entries) || !entry || !entry.tmdbId) return;
  const id = entry.id || '';
  DATA.entries = [entry, ...DATA.entries.filter((e) => e.id !== id && String(e.tmdbId || '') !== String(entry.tmdbId))];
}

function renderSuggest() {
  const f = suggestState.filters;
  const genreChips = SUGGEST_GENRES.map((g) =>
    `<button class="chip sg-chip${f.genres.includes(g) ? ' active' : ''}" data-genre="${esc(g)}">${esc(g)}</button>`
  ).join('');

  const histHtml = (suggestState.history && suggestState.history.length)
    ? `<div class="sg-row sg-history"><span class="sg-label">Recent</span><div class="sg-history-chips">${suggestState.history.map((h, i) => {
        const active = JSON.stringify(h) === JSON.stringify(f);
        return `<button class="chip sg-hist-chip${active ? ' active' : ''}" data-hist="${i}" title="Search: ${esc(suggestHistoryLabel(h))}">${esc(suggestHistoryLabel(h))}</button>`;
      }).join('')}</div></div>`
    : '';

  const resultsHtml = suggestState.loading
    ? '<div class="suggest-loading"><div class="spinner"></div>Searching TMDB\u2026</div>'
    : suggestState.results.length
      ? `<div class="grid suggest-grid">${suggestState.results.map(suggestCardMarkup).join('')}</div>`
      : '<div class="suggest-empty">Set your filters and hit <b>Search</b> to discover movies and series.</div>';

  app.innerHTML = `<div class="view shell">
    <div class="view-head">
      <div><h1>Suggest</h1><div class="sub">Discover movies & series by your taste</div></div>
    </div>
    <div class="suggest-filters">
      <div class="sg-row">
        <label class="sg-label">Type</label>
        <div class="sg-opts">
          <button class="chip${f.media_type === 'all' ? ' active' : ''}" data-sg-type="all">All</button>
          <button class="chip${f.media_type === 'movie' ? ' active' : ''}" data-sg-type="movie">Movies</button>
          <button class="chip${f.media_type === 'tv' ? ' active' : ''}" data-sg-type="tv">TV Shows</button>
        </div>
      </div>
      <div class="sg-row">
        <label class="sg-label">Genres</label>
        <div class="sg-chips" id="sgGenres">${genreChips}</div>
      </div>
      <div class="sg-row sg-row-inline">
        <div class="sg-field">
          <label class="sg-label" for="sgYearFrom">Year from</label>
          <input class="sg-input" id="sgYearFrom" type="number" min="1900" max="2030" placeholder="e.g. 2020" value="${f.year_from || ''}">
        </div>
        <div class="sg-field">
          <label class="sg-label" for="sgYearTo">Year to</label>
          <input class="sg-input" id="sgYearTo" type="number" min="1900" max="2030" placeholder="e.g. 2025" value="${f.year_to || ''}">
        </div>
        <div class="sg-field">
          <label class="sg-label" for="sgRating">Min TMDB rating</label>
          <input class="sg-input" id="sgRating" type="number" min="0" max="10" step="0.5" value="${f.min_rating}">
        </div>
        <div class="sg-field">
          <label class="sg-label" for="sgSort">Sort by</label>
          <select class="sg-input" id="sgSort">
            <option value="popularity.desc"${f.sort_by === 'popularity.desc' ? ' selected' : ''}>Popularity</option>
            <option value="vote_average.desc"${f.sort_by === 'vote_average.desc' ? ' selected' : ''}>Rating</option>
            <option value="primary_release_date.desc"${f.sort_by === 'primary_release_date.desc' ? ' selected' : ''}>Release Date</option>
          </select>
        </div>
        <div class="sg-field">
          <label class="sg-label" for="sgCount">Results</label>
          <input class="sg-input" id="sgCount" type="number" min="5" max="50" value="${f.count}">
        </div>
      </div>
      <div class="sg-row sg-actions">
        <button class="btn btn-gold" id="sgSearch">${ICONS.search} Search</button>
        <button class="btn btn-ghost" id="sgClear">Clear filters</button>
        <span class="sg-count">${suggestState.results.length ? suggestState.results.length + ' results' : ''}</span>
      </div>
      ${histHtml}
    </div>
    <div class="suggest-results" id="sgResults">${resultsHtml}</div>
  </div>`;

  // Wire events
  _wireSuggestEvents();
}

function suggestCardMarkup(item) {
  const typeLabel = item.media_type === 'tv' ? 'TV' : 'MOVIE';
  const genres = (item.genres || []).slice(0, 2).join(' \u00b7 ');
  const badges = [];
  if (item.tmdb_score) badges.push(`<span class="b tmdb">\u2605 ${item.tmdb_score.toFixed(1)}</span>`);
  badges.push(`<span class="b ${item.media_type}">${typeLabel}</span>`);
  if (item.in_watchlist) badges.push('<span class="b" style="color:var(--gold)">On Watchlist</span>');
  if (item.in_library) badges.push('<span class="b" style="color:var(--green)">In Library</span>');

  const poster = item.poster
    ? `<img class="poster img-load" src="${esc(item.poster)}" alt="" loading="lazy" onload="this.classList.add('loaded')" referrerpolicy="no-referrer">`
    : `<div class="poster-ph">\ud83c\udfac</div>`;

  return `<article class="card suggest-card" data-tmdb-id="${item.tmdb_id}" data-type="${esc(item.media_type)}" data-title="${esc(item.title)}" tabindex="0" role="button" aria-label="${esc(item.title)} (${item.year || ''})">
      <div class="card-inner">
        <div class="imgbox">${poster}</div>
        <div class="shade" aria-hidden="true"></div>
        <div class="badges">${badges.join('')}</div>
        <div class="card-actions">
          <button class="btn btn-ghost btn-sm mini-btn" data-sg-add="${item.tmdb_id}" data-sg-type="${esc(item.media_type)}" aria-label="Add ${esc(item.title)} to watchlist">
            ${item.in_watchlist ? ICONS.check + ' Added' : ICONS.down + ' Add to Watchlist'}
          </button>
          <button class="btn btn-gold btn-sm mini-btn" data-sg-download="${item.tmdb_id}" data-sg-type="${esc(item.media_type)}" data-sg-title="${esc(item.title)}" data-sg-year="${item.year || ''}" aria-label="Download ${esc(item.title)}">
            ${ICONS.down} Download
          </button>
        </div>
      </div>
      <div class="card-info">
        <div class="ci-title">${esc(item.title)}</div>
        <div class="ci-meta">${item.year || ''} · ${genres}</div>
      </div>
    </article>`;
}

function _wireSuggestEvents() {
  // Genre chips
  $('#sgGenres')?.addEventListener('click', (e) => {
    const chip = e.target.closest('.sg-chip');
    if (!chip) return;
    const g = chip.dataset.genre;
    const f = suggestState.filters;
    if (f.genres.includes(g)) { f.genres = f.genres.filter((x) => x !== g); chip.classList.remove('active'); }
    else { f.genres.push(g); chip.classList.add('active'); }
  });

  // Type chips
  $$('[data-sg-type]').forEach((btn) => {
    btn.addEventListener('click', () => {
      suggestState.filters.media_type = btn.dataset.sgType;
      $$('[data-sg-type]').forEach((b) => b.classList.toggle('active', b.dataset.sgType === suggestState.filters.media_type));
    });
  });

  // Search button
  $('#sgSearch')?.addEventListener('click', _runSuggest);

  // Recent-search chip -> load that filter set + run
  $$('.sg-hist-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      const h = suggestState.history && suggestState.history[+chip.dataset.hist];
      if (!h) return;
      suggestState.filters = JSON.parse(JSON.stringify(h));
      renderSuggest();  // repopulate the input fields + active chips from filters
      _runSuggest();    // reads the (now-populated) inputs
    });
  });

  // Clear button
  $('#sgClear')?.addEventListener('click', () => {
    suggestState.filters = { media_type: 'all', genres: [], year_from: null, year_to: null, min_rating: 6.0, sort_by: 'popularity.desc', count: 20 };
    suggestState.results = [];
    renderSuggest();
  });

  // Card results — Add / Download buttons + card-click detail modal
  $('#sgResults')?.addEventListener('click', (e) => {
    // Add to Watchlist button
    const addBtn = e.target.closest('[data-sg-add]');
    if (addBtn) {
      e.preventDefault(); e.stopPropagation();
      const item = suggestState.results.find((r) => r.tmdb_id === +addBtn.dataset.sgAdd);
      if (!item) return;
      sgAddToWatchlist(item, addBtn);
      return;
    }

    // Download button — adds to watchlist AND triggers download
    const dlBtn = e.target.closest('[data-sg-download]');
    if (dlBtn) {
      e.preventDefault(); e.stopPropagation();
      const item = suggestState.results.find((r) => r.tmdb_id === +dlBtn.dataset.sgDownload);
      if (!item) return;
      sgDownload(item, dlBtn);
      return;
    }

    // Click elsewhere on the card → open detail modal (IMDb rating + synopsis)
    const card = e.target.closest('.suggest-card[data-tmdb-id]');
    if (card && !e.target.closest('button')) {
      e.preventDefault();
      openSuggestDetail(card.dataset.tmdbId, card.dataset.type, card.dataset.title);
    }
  });
}

/* ---------- suggest card actions (shared by card + detail modal) ---------- */
function sgAddToWatchlist(item, btn) {
  if (!item || !btn) return Promise.resolve(false);
  btn.disabled = true;
  btn.innerHTML = ICONS.check + ' Adding\u2026';
  return API.postJSON(`/api/suggest/add/${item.tmdb_id}?media_type=${item.media_type}`)
    .then((resp) => {
      if (resp.ok) {
        item.in_watchlist = true;
        btn.innerHTML = ICONS.check + ' Added';
        btn.classList.add('done');
        toast('Added to watchlist', resp.title || item.title || '');
        // Full card (poster/trailer/director/cast/scores) from the enriched
        // entry the backend persisted; fall back to the thin suggest stub.
        pushSuggestEntryToApp(entryFromWatchlistEntry(resp.entry) || entryFromSuggestItem(item));
        return true;
      }
      btn.disabled = false;
      btn.innerHTML = item.in_watchlist ? (ICONS.check + ' Added') : (ICONS.down + ' Add to Watchlist');
      toast('Add failed', resp.message || 'unknown error', 'err');
      return false;
    })
    .catch((err) => {
      btn.disabled = false;
      btn.innerHTML = item.in_watchlist ? (ICONS.check + ' Added') : (ICONS.down + ' Add to Watchlist');
      toast('Add failed', err.message, 'err');
      return false;
    });
}

// Adds to watchlist first, then triggers the Radarr/Sonarr download.
function sgDownload(item, btn) {
  if (!item || !btn) return Promise.resolve(false);
  btn.disabled = true;
  btn.innerHTML = ICONS.down + ' Adding\u2026';
  return API.postJSON(`/api/suggest/add/${item.tmdb_id}?media_type=${item.media_type}`)
    .then((addResp) => {
      if (!addResp.ok && !addResp.already) throw new Error(addResp.message || 'Failed to add to watchlist');
      item.in_watchlist = true;
      // Ensure the title is/becomes a watchlist entry (downloading also adds it)
      // with a FULL card (poster/trailer/…), not a thin stub.
      pushSuggestEntryToApp(entryFromWatchlistEntry(addResp.entry) || entryFromSuggestItem(item));
      const mediaId = (item.media_type === 'tv' ? 'tv' : 'movie') + ':tmdb:' + item.tmdb_id;
      return API.requestMedia(mediaId);
    })
    .then(() => {
      btn.innerHTML = ICONS.check + ' Downloading';
      btn.classList.add('done');
      toast('Download started', item.title || '');
      return true;
    })
    .catch((err) => {
      btn.disabled = false;
      btn.innerHTML = ICONS.down + ' Download';
      toast('Download failed', err.message, 'err');
      return false;
    });
}

/* ---------- suggest card-click detail modal (issue: IMDb rating + synopsis) ---------- */
function openSuggestDetail(tmdbId, mediaType, fallbackTitle) {
  const overlay = document.createElement('div');
  overlay.className = 'overlay';
  overlay.tabIndex = -1;
  overlay.innerHTML = `<div class="modal suggest-detail" role="dialog" aria-modal="true" aria-label="${esc(fallbackTitle || 'Title details')}">
    <div class="modal-back"><div class="ph">🎬</div><div class="shade" aria-hidden="true"></div>
      <button class="modal-x" data-role="close" aria-label="Close">${ICONS.x}</button></div>
    <div class="modal-content"><div class="suggest-detail-loading"><div class="spinner"></div>Fetching details\u2026</div></div>
  </div>`;
  document.body.appendChild(overlay);
  requestAnimationFrame(() => overlay.classList.add('show'));
  document.body.style.overflow = 'hidden';
  overlay.focus();

  const closeFn = () => { overlay.remove(); document.body.style.overflow = ''; };
  const sel = overlay.querySelector('[data-role="close"]');
  if (sel) sel.addEventListener('click', closeFn);
  overlay.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeFn(); });
  overlay.addEventListener('click', (e) => { if (e.target === overlay) closeFn(); });

  // On-demand fetch: full metadata + IMDb rating + synopsis (cached backend).
  API.suggestDetail(tmdbId, mediaType)
    .then((d) => {
      if (!overlay.isConnected) return;
      if (!d || d.ok === false) {
        overlay.querySelector('.modal-content').innerHTML =
          `<div class="suggest-empty">Couldn't load details for ${esc(fallbackTitle || 'this title')}.</div>`;
        return;
      }
      renderSuggestDetailBody(overlay, d, fallbackTitle, closeFn);
    })
    .catch((err) => {
      if (!overlay.isConnected) return;
      overlay.querySelector('.modal-content').innerHTML =
        `<div class="suggest-empty">Couldn't load details: ${esc(err.message)}</div>`;
    });
}

function renderSuggestDetailBody(overlay, d, fallbackTitle, closeFn) {
  const title = d.title || fallbackTitle || '';
  const typeLabel = d.media_type === 'tv' ? 'TV Series' : 'Movie';
  const meta = [d.year, d.cert, d.runtime ? fmtRuntime(d.runtime) : '', typeLabel].filter(Boolean);
  const genres = (d.genres || []).slice(0, 4);
  const scores = [];
  if (d.imdb_rating > 0) scores.push(`<span class="score imdb">${ICONS.star} ${fmtRating(d.imdb_rating)} IMDb</span>`);
  else if (d.imdb_id) scores.push('<span class="score missing">IMDb unavailable</span>');
  if (d.tmdb_score > 0) scores.push(`<span class="score tmdb">${ICONS.star} ${fmtRating(d.tmdb_score)} TMDB</span>`);
  const facts = [];
  if (d.director) facts.push(['Director', d.director]);
  if (d.cast && d.cast.length) facts.push(['Starring', d.cast.slice(0, 5).join(' · ')]);
  if (d.vote_count) facts.push(['Votes', Number(d.vote_count).toLocaleString()]);
  const back = d.backdrop || d.poster || '';
  const bg = back ? `<img src="${esc(back)}" alt="" referrerpolicy="no-referrer">` : '<div class="ph">🎬</div>';

  overlay.innerHTML = `<div class="modal suggest-detail" role="dialog" aria-modal="true" aria-label="${esc(title)} details">
    <div class="modal-back">${bg}<div class="shade" aria-hidden="true"></div>
      <button class="modal-x" data-role="close" aria-label="Close">${ICONS.x}</button></div>
    <div class="modal-content">
      <h2 class="modal-title">${esc(title)}</h2>
      <div class="modal-meta">${meta.map((m) => `<span class="chip">${esc(m)}</span>`).join('')}${genres.map((g) => `<span class="chip">${esc(g)}</span>`).join('')}</div>
      <div class="modal-scores">${scores.join('') || '<span class="score missing">No rating data yet</span>'}</div>
      <p class="modal-overview">${esc(d.overview || 'No synopsis available yet.')}</p>
      ${facts.length ? `<div class="modal-facts">${facts.map((f) => `<div class="fact"><div class="k">${esc(f[0])}</div><div class="v">${esc(f[1])}</div></div>`).join('')}</div>` : ''}
      <div class="modal-actions">
        <button class="btn btn-ghost" data-sg-detail-add>${ICONS.down} Add to Watchlist</button>
        <button class="btn btn-gold" data-sg-detail-dl>${ICONS.down} Download</button>
      </div>
    </div>
  </div>`;

  overlay.focus();
  const csel = overlay.querySelector('[data-role="close"]');
  if (csel) csel.addEventListener('click', closeFn);
  const item = { tmdb_id: d.id, media_type: d.media_type, title, in_watchlist: !!d.already_in_watchlist };
  const addB = overlay.querySelector('[data-sg-detail-add]');
  const dlB = overlay.querySelector('[data-sg-detail-dl]');
  if (addB) addB.addEventListener('click', (e) => { e.preventDefault(); sgAddToWatchlist(item, addB); });
  if (dlB) dlB.addEventListener('click', (e) => { e.preventDefault(); sgDownload(item, dlB); });
}

async function _runSuggest() {
  const f = suggestState.filters;
  // Read current input values
  f.year_from = +$('#sgYearFrom')?.value || null;
  f.year_to = +$('#sgYearTo')?.value || null;
  f.min_rating = +$('#sgRating')?.value || 0;
  f.sort_by = $('#sgSort')?.value || 'popularity.desc';
  f.count = +$('#sgCount')?.value || 20;

  suggestState.loading = true;
  const container = $('#sgResults');
  if (container) container.innerHTML = '<div class="suggest-loading"><div class="spinner"></div>Searching TMDB\u2026</div>';

  try {
    const resp = await API.suggest(f);
    suggestState.results = resp.results || [];
    suggestState.loading = false;
    suggestHistoryPush(JSON.parse(JSON.stringify(f)));
    if (container) container.innerHTML = `<div class="grid suggest-grid">${suggestState.results.map(suggestCardMarkup).join('')}</div>`;
    const countEl = document.querySelector('.sg-count');
    if (countEl) countEl.textContent = suggestState.results.length + ' results';
  } catch (err) {
    suggestState.loading = false;
    if (container) container.innerHTML = `<div class="suggest-empty">Search failed: ${esc(err.message)}</div>`;
    toast('Suggest failed', err.message, 'err');
  }
}

/* ---------- lazy grid (infinite scroll) ---------- */
// Render the first LAZY_PAGE cards immediately and append the rest as the user
// scrolls to the #gridMore sentinel — keeps the DOM light so big lists
// (Movies/TV/Watchlist) stay smooth. Re-initialised on every view render.
const LAZY_PAGE = 36;
let lazyObs = null;
let lazyCtx = null;          // { entries, idx, gridEl }

function initLazyGrid(entries) {
  lazyTeardown();
  const grid = $('#grid');
  if (!grid || !Array.isArray(entries)) return;
  const first = Math.min(LAZY_PAGE, entries.length);
  lazyCtx = { entries, idx: first, gridEl: grid };
  if (entries.length <= first) {
    const sent = $('#gridMore');
    if (sent) sent.remove();
    return;
  }
  const sentinel = $('#gridMore');
  if (!sentinel) return;
  lazyObs = new IntersectionObserver((io) => {
    if (io[0].isIntersecting) lazyAppend();
  }, { rootMargin: '900px 0px' });
  lazyObs.observe(sentinel);
}

function lazyAppend() {
  if (!lazyCtx) return;
  const { entries, gridEl } = lazyCtx;
  if (lazyCtx.idx >= entries.length) { lazyTeardown(); return; }
  const batch = entries.slice(lazyCtx.idx, lazyCtx.idx + LAZY_PAGE);
  lazyCtx.idx += batch.length;
  const html = batch.map((e) => cardMarkup(e)).join('');
  const sent = $('#gridMore');
  if (sent) sent.insertAdjacentHTML('beforebegin', html);
  else gridEl.insertAdjacentHTML('beforeend', html);
  if (lazyCtx.idx >= entries.length) {
    const s = $('#gridMore');
    if (s) s.remove();
    lazyTeardown();
  }
}

function lazyTeardown() {
  if (lazyObs) { lazyObs.disconnect(); lazyObs = null; }
  lazyCtx = null;
}

/* ---------- grid views (movies / tv) ---------- */
let gridGenre = {};           // per-kind active genre filter (source-filtered)

function renderGrid(kind) {
  let entries = DATA.entries.filter((e) => e.type === (kind === 'tv' ? 'tv' : 'movie'));
  const gf = gridGenre[kind] || '';
  if (gf) entries = entries.filter((e) => (e.genres || []).includes(gf));
  const title = kind === 'tv' ? 'TV Shows' : 'Movies';
  const genres = [...new Set(entries.flatMap((e) => e.genres || []))].sort();
  const gSel = `<label class="sr-only" for="gfilter">Filter by genre</label>
    <select class="select" id="gfilter" aria-label="Filter by genre"><option value="">All genres</option>${genres.map((g) => `<option value="${esc(g)}">${esc(g)}</option>`).join('')}</select>`;
  const page = entries.slice(0, LAZY_PAGE);
  const inner = entries.length
    ? `<div class="grid" id="grid">${page.map((e) => cardMarkup(e)).join('')}${entries.length > LAZY_PAGE ? '<div class="grid-more" id="gridMore" aria-hidden="true"></div>' : ''}</div>`
    : emptyState(kind === 'tv' ? 'No TV series yet' : 'No movies yet', `Your ${title.toLowerCase()} will appear here as the recommendation engine adds them.`);
  app.innerHTML = `<div class="view shell">
    <div class="view-head">
      <div><h1>${title}</h1><div class="sub">${entries.length} title${entries.length === 1 ? '' : 's'}</div></div>
      <div class="controls">${gSel}</div>
    </div>
    ${inner}
  </div>`;
  const sel = $('#gfilter');
  if (sel) {
    sel.value = gf;
    sel.addEventListener('change', () => { gridGenre[kind] = sel.value; renderGrid(kind); });
  }
  initLazyGrid(entries);
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
  const page = list.slice(0, LAZY_PAGE);
  const inner = list.length
    ? `<div class="grid" id="grid">${page.map((e) => cardMarkup(e)).join('')}${list.length > LAZY_PAGE ? '<div class="grid-more" id="gridMore" aria-hidden="true"></div>' : ''}</div>`
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
  initLazyGrid(list);
}

/* ---------- downloaded ---------- */
function renderDownloaded() {
  const list = DATA.entries.filter((e) => isDownloaded(e) || isBusy(e));
  const page = list.slice(0, LAZY_PAGE);
  const inner = list.length
    ? `<div class="grid" id="grid">${page.map((e) => cardMarkup(e)).join('')}${list.length > LAZY_PAGE ? '<div class="grid-more" id="gridMore" aria-hidden="true"></div>' : ''}</div>`
    : emptyState('Nothing downloaded yet', 'Click Download on any title and it will flow in here automatically.');
  app.innerHTML = `<div class="view shell">
    <div class="view-head">
      <div><h1>Downloaded</h1><div class="sub">${list.length} title${list.length === 1 ? '' : 's'} in your library pipeline</div></div>
    </div>
    ${inner}
  </div>`;
  initLazyGrid(list);
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
      ${LIB.recent && LIB.recent.length ? `<div class="row-head"><h2><span class="swatch" aria-hidden="true"></span> Recently Added to Library</h2></div><div class="row">${LIB.recent.map((r) => libraryCard(r)).join('')}</div>` : ''}
      ${fullLibraryGridMarkup()}`
    : emptyState('Library unavailable', 'Connect Plex or Emby in your .env and it will appear here automatically.');
  app.innerHTML = `<div class="view shell">
    <div class="view-head"><div><h1>My Library</h1><div class="sub">Your media server at a glance</div></div></div>
    ${inner}
  </div>`;
}

function libraryCard(r) {
  // Poster: Jellyfin items get a proxied primary image via our /api proxy (keeps
  // the token server-side); fall back to the Plex thumb proxy for Plex items.
  const thumb = r.item_id
    ? `<img src="${esc('/api/jellyfin/poster?id=' + encodeURIComponent(r.item_id) + '&width=500')}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display='none'">`
    : (r.thumb
        ? `<img src="${esc('/api/plex/thumb?path=' + encodeURIComponent(r.thumb) + '&width=500')}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display='none'">`
        : '');
  const plexUrl = r.plexUrl || (LIB?.urls?.plex ? LIB.urls.plex + '/search' : '');
  let embyUrl = r.embyUrl || '';
  if (!embyUrl && LIB?.urls?.emby) {
    embyUrl = `${LIB.urls.emby.replace(/\/web\/index\.html$/, '')}/web/index.html#!/search/${encodeURIComponent(r.title || '')}`;
  }
  // Jellyfin: prefer the item's direct details link (from the backend), else build
  // one from item_id. Jellyfin web uses `#/` hash routes (NOT `#!/` hashbang).
  let jfUrl = r.jellyfinUrl || '';
  if (!jfUrl && r.item_id && LIB?.urls?.jellyfin) {
    jfUrl = `${LIB.urls.jellyfin}#/details?id=${encodeURIComponent(r.item_id)}`;
  }
  if (!jfUrl && LIB?.urls?.jellyfin) {
    jfUrl = `${LIB.urls.jellyfin}#/search?query=${encodeURIComponent(r.title || '')}`;
  }
  return `<div class="card" tabindex="0" role="button" aria-label="${esc(r.title)}">
    <div class="card-inner" style="--card-aspect: 2/3">
      <div class="imgbox">${thumb || '<div class="poster-ph">🎬</div>'}</div>
      <div class="shade"></div>
      <div class="badges"><span class="b ${r.type}">${r.type === 'tv' ? 'TV' : 'MOVIE'}</span></div>
      ${playbackMarkup(r)}
      <div class="watchnow" style="position:absolute; left:50%; bottom:12px; transform:translateX(-50%); z-index:5; display:flex; gap:8px;">
        ${r.item_id ? `<button class="btn btn-gold btn-sm mini-btn" data-act="play" data-jf-item="${esc(r.item_id)}" data-resume="${esc(r.playback_position || 0)}" data-title="${esc(r.title)}">${ICONS.play} Play in RKM</button>` : ''}
        ${plexUrl ? `<button class="btn btn-purple btn-sm mini-btn" data-act="watch-plex" data-url="${esc(plexUrl)}">${ICONS.play} Plex</button>` : ''}
        ${embyUrl ? `<button class="btn btn-gold btn-sm mini-btn" data-act="watch-emby" data-url="${esc(embyUrl)}">${ICONS.play} Emby</button>` : ''}
        ${jfUrl ? `<button class="btn btn-blue btn-sm mini-btn" data-act="watch-jellyfin" data-url="${esc(jfUrl)}">${ICONS.play} Jellyfin</button>` : ''}
      </div>
    </div>
    <div class="card-info"><div class="ci-title">${esc(r.title)}</div><div class="ci-meta">${r.year || ''}</div></div>
  </div>`;
}

function fullLibraryGridMarkup() {
  if (!LIBALL || !LIBALL.length) return '';
  return `<div class="row-head"><h2><span class="swatch" aria-hidden="true"></span> Full Library <span class="libcount">${LIBALL.length} titles</span></h2></div>
    <div class="grid">${LIBALL.map((r) => libraryCard(r)).join('')}</div>`;
}

function continueWatchingRowMarkup() {
  const items = (LIBWATCH || []).filter((r) => r.item_id && (Number(r.playback_position) > 0 || r.played));
  if (!items.length) return '';
  return `<div class="row-head"><h2><span class="swatch" aria-hidden="true"></span> Continue Watching</h2></div>
    <div class="row">${items.map((r) => libraryCard(r)).join('')}</div>`;
}

function libraryStripMarkup() {
  const counts = LIB?.counts || { movie: 0, show: 0 };
  if (LIB?.available) {
    // Connected: show a live "My Library" row with counts + a door into the
    // Library view (which lists Jellyfin items with Watch buttons).
    return `<div class="row-head">
      <h2><span class="swatch" aria-hidden="true"></span> My Library · ${esc(LIB?.server || '')}</h2>
      <button class="row-more" data-view="library">Open ${'›'} <span class="libcount">${counts.movie || 0} films · ${counts.show || 0} shows</span></button>
    </div>`;
  }
  return `<div class="row-head">
    <h2><span class="swatch" aria-hidden="true"></span> My Library</h2>
    <button class="row-more" data-view="library">Open ${'›'}</button>
  </div>
  <div class="row"><div class="empty" style="margin:0; padding:46px 20px; border-style:dashed">
    <div class="ec">📚</div><h3>Library preview</h3>
    <p>Connect a library backend (PLEX_URL/PLEX_TOKEN, EMBY_URL/EMBY_API_KEY, or JELLYFIN_URL/JELLYFIN_API_KEY) and your library counts and recent additions appear here.</p>
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
    const playBtn = e.target.closest('[data-role="play-jellyfin"]');
    if (trailerBtn) { e.preventDefault(); loadTrailer(); return; }
    if (dlBtn) { e.preventDefault(); if (modalEntry) doDownload(modalEntry, { in: 'modal' }); return; }
    if (playBtn) { e.preventDefault(); openPlayer(playBtn.dataset.jfItem, modalEntry ? modalEntry.title : '', Number(playBtn.dataset.resume || 0)); return; }
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

/* In-app "Play in RKM" button — native <video> over the /api/jellyfin/stream
   proxy. Only rendered when Jellyfin is the available source AND carries a
   native item id. Returns '' otherwise so callers can prepend it freely. */
function playInRkmMarkup(jf, entry) {
  if (!jf || !jf.item_id) return '';
  const title = (entry && entry.title) || '';
  return `<button class="btn btn-gold" data-role="play-jellyfin" data-jf-item="${esc(jf.item_id)}" data-resume="${esc(jf.playback_position || 0)}" aria-label="Play ${esc(title)} in RKM">${ICONS.play} Play in RKM</button>`;
}

/* Watched / progress marker from an object carrying played/playback_position/
   runtime (seconds). Fully played -> a watched tick; partially watched (pos>0)
   -> an amber resume bar with %; otherwise '' . */
function playbackMarkup(info) {
  if (!info) return '';
  const played = !!info.played;
  const pos = info.playback_position || 0;
  const runtime = info.runtime || 0;
  if (played) {
    return `<span class="b watched-tick" role="img" aria-label="Watched" title="Watched">${ICONS.check}</span>`;
  }
  if (runtime > 0 && pos > 0) {
    const pct = Math.min(100, Math.round((pos / runtime) * 100));
    return `<span class="resume-bar" role="img" aria-label="${pct}% watched" title="${pct}% watched"><span class="resume-fill" style="width:${pct}%"></span><span class="resume-pct">${pct}%</span></span>`;
  }
  return '';
}

function modalDownloadButton(entry, s) {
  const caps = s.capabilities || { can_download: false, can_watch: false };
  const svc = entry.type === 'tv' ? 'Sonarr' : 'Radarr';
  // WATCH path — capability.can_watch + watch links (§19/§20).
  if (caps.can_watch) {
    const plex = (s.watch && s.watch.plex && s.watch.plex.available) ? s.watch.plex : null;
    const emby = (s.watch && s.watch.emby && s.watch.emby.available) ? s.watch.emby : null;
    const jf = (s.watch && s.watch.jellyfin && s.watch.jellyfin.available) ? s.watch.jellyfin : null;
    // In-app playback first when Jellyfin is available with a native item id.
    const jwt = playInRkmMarkup(jf, entry);
    if (plex && emby) {
      return `<div class="modal-watch-group">${jwt}
        <a class="btn btn-purple" target="_blank" rel="noopener" data-role="watchplex" href="${esc(plex.url || '')}">${ICONS.play} Watch on Plex</a>
        <a class="btn btn-purple" target="_blank" rel="noopener" data-role="watchemby" href="${esc(emby.url || '')}">${ICONS.play} Watch on Emby</a>
      </div>`;
    } else if (jf && (plex || emby)) {
      return `<div class="modal-watch-group">${jwt}
        ${plex ? `<a class="btn btn-purple" target="_blank" rel="noopener" data-role="watchplex" href="${esc(plex.url || '')}">${ICONS.play} Watch on Plex</a>` : ''}
        ${emby ? `<a class="btn btn-purple" target="_blank" rel="noopener" data-role="watchemby" href="${esc(emby.url || '')}">${ICONS.play} Watch on Emby</a>` : ''}
        <a class="btn btn-purple" target="_blank" rel="noopener" data-role="watchjellyfin" href="${esc(jf.url || '')}">${ICONS.play} Watch on Jellyfin</a>
      </div>`;
    } else if (plex) {
      return `<div class="modal-watch-group">${jwt}<a class="btn btn-purple" data-role="watchplex" target="_blank" rel="noopener" href="${esc(plex.url || '')}">${ICONS.play} Watch on Plex</a></div>`;
    } else if (emby) {
      return `<div class="modal-watch-group">${jwt}<a class="btn btn-purple" data-role="watchemby" target="_blank" rel="noopener" href="${esc(emby.url || '')}">${ICONS.play} Watch on Emby</a></div>`;
    } else if (jf) {
      return `<div class="modal-watch-group">${jwt}<a class="btn btn-purple" data-role="watchjellyfin" target="_blank" rel="noopener" href="${esc(jf.url || '')}">${ICONS.play} Watch on Jellyfin</a></div>`;
    }
    return `<button class="btn btn-green" data-role="download" disabled>${ICONS.check} Available</button>`;
  }
  // DOWNLOAD / progress path — capability.can_download + state.
  if (s.state === 'downloaded') return `<button class="btn btn-green" data-role="download" disabled>${ICONS.check} Available in library</button>`;
  if (s.state === 'requested') return `<button class="btn btn-blue" data-role="download" disabled>${ICONS.check} Requested</button>`;
  if (s.state === 'downloading') return `<button class="btn btn-blue" data-role="download" disabled>${ICONS.down} Downloading ${s.progress || 0}%</button>`;
  if (caps.can_download) {
    return `<button class="btn btn-gold" data-role="download" aria-label="Add ${esc(entry.title)} to ${svc}">${ICONS.down} Download</button>`;
  }
  return `<button class="btn btn-ghost" data-role="download" disabled>Unavailable</button>`;
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

/* ---------------- in-app Jellyfin player ---------------- */
/* Native <video> overlay streaming through the same-origin /api/jellyfin/stream
   proxy (credential stays server-side). Direct play → Range/seeking intact. */
function openPlayer(itemId, title, resume) {
  closePlayer();
  _playerItemId = itemId || '';
  _playerResume = Math.max(0, Number(resume) || 0);
  _playerLastReport = 0;
  const ov = document.createElement('div');
  ov.className = 'overlay player-overlay';
  ov.innerHTML = `<div class="modal player-modal" role="dialog" aria-modal="true" aria-label="${esc(title || '')} player">
    <div class="player-head">
      <div class="player-title">${esc(title || 'Now playing')}</div>
      <button class="modal-x" data-role="close-player" aria-label="Close">${ICONS.x}</button>
    </div>
    <div class="player-stage">
      <video id="rkmPlayer" controls autoplay playsinline src="${esc('/api/jellyfin/stream/' + encodeURIComponent(itemId))}"></video>
    </div>
    <div class="player-note">Streaming direct from your library — seeking supported.</div>
  </div>`;
  document.body.appendChild(ov);
  requestAnimationFrame(() => ov.classList.add('show'));
  document.body.style.overflow = 'hidden';
  ov.addEventListener('click', (e) => {
    if (e.target === ov || e.target.closest('[data-role="close-player"]')) { closePlayer(); return; }
  });
  ov.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePlayer(); });
  const v = ov.querySelector('video');
  if (v) {
    v.focus();
    v.addEventListener('error', () => {
      if (modalPlayerErr(ov)) { reportProgress(_playerItemId, v.currentTime || 0, 'stopped'); showPlayerErr(ov); }
    });
    // Resume: seek the Range-backed stream to the saved position once duration is known.
    v.addEventListener('loadedmetadata', () => {
      if (_playerResume > 0 && v.duration && _playerResume < v.duration) {
        try { v.currentTime = _playerResume; } catch (e) { /* ignore seek failure */ }
      }
    });
    // Report back to Jellyfin, but never clobber the resume point: skip
    // play/timeupdate until the position reflects a resume (or real progress).
    v.addEventListener('play',    () => _reportPos(v, 'start'));
    v.addEventListener('timeupdate', () => {
      const now = Date.now();
      if (now - _playerLastReport < 5000) return;
      _playerLastReport = now;
      _reportPos(v, 'timeupdate');
    });
    v.addEventListener('pause', () => reportProgress(_playerItemId, v.currentTime || 0, 'stopped'));
    v.addEventListener('ended', () => reportProgress(_playerItemId, v.currentTime || 0, 'stopped'));
  }
}
let _playerItemId = '';
let _playerResume = 0;
let _playerLastReport = 0;
let _playerErrShown = false;
/* Only report play/timeupdate once the position reflects a resume (if one is
   expected) — otherwise a fresh stream sitting at 0s would reset Jellyfin's
   saved spot. Pause/ended/error (stopped) always report so the position holds. */
function _reportPos(v, event) {
  const pos = (v && v.currentTime) || 0;
  if (_playerResume > 0 && pos < _playerResume - 1) return; // seek not applied yet
  reportProgress(_playerItemId, pos, event);
}
/* POST playback position to the /api/jellyfin/progress proxy (token stays
   server-side). Fire-and-forget; a missing/not-Jellyfin backend is a soft no. */
function reportProgress(itemId, seconds, event) {
  if (!itemId) return;
  const ticks = Math.round((seconds || 0) * 1e7);
  try {
    fetch('/api/jellyfin/progress', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: itemId, position_ticks: ticks, is_paused: false, event }),
    }).catch(() => {});
  } catch (e) { /* ignore */ }
}
function modalPlayerErr(ov) {
  const v = ov.querySelector('video');
  if (!v || _playerErrShown) return false;
  _playerErrShown = true;
  return true;
}
function closePlayer() {
  _playerErrShown = false;
  const ov = $('.player-overlay');
  if (!ov) return;
  const v = ov.querySelector('video');
  if (v) { v.pause(); v.removeAttribute('src'); v.load(); }
  ov.classList.remove('show');
  document.body.style.overflow = '';
  setTimeout(() => ov.remove(), 220);
}
function showPlayerErr(ov) {
  const stage = ov.querySelector('.player-stage');
  if (!stage) return;
  stage.innerHTML = `<div class="player-error">⚠️ Couldn't play this file in the browser — the codec may not be supported.<br><span class="player-err-sub">Open it in Jellyfin directly instead.</span></div>`;
}

/* ---------------- interactions ---------------- */
/* Optimistically patch the in-memory resource so the UI reflects a just-made
   request without waiting for the 15s poll. §15 vocab: requested/already_requested
   both mean "now have it" for the controlling state flow here. */
function _applyRequestResult(entry, res) {
  const mid = API.mediaIdOf(entry);
  const provider = res.service || (entry.type === 'tv' ? 'sonarr' : 'radarr');
  // A terminal success (requested / already requested / available) -> REQUESTED-style.
  const terminal = (res.state === 'requested' || res.state === 'already_requested' || res.state === 'available');
  const state = terminal ? 'requested' : (res.state === 'ambiguous' ? 'ambiguous' : 'not_added');
  if (USES_RESOURCE_API) {
    RES[mid] = {
      id: mid,
      title: entry.title || '',
      year: entry.year || null,
      type: (entry.type === 'tv' || entry.isSeries) ? 'tv' : 'movie',
      status: state,
      capabilities: { can_download: true, can_watch: false },
      watch: {},
      acquisition: { provider, status: state },
      detail: res.message || '',
    };
  } else {
    const legacy = LEGACY_STATUS[entry.imdbId] || {};
    LEGACY_STATUS[entry.imdbId] = Object.assign({}, legacy, {
      state, service: provider, detail: res.message || legacy.detail,
    });
  }
}

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
    _applyRequestResult(entry, res);
    toast(res.message || `${entry.title} added to ${svc}`, entry.type === 'tv' ? 'Episodes will start downloading shortly.' : 'Your download will begin shortly.', 'ok');
    paint(`✓ Added to ${svc}`, 'btn-green', true);
    if (panel && panel.dataset.role === 'dlstate') { panel.className = 'dl-state showing ok'; panel.innerHTML = `<span>${ICONS.check} Requested — search running</span>`; }
    setTimeout(() => refreshStatus(true).then(renderMinimal), 2500);
  } catch (e) {
    toast('Download failed', e.message || 'Could not reach the download service.', 'err', 6000);
    paint('Failed — Retry', 'btn-danger', false);
    if (USES_RESOURCE_API) {
      const mid = API.mediaIdOf(entry);
      const r = RES[mid] || {};
      RES[mid] = Object.assign({}, r, { status: 'unavailable', capabilities: { can_download: true, can_watch: false }, detail: e.message });
    } else {
      const legacy = LEGACY_STATUS[entry.imdbId] || {};
      LEGACY_STATUS[entry.imdbId] = Object.assign({}, legacy, { state: 'unavailable', service: entry.type === 'tv' ? 'sonarr' : 'radarr' });
    }
  }
  if (opts.in !== 'hero' && opts.in !== 'modal') rerenderDownloadButtons(entry);
}

function rerenderDownloadButtons(entry) {
  const s = st(entry);
  // update any visible card buttons for this entry using the same capability logic
  const btns = $$(`[data-id="${entry.imdbId}"] [data-act="download"]`);
  const labels = { downloaded: 'Available', requested: 'Requested', downloading: 'Downloading', unavailable: 'Unavailable' };
  btns.forEach((b) => {
    if (canWatch(entry)) {
      b.innerHTML = `${ICONS.play} Watch Now`;
      b.className = `btn btn-purple btn-sm mini-btn`;
      b.disabled = false;
      return;
    }
    const label = labels[s.state] || 'Download';
    const cls = s.state === 'downloaded' ? 'btn-green' : (s.state === 'requested' || s.state === 'downloading') ? 'btn-blue' : s.state === 'unavailable' ? 'btn-ghost' : 'btn-gold';
    b.innerHTML = `${ICONS.down} ${label}`;
    b.className = `btn ${cls} btn-sm mini-btn`;
    b.disabled = !(s.state === 'not_added' && canDownload(entry));
  });
}

/* only rebuild markup for entries whose state changed */
let lastStatusKey = '';
function _statusKey() {
  if (USES_RESOURCE_API) {
    return Object.values(RES).map((r) => r.status + (r.progress || '')).join('|') + '|' + (INDEXER_ISSUE || '');
  }
  return Object.values(LEGACY_STATUS).map((s) => s.state + (s.progress || '')).join('|') + '|' + (INDEXER_ISSUE || '');
}
function renderMinimal() {
  const key = _statusKey();
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
       } else if (actBtn.dataset.act === 'play') {
         // In-app native video over the /api/jellyfin/stream proxy.
         // Works from grid cards (entry) AND Library cards (data-title).
         e.preventDefault();
         const jfid = actBtn.dataset.jfItem;
         const title = (entry && entry.title) || actBtn.dataset.title || '';
         if (jfid) openPlayer(jfid, title, Number(actBtn.dataset.resume || 0));
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
             } else if (actBtn.dataset.act === 'watch-jellyfin') {
               if (actBtn.dataset.url) {
                 window.open(actBtn.dataset.url, '_blank');
               }
             } else if (actBtn.dataset.act === 'watchnow') {
         // Handle Watch Now dropdown - for simplicity, we'll open Plex first if both available
         // In a full implementation, this would show a dropdown menu
         if (entry) {
                   const plexUrl = actBtn.dataset.plexUrl;
                   const embyUrl = actBtn.dataset.embyUrl;
                   const jfUrl = actBtn.dataset.jellyfinUrl;
                   if (plexUrl) {
                     window.open(plexUrl, '_blank');
                   } else if (embyUrl) {
                     window.open(embyUrl, '_blank');
                   } else if (jfUrl) {
                     window.open(jfUrl, '_blank');
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
  if (!card) return;
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    openModal(entryById(card.dataset.id));
  } else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
    e.preventDefault();
    gridKeyNav(e);
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
      // Trigger the add watchlist job on demand.
      // NOTE: must use the `/api` prefix — nginx only reverse-proxies /api/*;
      // a bare `/jobs/...` falls to the static fallback and returns 405.
      try {
        const job = await API.postJSON('/api/jobs/add_watchlist/run', { count: 20 });
        if (job && job.status === 'error') {
          // Endpoint returns HTTP 200 with status:'error' on failure — check it.
          console.warn('Watchlist update failed:', job.error);
          toast('Watchlist update failed', job.error || 'Could not fetch new recommendations.', 'warn', 3000);
        } else {
          toast('Watchlist updated', 'New recommendations have been fetched and added.', 'ok', 3000);
        }
      } catch (jobErr) {
        console.warn('Watchlist update failed:', jobErr);
        // Don't fail the whole refresh if the job fails
        toast('Watchlist update failed', 'Could not fetch new recommendations.', 'warn', 3000);
      }
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
  if (!DATA?.entries) return null;
  // Try imdbId first
  const byImdb = DATA.entries.find(e => e.imdbId === id);
  if (byImdb) return byImdb;
  // Then try tmdbId (note: tmdbId is number, but id is string)
  const tmdbNum = parseInt(id, 10);
  if (!isNaN(tmdbNum)) {
    return DATA.entries.find(e => e.tmdbId === tmdbNum);
  }
  return null;
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
    // periodic status refresh — 60s (each poll is a full server-side reconcile;
    // 15s was saturating the threadpool and blowing the nginx 120s window → 504s)
    setInterval(() => refreshStatus(true).then(renderMinimal), 60 * 1000);
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
window.RKM = { get state() { return { DATA, RES, LEGACY_STATUS, LIB, SERVICES, view: currentView, usesResourceApi: USES_RESOURCE_API }; } };