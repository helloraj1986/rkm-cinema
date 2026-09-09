import { describe, it, expect } from "vitest";
import type { ConfiguredLibraryShape, DetailPlay, MediaItem } from "../../lib/api/client";
import {
  addedTime,
  artTone,
  detailInProgress,
  detailPrimaryLabel,
  detailResumePercent,
  episodeItemCode,
  filterLibraryItems,
  filterLibraryRows,
  fmtRuntime,
  folderCountLabel,
  isContinueWatching,
  isEpisodeItem,
  isSeries,
  libraryByFolderId,
  libraryFilterFromParams,
  libraryFilterToParams,
  libraryGenres,
  libraryIconFor,
  libraryItemsByType,
  libraryKindLabel,
  libraryViewFromParams,
  personHeadshotUrl,
  pickHomeHero,
  playbackMarker,
  posterUrl,
  ratingText,
  resumePercent,
  seriesTargetForEpisode,
  similarItemToResult,
} from "./lib";

const base: MediaItem = {
  title: "T",
  item_id: "i1",
  type: "movie",
  played: false,
  playback_position: 0,
  runtime: 6000,
};

describe("playbackMarker (legacy parity)", () => {
  it("watched when played", () => {
    expect(playbackMarker({ ...base, played: true })).toEqual({ kind: "watched" });
  });
  it("resume % when partially watched", () => {
    expect(playbackMarker({ ...base, playback_position: 3000, runtime: 6000 })).toEqual({
      kind: "resume",
      percent: 50,
    });
  });
  it("caps at 100%", () => {
    expect(playbackMarker({ ...base, playback_position: 9000, runtime: 1000 })).toEqual({
      kind: "resume",
      percent: 100,
    });
  });
  it("none when no progress", () => {
    expect(playbackMarker(base)).toEqual({ kind: "none" });
  });
});

describe("isContinueWatching (legacy parity)", () => {
  it("true when in progress or watched", () => {
    expect(isContinueWatching({ ...base, playback_position: 120 })).toBe(true);
    expect(isContinueWatching({ ...base, played: true })).toBe(true);
  });
  it("false when no id or no progress", () => {
    expect(isContinueWatching({ ...base, item_id: "" })).toBe(false);
    expect(isContinueWatching(base)).toBe(false);
  });
});

describe("isSeries", () => {
  it("treats tv/show/series as series", () => {
    expect(isSeries({ ...base, type: "tv" })).toBe(true);
    expect(isSeries({ ...base, type: "show" })).toBe(true);
    expect(isSeries({ ...base, type: "movie" })).toBe(false);
  });
});

// ------------------------------------------------ Plex-style views (PLEX_VIEWS_PLAN)
describe("libraryItemsByType (folder split)", () => {
  const movie = { ...base, item_id: "m1", type: "movie" };
  const tv = { ...base, item_id: "t1", type: "tv" };
  it("movies folder keeps non-series only", () => {
    expect(libraryItemsByType([movie, tv], "movies").map((i) => i.item_id)).toEqual(["m1"]);
  });
  it("shows folder keeps series only", () => {
    expect(libraryItemsByType([movie, tv], "shows").map((i) => i.item_id)).toEqual(["t1"]);
  });
  it("tolerates empty/undefined lists", () => {
    expect(libraryItemsByType([], "movies")).toEqual([]);
    expect(libraryItemsByType(undefined as unknown as MediaItem[], "shows")).toEqual([]);
  });
  it("folder labels", () => {
    expect(libraryKindLabel("movies")).toBe("Movies");
    expect(libraryKindLabel("shows")).toBe("TV Shows");
  });
});

