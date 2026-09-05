import { describe, it, expect } from "vitest";
import type { EpisodeShape } from "../../lib/api/client";
import { episodeQueue, groupBySeason, nextEpisode, playLabel, startPosition } from "./lib";

const ep = (id: string, season: number, episode: number, played = false, position = 0): EpisodeShape => ({
  id,
  name: `E${episode}`,
  season,
  episode,
  played,
  playback_position: position,
  runtime: 3000,
});

describe("groupBySeason", () => {
  it("groups by season ascending", () => {
    const eps = [ep("s3e1", 3, 1), ep("s1e1", 1, 1), ep("s1e2", 1, 2), ep("s2e1", 2, 1)];
    const groups = groupBySeason(eps);
    expect(groups.map((g) => g.season)).toEqual([1, 2, 3]);
    expect(groups[0].episodes.map((e) => e.id)).toEqual(["s1e1", "s1e2"]);
  });
});

describe("nextEpisode", () => {
  it("returns the next entry in the queue", () => {
    const queue = episodeQueue([ep("e1", 1, 1), ep("e2", 1, 2, false, 150)]);
    expect(nextEpisode(queue, "e1")).toEqual({ id: "e2", name: "E2", position: 150 });
  });
  it("null at the end or for an unknown id", () => {
    const queue = episodeQueue([ep("e1", 1, 1)]);
    expect(nextEpisode(queue, "e1")).toBeNull();
    expect(nextEpisode(queue, "nope")).toBeNull();
  });
});

describe("playLabel / startPosition (legacy parity)", () => {
  it("replay from 0 when played", () => {
    expect(playLabel(ep("e", 1, 1, true, 999))).toBe("Replay");
    expect(startPosition(ep("e", 1, 1, true, 999))).toBe(0);
  });
  it("resume from saved position when in progress", () => {
    expect(playLabel(ep("e", 1, 1, false, 120))).toBe("Resume");
    expect(startPosition(ep("e", 1, 1, false, 120))).toBe(120);
  });
  it("play from 0 when untouched", () => {
    expect(playLabel(ep("e", 1, 1))).toBe("Play");
    expect(startPosition(ep("e", 1, 1))).toBe(0);
  });
});