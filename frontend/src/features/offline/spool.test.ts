import { describe, expect, it } from "vitest";

import {
  TICKS_PER_SECOND,
  confirmSpoolPosted,
  dropSpoolEntry,
  dueSpool,
  emptySpool,
  isFinished,
  parseSpoolEnvelope,
  readSpool,
  recordSpool,
  replayFailureNotice,
  resumeSecondsFrom,
  spoolEnvelope,
  spoolSize,
  writeSpool,
  type SpoolEntry,
  type SpoolState,
  type SpoolStorage,
} from "./spool";

const MINUTE = 60 * TICKS_PER_SECOND;
const NOW = 1_800_000_000_000; // a fixed clock: every assertion below is about arithmetic, not time.

function entry(overrides: Partial<SpoolEntry> = {}): SpoolEntry {
  return {
    itemId: "m-sholay",
    position_ticks: 64 * MINUTE,
    runtime_ticks: 204 * MINUTE,
    play_method: "DirectPlay",
    event: "timeupdate",
    recorded_at: NOW,
    ...overrides,
  };
}

function memoryStorage(seed: Record<string, string> = {}): SpoolStorage & { data: Record<string, string> } {
  const data: Record<string, string> = { ...seed };
  return {
    data,
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => {
      data[key] = value;
    },
    removeItem: (key) => {
      delete data[key];
    },
  };
}

const CONTEXT = { owner: "uid-admin", server: "http://rkm-hp:8124", now: NOW };

describe("the watermark — ⚠ the rule that stops a replay REWINDING someone", () => {
  it("keeps the FURTHEST position for a title, not the latest report", () => {
    // He watches offline to 1:04:00, then reopens the film: the player reports `start` at the resume
    // point — or at 0 after a deliberate restart. Last-write-wins would queue 0:00:00, and the replay
    // would move his resume point back to the beginning of a film he is an hour into.
    let state = recordSpool(emptySpool(), entry({ position_ticks: 64 * MINUTE }));
    state = recordSpool(state, entry({ position_ticks: 0, event: "start", recorded_at: NOW + 1_000 }));
    expect(state.entries["m-sholay"].position_ticks).toBe(64 * MINUTE);
  });

  it("moves forward when a later report is further along", () => {
    let state = recordSpool(emptySpool(), entry({ position_ticks: 10 * MINUTE }));
    state = recordSpool(state, entry({ position_ticks: 40 * MINUTE, recorded_at: NOW + 5_000 }));
    expect(state.entries["m-sholay"].position_ticks).toBe(40 * MINUTE);
    expect(state.entries["m-sholay"].recorded_at).toBe(NOW + 5_000);
  });

  it("⚠ absorbs a LATER runtime even when the position does not move, or a film could never be marked finished", () => {
    // The first reports of a play often arrive before the duration is known (`runtime_ticks: 0`).
    // If a later report knew the runtime but a smaller position, throwing the runtime away would
    // leave the replay unable to be read as "watched".
    let state = recordSpool(emptySpool(), entry({ position_ticks: 64 * MINUTE, runtime_ticks: 0 }));
    state = recordSpool(state, entry({ position_ticks: 10 * MINUTE, runtime_ticks: 204 * MINUTE, recorded_at: NOW + 1 }));
    expect(state.entries["m-sholay"].position_ticks).toBe(64 * MINUTE);
    expect(state.entries["m-sholay"].runtime_ticks).toBe(204 * MINUTE);
  });

  it("does not rewrite storage for an identical report (a play reports every second)", () => {
    const state = recordSpool(emptySpool(), entry());
    expect(recordSpool(state, entry({ recorded_at: NOW - 1 }))).toBe(state);
  });

  it("refuses an entry with no id, a negative position or a non-finite timestamp", () => {
    const state = emptySpool();
    expect(recordSpool(state, entry({ itemId: "" }))).toBe(state);
    expect(recordSpool(state, entry({ position_ticks: -1 }))).toBe(state);
    expect(recordSpool(state, entry({ position_ticks: Number.NaN }))).toBe(state);
    expect(recordSpool(state, entry({ recorded_at: Number.NaN }))).toBe(state);
  });

  it("keeps one entry per title", () => {
    let state = recordSpool(emptySpool(), entry({ itemId: "a", position_ticks: 10 }));
    state = recordSpool(state, entry({ itemId: "b", position_ticks: 20, recorded_at: NOW + 1_000 }));
    state = recordSpool(state, entry({ itemId: "a", position_ticks: 30, recorded_at: NOW + 2_000 }));
    expect(spoolSize(state)).toBe(2);
    expect(dueSpool(state).map((e) => e.itemId)).toEqual(["b", "a"]);
  });
});

