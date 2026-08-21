/* ============================================================
   RKM CINEMA — centralized API client (spec §24)
   Single place for request handling, JSON parsing, and errors.
   app.js delegates ALL /api/* and /dashboard-data.json calls here.
   Loaded BEFORE app.js via a plain <script defer>.
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
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      let msg = 'HTTP ' + r.status;
      try { const d = await r.json(); msg = d.detail || msg; } catch (e) { /* ignore */ }
      throw new Error(msg);
    }
    return r.json();
  }

  const API = {
    getJSON,
    postJSON,

    async getStatus()        { return getJSON('/api/status'); },
    async getConfig()        { return getJSON('/api/config'); },
    async getLibrary()       { return getJSON('/api/library'); },
    async getHealth()        { return getJSON('/api/health'); },
    async getQuality()       { return getJSON('/api/quality'); },
    async search(q)          { return getJSON('/api/search?q=' + encodeURIComponent(q || '')); },
    async getDashboardData() { return getJSON('/dashboard-data.json'); },

    async download(entry) {
      const body = {
        imdbId: entry.imdbId,
        type: entry.type,
        title: entry.title || '',
        year: entry.year || null,
        tmdbId: entry.tmdbId || null,
      };
      return postJSON('/api/download', body);
    },
  };

  global.API = API;
})(window);
