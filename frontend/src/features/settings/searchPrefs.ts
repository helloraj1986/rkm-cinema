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

/**
 * The copy for the MEANING-based fallback switch (SEARCH_IMPROVEMENT_PLAN Phase 6).
 *
 * ⚠ What each clause has to get right, because a person decides with it:
 *  - **"when nothing matches"** is the bound, and it is the honest promise: this never reorders a
 *    search that already worked, so turning it on cannot make a good result worse;
 *  - **"by meaning"** is what it actually does — the library's own descriptions are compared to
 *    what was typed — and it is why the title list it returns can contain films whose titles share
 *    no words with the query;
 *  - **"always below a real title match"** is the ranking guarantee a person can hold the app to
 *    (see `SEMANTIC_TRIGGER_SCORE` in the backend). Without it the feature reads as "search
 *    sometimes shows me unrelated films".
 */
export interface SemanticCopy {
  title: string;
  description: string;
  switchLabel: string;
  stateWord: string;
}

export function semanticCopy(enabled: boolean, profileName = ""): SemanticCopy {
  const who = profileName ? ` for ${profileName}` : "";
  return {
    title: "Search by meaning",
    description: enabled
      ? `When nothing in your library matches the words you typed, this profile also searches by MEANING${who} — so "something with a twist ending" can find films whose descriptions are close, even though no title says that. It only runs when the ordinary search finds nothing, and its results always rank below a real title match.`
      : "Search matches titles by name only. A query that describes a mood rather than naming a film will return nothing, for anyone using this profile.",
    switchLabel: enabled
      ? "Turn search by meaning off for this profile"
      : "Turn search by meaning on for this profile",
    stateWord: enabled ? "On" : "Off",
  };
}
