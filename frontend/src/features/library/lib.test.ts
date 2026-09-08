import { describe, it, expect } from "vitest";
import type { DetailPlay, MediaItem } from "../../lib/api/client";
import {
  addedTime,
  detailInProgress,
  detailPrimaryLabel,
  detailResumePercent,
  filterLibraryItems,
  fmtRuntime,
  isContinueWatching,
  isSeries,
  libraryGenres,
  libraryItemsByType,
  libraryKindLabel,
  personHeadshotUrl,
  playbackMarker,
  posterUrl,
  ratingText,
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