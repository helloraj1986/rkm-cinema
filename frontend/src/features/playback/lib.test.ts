import { describe, it, expect, afterEach } from "vitest";
import type { EpisodeShape } from "../../lib/api/client";
import {
  episodeQueue, groupBySeason, nextEpisode, playLabel, startPosition,
  nextPlayableEpisode, episodeCode,
  PLAYBACK_RATES, QUALITY_OPTIONS, qualityFor, AUTOPLAY_DELAY_MS,
  audioCodecNeedsTranscode, fmtTime, barTotal, isFiniteDuration, clampSeek,
  videoNeedsTranscode, pickStreamMode, streamModeLabel, playMethodForMode,
  parseVtt, parseVttTime, activeCueText,
  usesHls, nextHlsMode, hlsEngineFor, hlsModeLabel, HLS_LADDER,
  hlsConfigFor, resolutionLabel, abrBadgeLabel, HLS_MAX_BUFFER_SEC,
  HLS_ABR_DEFAULT_ESTIMATE_BPS, shouldAutoHideChrome, CHROME_HIDE_MS,
  warmGet, warmPut, warmDelete, warmClear, WARM_TTL_MS, WARM_MAX_ITEMS,
  WARM_AHEAD_SEC, type WarmEntry,
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
    expect(nextEpisode(queue, "e1")).toMatchObject({ id: "e2", name: "E2", position: 150 });
    expect(nextEpisode(queue, "e1")?.runtime).toBeGreaterThan(0); // API length travels with the queue
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
  it("fmtTime formats seconds as m:ss / h:mm:ss", () => {
    expect(fmtTime(0)).toBe("0:00");
    expect(fmtTime(59)).toBe("0:59");
    expect(fmtTime(65)).toBe("1:05");
    expect(fmtTime(600)).toBe("10:00");
    expect(fmtTime(3635)).toBe("1:00:35"); // 3 Body Problem S1E1
    expect(fmtTime(5704)).toBe("1:35:04"); // (500) Days of Summer
    expect(fmtTime(undefined)).toBe("0:00");
    expect(fmtTime(-5)).toBe("0:00");
    expect(fmtTime(Number.NaN)).toBe("0:00");
  });
  it("barTotal prefers finite stream duration, else the API runtime hint", () => {
    expect(barTotal(3635, 3635)).toBe(3635);      // resolved == hint
    expect(barTotal(Number.POSITIVE_INFINITY, 2648)).toBe(2648); // unknown stream → hint
    expect(barTotal(Number.NaN, 2648)).toBe(2648);
    expect(barTotal(0, 2648)).toBe(2648);          // pre-metadata 0 → hint
    expect(barTotal(null, 2648)).toBe(2648);
    expect(barTotal(undefined, 0)).toBe(0);        // nothing known
    expect(barTotal(Number.POSITIVE_INFINITY, undefined)).toBe(0);
    expect(barTotal(123.9, 100)).toBe(123.9);      // fractional stream duration kept
  });
  it("isFiniteDuration rejects Infinity/NaN/zero", () => {
    expect(isFiniteDuration(100)).toBe(true);
    expect(isFiniteDuration(0)).toBe(false);
    expect(isFiniteDuration(Number.POSITIVE_INFINITY)).toBe(false);
    expect(isFiniteDuration(Number.NaN)).toBe(false);
    expect(isFiniteDuration(null)).toBe(false);
    expect(isFiniteDuration(undefined)).toBe(false);
  });
  it("clampSeek bounds into [0, total]", () => {
    expect(clampSeek(-10, 2648)).toBe(0);
    expect(clampSeek(5000, 2648)).toBe(2648);
    expect(clampSeek(421, 2648)).toBe(421);
    expect(clampSeek(30, 0)).toBe(30); // unknown total → allow forward step
  });
});

