import { describe, it, expect } from "vitest";
import type { MediaItem } from "../../lib/api/client";
import { playbackMarker, isContinueWatching, isSeries, posterUrl } from "./lib";

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