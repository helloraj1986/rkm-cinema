import { useMemo, useState } from "react";
import type { SuggestFilters, SuggestResult } from "../../lib/api/client";
import { SuggestCard } from "./SuggestCard";
import { useAddToWatchlist, useRequestMedia, useSuggestRun } from "../watchlist/api";
import { suggestHistoryLabel, suggestHistoryPush, SUGGEST_GENRES } from "../watchlist/lib";
import { toast } from "../watchlist/toast";
import { acquisitionToast, errorMessage } from "../watchlist/actions";
import { EmptyState } from "../watchlist/CardRow";
import { SuggestDetailModal } from "./SuggestDetailModal";

const HISTORY_KEY = "rkm_suggest_history";

function loadHistory(): SuggestFilters[] {
  try {
    return JSON.parse(window.localStorage.getItem(HISTORY_KEY) || "[]") as SuggestFilters[];
  } catch {
    return [];
  }
}

function saveHistory(list: SuggestFilters[]) {
  try {
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify(list));
  } catch {
    /* storage may be unavailable — non-fatal */
  }
}

/**
 * Suggest (LEGACY_PARITY_PLAN): TMDB discover by taste — type/genre/year/
 * rating/sort/count filters, Recent-search history chips (last 10 persisted),
 * result grid with Add-to-Watchlist / Download, whole-card click → the full
 * detail modal (IMDb rating + synopsis via /api/suggest/detail).
 */
