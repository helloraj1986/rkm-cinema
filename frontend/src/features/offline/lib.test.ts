import { describe, expect, it } from "vitest";

import {
  ACTION_LABELS,
  actionsFor,
  applyEvent,
  applyEvents,
  diskSummary,
  downloadSummary,
  fmtBytes,
  isOfflineState,
  modeLabel,
  parseEvent,
  parseItem,
  parseReply,
  percentOf,
  rowStatusText,
  serverNote,
  sumBytes,
  transcodeWarning,
  upsert,
  type OfflineItem,
} from "./lib";

const GB = 1_000_000_000;

function row(overrides: Partial<OfflineItem> = {}): OfflineItem {
  return {
    itemId: "m-sholay",
    title: "Sholay",
    state: "ready",
    bytes: 1_543_383_346,
    totalBytes: 1_543_383_346,
    mode: "remux",
    error: null,
    url: "http://127.0.0.1:51234/offline/abc.mp4",
    contentType: "video/mp4",
    ...overrides,
  };
}

describe("the bridge is a boundary", () => {
  it("drops a row it cannot address — a row with no itemId has no cancel, delete or play", () => {
    expect(parseItem({ title: "Sholay", state: "ready" })).toBeNull();
    expect(parseItem({ itemId: "", state: "ready" })).toBeNull();
    expect(parseItem(null)).toBeNull();
    expect(parseItem("ready")).toBeNull();
  });

  it("drops a row whose state is not one of the four, rather than rendering a row with no controls", () => {
    expect(parseItem({ itemId: "i", state: "done" })).toBeNull();
    expect(parseItem({ itemId: "i", state: 7 })).toBeNull();
    expect(isOfflineState("paused")).toBe(true);
    expect(isOfflineState("Paused")).toBe(false);
  });

  it("reads a real row, keeping a missing number as 0 and a missing title as the id", () => {
    const parsed = parseItem({ itemId: "i1", state: "downloading", bytes: 10, totalBytes: 100 });
    expect(parsed).toEqual({
      itemId: "i1", title: "i1", state: "downloading", bytes: 10, totalBytes: 100,
      mode: "", error: null, url: null, contentType: null,
    });
  });

  it("⚠ never turns a MISSING number into a confident 0 through Number()", () => {
    // `Number(null) === 0` and `Number("") === 0`, so a naive cast would claim "0 B downloaded" for
    // a payload that never said how many bytes there were — and 0 B is a real answer to us.
    const parsed = parseItem({ itemId: "i1", state: "downloading", bytes: null, totalBytes: "" });
    expect(parsed?.bytes).toBe(0);
    expect(parsed?.totalBytes).toBe(0);
  });

  it("refuses a reply from another contract version instead of guessing its shape", () => {
    const reply = parseReply({ v: 2, ok: true, result: { items: [] } });
    expect(reply.ok).toBe(false);
    if (!reply.ok) expect(reply.error.code).toBe("unsupportedVersion");
  });

  it("keeps a refusal's code and sentence — both audiences, both fields", () => {
    const reply = parseReply({ v: 1, ok: false, error: { code: "badMode", message: "\"hd\" is not a rendition" } });
    expect(reply.ok).toBe(false);
    if (!reply.ok) {
      expect(reply.error.code).toBe("badMode");
      expect(reply.error.message).toContain("rendition");
    }
  });

  it("tells 'the app refused' apart from 'we cannot read what the app said'", () => {
    const refusal = parseReply({ v: 1, ok: false, error: { code: "notReady", message: "not ready" } });
    const unreadable = parseReply({ v: 1, ok: true, result: {} });
    expect(refusal.ok).toBe(false);
    expect(unreadable.ok).toBe(false);
    if (!refusal.ok) expect("unreadable" in refusal).toBe(false);
    if (!unreadable.ok) expect("unreadable" in unreadable).toBe(true);
  });

  it("reads a list reply, and an accepted one, and play, and ping", () => {
    const list = parseReply({ v: 1, ok: true, result: { items: [row()], bytes: 42, count: 1 } });
    expect(list.ok && list.kind === "list" && list.items).toHaveLength(1);
    const play = parseReply({
      v: 1, ok: true, result: { play: { itemId: "i", url: "http://127.0.0.1:1/offline/a.mp4", contentType: "video/mp4", size: 7 } },
    });
    expect(play.ok && play.kind === "play" && play.play.size).toBe(7);
    const accepted = parseReply({ v: 1, ok: true, result: { accepted: "download" } });
    expect(accepted.ok && accepted.kind === "accepted" && accepted.command).toBe("download");
    const ping = parseReply({ v: 1, ok: true, result: { accepted: "ping" } });
    expect(ping.ok && ping.kind).toBe("ping");
  });

  it("computes the list total from the rows when the app does not send one", () => {
    const reply = parseReply({ v: 1, ok: true, result: { items: [row({ bytes: 3 }), row({ itemId: "b", bytes: 4 })] } });
    expect(reply.ok && reply.kind === "list" && reply.bytes).toBe(7);
  });
});

