import { describe, expect, it } from "vitest";
import type { SuggestDetail, SuggestResult } from "../../lib/api/client";
import { MAX_CAST_FACT, MAX_CHIPS_GENRES, suggestDetailView } from "./detail";

const item: SuggestResult = {
  tmdb_id: 12259,
  title: "Sholay",
  year: 1975,
  media_type: "movie",
  tmdb_score: 7.4,
  vote_count: 900,
  genres: ["Action", "Drama", "Adventure", "Comedy", "Romance"],
  overview: "Two friends, their village, and a bandit.",
  poster: "/sholay.jpg",
  backdrop: "/sholay-bg.jpg",
  in_watchlist: false,
  in_library: false,
};

const detail: SuggestDetail = {
  ok: true,
  id: 12259,
  media_type: "movie",
  title: "Sholay",
  year: 1975,
  overview: "Full synopsis from TMDB.",
  genres: ["Action", "Drama"],
  runtime: 204,
  cert: "PG",
  cast: ["A", "B", "C", "D", "E", "F", "G"],
  director: "Ramesh Sippy",
  tmdb_score: 7.4,
  vote_count: 12345,
  poster: "/p2.jpg",
  backdrop: "/bg2.jpg",
  imdb_id: "tt0073707",
  imdb_rating: 8.1,
};

describe("suggest detail view (the fix for 'no details when I tap a title I do not own')", () => {
  it("renders the moment the row is tapped, BEFORE the detail request answers", () => {
    // ⚠ THE REGRESSION. A discovered title has no library page, so the sheet has to
    // show the row's own facts while /api/suggest/detail is still in flight. A view
    // that needed the response would open an empty sheet on a slow link — which is
    // indistinguishable, to the person tapping, from the bug this replaced.
    const v = suggestDetailView(item, undefined);
    expect(v.title).toBe("Sholay");
    expect(v.overview).toBe(item.overview);
    expect(v.chips).toContain("Movie");
    expect(v.backdrop).toBe("/sholay-bg.jpg");
    expect(v.failed).toBe(false);
  });

  it("prefers the full metadata once it arrives", () => {
    const v = suggestDetailView(item, detail);
    expect(v.overview).toBe("Full synopsis from TMDB.");
    expect(v.backdrop).toBe("/bg2.jpg");           // the detail's art wins
    expect(v.facts).toContainEqual(["Director", "Ramesh Sippy"]);
    expect(v.chips).toContain("PG");
    // ⚠ The "★ " prefix is part of the VALUE — the component strips it at render, so
    // the view model stays the single source of what the string says.
    expect(v.scores).toContainEqual("★ 8.1 IMDb");
    expect(v.scores).toContainEqual("★ 7.4 TMDB");
  });

  it("keeps the chip list scannable", () => {
    const v = suggestDetailView(item, undefined);
    const genres = v.chips.filter((c) => item.genres.includes(c));
    expect(genres).toHaveLength(MAX_CHIPS_GENRES);
    expect(v.chips).toContain("Movie");            // meta still leads
  });

  it("says IMDb is unavailable rather than showing a zero", () => {
    // The id proves a rating EXISTS; a 0 means we could not fetch it. Showing
    // "★ 0.0 IMDb" would be a wrong fact, and hiding it would be a missing one.
    const v = suggestDetailView(item, { ...detail, imdb_rating: 0 });
    expect(v.scores).toContainEqual("IMDb unavailable");
    expect(v.scores.some((s) => s.includes("0.0"))).toBe(false);
  });

  it("trims the cast fact instead of printing the whole list", () => {
    const v = suggestDetailView(item, detail);
    const starring = v.facts.find(([k]) => k === "Starring")?.[1] ?? "";
    expect(starring.split(" · ")).toHaveLength(MAX_CAST_FACT);
  });

  it("degrades to the row's basics instead of an empty sheet when the fetch fails", () => {
    for (const v of [
      suggestDetailView(item, undefined, true),               // transport error
      suggestDetailView(item, { ...detail, ok: false }),      // a 200 saying "not configured"
    ]) {
      expect(v.failed).toBe(true);
      expect(v.title).toBe("Sholay");                         // the facts are still there
      expect(v.overview).toBeTruthy();
    }
  });

  it("falls back to the card's own art, and then to the seeded tone", () => {
    const noArt = { ...item, backdrop: "", poster: "" };
    expect(suggestDetailView(noArt, undefined).backdrop).toBe("");
    expect(suggestDetailView(noArt, undefined).tone).toBeGreaterThanOrEqual(0);
    expect(suggestDetailView({ ...item, backdrop: "" }, undefined).backdrop).toBe("/sholay.jpg");
  });

  it("labels a series as a series even BEFORE the detail arrives", () => {
    // ⚠ Caught by this test. The label used to come only off the detail payload, so a
    // discovered TV show read "Movie" for as long as the request took — and the phone
    // is the surface that shows the chip before the fetch answers.
    expect(suggestDetailView({ ...item, media_type: "tv" }, undefined).chips).toContain("TV Series");
    expect(suggestDetailView(item, undefined).chips).toContain("Movie");
  });
});
