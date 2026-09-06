import { describe, it, expect } from "vitest";
import type { DetailPlay, MediaItem } from "../../lib/api/client";
import {
  detailInProgress,
  detailPrimaryLabel,
  detailResumePercent,
  fmtRuntime,
  isContinueWatching,
  isSeries,
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