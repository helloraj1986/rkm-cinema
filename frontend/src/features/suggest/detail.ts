/**
 * Everything the suggest-detail view SHOWS, derived from what arrived (SEARCH fix,
 * 2026-09-18).
 *
 * ⚠ Why this is a separate pure module. A title that is NOT in the library has no
 * `/library/item/:itemId` page to open — its facts come from `/api/suggest/detail`.
 * The desktop answers that with a `Dialog`; a phone needs the SAME answer in a
 * `Sheet`, because a centred 90vh dialog is the wrong composition on a 390px screen.
 * Two shells are fine; two renderers of the same facts are not, so the facts are
 * derived here once and both shells render the result.
 */
import type { SuggestDetail, SuggestResult } from "../../lib/api/client";
import { fmtRating, fmtRuntimeMin } from "../watchlist/lib";
import { artTone } from "../library/lib";

export interface SuggestDetailView {
  title: string;
  /** Meta followed by genres — one pill list, exactly as the modal has always shown it. */
  chips: string[];
  /** "8.1 IMDb", "7.4 TMDB", or the honest "IMDb unavailable" when it is known to be missing. */
  scores: string[];
  overview: string;
  facts: Array<[string, string]>;
  /** Backdrop, else poster, else the card's own art, else "" (the tone takes over). */
  backdrop: string;
  /** `artTone` index (0–5) — a NUMBER, used as `art-${tone}`. */
  tone: number;
  /**
   * ⚠ True only when the DETAIL fetch failed — the row's own summary facts are still
   * shown, so the view degrades to "the card below still shows the basics" rather
   * than to an empty screen. `d.ok === false` is a list endpoint's "not configured"
   * answer arriving on a 200, not a transport failure.
   */
  failed: boolean;
}

/** How many genres a chip list shows before it stops being scannable. */
export const MAX_CHIPS_GENRES = 4;

/** How many cast members the "Starring" fact names. */
export const MAX_CAST_FACT = 5;

export function suggestDetailView(
  item: SuggestResult,
  d: SuggestDetail | undefined,
  isError = false,
): SuggestDetailView {
  const title = d?.title || item.title;
  // ⚠ The ITEM's media type is the fallback, not "Movie". A discovered series shows
  // this chip the instant the sheet opens, before /api/suggest/detail has answered —
  // so reading the label only off the detail would label every TV show a Movie for as
  // long as the request takes. (The desktop modal had this too; the phone made it
  // visible, because the phone is the surface that opens before the fetch.)
  const typeLabel = (d?.media_type ?? item.media_type) === "tv" ? "TV Series" : "Movie";
  const meta = [d?.year ?? item.year, d?.cert, d?.runtime ? fmtRuntimeMin(d.runtime) : "", typeLabel]
    .filter(Boolean)
    .map(String);
  const genres = (d?.genres || item.genres || []).slice(0, MAX_CHIPS_GENRES);

  const scores: string[] = [];
  if (d && d.imdb_rating > 0) scores.push(`★ ${fmtRating(d.imdb_rating)} IMDb`);
  else if (d?.imdb_id) scores.push("IMDb unavailable");
  if (d && d.tmdb_score > 0) scores.push(`★ ${fmtRating(d.tmdb_score)} TMDB`);

  const facts: Array<[string, string]> = [];
  if (d?.director) facts.push(["Director", d.director]);
  if (d?.cast?.length) facts.push(["Starring", d.cast.slice(0, MAX_CAST_FACT).join(" · ")]);
  if (d?.vote_count) facts.push(["Votes", Number(d.vote_count).toLocaleString()]);

  return {
    title,
    chips: [...meta, ...genres],
    scores,
    overview: d?.overview || item.overview || "No synopsis available yet.",
    facts,
    backdrop: d?.backdrop || d?.poster || item.backdrop || item.poster || "",
    tone: artTone(title),
    failed: isError || Boolean(d && d.ok === false),
  };
}
