import { useSearchPrefs, useSetSearchPrefs } from "./api";
import { personalizationCopy, semanticCopy } from "./searchPrefs";
import { PrefSwitchCard } from "./PrefSwitchCard";

/**
 * The SEARCH preferences section — both of them, under one heading (SEARCH_IMPROVEMENT_PLAN Phase 5
 * and Phase 6).
 *
 * ⚠ **One section, two switches**, because they are the same question asked twice: how do I want
 * search to work? Splitting them into two headings would put two "Search" sections on one screen.
 *
 * * **Personalized search** (Phase 5) — bias discovery toward the genres this profile watches.
 * * **Search by meaning** (Phase 5's neighbour, Phase 6) — when the string matcher finds nothing,
 *   look for titles whose own descriptions are CLOSE to what was typed.
 *
 * ⚠ **Per profile, and the copy says so both times.** The server takes the profile from the session
 * (`api/session.py`, §11), so each sentence names whose setting it is rather than saying "your" — on
 * a shared device those are different promises.
 *
 * ⚠ **The writes are PATCHES, one preference each** (`useSetSearchPrefs`): the server treats a
 * missing field as "leave it alone", so turning one switch off cannot reset the other. The card
 * positions itself from the SERVER's stored answer, never from the click.
 */
export function SearchPrefsSection() {
  const prefs = useSearchPrefs();
  const setPrefs = useSetSearchPrefs();

  const personalization = prefs.data?.personalized ?? true;
  const semantic = prefs.data?.semantic ?? true;
  const who = prefs.data?.profile_name ?? "";
  const personalizationWords = personalizationCopy(personalization, who);
  const semanticWords = semanticCopy(semantic, who);

  return (
    <section aria-label="Search" className="flex flex-col gap-3">
      <h2 className="text-[11px] font-bold uppercase tracking-[0.14em] text-zinc-500">Search</h2>
      <PrefSwitchCard
        title={personalizationWords.title}
        description={personalizationWords.description}
        switchLabel={personalizationWords.switchLabel}
        stateWord={personalizationWords.stateWord}
        checked={personalization}
        busy={setPrefs.isPending}
        loading={prefs.isLoading}
        error={prefs.isError}
        testId="search-personalization"
        icon="sparkles"
        onToggle={() => setPrefs.mutate({ personalized: !personalization })}
      />
      <PrefSwitchCard
        title={semanticWords.title}
        description={semanticWords.description}
        switchLabel={semanticWords.switchLabel}
        stateWord={semanticWords.stateWord}
        checked={semantic}
        busy={setPrefs.isPending}
        loading={prefs.isLoading}
        error={prefs.isError}
        testId="search-semantic"
        icon="search"
        onToggle={() => setPrefs.mutate({ semantic: !semantic })}
      />
    </section>
  );
}
