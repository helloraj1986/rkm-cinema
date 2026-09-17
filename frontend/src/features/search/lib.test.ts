import { describe, it, expect } from "vitest";
import type { GlobalDiscoveryRow, GlobalOwnedRow } from "../../lib/api/client";
import {
  actionLabel, artUrl, codeOf, detailsTarget, discoveryEntryStub, discoveryToSuggestItem, kindWord,
  metaLine, noMatchesText, parseRecent, playTarget, pushRecent, RECENT_MAX,
} from "./lib";

const base: GlobalOwnedRow = {
  id: "s1", kind: "show", title: "3 Body Problem", year: 2024, genres: [],
  rating: 7.5, played: false, playback_position: 0, runtime: 0, play_count: 0, state: "watch",
};

const movie = (over: Partial<GlobalOwnedRow> = {}): GlobalOwnedRow => ({ ...base, id: "m1", kind: "movie", ...over });
const show = (over: Partial<GlobalOwnedRow> = {}): GlobalOwnedRow => ({ ...base, kind: "show", ...over });
const ep = (over: Partial<GlobalOwnedRow> = {}): GlobalOwnedRow => ({
  ...base, id: "ep2", kind: "episode", season: 1, episode: 2, series_id: "s1",
  series_name: "3 Body Problem", playback_position: 0, runtime: 3635, ...over,
});

describe("global search helpers (player parity + state copy)", () => {
  it("codeOf formats S/E", () => {
    expect(codeOf(1, 4)).toBe("S1E4");
    expect(codeOf(undefined, 4)).toBe("");
  });
  it("kindWord labels movie/show/episode", () => {
    expect(kindWord(movie())).toBe("Movie");
    expect(kindWord(show())).toBe("TV Show");
    expect(kindWord(ep())).toBe("Episode");
  });
  it("actionLabel maps the backend state machine", () => {
    expect(actionLabel(movie())).toBe("Watch Now");
    expect(actionLabel(movie({ state: "resume", playback_position: 600, remaining: 2700 }))).toBe("Continue Watching");
    expect(actionLabel(movie({ played: true, state: "watch_again" }))).toBe("Watch Again");
    expect(actionLabel(show({ state: "next_episode", next_episode: { id: "e2", season: 1, episode: 2, name: "Two", position: 0, remaining: 3635, kind: "play" } }))).toBe("Play Next Episode");
    expect(actionLabel(show({ state: "next_episode", next_episode: { id: "e2", season: 1, episode: 2, name: "Two", position: 100, remaining: 3535, kind: "continue" } }))).toBe("Continue Watching");
    expect(actionLabel(ep({ playback_position: 0 }))).toBe("Play");
    expect(actionLabel(ep({ playback_position: 900, state: "resume" }))).toBe("Resume");
  });
  it("metaLine carries S/E + year + remaining context", () => {
    expect(metaLine(show({ state: "next_episode", next_episode: { id: "e5", season: 1, episode: 5, name: "X", position: 0, remaining: 2700, kind: "play" } })))
      .toContain("S1E5");
    expect(metaLine(show({ state: "next_episode", next_episode: { id: "e5", season: 1, episode: 5, name: "X", position: 0, remaining: 1800, kind: "play" } })))
      .toContain("30 min left");
    expect(metaLine(movie({ state: "resume", remaining: 2700 }))).toContain("45 min left");
    expect(metaLine(ep())).toContain("3 Body Problem");
  });
  it("playTarget deep-links to the right item + episode", () => {
    expect(playTarget(movie())).toBe("/library/item/m1?play=1");
    expect(playTarget(ep())).toContain("/library/item/s1?play=1");
    expect(playTarget(ep())).toContain("episode=ep2");
    expect(playTarget(show({ state: "next_episode", next_episode: { id: "e2", season: 1, episode: 2, name: "Two", position: 0, remaining: 0, kind: "play" } })))
      .toContain("/library/item/s1?play=1&episode=e2");
  });
  it("detailsTarget points at the series page for episodes", () => {
    expect(detailsTarget(movie())).toBe("/library/item/m1");
    expect(detailsTarget(ep())).toBe("/library/item/s1");
  });
  it("artUrl builds the poster proxy", () => {
    expect(artUrl("abc")).toBe("/api/jellyfin/poster?id=abc&width=92");
  });
});