// ------------------------------------------- Library & discovery (roadmap item 4)
describe("addedTime", () => {
  it("parses plain ISO and normalises Jellyfin's 7-digit fractions", () => {
    const item = { ...base, item_id: "x", added: "2026-03-01T00:00:00.0000000Z" };
    const t = addedTime(item);
    expect(t).not.toBeNull();
    expect(t).toBe(Date.parse("2026-03-01T00:00:00.000Z"));
    expect(addedTime({ ...item, added: "2026-03-01T00:00:00Z" })).toBe(Date.parse("2026-03-01T00:00:00Z"));
    expect(addedTime({ ...item, added: "2026-03-01T00:00:00.123Z" })).toBe(Date.parse("2026-03-01T00:00:00.123Z"));
  });
  it("null when missing or malformed (never fabricates)", () => {
    const i = { ...base, item_id: "x" };
    expect(addedTime(i)).toBeNull();
    expect(addedTime({ ...i, added: null })).toBeNull();
    expect(addedTime({ ...i, added: "" })).toBeNull();
    expect(addedTime({ ...i, added: "not-a-date" })).toBeNull();
    expect(addedTime(undefined as unknown as MediaItem)).toBeNull();
  });
});

describe("libraryGenres", () => {
  it("unique + alphabetical union (case-distinct genres stay distinct)", () => {
    const a = { ...base, item_id: "a", genres: ["Drama", "Sci-Fi"] };
    const b = { ...base, item_id: "b", genres: ["Comedy", "drama"] };
    expect(libraryGenres([b, a])).toEqual(["Comedy", "Drama", "Sci-Fi", "drama"]);
  });
  it("empty list tolerance", () => {
    expect(libraryGenres([])).toEqual([]);
    expect(libraryGenres([{ ...base, item_id: "c" }])).toEqual([]);
  });
});

describe("libraryFilterFromParams / libraryFilterToParams (URL state §63)", () => {
  it("parses genre + sort from the query string (q= is ignored — global search owns text)", () => {
    const p = new URLSearchParams("q=mad%20max&genre=Action&sort=title");
    expect(libraryFilterFromParams(p)).toEqual({ q: "", genre: "Action", sort: "title" });
  });
  it("defaults when params are missing or unknown", () => {
    expect(libraryFilterFromParams(new URLSearchParams())).toEqual({ q: "", genre: "", sort: "recent" });
    expect(libraryFilterFromParams(new URLSearchParams("q=+"))).toEqual({ q: "", genre: "", sort: "recent" });
    // A bogus/removed sort key is never trusted → recent.
    expect(libraryFilterFromParams(new URLSearchParams("sort=rating"))).toEqual({ q: "", genre: "", sort: "recent" });
  });
  it("round-trips state through the URL (without q)", () => {
    const f = { q: "", genre: "Action", sort: "title" as const };
    const out = libraryFilterToParams(f).toString();
    expect(libraryFilterFromParams(new URLSearchParams(out))).toEqual(f);
    // Free-text no longer round-trips — it is dropped from the URL on write.
    const stale = libraryFilterToParams({ q: "mad max", genre: "Action", sort: "recent" }).toString();
    expect(stale).not.toContain("q=");
  });
  it("drops empty values so a clean view has no query string", () => {
    expect(libraryFilterToParams({ q: "", genre: "", sort: "recent" }).toString()).toBe("");
    expect(libraryFilterToParams({ q: "  ", genre: "", sort: "unwatched" }).toString()).toBe("sort=unwatched");
  });
});

describe("libraryViewFromParams (view mode §17)", () => {
  it("compact when view=compact, grid otherwise", () => {
    expect(libraryViewFromParams(new URLSearchParams("view=compact"))).toBe("compact");
    expect(libraryViewFromParams(new URLSearchParams("view=grid"))).toBe("grid");
    expect(libraryViewFromParams(new URLSearchParams("view=bogus"))).toBe("grid");
    expect(libraryViewFromParams(new URLSearchParams())).toBe("grid");
  });
});