describe("stream routing (tier 1 honest modes)", () => {
  const h264 = { codec: "h264", profile: "High", bit_depth: 8 };
  const h264hi10 = { codec: "h264", profile: "High 10", bit_depth: 10 };
  const hevc = { codec: "hevc", profile: "Main", bit_depth: 8 };
  it("videoNeedsTranscode flags unsafe codecs + 10-bit h264", () => {
    expect(videoNeedsTranscode(h264)).toBe(false);
    expect(videoNeedsTranscode(h264hi10)).toBe(true); // High-10 undecodable
    expect(videoNeedsTranscode(hevc)).toBe(true);
    expect(videoNeedsTranscode({ codec: "mpeg2video" })).toBe(true);
    expect(videoNeedsTranscode(null)).toBe(false);
    expect(videoNeedsTranscode(undefined)).toBe(false);
    expect(videoNeedsTranscode({})).toBe(false); // unknown → attempt play
  });
  it("pickStreamMode picks direct for browser-safe mp4", () => {
    expect(pickStreamMode({ quality: "Original", container: "mp4", video: h264, activeAudioCodec: "aac" })).toBe("direct");
  });
  it("pickStreamMode remuxes non-mp4 containers", () => {
    expect(pickStreamMode({ quality: "Original", container: "mkv", video: h264, activeAudioCodec: "aac" })).toBe("remux");
    expect(pickStreamMode({ quality: "Original", container: "", video: h264, activeAudioCodec: "aac" })).toBe("direct");
  });
  it("pickStreamMode honours audio + video codecs", () => {
    expect(pickStreamMode({ quality: "Original", container: "mp4", video: h264, activeAudioCodec: "eac3" })).toBe("transcode_audio");
    expect(pickStreamMode({ quality: "Original", container: "mkv", video: hevc, activeAudioCodec: "aac" })).toBe("transcode");
  });
  it("quality + explicit audio track force non-direct (Static ignores them)", () => {
    expect(pickStreamMode({ quality: "1080p", container: "mp4", video: h264, activeAudioCodec: "aac" })).toBe("transcode");
    expect(pickStreamMode({ quality: "Original", container: "mp4", video: h264, activeAudioCodec: "aac", forceNonDirect: true })).toBe("remux");
  });
  it("labels + play methods map 1:1", () => {
    expect(streamModeLabel("direct")).toBe("Direct play");
    expect(streamModeLabel("remux")).toBe("Remux");
    expect(streamModeLabel("transcode")).toBe("Transcode");
    expect(playMethodForMode("direct")).toBe("DirectPlay");
    expect(playMethodForMode("remux")).toBe("DirectStream");
    expect(playMethodForMode("transcode_audio")).toBe("Transcode");
    expect(playMethodForMode("transcode")).toBe("Transcode");
  });
});

describe("subtitle overlay (WebVTT)", () => {
  it("parseVttTime handles mm:ss.mmm and h:mm:ss.mmm", () => {
    expect(parseVttTime("00:05.500")).toBeCloseTo(5.5, 3);
    expect(parseVttTime("1:02:03.004")).toBeCloseTo(3723.004, 3);
    expect(parseVttTime("12:34,567")).toBeCloseTo(754.567, 3);
    expect(parseVttTime("garbage")).toBe(0);
  });
  it("parseVtt extracts multi-line cues, strips tags and skips settings", () => {
    const vtt = `WEBVTT

00:00:01.000 --> 00:00:04.000 align:start position:0%
Hello <i>world</i>

00:00:05.000 --> 00:00:08.000
First line
Second line

00:00:10.000 --> 00:00:12.000
Last`;
    const cues = parseVtt(vtt);
    expect(cues).toHaveLength(3);
    expect(cues[0]).toEqual({ start: 1, end: 4, text: "Hello world" });
    expect(cues[1].text).toBe("First line\nSecond line");
    expect(cues[1].start).toBe(5);
    expect(cues[2].end).toBe(12);
  });
  it("parseVtt tolerates NOTE/STYLE headers and CRLF", () => {
    const vtt = "WEBVTT\r\n\r\nNOTE intro\r\n\r\nSTYLE\r\n::cue { color: #fff }\r\n\r\n00:01:00.000 --> 00:01:02.000\r\nSubs on\r\n";
    const cues = parseVtt(vtt);
    expect(cues).toHaveLength(1);
    expect(cues[0].text).toBe("Subs on");
  });
  it("activeCueText matches the current position", () => {
    const cues = [{ start: 5, end: 8, text: "a" }, { start: 421, end: 423, text: "mid" }];
    expect(activeCueText(cues, 0)).toBeNull();
    expect(activeCueText(cues, 5)).toBe("a");
    expect(activeCueText(cues, 7.9)).toBe("a");
    expect(activeCueText(cues, 8)).toBeNull();
    expect(activeCueText(cues, 422)).toBe("mid");
    expect(activeCueText(cues, 9)).toBeNull();
  });
});

