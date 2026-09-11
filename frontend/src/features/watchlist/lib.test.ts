import { describe, it, expect } from "vitest";
import type { MediaResource, SearchHit, SuggestFilters, WatchlistEntry } from "../../lib/api/client";
import {
  buildWatchlistRows,
  cardPrimaryAction,
  daySeed,
  entryForHit,
  filterWatchlist,
  fmtEta,
  fmtRating,
  fmtRuntimeMin,
  isSameWatchlistTitle,
  upsertWatchlistEntries,
  jellyfinMarker,
  mediaIdOf,
  persistedToEntry,
  pickHero,
  resolveState,
  seededShuffle,
  suggestHistoryLabel,
  suggestHistoryPush,
  suggestItemToEntry,
  timeAgo,
} from "./lib";

const movie: WatchlistEntry = {
  imdbId: "tt0133093",
  tmdbId: 603,
  tvdbId: null,
  title: "The Matrix",
  year: 1999,
  type: "movie",
  category: "Sci-Fi/Fantasy",
  genres: ["Science Fiction", "Action"],
  lang: "English",
  cert: "AU-M",
  rt: 88,
  imdb: 8.7,
  tmdbScore: 8.1,
  overview: "A computer hacker learns the truth.",
  cast: ["Keanu Reeves"],
  director: "The Wachowskis",
  runtime: 136,
  poster: "https://p/m.jpg",
  backdrop: "https://p/m-b.jpg",
  trailerId: "vKQi3bBA1y8",
  trailerTitle: "The Matrix Trailer",
  trailerUrl: "https://www.youtube.com/embed/vKQi3bBA1y8?autoplay=1",
  added: "2026-01-01",
  source: "auto",
  state: "pending",
};

const show: WatchlistEntry = {
  ...movie,
  imdbId: "tt11280740",
  tmdbId: 95396,
  title: "Severance",
  year: 2022,
  type: "tv",
  category: "Thriller",
  genres: ["Thriller"],
  rt: 90,
  imdb: 8.5,
  added: "2026-02-01",
};

function res(id: string, status: string, extra: Partial<MediaResource> = {}): MediaResource {
  return {
    id,
    title: "T",
    type: "movie",
    status,
    capabilities: { can_download: status === "not_added", can_watch: status === "available" },
    watch: {},
    ...extra,
  };
}

const noRes = (e: WatchlistEntry) => resolveState(e, null, true);

describe("mediaIdOf (legacy api.js parity)", () => {
  it("prefers tmdb, types movie/tv", () => {
    expect(mediaIdOf(movie)).toBe("movie:tmdb:603");
    expect(mediaIdOf(show)).toBe("tv:tmdb:95396");
  });
  it("falls back to imdb with tt prefix", () => {
    expect(mediaIdOf({ type: "movie", imdbId: "tt123" })).toBe("movie:imdb:tt123");
    expect(mediaIdOf({ type: "tv", imdbId: "123" })).toBe("tv:imdb:tt123");
  });
  it("isSeries forces tv even without type", () => {
    expect(mediaIdOf({ isSeries: true, tmdbId: 1 })).toBe("tv:tmdb:1");
  });
});

describe("resolveState (legacy st() parity)", () => {
  it("maps a full resource", () => {
    const r = res("movie:tmdb:603", "available", {
      watch: {
        jellyfin: { available: true, url: "https://jf/x", item_id: "jf-1", played: false, playback_position: 600, runtime: 5704 },
      },
      acquisition: { provider: "radarr", status: "available" },
    });
    const st = resolveState(movie, r, true);
    expect(st.state).toBe("available");
    expect(st.capabilities.can_watch).toBe(true);
    expect(st.jellyfinItemId).toBe("jf-1");
    expect(st.jellyfinUrl).toBe("https://jf/x");
    expect(st.service).toBe("radarr");
  });
  it("defaults missing resources to actionable not_added (never unavailable)", () => {
    const st = resolveState(show, null, true);
    expect(st.state).toBe("not_added");
    expect(st.capabilities.can_download).toBe(true);
    expect(st.service).toBe("sonarr"); // tv entry
  });
});