export function SuggestView() {
  const run = useSuggestRun();
  const add = useAddToWatchlist();
  const request = useRequestMedia();
  const [filters, setFilters] = useState<SuggestFilters>(() => ({
    media_type: "all",
    genres: [],
    year_from: null,
    year_to: null,
    min_rating: 6.0,
    sort_by: "popularity.desc",
    count: 20,
  }));
  const [history, setHistory] = useState<SuggestFilters[]>(loadHistory);
  const [results, setResults] = useState<SuggestResult[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [detail, setDetail] = useState<SuggestResult | null>(null);

  const readInputs = (): SuggestFilters => ({
    media_type: filters.media_type,
    genres: [...filters.genres],
    year_from: filters.year_from,
    year_to: filters.year_to,
    min_rating: filters.min_rating,
    sort_by: filters.sort_by,
    count: filters.count,
  });

  const search = (snapshot: SuggestFilters) => {
    run.mutate(snapshot, {
      onSuccess: (resp) => {
        setResults(resp.results || []);
        const next = suggestHistoryPush(loadHistory(), snapshot);
        setHistory(next);
        saveHistory(next);
      },
      onError: (e) => toast("Suggest failed", errorMessage(e), "err", 6000),
    });
  };

  const toggleGenre = (g: string) => {
    setFilters((f) => ({
      ...f,
      genres: f.genres.includes(g) ? f.genres.filter((x) => x !== g) : [...f.genres, g],
    }));
  };

  const clear = () => {
    setFilters({
      media_type: "all",
      genres: [],
      year_from: null,
      year_to: null,
      min_rating: 6.0,
      sort_by: "popularity.desc",
      count: 20,
    });
    setResults([]);
  };

  const applyHistory = (h: SuggestFilters) => {
    setFilters({ ...h, genres: [...h.genres] });
    search({ ...h, genres: [...h.genres] });
  };

  const patchItem = (tmdbId: number, patch: Partial<SuggestResult>) =>
    setResults((rs) => rs.map((r) => (r.tmdb_id === tmdbId ? { ...r, ...patch } : r)));

  const handleAdd = (item: SuggestResult) => {
    setBusyId(item.tmdb_id);
    add.mutate(
      { tmdbId: item.tmdb_id, mediaType: item.media_type },
      {
        onSuccess: (resp) => {
          if (resp.ok) {
            patchItem(item.tmdb_id, { in_watchlist: true });
            toast("Added to watchlist", resp.title || item.title || "");
          } else {
            toast("Add failed", resp.message || "unknown error", "err");
          }
        },
        onError: (e) => toast("Add failed", errorMessage(e), "err"),
        onSettled: () => setBusyId(null),
      },
    );
  };

  const handleDownload = (item: SuggestResult) => {
    setBusyId(item.tmdb_id);
    add.mutate(
      { tmdbId: item.tmdb_id, mediaType: item.media_type },
      {
        onSuccess: (addResp) => {
          if (!addResp.ok && !addResp.already) {
            toast("Download failed", addResp.message || "Failed to add to watchlist", "err");
            setBusyId(null);
            return;
          }
          patchItem(item.tmdb_id, { in_watchlist: true });
          const mediaId = (item.media_type === "tv" ? "tv" : "movie") + ":tmdb:" + item.tmdb_id;
          request.mutate(mediaId, {
            onSuccess: (r) => {
              if (r.ok) toast("Download started", item.title || "");
              else toast("Download failed", r.message || r.state, "err", 6000);
            },
            onError: (e) => acquisitionToast(e, "Download failed"),
            onSettled: () => setBusyId(null),
          });
        },
        onError: (e) => {
          toast("Download failed", errorMessage(e), "err");
          setBusyId(null);
        },
      },
    );
  };

  const openDetail = (item: SuggestResult) => setDetail(item);

  const counts = useMemo(() => results.length, [results]);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-bold text-white">Suggest</h1>
        <div className="text-sm text-zinc-500">Discover movies & series by your taste</div>
      </div>

      {/* filters */}
      <div className="flex flex-col gap-3 rounded-2xl border border-zinc-800 bg-zinc-900/40 p-4">
        <FilterRow label="Type">
          {(["all", "movie", "tv"] as const).map((t) => (
            <Chip key={t} active={filters.media_type === t} onClick={() => setFilters((f) => ({ ...f, media_type: t }))}>
              {t === "all" ? "All" : t === "movie" ? "Movies" : "TV Shows"}
            </Chip>
          ))}
        </FilterRow>
        <FilterRow label="Genres">
          <div className="flex flex-wrap gap-1.5">
            {SUGGEST_GENRES.map((g) => (
              <Chip key={g} active={filters.genres.includes(g)} onClick={() => toggleGenre(g)}>
                {g}
              </Chip>
            ))}
          </div>
        </FilterRow>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <NumberField label="Year from" value={filters.year_from?.toString() ?? ""} placeholder="e.g. 2020" onChange={(v) => setFilters((f) => ({ ...f, year_from: v ? Number(v) : null }))} />
          <NumberField label="Year to" value={filters.year_to?.toString() ?? ""} placeholder="e.g. 2025" onChange={(v) => setFilters((f) => ({ ...f, year_to: v ? Number(v) : null }))} />
          <NumberField label="Min TMDB rating" value={filters.min_rating?.toString() ?? ""} placeholder="6.0" onChange={(v) => setFilters((f) => ({ ...f, min_rating: v ? Number(v) : 0 }))} />
          <label className="flex flex-col gap-1 text-xs font-semibold text-zinc-400">
            Sort by
            <select
              value={filters.sort_by}
              onChange={(e) => setFilters((f) => ({ ...f, sort_by: e.target.value }))}
              className="rounded-lg border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-200"
            >
              <option value="popularity.desc">Popularity</option>
              <option value="vote_average.desc">Rating</option>
              <option value="primary_release_date.desc">Release Date</option>
            </select>
          </label>
          <NumberField label="Results" value={String(filters.count ?? 20)} placeholder="20" onChange={(v) => setFilters((f) => ({ ...f, count: v ? Number(v) : 20 }))} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => search(readInputs())}
            disabled={run.isPending}
            className="rounded-full bg-amber-400 px-5 py-1.5 text-sm font-bold text-black hover:bg-amber-300 disabled:opacity-60"
          >
            {run.isPending ? "Searching…" : "⌕ Search"}
          </button>
          <button type="button" onClick={clear} className="rounded-full bg-zinc-800 px-4 py-1.5 text-sm font-semibold text-zinc-300 hover:bg-zinc-700">
            Clear filters
          </button>
          {counts ? <span className="text-xs text-zinc-500">{counts} result{counts === 1 ? "" : "s"}</span> : null}
        </div>

        {history.length ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-600">Recent</span>
            {history.map((h, i) => (
              <Chip key={i} active={JSON.stringify(h) === JSON.stringify(filters)} onClick={() => applyHistory(h)} title={suggestHistoryLabel(h)}>
                {suggestHistoryLabel(h)}
              </Chip>
            ))}
          </div>
        ) : null}
      </div>

      {/* results */}
      <div className="flex flex-wrap gap-3">
        {run.isPending ? (
          <div className="py-8 text-sm text-zinc-500">Searching TMDB…</div>
        ) : results.length ? (
          results.map((item) => (
            <SuggestCard
              key={item.tmdb_id}
              item={item}
              busy={busyId === item.tmdb_id}
              onAdd={() => handleAdd(item)}
              onDownload={() => handleDownload(item)}
              onOpen={() => openDetail(item)}
            />
          ))
        ) : run.isError ? (
          <EmptyState title="Search failed" sub="Could not reach TMDB through the API. Try again shortly." />
        ) : (
          <div className="py-6 text-sm text-zinc-500">
            Set your filters and hit <b>Search</b> to discover movies and series.
          </div>
        )}
      </div>

      {detail ? (
        <SuggestDetailModal
          item={detail}
          busy={busyId === detail.tmdb_id}
          onClose={() => setDetail(null)}
          onAdd={() => handleAdd(detail)}
          onDownload={() => handleDownload(detail)}
        />
      ) : null}
    </div>
  );
}

function FilterRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="w-14 shrink-0 text-[11px] font-bold uppercase tracking-widest text-zinc-600">{label}</span>
      {children}
    </div>
  );
}

export function Chip({
  active,
  onClick,
  children,
  title,
}: {
  active?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-pressed={active}
      className={`rounded-full px-2.5 py-1 text-xs font-semibold transition ${
        active ? "bg-amber-400 text-black" : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
      }`}
    >
      {children}
    </button>
  );
}

function NumberField({
  label,
  value,
  placeholder,
  onChange,
}: {
  label: string;
  value: string;
  placeholder?: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs font-semibold text-zinc-400">
      {label}
      <input
        type="number"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-200"
      />
    </label>
  );
}
