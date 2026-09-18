import { describe, expect, it } from "vitest";
import { personalizationCopy, semanticCopy } from "./searchPrefs";

describe("search personalization copy (SEARCH_IMPROVEMENT_PLAN Phase 5)", () => {
  it("says whose setting it is, because on a shared device 'your' is a lie", () => {
    const named = personalizationCopy(true, "Rajeev");
    expect(named.description).toContain("Rajeev");
    expect(personalizationCopy(true).description).not.toContain("for ");
  });

  it("promises only what the ranking actually does", () => {
    const on = personalizationCopy(true, "Rajeev");
    // ⚠ Taste reorders DISCOVERY only — the copy must not imply it reorders the
    // library he already owns.
    expect(on.description).toContain("do not own yet");
    // ⚠ …and it must state the bound. This is the sentence that stops the feature
    // reading as "search ignored what I typed".
    expect(on.description).toMatch(/never puts one ahead/i);
  });

  it("describes the OFF state as neutral rather than as a loss", () => {
    const off = personalizationCopy(false, "Rajeev");
    expect(off.description).toMatch(/neutral/i);
    expect(off.description).not.toContain("Rajeev");
  });

  it("names the OUTCOME on the switch, not the mechanism", () => {
    expect(personalizationCopy(true).switchLabel).toMatch(/turn personalized search off/i);
    expect(personalizationCopy(false).switchLabel).toMatch(/turn personalized search on/i);
    expect(personalizationCopy(true).stateWord).toBe("On");
    expect(personalizationCopy(false).stateWord).toBe("Off");
  });
});

describe("search-by-meaning copy (SEARCH_IMPROVEMENT_PLAN Phase 6)", () => {
  it("says whose setting it is, in the ON state", () => {
    expect(semanticCopy(true, "Rajeev").description).toContain("Rajeev");
  });

  it("⚠ states the BOUND, which is the only reason this switch is safe to leave on", () => {
    const on = semanticCopy(true, "Rajeev");
    // "only runs when the ordinary search finds nothing" — a person must be able to believe that
    // turning this on cannot reorder a search that already worked.
    expect(on.description).toMatch(/only runs when the ordinary search finds nothing/i);
    // …and the ranking guarantee behind it (SEMANTIC_TRIGGER_SCORE in the backend).
    expect(on.description).toMatch(/rank below a real title match/i);
  });

  it("does not promise recommendations, and names the mechanism it really uses", () => {
    const on = semanticCopy(true, "Rajeev");
    expect(on.description).toMatch(/by meaning/i);
    // ⚠ It is a FALLBACK, not a recommender: the measured probe leads with the right film on two of
    // three conversational queries and gets one of three on a mood query, so nothing here may claim
    // "films you will like".
    expect(on.description).not.toMatch(/recommend|you'll love|will love/i);
    // The example is his own query from the plan, and it is honest about WHY it can work.
    expect(on.description).toContain("something with a twist ending");
    expect(on.description).toMatch(/no title says that/i);
  });

  it("describes the OFF state plainly, and still says who it applies to", () => {
    const off = semanticCopy(false, "Rajeev");
    expect(off.description).toMatch(/by name only/i);
    expect(off.description).toMatch(/return nothing/i);
  });

  it("names the OUTCOME on the switch, not the mechanism", () => {
    expect(semanticCopy(true).switchLabel).toMatch(/turn search by meaning off/i);
    expect(semanticCopy(false).switchLabel).toMatch(/turn search by meaning on/i);
    expect(semanticCopy(true).stateWord).toBe("On");
    expect(semanticCopy(false).stateWord).toBe("Off");
  });

  it("⚠ the two switches never share wording, or one screen would describe two things identically", () => {
    expect(semanticCopy(true, "Rajeev").title).not.toBe(personalizationCopy(true, "Rajeev").title);
    expect(semanticCopy(true).switchLabel).not.toBe(personalizationCopy(true).switchLabel);
  });
});