describe("filterLibraryItems", () => {
  const mk = (over: Partial<MediaItem>): MediaItem => ({ ...base, item_id: over.item_id!, ...over });
  const older = mk({ item_id: "older", title: "Zeta Old", added: "2026-01-01T00:00:00.0000000Z", genres: ["Drama"] });
  const newer = mk({ item_id: "newer", title: "Alpha New", added: "2026-06-01T00:00:00.0000000Z", genres: ["Sci-Fi"] });
  const noDate = mk({ item_id: "nodate", title: "Mid NoDate", played: true, genres: ["Drama", "Sci-Fi"] });
  const list = [older, newer, noDate];

  it("title search is case-insensitive substring", () => {
    expect(filterLibraryItems(list, { q: "alpha" }).map((i) => i.item_id)).toEqual(["newer"]);
    expect(filterLibraryItems(list, { q: "ZETA" }).map((i) => i.item_id)).toEqual(["older"]);
  });
  it("genre membership filter", () => {
    expect(filterLibraryItems(list, { genre: "Sci-Fi" }).map((i) => i.item_id).sort()).toEqual(["newer", "nodate"]);
  });
  it("q + genre combine", () => {
    expect(filterLibraryItems(list, { q: "no", genre: "Drama" }).map((i) => i.item_id)).toEqual(["nodate"]);
  });
  it("default sort is recently-added desc with unknown dates last", () => {
    expect(filterLibraryItems(list).map((i) => i.item_id)).toEqual(["newer", "older", "nodate"]);
  });
  it("title sort A–Z", () => {
    expect(filterLibraryItems(list, { sort: "title" }).map((i) => i.item_id)).toEqual(["newer", "nodate", "older"]);
  });
  it("unwatched sort puts unplayed first, then recently added", () => {
    const playedNew = mk({ item_id: "playednew", title: "Watched Recent", played: true, added: "2026-07-01T00:00:00.0000000Z" });
    expect(filterLibraryItems([...list, playedNew], { sort: "unwatched" }).map((i) => i.item_id)).toEqual([
      "newer", "older", "playednew", "nodate",
    ]);
  });
  it("title-desc sorts Z–A", () => {
    expect(filterLibraryItems(list, { sort: "title-desc" }).map((i) => i.item_id)).toEqual([
      "older", "nodate", "newer",
    ]);
  });
  it("release sort is newest year first, unknown years last", () => {
    const y2024 = mk({ item_id: "y2024", title: "Newest", year: 2024, added: "2026-01-01T00:00:00Z" });
    const y1999 = mk({ item_id: "y1999", title: "Oldest", year: 1999, added: "2026-01-01T00:00:00Z" });
    const unknown = mk({ item_id: "unknown", title: "No Year", added: "2026-01-01T00:00:00Z" });
    expect(filterLibraryItems([y1999, y2024, unknown], { sort: "release" }).map((i) => i.item_id)).toEqual([
      "y2024", "y1999", "unknown",
    ]);
  });
  it("recently-played sorts by LastPlayedDate desc, never-played last", () => {
    const a = mk({ item_id: "a", title: "Played Old", played: true, last_played: "2026-01-01T00:00:00Z" });
    const b = mk({ item_id: "b", title: "Played New", played: true, last_played: "2026-06-01T00:00:00Z" });
    const c = mk({ item_id: "c", title: "Never", played: false });
    expect(filterLibraryItems([a, c, b], { sort: "recently-played" }).map((i) => i.item_id)).toEqual(["b", "a", "c"]);
  });
  it("progress sort is highest resume fraction first; finished rows last", () => {
    const half = mk({ item_id: "half", title: "Half", playback_position: 3000, runtime: 6000 });
    const q = mk({ item_id: "q", title: "Quarter", playback_position: 1500, runtime: 6000 });
    const done = mk({ item_id: "done", title: "Done", played: true, playback_position: 6000, runtime: 6000 });
    const no = mk({ item_id: "no", title: "None" });
    expect(filterLibraryItems([no, done, q, half], { sort: "progress" }).map((i) => i.item_id)).toEqual([
      "half", "q", "no", "done",
    ]);
  });
  it("runtime sort is longest first; unknown runtime last", () => {
    const long = mk({ item_id: "long", title: "Long", runtime: 9000 });
    const short = mk({ item_id: "short", title: "Short", runtime: 1800 });
    const noRuntime = mk({ item_id: "noruntime", title: "No Runtime", runtime: 0, added: "2026-01-01T00:00:00Z" });
    expect(filterLibraryItems([short, noRuntime, long], { sort: "runtime" }).map((i) => i.item_id)).toEqual([
      "long", "short", "noruntime",
    ]);
  });
  it("tolerates empty input", () => {
    expect(filterLibraryItems([], { q: "x" })).toEqual([]);
    expect(filterLibraryItems(undefined as unknown as MediaItem[])).toEqual([]);
  });
});

