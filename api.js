/* ============================================================
   RKM CINEMA — centralized API client (spec §24)
   Single place for request handling, JSON parsing, and errors.
   app.js delegates ALL /api/* and /dashboard-data.json calls here.
   Loaded BEFORE app.js via a plain <script defer>.

   Phase 11: primary data path is the resource API (§17/§18) —
   /api/watchlist, /api/media/{id}/request, /api/reconcile. All
   set through the resource methods below. Legacy endpoints
   (/api/status, /api/download) are kept ONLY as a fallback while
   the started image predates Phase 10/11 (graceful, one caller).
   ============================================================ */
(function (global) {
  'use strict';

  async function getJSON(url) {
    const r = await fetch(url, { headers: { 'Accept': 'application/json' } });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }

  async function postJSON(url, body) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    if (!r.ok) {
      let msg = 'HTTP ' + r.status;
      try {
        const d = await r.json();
        msg = (d && (d.detail || d.message)) || d || msg;
        if (typeof msg !== 'string') msg = JSON.stringify(msg);
      } catch (e) { /* ignore */ }
      const err = new Error(msg);
      err.status = r.status;
      throw err;
    }
    return r.json();
  }

  /* Canonical media_id for an entry, mirroring the backend identity rule
     (domain/identity.txt): type:tmdb:{id} > type:imdb:{id} > type:tvdb:{id}.
     This is how a watchlist entry maps onto a §18 resource's `id`. */
  function mediaIdOf(e) {
    const t = (e.type === 'tv' || e.isSeries) ? 'tv' : 'movie';
    if (e.tmdbId) return t + ':tmdb:' + e.tmdbId;
    if (e.imdbId) {
      const im = String(e.imdbId);
      return t + ':imdb:' + (im.toLowerCase().indexOf('tt') === 0 ? im : 'tt' + im);
    }
    if (e.tvdbId) return t + ':tvdb:' + e.tvdbId;
    return t + ':imdb:' + (e.imdbId || '');
  }

  /* Build a resource-shaped object from a legacy /api/status entry, so the
     fallback path (old image) still yields {state, capabilities, watch}. */
  function legacyStatusToResource(entry, legacy) {
    const state = (legacy && legacy.state) || 'not_added';
    const watch = {};
    if (legacy && legacy.plexUrl) watch.plex = { available: true, url: legacy.plexUrl };
    if (legacy && legacy.embyUrl) watch.emby = { available: true, url: legacy.embyUrl };
    let canWatch = state === 'available' || state === 'downloaded';
    let canDownload = state === 'not_added' || state === 'requested';
    return {
      id: mediaIdOf(entry),
      title: entry.title || '',
      year: entry.year || null,
      type: (entry.type === 'tv' || entry.isSeries) ? 'tv' : 'movie',
      status: state,
      capabilities: { can_download: canDownload, can_watch: canWatch },
      watch: watch,
      acquisition: legacy && legacy.service ? { provider: legacy.service, status: state } : null,
      detail: legacy ? legacy.detail : '',
      progress: legacy ? legacy.progress : undefined,
    };
  }

  const API = {
    getJSON,
    postJSON,
    mediaIdOf,
    legacyStatusToResource,

    /* ---- Phase 10/11 resource API (primary) ---- */
    async getWatchlist() { return getJSON('/api/watchlist'); },
    async getMedia(id)   { return getJSON('/api/media/' + encodeURIComponent(id)); },
    async requestMedia(mediaId) { return postJSON('/api/media/' + encodeURIComponent(mediaId) + '/request'); },
    async reconcile()    { return postJSON('/api/reconcile', {}); },
    async getJobs()      { return getJSON('/api/jobs'); },

    /* ---- legacy (fallback only) ---- */
    async getStatusLegacy() { return getJSON('/api/status'); },
    async downloadLegacy(entry) {
      const body = {
        imdbId: entry.imdbId,
        type: entry.type,
        title: entry.title || '',
        year: entry.year || null,
        tmdbId: entry.tmdbId || null,
      };
      return postJSON('/api/download', body);
    },

    /* ---- suggest ---- */
    async suggest(filters) { return postJSON('/api/suggest', filters); },
    async suggestDetail(tmdbId, mediaType) {
      return getJSON('/api/suggest/detail/' + encodeURIComponent(tmdbId) + '?media_type=' + encodeURIComponent(mediaType || 'movie'));
    },

    /* ---- shared (both paths) ---- */
    async getConfig()        { return getJSON('/api/config'); },
    async getLibrary()       { return getJSON('/api/library'); },
    async getLibraryItems()       { return getJSON('/api/library/items'); },
    async getContinueWatching()   { return getJSON('/api/library/continue-watching'); },
    async getSeriesEpisodes(id) { return getJSON('/api/library/series/' + encodeURIComponent(id) + '/episodes'); },
    async getHealth()        { return getJSON('/api/health'); },
    async getQuality()       { return getJSON('/api/quality'); },
    async search(q)          { return getJSON('/api/search?q=' + encodeURIComponent(q || '')); },
    async getDashboardData() { return getJSON('/dashboard-data.json'); },
  };

  global.API = API;
})(window);