describe("the phone search screen's rules (M3)", () => {
  it("echoes the query in the no-matches sentence — a typo stays visible", () => {
    expect(noMatchesText("sholai")).toBe("No matches for “sholai”.");
  });

  it("parseRecent survives junk instead of rendering it", () => {
    // ⚠ Every one of these is a value the app itself could have written, or a person could have
    // edited by hand: the screen must show NOTHING rather than "[object Object]" under a heading.
    expect(parseRecent(null)).toEqual([]);
    expect(parseRecent("")).toEqual([]);
    expect(parseRecent("not json at all")).toEqual([]);
    expect(parseRecent("{\"a\":1}")).toEqual([]);
    expect(parseRecent('["sholay", 7, null, "", "   ", {"q":"x"}]')).toEqual(["sholay"]);
  });

  it("parseRecent dedupes case-insensitively and keeps the newest spelling", () => {
    expect(parseRecent('["Sholay","sholay","SHOLAY"]')).toEqual(["Sholay"]);
    expect(parseRecent('["b","a","b"]')).toEqual(["b", "a"]);
  });

  it("parseRecent caps the list at RECENT_MAX", () => {
    const many = JSON.stringify(Array.from({ length: RECENT_MAX + 4 }, (_, i) => `q${i}`));
    expect(parseRecent(many)).toHaveLength(RECENT_MAX);
  });

  it("pushRecent puts the new query first and moves a repeat up", () => {
    expect(pushRecent(["a", "b"], "c")).toEqual(["c", "a", "b"]);
    expect(pushRecent(["a", "b"], "b")).toEqual(["b", "a"]);
    expect(pushRecent(["a", "B"], "b")).toEqual(["b", "a"]); // the latest SPELLING wins
  });

  it("pushRecent ignores an empty query — a blank line is not a search", () => {
    expect(pushRecent(["a"], "   ")).toEqual(["a"]);
    expect(pushRecent(["a"], "")).toEqual(["a"]);
  });

  it("pushRecent never grows past RECENT_MAX", () => {
    const full = Array.from({ length: RECENT_MAX }, (_, i) => `q${i}`);
    const next = pushRecent(full, "new");
    expect(next).toHaveLength(RECENT_MAX);
    expect(next[0]).toBe("new");
  });
});

describe("discovery rows → the shared action language (M3)", () => {
  const disc: GlobalDiscoveryRow = {
    tmdb_id: 12259, media_type: "movie", title: "Sholay", year: 1975,
    poster: "/p.jpg", overview: "Two friends.", in_watchlist: false,
  };

  it("becomes a SuggestResult the shared detail sheet/card can read", () => {
    const item = discoveryToSuggestItem(disc, true);
    expect(item.tmdb_id).toBe(12259);
    expect(item.title).toBe("Sholay");
    expect(item.year).toBe(1975);
    expect(item.media_type).toBe("movie");
    expect(item.in_watchlist).toBe(true);
    // ⚠ Scores are NOT invented from the row's absence of one.
    expect(item.tmdb_score).toBe(0);
    expect(item.vote_count).toBe(0);
    expect(item.in_library).toBe(false);
  });

  it("becomes a WatchlistEntry stub that names the canonical media id", () => {
    const entry = discoveryEntryStub(disc);
    expect(entry.tmdbId).toBe(12259);
    expect(entry.type).toBe("movie");
    expect(entry.source).toBe("search");
    // ⚠ imdbId stays EMPTY: filling it in would make the *arr search match by IMDb id instead of by
    // the TMDB id the user actually picked (the drift the same stub had to fix for the palette).
    expect(entry.imdbId).toBe("");
  });

  it("a TV discovery row requests TV, not a movie", () => {
    expect(discoveryEntryStub({ ...disc, media_type: "tv" }).type).toBe("tv");
    expect(discoveryToSuggestItem({ ...disc, media_type: "tv" }, false).media_type).toBe("tv");
  });
});