describe("posterUrl", () => {
  it("prefers the jellyfin poster proxy when an id exists", () => {
    expect(posterUrl({ item_id: "abc 1", thumb: null })).toContain("/api/jellyfin/poster?id=abc%201");
  });
  it("falls back to the plex thumb proxy", () => {
    expect(posterUrl({ item_id: "", thumb: "/z/t.jpg" })).toContain("/api/plex/thumb?path=");
  });
  it("null when neither", () => {
    expect(posterUrl({ item_id: "", thumb: null })).toBeNull();
  });
});

// ------------------------------------------------ Plex-style detail (Phase 2)
const play = (over: Partial<DetailPlay> = {}): DetailPlay => ({
  played: false, resume_ticks: 0, resume: 0, play_count: 0, ...over,
});

describe("personHeadshotUrl", () => {
  it("builds the same-origin person proxy URL", () => {
    expect(personHeadshotUrl("p 1")).toContain("/api/jellyfin/person?id=p%201&width=200");
  });
  it("null without an id", () => {
    expect(personHeadshotUrl("")).toBeNull();
  });
});

describe("fmtRuntime", () => {
  it("Plex-style hours/minutes", () => {
    expect(fmtRuntime(5704)).toBe("1h 35m");
    expect(fmtRuntime(3600)).toBe("1h");
    expect(fmtRuntime(44 * 60)).toBe("44m");
  });
  it("empty when unknown or zero", () => {
    expect(fmtRuntime(0)).toBe("");
    expect(fmtRuntime(null)).toBe("");
    expect(fmtRuntime(undefined)).toBe("");
  });
});

describe("ratingText", () => {
  it("one decimal, trimmed", () => {
    expect(ratingText(7.473)).toBe("7.5");
    expect(ratingText(8.0)).toBe("8");
    expect(ratingText(9)).toBe("9");
  });
  it("empty when absent", () => {
    expect(ratingText(null)).toBe("");
    expect(ratingText(undefined)).toBe("");
    expect(ratingText(0)).toBe("");
  });
});

describe("detail resume helpers", () => {
  it("resume percent only when mid-play and not finished", () => {
    expect(detailResumePercent(play({ resume: 2934 }), 5704)).toBe(51);
    expect(detailResumePercent(play({ resume: 5704 }), 5704)).toBe(100);
    expect(detailResumePercent(play({ resume: 0 }), 5704)).toBe(0);
    expect(detailResumePercent(play({ played: true, resume: 2934 }), 5704)).toBe(0);
    expect(detailResumePercent(undefined, 5704)).toBe(0);
  });
  it("in-progress/primary label", () => {
    expect(detailInProgress(play({ resume: 2934 }))).toBe(true);
    expect(detailInProgress(play())).toBe(false);
    expect(detailInProgress(play({ played: true, resume: 2934 }))).toBe(false);
    expect(detailPrimaryLabel(play({ resume: 2934 }))).toBe("Resume");
    expect(detailPrimaryLabel(play())).toBe("Play");
    expect(detailPrimaryLabel(undefined)).toBe("Play");
  });
});

describe("similarItemToResult (row → actionable SuggestResult)", () => {
  it("maps a movie row", () => {
    const r = similarItemToResult({
      id: 135254, title: "Movie A", year: 2014, kind: "movie",
      score: 7.1, poster: "http://img/p.jpg", backdrop: null,
    });
    expect(r.tmdb_id).toBe(135254);
    expect(r.title).toBe("Movie A");
    expect(r.year).toBe(2014);
    expect(r.media_type).toBe("movie");
    expect(r.tmdb_score).toBe(7.1);
    expect(r.poster).toBe("http://img/p.jpg");
    expect(r.backdrop).toBe("");
    expect(r.in_watchlist).toBe(false);
    expect(r.in_library).toBe(false);
  });
  it("maps a show row to tv + tolerates missing score/year", () => {
    const r = similarItemToResult({ id: 19, title: "Show B", year: null, kind: "show", score: 0 });
    expect(r.media_type).toBe("tv");
    expect(r.year).toBeNull();
    expect(r.tmdb_score).toBe(0);
    expect(r.genres).toEqual([]);
  });
});