describe("events", () => {
  it("reads every event the app can send, and drops the ones it cannot", () => {
    expect(parseEvent({ v: 1, e: "progress", itemId: "i", bytes: 1, totalBytes: 2, percent: 50 })?.e).toBe("progress");
    expect(parseEvent({ v: 1, e: "ready", itemId: "i", url: "u", bytes: 1 })?.e).toBe("ready");
    expect(parseEvent({ v: 1, e: "removed", itemId: "i" })?.e).toBe("removed");
    expect(parseEvent({ v: 1, e: "state", itemId: "i", title: "T", state: "ready" })?.e).toBe("state");
    expect(parseEvent({ v: 1, e: "probe" })?.e).toBe("probe");
    expect(parseEvent({ v: 2, e: "removed", itemId: "i" })).toBeNull(); // another contract
    expect(parseEvent({ v: 1, e: "ready", itemId: "i" })).toBeNull();  // a ready event without a URL
    expect(parseEvent({ v: 1, e: "removed" })).toBeNull();             // nothing to remove
    expect(parseEvent({ v: 1, e: "teleported", itemId: "i" })).toBeNull();
  });

  it("a state event replaces the row but never the file's content type", () => {
    const next = applyEvent([row()], {
      e: "state", itemId: "m-sholay",
      item: { ...row(), state: "downloading", url: null, bytes: 10, contentType: null },
    });
    expect(next[0].state).toBe("downloading");
    expect(next[0].url).toBeNull();
    // ⚠ The event's row carries no contentType; it describes the FILE, which has not changed.
    expect(next[0].contentType).toBe("video/mp4");
  });

  it("a ready event turns the row ready and carries the loopback URL", () => {
    const next = applyEvent([row({ state: "downloading", bytes: 5, totalBytes: 100, url: null })], {
      e: "ready", itemId: "m-sholay", url: "http://127.0.0.1:5/offline/x.mp4", contentType: "video/mp4", bytes: 100,
    });
    expect(next[0].state).toBe("ready");
    expect(next[0].url).toBe("http://127.0.0.1:5/offline/x.mp4");
    expect(next[0].bytes).toBe(100);
  });

  it("progress moves the bytes and keeps a known total when the event omits one", () => {
    const next = applyEvent([row({ state: "downloading", totalBytes: 100, bytes: 3 })], {
      e: "progress", itemId: "m-sholay", bytes: 40, totalBytes: 0, percent: 40,
    });
    expect(next[0].bytes).toBe(40);
    expect(next[0].totalBytes).toBe(100);
  });

  it("ignores progress for a title it has no row for — the state event owns a row's existence", () => {
    expect(applyEvent([], { e: "progress", itemId: "ghost", bytes: 1, totalBytes: 2, percent: 1 })).toEqual([]);
  });

  it("a removed event for a row we never had is a no-op, not a re-render", () => {
    const rows = [row()];
    expect(applyEvent(rows, { e: "removed", itemId: "ghost" })).toBe(rows);
  });

  it("removes a title the app has forgotten, so no row offers a film that is gone", () => {
    expect(applyEvent([row(), row({ itemId: "b" })], { e: "removed", itemId: "m-sholay" })).toHaveLength(1);
  });

  it("applies a batch in order", () => {
    const rows = applyEvents([], [
      { e: "state", itemId: "m-sholay", item: row({ state: "downloading", url: null }) },
      { e: "ready", itemId: "m-sholay", url: "http://127.0.0.1:5/offline/x.mp4", contentType: "video/mp4", bytes: 100 },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].state).toBe("ready");
  });

  it("keeps native's own order when a row is replaced", () => {
    const rows = [row({ itemId: "a" }), row({ itemId: "b" })];
    const next = upsert(rows, row({ itemId: "a", state: "paused" }));
    expect(next.map((r) => r.itemId)).toEqual(["a", "b"]);
    expect(next[0].state).toBe("paused");
  });
});

