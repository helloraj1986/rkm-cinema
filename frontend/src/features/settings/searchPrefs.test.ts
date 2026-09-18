import { describe, expect, it } from "vitest";
import { personalizationCopy } from "./searchPrefs";

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
