import type { AmbiguousMatch } from "../watchlist/actions";

/**
 * "More than one title matched" — what the server actually said, inside the surface where the person
 * acted.
 *
 * ⚠ **Why this exists at all.** `POST /api/media/{id}/request` answers **409** with
 * `detail: {message, candidates}` when a title request matches several titles. Until now the whole
 * thing collapsed into a toast that carried only the sentence (`ApiError.detail`), so the one
 * failure a person could reason about arrived as a dead end: *"Two titles matched — pick one"*,
 * with nothing to look at and no way to see which two. `ApiError.payload` +
 * `ambiguousCandidates()` keep the list (2026-09-18), and this is the list rendered.
 *
 * ⚠ **It is READ-ONLY, and that is the whole design.** The server's candidates carry a title and a
 * year and **no id**, so "pick one" has nothing to re-request with — a pickable row here would be a
 * control that cannot act, which is exactly the defect M3-part-4 removed from the details page.
 * Making it actionable is a BACKEND phase (carry an id on each candidate and accept a chosen one on
 * the request path) and is his call, not this component's: see `KNOWN_ISSUES` §7.
 *
 * ⚠ **One renderer, both shells.** It lives in `SuggestDetailBody`, which the desktop's `Dialog` and
 * the phone's `Sheet` both render, so the two surfaces cannot come to describe the same 409
 * differently — the same reason the body itself was extracted.
 */
export const AMBIGUOUS_FALLBACK = "More than one title matched.";

/**
 * The sentence that says what to do about it. ⚠ It names the *arr app on purpose: that is where the
 * pick CAN be made today, and pointing at a control that does not exist would be worse than saying
 * nothing.
 */
export const AMBIGUOUS_NO_PICK =
  "This app cannot tell which one you meant — add it from Radarr or Sonarr instead.";

export function AmbiguousMatches({ match }: { match: AmbiguousMatch }) {
  return (
    <section
      data-testid="ambiguous-matches"
      // ⚠ `role="status"`, not `alert`: the request failed on a screen the person is looking at, so
      // the text must be readable where it is — not shouted over it.
      role="status"
      className="mt-4 rounded-[10px] border border-amber-400/25 bg-amber-400/[.06] p-3"
    >
      <p className="text-[13px] font-semibold leading-snug text-amber-300">
        {match.message || AMBIGUOUS_FALLBACK}
      </p>
      <ul className="mt-2 flex flex-col gap-1">
        {match.candidates.map((c, i) => (
          <li
            key={`${c.title}-${c.year ?? ""}-${i}`}
            data-testid="ambiguous-candidate"
            className="flex items-baseline gap-2 text-[13px] text-zinc-200"
          >
            <span aria-hidden="true" className="text-zinc-500">
              ·
            </span>
            <span className="min-w-0 font-medium">{c.title}</span>
            {c.year ? <span className="shrink-0 text-[12px] text-zinc-500">{c.year}</span> : null}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[12px] leading-relaxed text-zinc-400">{AMBIGUOUS_NO_PICK}</p>
    </section>
  );
}
