import { describe, expect, it } from "vitest";
import { ApiError } from "../../lib/api/client";
import { ambiguousMatch } from "./actions";

/**
 * The READER half of the 409 story: turning a caught error into "the server matched several titles
 * and will not choose".
 *
 * ⚠ `ambiguousCandidates` (in `lib/api/client.ts`) already pins the SHAPE — title/year, junk rows
 * dropped, a non-ApiError yields `[]`. This file pins the DECISION built on it: when the shared
 * download action should stop and let a surface render structure instead of a toast, and — just as
 * important — when it must not. Every "no" case here is a 409-shaped imposter that has to keep the
 * old behaviour, because a screen that swallowed an ordinary failure into an empty panel would be a
 * worse bug than the one this feature fixes.
 */
describe("ambiguousMatch", () => {
  it("returns the sentence AND the candidates for a real ambiguous match", () => {
    const err = new ApiError(409, "Two titles matched — pick one", "Two titles matched — pick one", {
      message: "Two titles matched — pick one",
      candidates: [
        { title: "Sholay", year: 1975 },
        { title: "The Sholay Girl", year: 2019 },
      ],
    });

    const match = ambiguousMatch(err);

    expect(match?.message).toBe("Two titles matched — pick one");
    expect(match?.candidates.map((c) => c.title)).toEqual(["Sholay", "The Sholay Girl"]);
    expect(match?.candidates[1].year).toBe(2019);
  });

  it("keeps structure that arrived without a sentence", () => {
    // ⚠ `message` is "" and NOT undefined: the panel has its own fallback sentence, and a screen
    // must be able to tell "the server said nothing" from "there is no match here".
    const err = new ApiError(409, "", null, { candidates: [{ title: "Only one named" }] });
    const match = ambiguousMatch(err);
    expect(match?.message).toBe("");
    expect(match?.candidates).toHaveLength(1);
  });

  it("is null for a 409 whose candidate list is empty — a sentence is not a choice", () => {
    const err = new ApiError(409, "Something needs deciding", "Something needs deciding", {
      message: "Something needs deciding",
      candidates: [],
    });
    expect(ambiguousMatch(err)).toBeNull();
  });

  it("is null for a string detail, a plain error, or nothing at all", () => {
    // The three cases that must keep the toast they always had.
    expect(ambiguousMatch(new ApiError(409, "pick one", "pick one"))).toBeNull();
    expect(ambiguousMatch(new Error("network down"))).toBeNull();
    expect(ambiguousMatch(null)).toBeNull();
    expect(ambiguousMatch(undefined)).toBeNull();
  });

  it("is null for a 200-shaped payload that merely LOOKS like a candidate list", () => {
    // A success body carries `candidates` too (empty in practice). It is not an error, so it can
    // never reach here — but a payload whose rows are junk must not manufacture a match either.
    const err = new ApiError(500, "boom", "boom", { candidates: [{ year: 2001 }, "nope"] });
    expect(ambiguousMatch(err)).toBeNull();
  });
});
