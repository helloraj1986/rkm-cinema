import { Card } from "../../components/ui/Card";
import { Icon } from "../../components/ui/Icon";
import { useSearchPrefs, useSetSearchPrefs } from "./api";
import { personalizationCopy } from "./searchPrefs";

/**
 * The one search preference (SEARCH_IMPROVEMENT_PLAN Phase 5): whether discovery
 * results are nudged toward the genres this profile actually watches.
 *
 * ⚠ **Per profile, and the screen says so.** The server takes the profile from the
 * session (`api/session.py`, §11), so the copy names whose setting this is rather
 * than saying "your" — on a shared device those are different sentences.
 *
 * ⚠ **A real switch, not a checkbox.** `role="switch"` + `aria-checked` is what a
 * screen reader announces as on/off, and the whole row is the label so the tap
 * target is not a 36px pill on a phone.
 *
 * ⚠ The mutation writes the SERVER's answer back into the cache (`useSetSearchPrefs`)
 * — the switch positions itself from the response, never from the click, so a
 * refused or altered write cannot leave the UI claiming a setting that is not stored.
 */
export function SearchPersonalizationCard() {
  const prefs = useSearchPrefs();
  const setPrefs = useSetSearchPrefs();

  const enabled = prefs.data?.personalized ?? true;
  const copy = personalizationCopy(enabled, prefs.data?.profile_name ?? "");
  const busy = setPrefs.isPending;

  return (
    <section aria-label="Search">
      <h2 className="mb-2 text-[11px] font-bold uppercase tracking-[0.14em] text-zinc-500">Search</h2>
      <Card className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            <span
              aria-hidden="true"
              className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-white/[.06] text-zinc-400"
            >
              <Icon name="sparkles" size={16} />
            </span>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-zinc-100">{copy.title}</div>
              <p className="mt-1 max-w-prose text-[12px] leading-relaxed text-zinc-500">
                {prefs.isError
                  ? "Couldn't read this setting — it may not be what the server has stored."
                  : prefs.isLoading
                    ? "Reading this profile's setting…"
                    : copy.description}
              </p>
            </div>
          </div>

          <button
            type="button"
            role="switch"
            aria-checked={enabled}
            aria-label={copy.switchLabel}
            disabled={busy || prefs.isLoading}
            data-testid="search-personalization"
            onClick={() => setPrefs.mutate(!enabled)}
            className="mt-0.5 flex shrink-0 items-center gap-2 rounded-full disabled:opacity-50"
          >
            <span className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
              {copy.stateWord}
            </span>
            <span
              aria-hidden="true"
              className={`relative inline-block h-6 w-11 rounded-full ring-1 transition ${
                enabled ? "bg-accent ring-accent/60" : "bg-white/[.08] ring-white/10"
              }`}
            >
              <span
                className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${
                  enabled ? "left-[22px]" : "left-0.5"
                }`}
              />
            </span>
          </button>
        </div>
      </Card>
    </section>
  );
}