describe("HLS ABR/buffer policy (player tail)", () => {
  it("hlsConfigFor sets the LAN-first buffer + ABR policy", () => {
    const c = hlsConfigFor();
    expect(c.maxBufferLength).toBe(HLS_MAX_BUFFER_SEC);
    expect(c.maxMaxBufferLength).toBeGreaterThan(HLS_MAX_BUFFER_SEC);
    expect(c.abrEwmaDefaultEstimate).toBe(HLS_ABR_DEFAULT_ESTIMATE_BPS);
    expect(c.capLevelToPlayerSize).toBe(false); // never downscale to element size
    expect(c.abrBandWidthUpFactor).toBeGreaterThan(1);
    expect(c.abrBandWidthFactor).toBeLessThan(1);
  });
  it("hlsConfigFor honours a positive startPosition only", () => {
    expect(hlsConfigFor().startPosition).toBeUndefined();
    expect(hlsConfigFor({ startPosition: 0 }).startPosition).toBeUndefined();
    expect(hlsConfigFor({ startPosition: 421 }).startPosition).toBe(421);
  });
  it("resolutionLabel buckets heights honestly", () => {
    expect(resolutionLabel(2160)).toBe("4K");
    expect(resolutionLabel(1088)).toBe("1080p");
    expect(resolutionLabel(1080)).toBe("1080p");
    expect(resolutionLabel(720)).toBe("720p");
    expect(resolutionLabel(480)).toBe("480p");
    expect(resolutionLabel(240)).toBe("240p");
    expect(resolutionLabel(0)).toBe("Auto");
    expect(resolutionLabel(undefined)).toBe("Auto");
  });
  it("abrBadgeLabel reads Auto until a live level exists", () => {
    expect(abrBadgeLabel(null)).toBe("Auto");
    expect(abrBadgeLabel({})).toBe("Auto");
    expect(abrBadgeLabel({ height: 2160, bitrate: 40_000_000 })).toBe("Auto · 4K");
    expect(abrBadgeLabel({ height: 1080 })).toBe("Auto · 1080p");
  });
});

describe("auto-hide chrome (player tail)", () => {
  const ready = { playing: true, switching: false, error: false, upNext: false, hoverChrome: false, idleMs: CHROME_HIDE_MS + 500 };
  it("hides only once playing and idle past the threshold", () => {
    expect(shouldAutoHideChrome(ready)).toBe(true);
    expect(shouldAutoHideChrome({ ...ready, idleMs: CHROME_HIDE_MS - 500 })).toBe(false);
  });
  it("never hides while paused, loading, erroring, up-next showing, or hovered", () => {
    expect(shouldAutoHideChrome({ ...ready, playing: false })).toBe(false);
    expect(shouldAutoHideChrome({ ...ready, switching: true })).toBe(false);
    expect(shouldAutoHideChrome({ ...ready, error: true })).toBe(false);
    expect(shouldAutoHideChrome({ ...ready, upNext: true })).toBe(false);
    expect(shouldAutoHideChrome({ ...ready, hoverChrome: true })).toBe(false);
  });
  it("threshold is a sane 2–4 s", () => {
    expect(CHROME_HIDE_MS).toBeGreaterThanOrEqual(2000);
    expect(CHROME_HIDE_MS).toBeLessThanOrEqual(4000);
  });
});

describe("warm-start cache (player tail)", () => {
  const entry = (at: number): WarmEntry => ({ info: Promise.resolve(null), at });
  afterEach(() => warmClear());
  it("stores and returns a warm entry", async () => {
    warmPut("e2", entry(1000), 1000);
    const got = warmGet("e2", 2000);
    expect(got).not.toBeNull();
    await expect(got!.info).resolves.toBeNull();
  });
  it("expires entries past the TTL on read", () => {
    warmPut("e2", entry(1000), 1000);
    expect(warmGet("e2", 1000 + WARM_TTL_MS)).not.toBeNull(); // boundary still live
    expect(warmGet("e2", 1000 + WARM_TTL_MS + 1)).toBeNull();
  });
  it("warmPut replaces an existing entry (no duplicate promise)", () => {
    const a = entry(1);
    warmPut("x", a, 1);
    warmPut("x", entry(2), 2);
    expect(warmGet("x", 3)).not.toBe(a);
  });
  it("evicts the oldest entry once over the cap", () => {
    for (let i = 1; i <= WARM_MAX_ITEMS; i++) warmPut(`id${i}`, entry(i * 1000), i * 1000);
    warmPut("new", entry(9000), 9000);
    expect(warmGet("id1", 10_000)).toBeNull(); // oldest evicted
    expect(warmGet("new", 10_000)).not.toBeNull();
  });
  it("warmDelete removes an entry", () => {
    warmPut("x", entry(1), 1);
    warmDelete("x");
    expect(warmGet("x", 2)).toBeNull();
  });
  it("warms 45 s before the end", () => {
    expect(WARM_AHEAD_SEC).toBe(45);
  });
});

