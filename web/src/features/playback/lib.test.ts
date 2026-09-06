import { describe, it, expect } from "vitest";
import type { EpisodeShape } from "../../lib/api/client";
import {
  episodeQueue, groupBySeason, nextEpisode, playLabel, startPosition,
  PLAYBACK_RATES, QUALITY_OPTIONS, qualityFor, AUTOPLAY_DELAY_MS,
  audioCodecNeedsTranscode,
} from "./lib";

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

describe("item 3 player helpers", () => {
  it("offers 0.5–2× playback rates", () => {
    expect(PLAYBACK_RATES).toEqual([0.5, 1, 1.25, 1.5, 2]);
  });
  it("maps a quality label to a bitrate (null = Original)", () => {
    expect(qualityFor("Original")).toBeNull();
    expect(qualityFor("1080p")).toBe(8_000_000);
    expect(qualityFor("720p")).toBe(5_000_000);
    expect(qualityFor("480p")).toBe(2_500_000);
    expect(qualityFor("nope")).toBeNull();
    // every option resolves
    for (const q of QUALITY_OPTIONS) expect(q.bitrate).toBe(qualityFor(q.label));
  });
  it("has a finite autoplay-next countdown", () => {
    expect(AUTOPLAY_DELAY_MS).toBeGreaterThan(0);
  });
  it("audioCodecNeedsTranscode only for non-browser codecs", () => {
    expect(audioCodecNeedsTranscode("eac3")).toBe(true);
    expect(audioCodecNeedsTranscode("ac3")).toBe(true);
    expect(audioCodecNeedsTranscode("dts")).toBe(true);
    expect(audioCodecNeedsTranscode("TRUEHD")).toBe(true);
    expect(audioCodecNeedsTranscode("aac")).toBe(false);
    expect(audioCodecNeedsTranscode("AAC")).toBe(false); // case-insensitive
    expect(audioCodecNeedsTranscode("opus")).toBe(false);
    expect(audioCodecNeedsTranscode("flac")).toBe(false);
    // Unknown/missing → assume safe (don't over-transcode).
    expect(audioCodecNeedsTranscode(undefined)).toBe(false);
    expect(audioCodecNeedsTranscode(null)).toBe(false);
    expect(audioCodecNeedsTranscode("")).toBe(false);
  });
});