describe("cardPrimaryAction (legacy cardMarkup/downloadButton ordering)", () => {
  it("Play in RKM first when a Jellyfin item id is available", () => {
    const r = res("movie:tmdb:603", "available", {
      capabilities: { can_download: false, can_watch: true },
      watch: { jellyfin: { available: true, url: "https://jf/x", item_id: "jf-1" } },
    });
    expect(cardPrimaryAction(movie, resolveState(movie, r, true))).toEqual({
      type: "play-rkm",
      itemId: "jf-1",
      label: "Play in RKM",
    });
    expect(cardPrimaryAction(show, resolveState(show, r, true)).type).toBe("play-rkm");
  });
  it("watch-link when a server link resolves but has no in-app item id", () => {
    const r = res("movie:tmdb:603", "available", {
      capabilities: { can_download: false, can_watch: true },
      watch: { jellyfin: { available: true, url: "https://jf/x" } },
    });
    const a = cardPrimaryAction(movie, resolveState(movie, r, true));
    expect(a).toMatchObject({ type: "watch-link", provider: "jellyfin", label: "Watch on Jellyfin" });
  });
  it("disabled Available when capability says watchable but no live link", () => {
    const r = res("movie:tmdb:603", "available", {
      capabilities: { can_download: false, can_watch: true },
    });
    expect(cardPrimaryAction(movie, resolveState(movie, r, true)).type).toBe("available");
  });
  it("download only when not_added and can_download", () => {
    const r = res("movie:tmdb:603", "not_added", { capabilities: { can_download: true, can_watch: false } });
    expect(cardPrimaryAction(movie, resolveState(movie, r, true)).type).toBe("download");
  });
  it("state labels: requested / downloading (with capped %) / unavailable", () => {
    const req = res("movie:tmdb:603", "requested", { capabilities: { can_download: false, can_watch: false } });
    expect(cardPrimaryAction(movie, resolveState(movie, req, true)).type).toBe("requested");
    const dl = res("movie:tmdb:603", "downloading", {
      capabilities: { can_download: false, can_watch: false },
      progress: 120,
    });
    expect(cardPrimaryAction(movie, resolveState(movie, dl, true))).toEqual({ type: "downloading", progress: 99 });
    const no = res("movie:tmdb:603", "failed", { capabilities: { can_download: false, can_watch: false } });
    expect(cardPrimaryAction(movie, resolveState(movie, no, true)).type).toBe("unavailable");
  });
});

describe("jellyfinMarker (legacy playbackMarkup parity)", () => {
  it("watched tick when played", () => {
    expect(jellyfinMarker({ available: true, played: true })).toEqual({ kind: "watched" });
  });
  it("amber resume % when position known", () => {
    expect(jellyfinMarker({ available: true, played: false, playback_position: 3000, runtime: 6000 })).toEqual({
      kind: "resume",
      percent: 50,
    });
  });
  it("none when absent / no progress", () => {
    expect(jellyfinMarker(undefined)).toEqual({ kind: "none" });
    expect(jellyfinMarker({ available: true, played: false })).toEqual({ kind: "none" });
  });
});