describe("HLS/MSE transport (player Phase 2)", () => {
  it("usesHls is true for every non-direct mode", () => {
    expect(usesHls("direct")).toBe(false);
    expect(usesHls("remux")).toBe(true);
    expect(usesHls("transcode_audio")).toBe(true);
    expect(usesHls("transcode")).toBe(true);
  });
  it("the HLS ladder escalates remux → transcode_audio → transcode → give-up", () => {
    expect(HLS_LADDER).toEqual(["remux", "transcode_audio", "transcode"]);
    // from a direct-play failure the first HLS attempt is remux (copy-copy)
    expect(nextHlsMode("direct")).toBe("remux");
    expect(nextHlsMode("remux")).toBe("transcode_audio");
    expect(nextHlsMode("transcode_audio")).toBe("transcode");
    expect(nextHlsMode("transcode")).toBeNull();
  });
  it("hlsEngineFor prefers native HLS on Apple mobile, hls.js elsewhere", () => {
    // Safari/iOS (Apple mobile): canPlayType maybe/probably → native HLS.
    expect(hlsEngineFor(() => "maybe", false, true)).toBe("native");
    expect(hlsEngineFor(() => "probably", false, true)).toBe("native");
    // Desktop Chrome/Firefox/Edge: no Apple UA → hls.js when MSE is available —
    // even recent Chromium that advertises canPlayType("maybe") (native TS
    // demuxers proved unreliable for Jellyfin segments; hls.js transmuxes).
    expect(hlsEngineFor(() => "maybe", true, false)).toBe("hlsjs");
    expect(hlsEngineFor(() => "", true, false)).toBe("hlsjs");
    expect(hlsEngineFor(() => "no", true, true)).toBe("hlsjs"); // canPlayType no → not native
    // no MSE at all → none (ancient browser; error path)
    expect(hlsEngineFor(() => "", false, false)).toBe("none");
  });
  it("hlsModeLabel is a clear per-mode chip label", () => {
    expect(hlsModeLabel("direct")).toBe("Direct play");
    expect(hlsModeLabel("remux")).toBe("Remux (HLS)");
    expect(hlsModeLabel("transcode_audio")).toBe("Transcode (audio)");
    expect(hlsModeLabel("transcode")).toBe("Transcode");
  });
});

describe("nextPlayableEpisode + episodeCode (series preplay auto-continue)", () => {
  const mk = (id: string, season: number, episode: number, over: Partial<EpisodeShape> = {}): EpisodeShape => ({
    id, name: `E${id}`, season, episode, played: false,
    playback_position: 0, runtime: 1800, ...over,
  });
  it("prefers the in-progress episode", () => {
    const eps = [
      mk("a", 1, 1),
      mk("b", 1, 2, { playback_position: 600 }),
      mk("c", 1, 3),
    ];
    expect(nextPlayableEpisode(eps)?.id).toBe("b");
  });
  it("else the first unwatched, sorted by season/episode", () => {
    const eps = [
      mk("s2e1", 2, 1, { played: true }),
      mk("s1e1", 1, 1),
      mk("s1e2", 1, 2),
    ];
    expect(nextPlayableEpisode(eps)?.id).toBe("s1e1");
  });
  it("null when everything is watched", () => {
    const eps = [mk("a", 1, 1, { played: true }), mk("b", 1, 2, { played: true })];
    expect(nextPlayableEpisode(eps)).toBeNull();
  });
  it("episodeCode formats S/E", () => {
    expect(episodeCode({ season: 1, episode: 4 })).toBe("S1E4");
  });
});