describe("filterLibraryRows (drop titles already in the local library)", () => {
  const library: MediaItem[] = [
    { ...base, item_id: "p1", title: "Prisoners", year: 2013 },
    { ...base, item_id: "b1", title: "Breaking Bad", year: 2008, type: "tv" },
  ];
  const row = (title: string, year?: number | null) => ({ id: 1, title, year: year ?? null, kind: "movie" as const, score: 0 });

  it("drops an exact title+year duplicate", () => {
    expect(filterLibraryRows([row("Prisoners", 2013), row("New Film", 2024)], library)).toEqual([
      row("New Film", 2024),
    ]);
  });
  it("is case-insensitive on title", () => {
    expect(filterLibraryRows([row("prisoners", 2013)], library)).toEqual([]);
  });
  it("keeps a same-name different-year title (remake) — never over-drop", () => {
    expect(filterLibraryRows([row("Prisoners", 2026)], library)).toEqual([row("Prisoners", 2026)]);
  });
  it("drops when years agree but a library year is a string", () => {
    const libStr = [{ ...base, item_id: "s1", title: "Scrubs", year: "2001" as unknown as number }];
    expect(filterLibraryRows([row("Scrubs", 2001)], libStr)).toEqual([]);
  });
  it("keeps an empty result and tolerates a null library", () => {
    expect(filterLibraryRows([], library)).toEqual([]);
    expect(filterLibraryRows([row("X", 1999)], null as unknown as MediaItem[])).toEqual([row("X", 1999)]);
  });
});

