import { useEffect, useMemo, useRef, useState } from "react";
import type { SearchHit, WatchlistEntry } from "../../lib/api/client";
import { useCardActions } from "../watchlist/actions";
import { useSearch, useWatchlist } from "../watchlist/api";
import { WatchlistDetail } from "../watchlist/WatchlistDetail";
import { entryForHit, resolveState, type ResolvedState } from "../watchlist/lib";
import { EmptyState } from "../watchlist/CardRow";

const DEBOUNCE_MS = 180;

/**
 * Search (LEGACY_PARITY_PLAN): dedicated page replacing the legacy header
 * combobox — same API (GET /api/search: watchlist + TMDB groups), debounced
 * input, ArrowUp/Down/Enter/Escape selection, per-row Download, row click →
 * the rich entry's detail modal (live hits open an ad-hoc stub entry).
 */
export function SearchView() {
  const { entries, stateFor } = useWatchlist();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const actions = useCardActions();
  const { data, isFetching, isError } = useSearch(debounced);
  const [sel, setSel] = useState(-1);
  const [detail, setDetail] = useState<{ entry: WatchlistEntry; state: ResolvedState } | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => setSel(-1), [data]);

  const hits = useMemo(() => {
    const local = data?.watchlist ?? [];
    const live = data?.tmdb ?? [];
    const merged = [...local, ...live];
    if (merged.length) return merged;
    // Local fallback over the live rich entries when the API search is empty
    // (parity with the legacy offline fallback over DATA).
    if (entries.length && debounced) {
      const needle = debounced.toLowerCase();
      return entries
        .filter((e) => {
          const hay = [e.title, e.director, e.category, e.year, (e.cast || []).join(" "), (e.genres || []).join(" ")]
            .join(" ")
            .toLowerCase();
          return hay.includes(needle);
        })
        .map(
          (e): SearchHit => ({
            title: e.title,
            year: e.year,
            type: e.type,
            imdbId: e.imdbId,
            tmdbId: e.tmdbId,
            poster: e.poster,
            inWatchlist: true,
            director: e.director,
            cast: e.cast,
            snippet: e.overview,
          }),
        );
    }
    return merged;
  }, [data, entries, debounced]);

  const openHit = (hit: SearchHit) => {
    const entry = entryForHit(entries, hit);
    if (entry) {
      // Live resolved state (resource + services) so actions/markers are truthful.
      setDetail({ entry, state: stateFor(entry) });
      return;
    }
    const stub: WatchlistEntry = {
      imdbId: hit.imdbId,
      tmdbId: hit.tmdbId ?? null,
      tvdbId: null,
      title: hit.title,
      year: hit.year ?? 0,
      type: hit.type === "tv" ? "tv" : "movie",
      category: "Other",
      genres: [],
      lang: "",
      cert: "",
      rt: null,
      imdb: null,
      tmdbScore: null,
      overview: hit.snippet || "",
      cast: hit.cast || [],
      director: hit.director || "",
      runtime: null,
      poster: hit.poster || "",
      backdrop: "",
      trailerId: "",
      trailerTitle: "",
      trailerUrl: `https://www.youtube.com/results?search_query=${encodeURIComponent(`${hit.title} trailer`)}`,
      added: "",
      source: "search",
    };
    setDetail({ entry: stub, state: resolveState(stub, null, true) });
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!hits.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSel((s) => Math.min(s + 1, hits.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSel((s) => Math.max(s - 1, -1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (sel >= 0 && hits[sel]) openHit(hits[sel]);
    } else if (e.key === "Escape") {
      setQ("");
      setDebounced("");
      inputRef.current?.blur();
    }
  };

  const noMatch = Boolean(debounced) && !isFetching && !hits.length;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-bold text-white">Search</h1>
        <div className="text-sm text-zinc-500">Search movies, shows, actors…</div>
      </div>

      <div className="relative">
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" aria-hidden="true">
          ⌕
        </span>
        <input
          ref={inputRef}
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Search movies, shows, actors…"
          autoComplete="off"
          aria-label="Search movies, shows, actors"
          role="combobox"
          aria-expanded={Boolean(debounced)}
          className="w-full rounded-xl border border-zinc-800 bg-zinc-900 py-2.5 pl-9 pr-4 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-amber-400/60"
        />
      </div>

      {isFetching && debounced ? <div className="text-sm text-zinc-500">Searching…</div> : null}

      {data && !data.tmdbKey && data.tmdb.length === 0 ? (
        <div className="text-xs text-zinc-600">
          Live TMDB search is off (no TMDB key) — results below are from your watchlist.
        </div>
      ) : null}

      {noMatch ? (
        <EmptyState title={`No matches for "${debounced}"`} sub="Try a title, actor or director." />
      ) : null}

      {hits.length ? (
        <div className="flex flex-col gap-2">
          {data?.watchlist?.length ? <GroupLabel>Watchlist</GroupLabel> : null}
          {hits.slice(0, data?.watchlist?.length || 0).map((hit, i) => (
            <SearchRow
              key={`wl-${hit.imdbId || hit.tmdbId}-${i}`}
              hit={hit}
              selected={sel === i}
              idx={i}
              onSelect={() => setSel(i)}
              onOpen={() => openHit(hit)}
              onDownload={() => {
                const entry = entryForHit(entries, hit);
                if (entry) actions.download(entry);
              }}
            />
          ))}
          {data?.tmdb?.length ? <GroupLabel>Live results (TMDB)</GroupLabel> : null}
          {hits.slice(data?.watchlist?.length || 0).map((hit, i) => {
            const idx = (data?.watchlist?.length || 0) + i;
            return (
              <SearchRow
                key={`tmdb-${hit.tmdbId ?? hit.imdbId}-${i}`}
                hit={hit}
                selected={sel === idx}
                idx={idx}
                onSelect={() => setSel(idx)}
                onOpen={() => openHit(hit)}
                onDownload={() => {
                  const stub: WatchlistEntry = {
                    imdbId: hit.imdbId,
                    tmdbId: hit.tmdbId ?? null,
                    tvdbId: null,
                    title: hit.title,
                    year: hit.year ?? 0,
                    type: hit.type === "tv" ? "tv" : "movie",
                    category: "Other",
                    genres: [],
                    lang: "",
                    cert: "",
                    rt: null,
                    imdb: null,
                    tmdbScore: null,
                    overview: hit.snippet || "",
                    cast: hit.cast || [],
                    director: hit.director || "",
                    runtime: null,
                    poster: hit.poster || "",
                    backdrop: "",
                    trailerId: "",
                    trailerTitle: "",
                    trailerUrl: "",
                    added: "",
                    source: "search",
                  };
                  actions.download(stub);
                }}
              />
            );
          })}
        </div>
      ) : null}

      {isError && debounced ? (
        <EmptyState title="Search failed" sub="Could not reach the search API. Try again shortly." />
      ) : null}

      {detail ? (
        <WatchlistDetail
          entry={detail.entry}
          state={detail.state}
          onClose={() => setDetail(null)}
          onDownload={actions.download}
          onPlayInRkm={(entry, itemId) => {
            setDetail(null);
            actions.playInRkm(entry, itemId);
          }}
          onWatchLink={actions.watchLink}
        />
      ) : null}
    </div>
  );
}

function GroupLabel({ children }: { children: string }) {
  return (
    <div className="pt-2 text-[11px] font-bold uppercase tracking-widest text-zinc-600">{children}</div>
  );
}

function SearchRow({
  hit,
  selected,
  idx,
  onSelect,
  onOpen,
  onDownload,
}: {
  hit: SearchHit;
  selected: boolean;
  idx: number;
  onSelect: () => void;
  onOpen: () => void;
  onDownload: () => void;
}) {
  return (
    <div
      role="option"
      aria-selected={selected}
      data-idx={idx}
      onMouseEnter={onSelect}
      onClick={onOpen}
      className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2 transition ${
        selected ? "border-amber-400/50 bg-zinc-800/80" : "border-zinc-800 bg-zinc-900/40 hover:bg-zinc-900"
      }`}
    >
      {hit.poster ? (
        <img
          src={hit.poster}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={(e) => ((e.currentTarget as HTMLImageElement).style.visibility = "hidden")}
          className="h-14 w-10 shrink-0 rounded object-cover"
        />
      ) : (
        <div className="flex h-14 w-10 shrink-0 items-center justify-center rounded bg-zinc-800 text-lg">🎬</div>
      )}
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-zinc-100">
          {hit.title} {hit.year ? <span className="font-normal text-zinc-500">({hit.year})</span> : null}
          {hit.inWatchlist ? <span className="ml-2 text-[10px] font-bold text-emerald-400">In watchlist</span> : null}
        </div>
        <div className="truncate text-xs text-zinc-500">
          {hit.type === "tv" ? "TV Series" : "Movie"}
          {hit.director ? ` · ${hit.director}` : ""}
          {hit.cast?.length ? ` · ${hit.cast.join(", ")}` : ""}
        </div>
      </div>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onDownload();
        }}
        className="shrink-0 rounded-full bg-amber-400 px-3 py-1 text-xs font-bold text-black hover:bg-amber-300"
      >
        ↓ Download
      </button>
    </div>
  );
}
