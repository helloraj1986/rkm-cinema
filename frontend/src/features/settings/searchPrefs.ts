/**
 * The copy for the search-personalization switch (SEARCH_IMPROVEMENT_PLAN Phase 5).
 *
 * ⚠ Pure, and separate from the component, for the reason the rest of this app keeps
 * its wording in `lib.ts` files: the sentence is the RULE (it has to describe what
 * ranking actually does, including what it deliberately does not do), and a rule that
 * lives inside JSX cannot be unit-tested or reused on a second surface.
 *
 * What the description has to get right, and why each clause is load-bearing:
 *  - "titles you do not own yet" — taste reorders DISCOVERY only; suggesting it also
 *    reorders his own library would be a lie a person could catch.
 *  - "never ahead of a title that matches better" — the bound is the honest promise,
 *    and it is the one that stops this reading as "search ignored what I typed".
 */

export interface PersonalizationCopy {
  title: string;
  description: string;
  /** The switch's accessible name — states the OUTCOME, not the mechanism. */
  switchLabel: string;
  /** Short state word shown beside the switch. */
  stateWord: string;
}

export function personalizationCopy(enabled: boolean, profileName = ""): PersonalizationCopy {
  const who = profileName ? ` for ${profileName}` : "";
  return {
    title: "Personalized search",
    description: enabled
      ? `Titles you do not own yet are nudged toward the genres you watch${who}. Taste only reorders titles of similar relevance — it never puts one ahead of a title that matches what you typed better.`
      : "Search is neutral: nothing you have watched affects the order of results, for anyone using this profile.",
    switchLabel: enabled
      ? "Turn personalized search off for this profile"
      : "Turn personalized search on for this profile",
    stateWord: enabled ? "On" : "Off",
  };
}
