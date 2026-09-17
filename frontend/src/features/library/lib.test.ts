import { describe, it, expect } from "vitest";
import type { ConfiguredLibraryShape, DetailPlay, MediaItem } from "../../lib/api/client";
import {
  addedTime,
  artTone,
  cardMetaLine,
  continueWatchingItems,
  detailInProgress,
  detailPrimaryLabel,
  detailResumePercent,
  episodeItemCode,
  episodeProgress,
  filterLibraryItems,
  heroEyebrow,
  heroPrimaryLabel,
  filterLibraryRows,
  firstMountCount,
  FIRST_PAINT_CARDS,
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
  libraryNavEntries,
  libraryViewFromParams,
  mountedCount,
  needsMoreRows,
  nextExtraCount,
  personHeadshotUrl,
  pickHomeHero,
  playbackMarker,
  posterUrl,
  recentlyAddedItems,
  ratingText,
  resumePercent,
  scanFailure,
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

/**
 * M3 · extraction E3. The row's rule used to be spelled out at each call site
 * (`LibraryHomeView` and `DiscoverView`). This pins the ONE copy both now call, and pins
 * the two things a caller can get wrong by hand: order (the row keeps the server's order)
 * and the missing-answer case (a pending query is `undefined`, not an empty array).
 */
describe("continueWatchingItems (M3 · E3)", () => {
  it("keeps only the in-progress/watched titles, in the order the server gave them", () => {
    const items: MediaItem[] = [
      { ...base, title: "watched", played: true },
      { ...base, title: "idle" },
      { ...base, title: "in progress", playback_position: 120 },
      { ...base, title: "no id", item_id: "", played: true },
    ];
    expect(continueWatchingItems(items).map((i) => i.title)).toEqual(["watched", "in progress"]);
  });
  it("answers [] for the shapes a query has before it has data", () => {
    expect(continueWatchingItems(undefined)).toEqual([]);
    expect(continueWatchingItems(null)).toEqual([]);
    expect(continueWatchingItems([])).toEqual([]);
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
  it("uses the media server poster proxy when an id exists", () => {
    expect(posterUrl({ item_id: "abc 1" })).toContain("/api/jellyfin/poster?id=abc%201");
  });
  it("null when there is no item id (callers show the seeded art)", () => {
    expect(posterUrl({ item_id: "" })).toBeNull();
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

describe("scanFailure", () => {
  // Phase E (2026-09-13): `GET /api/library/scan` is administrators-only, and
  // `require_admin_session` refuses a signed-out caller (401) and a member (403) even while
  // enforcement is off. The controls are hidden for a non-administrator, so this normally fires
  // only when a session expired mid-scan — and "check the backend" would then be a lie about a
  // backend that is working perfectly.
  it("names the permission problem for 401 and 403, never the backend", () => {
    for (const status of [401, 403]) {
      const f = scanFailure({ status });
      expect(f.title).toContain("administrator");
      expect(f.sub).toContain("administrator");
      expect(f.sub).not.toContain("backend");
    }
  });

  it("keeps the backend wording for a real backend failure", () => {
    expect(scanFailure({ status: 502 }).sub).toContain("backend");
    expect(scanFailure(new TypeError("fetch failed")).sub).toContain("backend");
    expect(scanFailure(undefined).sub).toContain("backend");
  });
});

/**
 * `libraryNavEntries` — the ONE filter both navigation surfaces use (2026-09-14).
 *
 * His report, from the iPad: *"even though raj profile have access to all three libraries..only two
 * can be seen at the bottom"*. The sidebar and the mobile bar had their own copies of this rule and
 * they disagreed: the sidebar kept an unresolved library and warned about it, the mobile bar dropped
 * it. These tests pin the rule, and the first one pins the reason it exists.
 */
describe("libraryNavEntries", () => {
  const resolved: ConfiguredLibraryShape = {
    name: "Movies",
    path: "/data/movies",
    folder_id: "f1",
    collection_type: "movies",
    ok: true,
    warning: "",
  };
  const unresolved: ConfiguredLibraryShape = {
    name: "TV Shows",
    path: "B:/RKM_MEDIA/TV Shows",
    folder_id: null,
    collection_type: "tvshows",
    ok: false,
    warning: "folder not found on the server",
  };

  it("KEEPS EVERY LIBRARY — a profile's library is never dropped by the UI", () => {
    // The whole complaint, in one assertion: three in, three out.
    const entries = libraryNavEntries([resolved, unresolved, { ...resolved, name: "Movies Kids", folder_id: "f2" }]);
    expect(entries.map((e) => e.name)).toEqual(["Movies", "TV Shows", "Movies Kids"]);
  });

  it("links a resolved library to its folder route", () => {
    expect(libraryNavEntries([resolved])[0].to).toBe("/library/folder/f1");
  });

  it("keeps an unresolved library as a row, with the server's own reason", () => {
    const [entry] = libraryNavEntries([unresolved]);
    expect(entry.to).toBeNull();
    expect(entry.warning).toBe("folder not found on the server");
    expect(entry.icon).toBe("tv");
  });

  it("treats ok-without-a-folder as unresolved — the route needs the id, not the flag", () => {
    expect(libraryNavEntries([{ ...resolved, ok: true, folder_id: null }])[0].to).toBeNull();
  });

  it("always has something to show when the server sends no reason", () => {
    expect(libraryNavEntries([{ ...unresolved, warning: "" }])[0].warning).toBe("Library unavailable");
  });

  it("url-encodes the folder id, because ids are not ours to choose", () => {
    expect(libraryNavEntries([{ ...resolved, folder_id: "a b/c" }])[0].to).toBe(
      "/library/folder/a%20b%2Fc",
    );
  });

  it("tolerates an empty list, which is what a fresh install answers", () => {
    expect(libraryNavEntries([])).toEqual([]);
  });
});

/**
 * M3 · extraction E8. This is the line under a poster, and M3 adds a SECOND card (the phone's
 * `PosterCard`) that must read identically — so the rule is pinned here, where both cards read
 * it, rather than in whichever card happened to hold it first.
 *
 * Each case below is the desktop card's existing output, character for character, including the
 * two easy ones to break: a play count of exactly 1 (says nothing, must not appear) and a title
 * with no year and no runtime (must be an EMPTY line, not a line starting with " · ").
 */
describe("cardMetaLine (M3 · E8)", () => {
  it("movie: year then runtime", () => {
    expect(cardMetaLine({ ...base, year: 1999 })).toBe("1999 · 1h 40m");
  });
  it("series: year then TV, never a runtime", () => {
    expect(cardMetaLine({ ...base, type: "tv", year: 2015 })).toBe("2015 · TV");
  });
  it("play count only when it says something", () => {
    expect(cardMetaLine({ ...base, year: 1999, play_count: 3 })).toBe("1999 · 1h 40m · 3 plays");
    expect(cardMetaLine({ ...base, year: 1999, play_count: 1 })).toBe("1999 · 1h 40m");
  });
  it("episode: code then series name", () => {
    expect(
      cardMetaLine({
        ...base,
        kind: "episode",
        year: 2015,
        episode: { season: 1, number: 4, series_id: "s1", series_name: "Barry" },
      }),
    ).toBe("S1E4 · Barry");
  });
  it("a title with nothing known is empty, not a separator", () => {
    expect(cardMetaLine({ title: "T", item_id: "i1" })).toBe("");
  });
});

/**
 * M3 · extraction E4 — the pure half of the Home view model. The rail LENGTHS are named in
 * `useHomeRows` (they are a presentation decision); what belongs here is the row's own rule:
 * a recently-added row with no id is not a title you can open, so it is dropped.
 */
describe("recentlyAddedItems (M3 · E4)", () => {
  it("keeps the rows you can open, in the server's order", () => {
    const rows: MediaItem[] = [
      { ...base, title: "kept", item_id: "a" },
      { ...base, title: "dead row", item_id: "" },
      { ...base, title: "kept too", item_id: "b" },
    ];
    expect(recentlyAddedItems(rows).map((i) => i.title)).toEqual(["kept", "kept too"]);
  });
  it("answers [] before the query has data", () => {
    expect(recentlyAddedItems(undefined)).toEqual([]);
    expect(recentlyAddedItems(null)).toEqual([]);
  });
});

/**
 * M3 · progressive mounting — the rule that removed the 1.7–2.0 s tap.
 *
 * ⚠ These tests exist to make "713 rows in one commit" IMPOSSIBLE rather than merely unlikely:
 * `LibraryFolderView` used to map the whole list, and the first paint mounting the entire folder is
 * exactly the bug. The first case below is the falsification — if `FIRST_PAINT_CARDS` ever equals
 * `total`, or `firstMountCount` is bypassed, it goes RED.
 */
describe("progressive mounting (M3)", () => {
  const TOTAL = 713;

  it("the FIRST paint mounts a screenful, never the whole folder", () => {
    expect(firstMountCount(TOTAL)).toBe(48);
    expect(firstMountCount(TOTAL)).toBeLessThan(TOTAL);
    expect(mountedCount(TOTAL, 0)).toBe(48);
  });

  it("grows to exactly the list, in steps, and never past it", () => {
    let extra = 0;
    const seen: number[] = [mountedCount(TOTAL, extra)];
    for (let i = 0; i < 100 && needsMoreRows(mountedCount(TOTAL, extra), TOTAL); i += 1) {
      extra = nextExtraCount(extra, TOTAL);
      seen.push(mountedCount(TOTAL, extra));
    }
    expect(seen[0]).toBe(48);
    expect(seen[1]).toBe(96);
    expect(seen[seen.length - 1]).toBe(TOTAL);
    expect(Math.max(...seen)).toBe(TOTAL);
    // ⚠ monotonic, and no single step is the whole list
    for (let i = 1; i < seen.length; i += 1) {
      expect(seen[i]).toBeGreaterThanOrEqual(seen[i - 1]);
      expect(seen[i] - seen[i - 1]).toBeLessThanOrEqual(48);
    }
  });

  it("a list shorter than a screenful mounts whole and never grows", () => {
    expect(mountedCount(30, 0)).toBe(30);
    expect(firstMountCount(30)).toBe(30);
    expect(needsMoreRows(30, 30)).toBe(false);
    expect(nextExtraCount(0, 30)).toBe(0);
    expect(nextExtraCount(0, 0)).toBe(0);
  });

  it("answers 0 — not NaN or negative — for the shapes a query has before it answers", () => {
    expect(firstMountCount(0)).toBe(0);
    expect(mountedCount(0, 0)).toBe(0);
    expect(mountedCount(-5, -5)).toBe(0);
    expect(mountedCount(TOTAL, -5)).toBe(48);   // a negative offset must not UNMOUNT the first screen
    expect(nextExtraCount(-5, TOTAL)).toBe(48); // nor make growth go backwards
  });

  it("⚠ CANNOT exceed the list even if the growth state is wrong", () => {
    expect(mountedCount(TOTAL, 99999)).toBe(TOTAL);
    expect(mountedCount(30, 99999)).toBe(30);
  });
});

describe("the Home hero's labels (M3)", () => {
  it("says what the hero is showing — and an episode of a continuation is not a plain Continue Watching", () => {
    expect(heroEyebrow(true, false)).toBe("Continue Watching");
    expect(heroEyebrow(true, true)).toBe("Continue episode");
    expect(heroEyebrow(false, false)).toBe("Recently Added");
    expect(heroEyebrow(false, true)).toBe("Recently Added");
  });

  it("names the five primary cases — and a series never offers to PLAY", () => {
    expect(heroPrimaryLabel({ isEpisode: false, episodeCode: "", isSeries: false, percent: 0 })).toBe("Play");
    expect(heroPrimaryLabel({ isEpisode: false, episodeCode: "", isSeries: false, percent: 42 })).toBe("Resume");
    expect(heroPrimaryLabel({ isEpisode: false, episodeCode: "", isSeries: true, percent: 0 })).toBe("Explore Episodes");
    expect(heroPrimaryLabel({ isEpisode: true, episodeCode: "S1E4", isSeries: false, percent: 0 })).toBe("Play S1E4");
    expect(heroPrimaryLabel({ isEpisode: true, episodeCode: "S1E4", isSeries: false, percent: 10 })).toBe("Resume S1E4");
  });

  it("never leaves a trailing space when the episode has no code", () => {
    expect(heroPrimaryLabel({ isEpisode: true, episodeCode: "", isSeries: false, percent: 0 })).toBe("Play");
  });
});

describe("episodeProgress (M4 · E6)", () => {
  const ep = (played: boolean, pos: number, runtime: number) => ({
    played,
    playback_position: pos,
    runtime,
  });

  it("reads a half-watched episode as a percent AND a countdown", () => {
    const p = episodeProgress(ep(false, 1200, 3600));
    expect(p.percent).toBe(33);
    expect(p.inProgress).toBe(true);
    expect(p.remainingLabel).toBe("40m left");
  });

  it("an episode 2 seconds from the end says 1m left — never 0m left", () => {
    expect(episodeProgress(ep(false, 3598, 3600)).remainingLabel).toBe("1m left");
  });

  it("⚠ NEVER divides by an unknown runtime — 0%, and no countdown", () => {
    const p = episodeProgress(ep(false, 900, 0));
    expect(p.percent).toBe(0);
    expect(p.inProgress).toBe(true); // it IS mid-play; there is just nothing to count down against
    expect(p.remainingLabel).toBe("");
  });

  it("a finished episode is not in progress and has no countdown, even with a position left over", () => {
    const p = episodeProgress(ep(true, 1800, 3600));
    expect(p.inProgress).toBe(false);
    expect(p.remainingLabel).toBe("");
  });

  it("an untouched episode is 0% and not in progress", () => {
    const p = episodeProgress(ep(false, 0, 3600));
    expect(p.percent).toBe(0);
    expect(p.inProgress).toBe(false);
    expect(p.remainingLabel).toBe("");
  });

  it("clamps at 100 — a position past the runtime is not 104%", () => {
    expect(episodeProgress(ep(false, 4000, 3600)).percent).toBe(100);
  });

  it("treats a missing position as zero rather than NaN", () => {
    const p = episodeProgress({ played: false, playback_position: undefined as unknown as number, runtime: 3600 });
    expect(p.percent).toBe(0);
    expect(p.inProgress).toBe(false);
  });
});
