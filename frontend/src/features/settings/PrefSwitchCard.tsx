import { Icon } from "../../components/ui/Icon";
import { Card } from "../../components/ui/Card";

/**
 * The ONE search-preference switch row (SEARCH_IMPROVEMENT_PLAN Phase 5, Phase 6).
 *
 * ⚠ Extracted the moment search got a SECOND preference. Two nearly identical 60-line cards is how
 * these come to disagree: one gets the `role="switch"` contract and the other gets an `aria-pressed`
 * button, one positions itself from the server's answer and the other from the click. The behaviour
 * that matters is identical, so it lives in one place and only the COPY differs (the copy is a rule —
 * see `searchPrefs.ts` — and is passed in per preference).
 *
 * ⚠ **A real switch, not a checkbox.** `role="switch"` + `aria-checked` is what a screen reader
 * announces as on/off, and the whole row is the label so the tap target is not a 36px pill on a phone.
 *
 * ⚠ The caller positions it from the SERVER's answer (`useSearchPrefs` writes the response into the
 * cache), never from the click — a refused or altered write cannot leave the UI claiming a setting
 * that is not stored.
 */
export function PrefSwitchCard({
  title,
  description,
  switchLabel,
  stateWord,
  checked,
  busy,
  loading,
  error,
  testId,
  icon = "sparkles",
  onToggle,
}: {
  title: string;
  description: string;
  /** The accessible name — states the OUTCOME, not the mechanism. */
  switchLabel: string;
  stateWord: string;
  checked: boolean;
  busy: boolean;
  loading: boolean;
  error: boolean;
  /** Stable handle for the browser checks (never a class). */
  testId: string;
  icon?: "sparkles" | "search";
  onToggle: () => void;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <span
            aria-hidden="true"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-white/[.06] text-zinc-400"
          >
            <Icon name={icon} size={16} />
          </span>
          <div className="min-w-0">
            <div className="text-sm font-semibold text-zinc-100">{title}</div>
            <p className="mt-1 max-w-prose text-[12px] leading-relaxed text-zinc-500">
              {error
                ? "Couldn't read this setting — it may not be what the server has stored."
                : loading
                  ? "Reading this profile's setting…"
                  : description}
            </p>
          </div>
        </div>

        <button
          type="button"
          role="switch"
          aria-checked={checked}
          aria-label={switchLabel}
          disabled={busy || loading}
          data-testid={testId}
          onClick={onToggle}
          className="mt-0.5 flex shrink-0 items-center gap-2 rounded-full disabled:opacity-50"
        >
          <span className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
            {stateWord}
          </span>
          <span
            aria-hidden="true"
            className={`relative inline-block h-6 w-11 rounded-full ring-1 transition ${
              checked ? "bg-accent ring-accent/60" : "bg-white/[.08] ring-white/10"
            }`}
          >
            <span
              className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${
                checked ? "left-[22px]" : "left-0.5"
              }`}
            />
          </span>
        </button>
      </div>
    </Card>
  );
}