describe("the two paths agreeing", () => {
  it("⚠ a LIVE post supersedes a queued position at or below it — the other half of 'newest wins'", () => {
    const queued = recordSpool(emptySpool(), entry({ position_ticks: 64 * MINUTE }));
    const after = confirmSpoolPosted(queued, "m-sholay", 80 * MINUTE);
    expect(spoolSize(after)).toBe(0);
    // Replaying the 64-minute entry after the server has heard 80 minutes would REWIND him.
  });

  it("⚠ a live post BELOW a queued position leaves the queue alone — the server is behind, not ahead", () => {
    const queued = recordSpool(emptySpool(), entry({ position_ticks: 64 * MINUTE }));
    expect(confirmSpoolPosted(queued, "m-sholay", 10 * MINUTE)).toBe(queued);
  });

  it("confirming a title that is not queued changes nothing", () => {
    const state = emptySpool();
    expect(confirmSpoolPosted(state, "ghost", 1)).toBe(state);
  });

  it("⚠ drops only the entry that was replayed — a newer one recorded mid-flight survives the race", () => {
    const queued = recordSpool(emptySpool(), entry({ recorded_at: NOW }));
    const newer = recordSpool(queued, entry({ position_ticks: 70 * MINUTE, recorded_at: NOW + 500 }));
    const after = dropSpoolEntry(newer, "m-sholay", NOW);
    expect(spoolSize(after)).toBe(1);
    expect(after.entries["m-sholay"].position_ticks).toBe(70 * MINUTE);
  });

  it("flushing in order, oldest first", () => {
    let state = recordSpool(emptySpool(), entry({ itemId: "b", recorded_at: NOW + 900 }));
    state = recordSpool(state, entry({ itemId: "a", recorded_at: NOW + 100 }));
    expect(dueSpool(state).map((e) => e.itemId)).toEqual(["a", "b"]);
  });

  it("is deterministic for two entries recorded in the same millisecond", () => {
    let state = recordSpool(emptySpool(), entry({ itemId: "b", recorded_at: NOW }));
    state = recordSpool(state, entry({ itemId: "a", recorded_at: NOW }));
    expect(dueSpool(state).map((e) => e.itemId)).toEqual(["a", "b"]);
  });
});

describe("where an offline play starts", () => {
  it("takes whichever is FURTHER: the server's answer or this device's own queue", () => {
    const state = recordSpool(emptySpool(), entry({ position_ticks: 64 * MINUTE }));
    expect(resumeSecondsFrom(state, "m-sholay", 30 * 60, 204 * 60)).toBe(64 * 60);
    expect(resumeSecondsFrom(state, "m-sholay", 90 * 60, 204 * 60)).toBe(90 * 60);
  });

  it("falls back to the server's answer when nothing is queued", () => {
    expect(resumeSecondsFrom(emptySpool(), "m-sholay", 300, 7200)).toBe(300);
    expect(resumeSecondsFrom(emptySpool(), "m-sholay", 0, 7200)).toBe(0);
    expect(resumeSecondsFrom(emptySpool(), "m-sholay", Number.NaN, 7200)).toBe(0);
  });

  it("⚠ a position near the end is not a resume point — it means the film is done", () => {
    const state = recordSpool(emptySpool(), entry({ position_ticks: 203 * MINUTE, runtime_ticks: 204 * MINUTE }));
    expect(resumeSecondsFrom(state, "m-sholay", 0, 204 * 60)).toBe(0);
    expect(isFinished(203 * MINUTE, 204 * MINUTE)).toBe(true);
    expect(isFinished(190 * MINUTE, 204 * MINUTE)).toBe(false);
  });

  it("an unknown runtime never reads as finished", () => {
    expect(isFinished(999 * MINUTE, 0)).toBe(false);
  });
});

