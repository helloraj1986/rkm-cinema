import { describe, it, expect } from "vitest";
import type { GlobalOwnedRow } from "../../lib/api/client";
import {
  actionLabel, artUrl, codeOf, detailsTarget, kindWord, metaLine, playTarget,
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