describe("discover rows (legacy buildRows parity)", () => {
  const e1 = { ...movie, added: "2026-01-01" };
  const e2 = { ...show, added: "2026-02-01", director: "" };
  const e3 = { ...movie, imdbId: "tt1", tmdbId: 1, title: "Dark", year: 2015, imdb: 7.9, rt: 70, added: "2026-03-01", director: "" };
  const e4 = { ...movie, imdbId: "tt2", tmdbId: 2, title: "Citizen", year: 1941, imdb: 8.0, rt: 89, added: "2026-04-01", director: "" };
  const e5 = { ...show, imdbId: "tt3", tmdbId: 3, title: "Cult Show", year: 2020, imdb: 8.1, rt: 90, added: "2026-05-01", genres: ["Drama"], category: "Drama", director: "Nolan" };
  const e6 = { ...movie, imdbId: "tt4", tmdbId: 4, title: "Prestige", year: 2006, imdb: 8.5, rt: 76, added: "2026-06-01", director: "Nolan" };
  const all = [e1, e2, e3, e4, e5, e6];

  it("starts with Tonight's Picks then New to Your Watchlist", () => {
    const rows = buildWatchlistRows(all);
    expect(rows[0].id).toBe("tonight");
    expect(rows[1].id).toBe("new");
  });
  it("excludes the auto hero from Tonight's Picks but keeps it in New", () => {
    const rows = buildWatchlistRows(all);
    const hero = pickHero(all, "auto"); // highest imdb (8.7 = e1)
    expect(hero?.title).toBe("The Matrix");
    expect(rows[0].items.some((e) => e.imdbId === hero?.imdbId)).toBe(false);
    expect(rows[1].items.some((e) => e.imdbId === hero?.imdbId)).toBe(true);
  });
  it("highly rated / gems / acclaim appear with 2+ qualifying titles", () => {
    const rows = buildWatchlistRows(all);
    const ids = rows.map((r) => r.id);
    expect(ids).toContain("top"); // e3 (7.9) + e4 (8.0/89)
    expect(ids).toContain("gems"); // rt>=85 & imdb<=8.3 -> e4, e5
    expect(ids).toContain("acclaim"); // imdb>=8.0 & rt>=88 -> e4, e5
  });
  it("category rows (top 3, ≥2) and director rows (2+ titles)", () => {
    const rows = buildWatchlistRows(all);
    const cat = rows.find((r) => r.id.startsWith("cat-"));
    const dir = rows.find((r) => r.id.startsWith("dir-"));
    expect(cat).toBeTruthy();
    expect(dir?.title).toBe("Because You Like Nolan");
    expect(dir?.items.length).toBe(2);
  });
  it("never exceeds 8 rows and is deterministic for the same seed", () => {
    expect(buildWatchlistRows(all).length).toBeLessThanOrEqual(8);
    expect(JSON.stringify(buildWatchlistRows(all))).toBe(JSON.stringify(buildWatchlistRows(all)));
  });
});

describe("seededShuffle / daySeed (legacy parity)", () => {
  it("is deterministic per seed and stable across calls", () => {
    const a = seededShuffle([1, 2, 3, 4, 5, 6], 20260907);
    const b = seededShuffle([1, 2, 3, 4, 5, 6], 20260907);
    expect(a).toEqual(b);
    expect(a.sort()).toEqual([1, 2, 3, 4, 5, 6]);
  });
  it("daySeed is YYYYMMDD for an explicit date", () => {
    expect(daySeed(new Date(2026, 8, 7, 12))).toBe(20260907);
  });
});

describe("pickHero (legacy parity)", () => {
  const all = [movie, show];
  it("auto = highest IMDb", () => {
    expect(pickHero(all, "auto")?.imdbId).toBe("tt0133093");
  });
  it("newest = latest added", () => {
    expect(pickHero(all, "newest")?.imdbId).toBe("tt11280740");
  });
  it("random is seeded by the day (deterministic within a day)", () => {
    expect(pickHero(all, "random")?.imdbId).toBe(pickHero(all, "random")?.imdbId);
  });
  it("null on empty", () => {
    expect(pickHero([], "auto")).toBeNull();
  });
});

describe("watchlist upsert dedupe (regression: overlay adds wiping the cache)", () => {
  const tmdbOnly = (id: number, title = "T") => ({ ...movie, imdbId: "", tmdbId: id, title });
  it("isSameWatchlistTitle matches only on REAL ids", () => {
    expect(isSameWatchlistTitle({ tmdbId: 603, imdbId: "" }, { tmdbId: 603, imdbId: "" })).toBe(true);
    expect(isSameWatchlistTitle({ tmdbId: null, imdbId: "tt0133093" }, { tmdbId: null, imdbId: "tt0133093" })).toBe(true);
    // Two different empty-imdb titles are NOT the same — the bug that dropped
    // every previously-added TMDB-only entry on each new add.
    expect(isSameWatchlistTitle({ tmdbId: 1756365, imdbId: "" }, { tmdbId: 1723854, imdbId: "" })).toBe(false);
    expect(isSameWatchlistTitle({ tmdbId: null, imdbId: "" }, { tmdbId: null, imdbId: "" })).toBe(false);
  });
  it("upsertWatchlistEntries prepends and never drops unrelated empty-imdb titles", () => {
    const ironMan = tmdbOnly(1723854, "Iron Man");
    const prior = [tmdbOnly(1756365, "Sappho's Tale"), movie];
    const next = upsertWatchlistEntries(prior, ironMan);
    expect(next).toHaveLength(3);
    expect(next[0].title).toBe("Iron Man");
    expect(next.map((e) => e.title)).toContain("Sappho's Tale");
  });
  it("upsertWatchlistEntries drops the SAME title only", () => {
    const same = { ...movie }; // same tmdb+imdb as `movie`
    const next = upsertWatchlistEntries([movie, tmdbOnly(1756365, "Sappho's Tale")], same);
    expect(next).toHaveLength(2); // duplicate `movie` dropped, Sappho kept
    expect(next.filter((e) => e.title === "The Matrix")).toHaveLength(1);
    expect(next.map((e) => e.title)).toContain("Sappho's Tale");
  });
});