describe("why a replay did not land — the three cases must not read the same", () => {
  it("tells an expired session, a dead network and a refusal apart", () => {
    // ⚠ The queue was silent for a whole round (three positions, no reason on screen). The status is
    // the only thing that distinguishes these, and only one of them means "wait".
    expect(replayFailureNotice(401)).toContain("Sign in again");
    expect(replayFailureNotice(403)).toContain("Sign in again");
    expect(replayFailureNotice(null)).toContain("could not be reached");
    expect(replayFailureNotice(502)).toContain("could not record");
    expect(replayFailureNotice(400)).toContain("refused");
  });

  it("never says the positions are lost — they are kept in every case", () => {
    for (const status of [null, 400, 401, 403, 500, 502, 503]) {
      expect(replayFailureNotice(status)).toMatch(/kept|Sign in again/);
    }
  });
});

describe("the envelope — the queue outlives the page, so it must be stamped", () => {
  it("round-trips through storage", () => {
    const storage = memoryStorage();
    const state = recordSpool(emptySpool(), entry());
    expect(writeSpool(storage, state, CONTEXT)).toBeGreaterThan(0);
    const back = readSpool(storage, CONTEXT);
    expect(back?.entries["m-sholay"].position_ticks).toBe(64 * MINUTE);
  });

  it("⚠ REFUSES a queue written by another profile, and deletes it rather than replaying it", () => {
    const storage = memoryStorage();
    writeSpool(storage, recordSpool(emptySpool(), entry()), { owner: "uid-kid", server: CONTEXT.server, now: NOW });
    // Somebody else's viewing position, replayed under this session, would land in the WRONG
    // person's Continue Watching — an identity leak, not a stale render.
    expect(readSpool(storage, CONTEXT)).toBeNull();
    expect(storage.data["rkm.offline-spool.v1"]).toBeUndefined();
  });

  it("⚠⚠ an UNKNOWN owner neither reads NOR destroys the queue", () => {
    // A page that loads with no network cannot ask who is watching (`/api/auth/me` cannot answer), and
    // that is exactly the launch where the positions on disk matter most. Deleting the envelope then
    // would lose the one thing the queue exists to carry — so nothing is read and nothing is removed.
    const storage = memoryStorage();
    writeSpool(storage, recordSpool(emptySpool(), entry()), CONTEXT);
    expect(readSpool(storage, { ...CONTEXT, owner: "" })).toBeNull();
    expect(storage.data["rkm.offline-spool.v1"]).toBeDefined();
    // …and the next load that CAN identify the viewer still finds it.
    expect(readSpool(storage, CONTEXT)?.entries["m-sholay"].position_ticks).toBe(64 * MINUTE);
  });

  it("⚠ refuses a queue written for another SERVER — the same item ids name different films there", () => {
    const storage = memoryStorage();
    writeSpool(storage, recordSpool(emptySpool(), entry()), { owner: CONTEXT.owner, server: "http://other:1", now: NOW });
    expect(readSpool(storage, CONTEXT)).toBeNull();
  });

  it("refuses an envelope from another shape, another age, or no shape at all", () => {
    const state = recordSpool(emptySpool(), entry());
    expect(parseSpoolEnvelope({ ...spoolEnvelope(state, CONTEXT.owner, CONTEXT.server, NOW), schemaVersion: 99 }, CONTEXT)).toBeNull();
    expect(parseSpoolEnvelope(spoolEnvelope(state, CONTEXT.owner, CONTEXT.server, NOW), { ...CONTEXT, now: NOW + 20 * 24 * 3600_000 })).toBeNull();
    expect(parseSpoolEnvelope("a string", CONTEXT)).toBeNull();
    expect(parseSpoolEnvelope({ schemaVersion: 1, owner: CONTEXT.owner, server: CONTEXT.server, savedAt: "now", entries: {} }, CONTEXT)).toBeNull();
  });

  it("⚠ re-keys every entry by its OWN itemId — a hand-edited queue cannot replay one title as another", () => {
    const parsed = parseSpoolEnvelope(
      {
        schemaVersion: 1, owner: CONTEXT.owner, server: CONTEXT.server, savedAt: NOW,
        entries: { "some-other-key": { itemId: "m-sholay", position_ticks: 10, runtime_ticks: 0, play_method: "", event: "stopped", recorded_at: NOW } },
      },
      CONTEXT,
    );
    expect(Object.keys(parsed?.entries ?? {})).toEqual(["m-sholay"]);
  });

  it("drops an entry it cannot read rather than the whole queue", () => {
    const parsed = parseSpoolEnvelope(
      {
        schemaVersion: 1, owner: CONTEXT.owner, server: CONTEXT.server, savedAt: NOW,
        entries: {
          good: { itemId: "good", position_ticks: 10, runtime_ticks: 0, play_method: "", event: "stopped", recorded_at: NOW },
          bad: { itemId: "bad", position_ticks: "lots" },
        },
      },
      CONTEXT,
    );
    expect(Object.keys(parsed?.entries ?? {})).toEqual(["good"]);
  });

  it("defaults an unknown event name to timeupdate instead of refusing the entry", () => {
    const parsed = parseSpoolEnvelope(
      {
        schemaVersion: 1, owner: CONTEXT.owner, server: CONTEXT.server, savedAt: NOW,
        entries: { a: { itemId: "a", position_ticks: 10, runtime_ticks: 0, event: "watched-everything", recorded_at: NOW } },
      },
      CONTEXT,
    );
    expect(parsed?.entries.a.event).toBe("timeupdate");
  });

  it("an empty queue is DELETED rather than stored — no empty envelope to interpret later", () => {
    const storage = memoryStorage();
    writeSpool(storage, recordSpool(emptySpool(), entry()), CONTEXT);
    expect(writeSpool(storage, emptySpool(), CONTEXT)).toBeNull();
    expect(storage.data["rkm.offline-spool.v1"]).toBeUndefined();
  });

  it("⚠ writes nothing at all when nobody is signed in", () => {
    const storage = memoryStorage();
    expect(writeSpool(storage, recordSpool(emptySpool(), entry()), { ...CONTEXT, owner: "" })).toBeNull();
    expect(storage.data).toEqual({});
  });

  it("an unparseable value is deleted, so the next launch does not pay for the same parse", () => {
    const storage = memoryStorage({ "rkm.offline-spool.v1": "{not json" });
    expect(readSpool(storage, CONTEXT)).toBeNull();
    expect(storage.data["rkm.offline-spool.v1"]).toBeUndefined();
  });

  it("survives a storage that throws on read, write and delete (private mode)", () => {
    const hostile: SpoolStorage = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("denied");
      },
      removeItem: () => {
        throw new Error("denied");
      },
    };
    expect(readSpool(hostile, CONTEXT)).toBeNull();
    expect(writeSpool(hostile, recordSpool(emptySpool(), entry()), CONTEXT)).toBeNull();
    expect(readSpool(null, CONTEXT)).toBeNull();
    expect(writeSpool(null, emptySpool(), CONTEXT)).toBeNull();
  });
});

describe("the spool keeps its own arithmetic straight", () => {
  it("a queued position is seconds after a round trip through ticks", () => {
    const state: SpoolState = recordSpool(emptySpool(), entry({ position_ticks: 64 * MINUTE }));
    expect(state.entries["m-sholay"].position_ticks / TICKS_PER_SECOND).toBe(3840);
    expect(resumeSecondsFrom(state, "m-sholay", 0, 204 * 60)).toBe(3840);
  });
});