describe("the numbers a person reads", () => {
  it("⚠ refuses to turn an unknown total into a percentage (0% over an unknown file is a lie)", () => {
    expect(percentOf(10, 0)).toBeNull();
    expect(percentOf(0, 0)).toBeNull();
    expect(percentOf(10, Number.NaN)).toBeNull();
  });

  it("reports a real percentage, clamped", () => {
    expect(percentOf(50, 100)).toBe(50);
    expect(percentOf(0, 100)).toBe(0);
    expect(percentOf(100, 100)).toBe(100);
    expect(percentOf(200, 100)).toBe(100);
  });

  it("uses DECIMAL units, so the page and the app's own HUD agree about one file", () => {
    // The app logs `offline READY · 1.54 GB` for the film whose byte count is 1543383346.
    expect(fmtBytes(1_543_383_346)).toBe("1.54 GB");
    expect(fmtBytes(0)).toBe("0 B");
    expect(fmtBytes(999)).toBe("999 B");
    expect(fmtBytes(1_000)).toBe("1 kB");
    expect(fmtBytes(2_100_000_000)).toBe("2.10 GB");
    expect(fmtBytes(Number.NaN)).toBe("0 B");
  });

  it("says something true in every state, including the failing one", () => {
    expect(rowStatusText(row({ state: "downloading", bytes: 500 * 1e6, totalBytes: GB }))).toBe(
      "500 MB / 1.00 GB · 50%",
    );
    expect(rowStatusText(row({ state: "downloading", bytes: 500, totalBytes: 0 }))).toBe("500 B downloaded");
    expect(rowStatusText(row({ state: "paused", bytes: 5, totalBytes: 100 }))).toBe("5 B of 100 B — resumable");
    expect(rowStatusText(row({ state: "ready" }))).toBe("On this device · 1.54 GB");
    expect(rowStatusText(row({ state: "failed", error: "The server refused (401)." }))).toBe("The server refused (401).");
    expect(rowStatusText(row({ state: "failed", error: null }))).toBe("The download failed.");
  });

  it("labels the rendition the downloader recorded", () => {
    expect(modeLabel("remux")).toBe("Remux");
    expect(modeLabel("direct")).toBe("Direct");
    expect(modeLabel("transcode_audio")).toBe("Audio transcode");
    expect(modeLabel("")).toBe("");
    expect(modeLabel("something-new")).toBe("something-new");
  });

  it("shows the phone's real usage, counting only complete films", () => {
    expect(diskSummary([])).toBe("Nothing is downloaded yet.");
    expect(diskSummary([row(), row({ itemId: "b", state: "downloading", bytes: 5 })])).toBe(
      "1 title · 1.54 GB on this device",
    );
    expect(diskSummary([row(), row({ itemId: "b" })])).toBe("2 titles · 3.09 GB on this device");
  });
});

describe("what the detail page offers", () => {
  it("offers Download only when the device has no row at all", () => {
    expect(actionsFor(null)).toEqual([]);
    expect(ACTION_LABELS.download).toBe("Download");
  });

  it("offers exactly the controls the row's state can act on", () => {
    expect(actionsFor(row({ state: "downloading" }))).toEqual(["cancel", "delete"]);
    expect(actionsFor(row({ state: "paused" }))).toEqual(["resume", "delete"]);
    expect(actionsFor(row({ state: "failed" }))).toEqual(["retry", "delete"]);
    expect(actionsFor(row({ state: "ready" }))).toEqual(["play", "delete"]);
  });

  it("⚠ always offers Delete: bytes on a phone with no way to remove them is the worst state", () => {
    for (const state of ["downloading", "paused", "ready", "failed"] as const) {
      expect(actionsFor(row({ state }))).toContain("delete");
    }
  });
});

describe("the server's own answer", () => {
  const bundle = {
    item_id: "m-sholay", title: "Sholay", mode: "remux", needs_transcode: false,
    container: "mkv", video_codec: "h264", audio_codecs: ["aac"], duration_s: 12240,
    estimate_bytes: 2_100_000_000, state: "missing", bytes: 0, size: 0, borrowed: false,
  };

  it("⚠ says 'about' when it is quoting the backend's ESTIMATE, and the exact size when it has one", () => {
    expect(downloadSummary(bundle)).toBe("Remux · MKV · H264 · about 2.10 GB");
    expect(downloadSummary({ ...bundle, size: 1_543_383_346, state: "ready" })).toBe(
      "Remux · MKV · H264 · 1.54 GB",
    );
  });

  it("claims no resolution it was not told", () => {
    // The plan's example label is "1080p · 2.1 GB · remux"; the bundle carries no height, and a
    // confident "1080p" derived from a byte count is exactly the guess this feature cannot afford.
    expect(downloadSummary(bundle)).not.toContain("1080p");
    expect(downloadSummary(bundle)).not.toContain("p ·");
  });

  it("says nothing at all when the server has not answered yet", () => {
    expect(downloadSummary(null)).toBe("");
    expect(downloadSummary(undefined)).toBe("");
  });

  it("warns when the download costs the server a re-encode, and stays quiet otherwise", () => {
    expect(transcodeWarning(bundle)).toBe("");
    expect(transcodeWarning({ ...bundle, needs_transcode: true })).toContain("re-encode");
  });

  it("⚠ tells the truth about a download that outlived its server record", () => {
    expect(serverNote(true, row())).toBe("");
    expect(serverNote(null, row())).toBe("");
    expect(serverNote(false, row({ state: "ready" }))).toContain("still plays");
    // A partial download cannot finish without the server, and saying otherwise would be a lie.
    expect(serverNote(false, row({ state: "paused" }))).toContain("cannot finish");
    expect(serverNote(false, row({ state: "failed" }))).toContain("cannot finish");
  });
});

describe("totals", () => {
  it("ignores a non-finite byte count rather than poisoning the total with NaN", () => {
    expect(sumBytes([row({ bytes: 10 }), row({ itemId: "b", bytes: Number.NaN })])).toBe(10);
  });
});