describe("filterWatchlist (legacy renderWatchlist parity)", () => {
  const all = [movie, show];
  it("movie / tv chips filter by type", () => {
    expect(filterWatchlist(all, noRes, { type: "movie" }).map((e) => e.title)).toEqual(["The Matrix"]);
    expect(filterWatchlist(all, noRes, { type: "tv" }).map((e) => e.title)).toEqual(["Severance"]);
  });
  it("downloaded chip uses resolved state (can_watch/downloaded)", () => {
    const stateFor = (e: WatchlistEntry) => resolveState(e, res("x", "available", { capabilities: { can_download: false, can_watch: true } }), true);
    expect(filterWatchlist([movie], stateFor, { type: "downloaded" }).length).toBe(1);
    expect(filterWatchlist([movie], noRes, { type: "downloaded" }).length).toBe(0);
    expect(filterWatchlist([movie], noRes, { type: "not" }).length).toBe(1);
  });
  it("sorts: recent (added desc), rating, release, title", () => {
    expect(filterWatchlist(all, noRes, { sort: "recent" }).map((e) => e.title)).toEqual(["Severance", "The Matrix"]);
    expect(filterWatchlist(all, noRes, { sort: "rating" }).map((e) => e.title)).toEqual(["The Matrix", "Severance"]);
    expect(filterWatchlist(all, noRes, { sort: "release" }).map((e) => e.title)).toEqual(["Severance", "The Matrix"]);
    expect(filterWatchlist(all, noRes, { sort: "title" }).map((e) => e.title)).toEqual(["Severance", "The Matrix"]);
  });
});

describe("formatting (legacy parity)", () => {
  it("fmtRating", () => {
    expect(fmtRating(8.7)).toBe("8.7");
    expect(fmtRating("8")).toBe("8");
    expect(fmtRating(undefined)).toBe("");
  });
  it("fmtRuntimeMin", () => {
    expect(fmtRuntimeMin(136)).toBe("2h 16m");
    expect(fmtRuntimeMin(44)).toBe("44m");
    expect(fmtRuntimeMin(0)).toBe("");
  });
  it("fmtEta", () => {
    expect(fmtEta(45)).toBe("45s");
    expect(fmtEta(3600)).toBe("60m"); // legacy returns minutes until m >= 90
    expect(fmtEta(5400)).toBe("1h 30m");
    expect(fmtEta(-1)).toBe("");
  });
  it("timeAgo", () => {
    expect(timeAgo(new Date(Date.now() - 5 * 60 * 1000).toISOString())).toBe("5 min ago");
    expect(timeAgo(new Date(Date.now() - 26 * 3600 * 1000).toISOString())).toBe("yesterday");
    expect(timeAgo("")).toBe("");
  });
});