describe("Continue-Watching episode helpers (episode facet)", () => {
  const epItem: MediaItem = {
    ...base,
    item_id: "ep1",
    title: "Our Lord",
    type: "episode",
    kind: "episode",
    playback_position: 1160,
    runtime: 2648,
    episode: { number: 4, season: 1, series_id: "ser1", series_name: "3 Body Problem" },
  };

  it("detects episode rows by kind or type", () => {
    expect(isEpisodeItem(epItem)).toBe(true);
    expect(isEpisodeItem({ ...base, kind: "episode" })).toBe(true);
    expect(isEpisodeItem({ ...base, type: "episode" })).toBe(true);
    expect(isEpisodeItem({ ...base, kind: "movie" })).toBe(false);
    expect(isEpisodeItem({ ...base, type: "tv", kind: "show" })).toBe(false);
    expect(isEpisodeItem(base)).toBe(false);
  });

  it("renders the SxEy code from the facet", () => {
    expect(episodeItemCode(epItem)).toBe("S1E4");
    expect(episodeItemCode({ ...base, kind: "movie" })).toBeNull();
    // No facet -> null (never fabricate a code).
    expect(episodeItemCode({ ...base, kind: "episode" })).toBeNull();
  });

  it("maps an episode card's whole-card click to the SERIES item", () => {
    const target = seriesTargetForEpisode(epItem);
    expect(target?.item_id).toBe("ser1");
    expect(target?.title).toBe("3 Body Problem");
    expect(target?.type).toBe("tv");
    expect(target?.kind).toBe("show");
    expect(target?.playback_position).toBe(0);
    expect(target?.runtime).toBe(0);
    // episode id stays available for instant-resume hover? No — the target is
    // for OPENING the series page; the hover action still uses the original.
    expect(target?.episode).toBeUndefined();
  });

  it("passes non-episode items through untouched", () => {
    expect(seriesTargetForEpisode({ ...base, kind: "movie" })).toBeNull();
    expect(seriesTargetForEpisode({ ...base, kind: "episode" })).toBeNull(); // no series_id
  });
});
describe("home hero + artwork tone (NEW_UX)", () => {
  const movie = (id: string, pos = 0, rt = 6000): MediaItem => ({
    ...base,
    item_id: id,
    title: `Movie ${id}`,
    type: "movie",
    playback_position: pos,
    runtime: rt,
  });
  const show = (id: string): MediaItem => ({ ...base, item_id: id, title: `Show ${id}`, type: "tv" });
  const episode = (id: string, seriesId: string): MediaItem => ({
    ...base,
    item_id: id,
    title: "Ep",
    type: "episode",
    kind: "episode",
    episode: { number: 2, season: 1, series_id: seriesId, series_name: "Show" },
    playback_position: 120,
    runtime: 2400,
  });

  it("artTone is deterministic, in range and differs across titles", () => {
    expect(artTone("Interstellar")).toBe(artTone("Interstellar"));
    expect(artTone(undefined)).toBeGreaterThanOrEqual(0);
    expect(artTone("Interstellar")).toBeGreaterThanOrEqual(0);
    expect(artTone("Interstellar")).toBeLessThan(6);
    const tones = new Set(["Mad Max", "Prisoners", "The Batman", "Dune", "Arrival", "Shōgun"].map(artTone));
    expect(tones.size).toBeGreaterThan(1); // palette variety, not one flat colour
  });

  it("resumePercent clamps to 0..100 and ignores finished items", () => {
    expect(resumePercent(movie("m", 0, 6000))).toBe(0);
    expect(resumePercent(movie("m", 3000, 6000))).toBe(50);
    expect(resumePercent(movie("m", 999999, 6000))).toBe(100);
    expect(resumePercent({ ...base, played: true })).toBe(0);
  });

  it("prefers an in-progress movie, then any in-progress item, then recent, then library", () => {
    const ep = episode("e1", "s1");
    const recent = [movie("r1")];
    // episode in progress is the ONLY in-progress row → hero falls back to it
    expect(pickHomeHero([ep], [], [show("x")])?.item_id).toBe("e1");
    // in-progress movie wins over an episode + recents
    expect(pickHomeHero([ep, movie("m1", 100)], recent, [show("x")])?.item_id).toBe("m1");
    // nothing in progress → most recently added first
    expect(pickHomeHero([], recent, [movie("m0")])?.item_id).toBe("r1");
    // empty everywhere except the library → first library item
    expect(pickHomeHero([], [], [show("x"), movie("m0")])?.item_id).toBe("m0"); // movie preferred
    expect(pickHomeHero([], [], [show("x")])?.item_id).toBe("x");
    expect(pickHomeHero([], [], [])).toBeNull();
  });

  it("ignores finished rows when picking the hero", () => {
    const done = { ...movie("d", 0), played: true };
    expect(pickHomeHero([done], [], [])).toBeNull();
  });
});

// ---------------------------------------------- configurable media libraries
// MEDIA_LIBRARIES_PLAN Phase 4: folder-scoped view-model helpers.
describe("configurable media libraries", () => {
  const libs: ConfiguredLibraryShape[] = [
    { name: "Movies", path: "/data/media/_movie", folder_id: "f-movies",
      collection_type: "movies", ok: true, warning: "" },
    { name: "My Anime", path: "F:/Media/Anime", folder_id: null,
      collection_type: "", ok: false, warning: "does not match" },
  ];

  it("maps collection type to a sidebar icon", () => {
    expect(libraryIconFor("movies")).toBe("film");
    expect(libraryIconFor("tvshows")).toBe("tv");
    expect(libraryIconFor("tv")).toBe("tv");
    expect(libraryIconFor("mixed")).toBe("folder");
    expect(libraryIconFor("")).toBe("folder");
  });

  it("finds a library by its resolved folder id", () => {
    expect(libraryByFolderId(libs, "f-movies")?.name).toBe("Movies");
    expect(libraryByFolderId(libs, "nope")).toBeNull();
    expect(libraryByFolderId(libs, null)).toBeNull();
    expect(libraryByFolderId([], "f-movies")).toBeNull();
  });

  it("formats the folder count label", () => {
    expect(folderCountLabel(0)).toBe("0 titles");
    expect(folderCountLabel(1)).toBe("1 title");
    expect(folderCountLabel(6)).toBe("6 titles");
  });
});