describe("search helpers (legacy parity)", () => {
  it("entryForHit finds by imdbId then tmdbId", () => {
    const hit: SearchHit = { title: "The Matrix", year: 1999, type: "movie", imdbId: "tt0133093", tmdbId: 603, poster: "", inWatchlist: true, director: "", cast: [], snippet: "" };
    expect(entryForHit([movie], hit)?.title).toBe("The Matrix");
    const hit2: SearchHit = { ...hit, imdbId: "unknown" };
    expect(entryForHit([movie], hit2)?.title).toBe("The Matrix");
  });
  it("returns null for live-only hits", () => {
    const hit: SearchHit = { title: "Brand New", year: 2026, type: "movie", imdbId: "", tmdbId: 999, poster: "", inWatchlist: false, director: "", cast: [], snippet: "" };
    expect(entryForHit([movie], hit)).toBeNull();
  });
  it("never matches a live TMDB hit (imdbId \"\") to a watchlist entry with an empty imdbId", () => {
    // Regression: pending TMDB-only titles persist with imdbId "" — before the
    // fix, `imdbId === ""` matched them against EVERY live TMDB hit, so any
    // live result's detail modal showed the first empty-imdb entry instead.
    const noImdb: WatchlistEntry = { ...movie, imdbId: "", tmdbId: 1756365, title: "Sappho's Tale" };
    const got: SearchHit = { title: "Game of Thrones", year: 2011, type: "tv", imdbId: "", tmdbId: 1399, poster: "", inWatchlist: false, director: "", cast: [], snippet: "" };
    expect(entryForHit([noImdb, movie], got)).toBeNull();
    // A hit that really IS the watchlist title still resolves via tmdbId.
    const sapphoHit: SearchHit = { ...got, title: "Sappho's Tale", tmdbId: 1756365 };
    expect(entryForHit([noImdb, movie], sapphoHit)?.title).toBe("Sappho's Tale");
  });
});

describe("add-flow mappers (legacy entryFromWatchlistEntry / entryFromSuggestItem)", () => {
  it("persistedToEntry maps the snake_case persisted entry to a full display entry", () => {
    const w = {
      title: "The Matrix", year: 1999, isSeries: false, imdbId: "tt0133093", tmdbId: 603,
      snippet: "", tmdb_overview: "Neo discovers the Matrix.", poster: "https://p/m.jpg",
      backdrop: "https://p/b.jpg", genres: ["Action"], cast: ["Keanu Reeves"],
      director: "The Wachowskis", trailerId: "vKQi3bBA1y8", tmdb_score: 8.1,
      runtime: 136, category: "Sci-Fi/Fantasy", added: "2026-09-07",
    };
    const e = persistedToEntry(w);
    expect(e).not.toBeNull();
    expect(e?.type).toBe("movie");
    expect(e?.overview).toBe("Neo discovers the Matrix.");
    expect(e?.tmdbScore).toBe(8.1);
    expect(e?.tmdbId).toBe(603);
    expect(e?.cast).toEqual(["Keanu Reeves"]);
  });
  it("persistedToEntry prefers snippet when no tmdb_overview", () => {
    const e = persistedToEntry({ title: "X", isSeries: true, tmdbId: 1, snippet: "snip" });
    expect(e?.type).toBe("tv");
    expect(e?.overview).toBe("snip");
  });
  it("suggestItemToEntry builds a display stub with a date-stamped added", () => {
    const e = suggestItemToEntry({
      tmdb_id: 123, title: "Fresh", year: 2026, media_type: "movie", tmdb_score: 7.5,
      vote_count: 10, genres: ["Drama"], overview: "o", poster: "p", backdrop: "b",
      in_watchlist: false, in_library: false,
    });
    expect(e.tmdbId).toBe(123);
    expect(e.type).toBe("movie");
    expect(e.category).toBe("Drama");
    expect(e.tmdbScore).toBe(7.5);
  });
});

describe("suggest history (legacy parity)", () => {
  const base: SuggestFilters = { media_type: "all", genres: [], year_from: null, year_to: null, min_rating: 6, sort_by: "popularity.desc", count: 20 };
  it("push dedupes and caps at 10, most recent first", () => {
    const f1 = { ...base, media_type: "movie" as const };
    const f2 = { ...base, genres: ["Action"] };
    let list = suggestHistoryPush([], f1);
    list = suggestHistoryPush(list, f2);
    list = suggestHistoryPush(list, f1);
    expect(list).toHaveLength(2);
    expect(list[0]).toEqual(f1);
  });
  it("label joins readable parts", () => {
    expect(suggestHistoryLabel({ ...base, media_type: "movie", genres: ["Action", "Sci-Fi", "Drama"], year_from: 2020, min_rating: 7, count: 20 })).toContain("Movies");
    expect(suggestHistoryLabel({ ...base, media_type: "tv" })).toContain("TV");
  });
});
