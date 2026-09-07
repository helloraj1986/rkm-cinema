import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useConfig } from "../settings/api";
import { useContinueWatching, useLibraryRecent } from "../library/api";
import { isContinueWatching } from "../library/lib";
import { MediaCard } from "../library/MediaCard";
import { EmptyState, CardRow } from "../watchlist/CardRow";
import { WatchCard } from "../watchlist/WatchCard";
import { WatchlistDetail } from "../watchlist/WatchlistDetail";
import { useCardActions } from "../watchlist/actions";
import { useWatchlist } from "../watchlist/api";
import {
  buildWatchlistRows,
  cardPrimaryAction,
  fmtRating,
  fmtRuntimeMin,
  pickHero,
  type HeroMode,
  type ResolvedState,
  type WatchlistEntry,
} from "../watchlist/lib";
import type { MediaItem } from "../../lib/api/client";

const HERO_ICON = "▶";

/**
 * Discover (LEGACY_PARITY_PLAN): hero (pickHero — auto/newest/random from
 * /api/config heroMode, localStorage override kept) + curated rows from
 * `buildWatchlistRows` + Continue Watching / Recently Added library rows +
 * a My Library strip. All actions share `useCardActions`.
 */
export function DiscoverView() {
  const navigate = useNavigate();
  const { entries, stateFor, isLoading, isError } = useWatchlist();
  const { data: cfg } = useConfig();
  const { data: cw } = useContinueWatching();
  const { data: lib } = useLibraryRecent();
  const actions = useCardActions();
  const [detail, setDetail] = useState<{ entry: WatchlistEntry; trailer?: boolean } | null>(null);

  const heroOverride = useMemo(() => {
    try {
      return window.localStorage.getItem("rkm_hero") || "";
    } catch {
      return "";
    }
  }, []);
  const heroMode: HeroMode = (heroOverride || cfg?.heroMode || "auto") as HeroMode;
  const hero = useMemo(() => pickHero(entries, heroMode), [entries, heroMode]);
  const rows = useMemo(() => buildWatchlistRows(entries), [entries]);

  const openEntry = (entry: WatchlistEntry, trailer = false) => setDetail({ entry, trailer });
  const continueItems = (cw?.items ?? []).filter(isContinueWatching);
  const recentItems = lib?.recent ?? [];

  if (isLoading && !entries.length) {
    return (
      <div className="flex flex-col gap-6" data-testid="discover-loading">
        <div className="h-72 animate-pulse rounded-2xl bg-zinc-900" />
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex gap-3">
            {[0, 1, 2, 3, 4].map((j) => (
              <div key={j} className="h-56 w-40 animate-pulse rounded-lg bg-zinc-900" />
            ))}
          </div>
        ))}
      </div>
    );
  }
  if (isError && !entries.length) {
    return <EmptyState title="RKM Cinema could not load" sub="Could not reach the watchlist API. Check the api container, then reload." />;
  }

  return (
    <div className="flex flex-col gap-8">
      {!entries.length ? (
        <EmptyState
          title="Your watchlist is empty"
          sub="The daily recommendation engine will bring fresh picks — or open Suggest to discover movies and series by your taste."
        />
      ) : null}

      {hero ? (
        <Hero entry={hero} state={stateFor(hero)} actions={actions} onOpen={openEntry} />
      ) : null}

      <div className="flex flex-col gap-8">
        {rows.map((row) => (
          <CardRow key={row.id} title={row.title} onSeeAll={() => navigate("/watchlist")}>
            {row.items.map((e) => (
              <WatchCard
                key={`${row.id}-${e.tmdbId ?? e.imdbId}`}
                entry={e}
                state={stateFor(e)}
                onOpen={openEntry}
                onDownload={actions.download}
                onPlayInRkm={actions.playInRkm}
                onWatchLink={actions.watchLink}
                onTrailer={(en) => openEntry(en, true)}
              />
            ))}
          </CardRow>
        ))}

        {continueItems.length ? (
          <CardRow title="Continue Watching">
            {continueItems.map((item: MediaItem) => (
              <MediaCard
                key={item.item_id}
                item={item}
                onQuickPlay={actions.quickPlayLibrary}
                onOpenDetail={actions.openLibraryItem}
                onToggleWatched={actions.toggleWatched}
              />
            ))}
          </CardRow>
        ) : null}

        {recentItems.length ? (
          <CardRow title="Recently Added to Library">
            {recentItems.map((item: MediaItem) => (
              <MediaCard
                key={item.item_id}
                item={item}
                onQuickPlay={actions.quickPlayLibrary}
                onOpenDetail={actions.openLibraryItem}
                onToggleWatched={actions.toggleWatched}
              />
            ))}
          </CardRow>
        ) : null}

        <LibraryStrip lib={lib} onOpen={() => navigate("/library/home")} />
      </div>

      {detail ? (
        <WatchlistDetail
          entry={detail.entry}
          state={stateFor(detail.entry)}
          openTrailer={detail.trailer}
          onClose={() => setDetail(null)}
          onDownload={actions.download}
          onPlayInRkm={actions.playInRkm}
          onWatchLink={actions.watchLink}
        />
      ) : null}
    </div>
  );
}

function Hero({
  entry,
  state,
  actions,
  onOpen,
}: {
  entry: WatchlistEntry;
  state: ResolvedState;
  actions: ReturnType<typeof useCardActions>;
  onOpen: (e: WatchlistEntry, trailer?: boolean) => void;
}) {
  const action = cardPrimaryAction(entry, state);
  const meta = [entry.year, entry.lang, entry.cert, entry.runtime ? fmtRuntimeMin(entry.runtime) : ""].filter(Boolean);
  const genres = (entry.genres || []).slice(0, 3);
  const scores: string[] = [];
  if (entry.imdb) scores.push(`★ ${fmtRating(entry.imdb)} IMDb`);
  if (entry.imdb === 0 && !scores.length) scores.push("IMDb n/a");
  if (entry.rt) scores.push(`${entry.rt}% RT`);
  const bg = entry.backdrop || entry.poster;

  return (
    <section className="relative overflow-hidden rounded-2xl border border-zinc-800" aria-label={`Featured: ${entry.title}`}>
      {bg ? (
        <img src={bg} alt="" referrerPolicy="no-referrer" className="absolute inset-0 h-full w-full object-cover" />
      ) : (
        <div className="absolute inset-0 bg-gradient-to-br from-zinc-800 to-zinc-950" />
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-zinc-950 via-zinc-950/55 to-zinc-950/20" />
      <div className="relative max-w-3xl px-6 py-16 sm:px-10 sm:py-20">
        <div className="text-xs font-bold uppercase tracking-[0.2em] text-amber-300">Featured pick</div>
        <h1 className="mt-2 text-4xl font-black tracking-tight text-white sm:text-5xl">{entry.title}</h1>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {[...meta, ...genres].map((m) => (
            <span key={m} className="rounded-full bg-black/50 px-2.5 py-0.5 text-xs text-zinc-200 ring-1 ring-white/10">
              {m}
            </span>
          ))}
        </div>
        {scores.length ? (
          <div className="mt-2.5 flex flex-wrap gap-3 text-sm font-semibold text-amber-200">
            {scores.map((s) => (
              <span key={s}>{s}</span>
            ))}
          </div>
        ) : null}
        {entry.overview ? (
          <p className="mt-3 line-clamp-3 max-w-2xl text-sm leading-relaxed text-zinc-300">{entry.overview}</p>
        ) : null}
        <div className="mt-5 flex flex-wrap gap-2">
          <PrimaryHeroAction action={action} entry={entry} onOpen={onOpen} actions={actions} />
          {entry.trailerId ? (
            <button
              type="button"
              onClick={() => onOpen(entry, true)}
              className="rounded-full bg-white/10 px-5 py-2 text-sm font-bold text-white ring-1 ring-white/25 backdrop-blur hover:bg-white/20"
            >
              {HERO_ICON} Watch Trailer
            </button>
          ) : (
            <a
              href={`https://www.youtube.com/results?search_query=${encodeURIComponent(`${entry.title} trailer`)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-full bg-white/10 px-5 py-2 text-sm font-bold text-white ring-1 ring-white/25 backdrop-blur hover:bg-white/20"
            >
              Search YouTube
            </a>
          )}
        </div>
      </div>
    </section>
  );
}

function PrimaryHeroAction({
  action,
  entry,
  onOpen,
  actions,
}: {
  action: ReturnType<typeof cardPrimaryAction>;
  entry: WatchlistEntry;
  onOpen: (e: WatchlistEntry, trailer?: boolean) => void;
  actions: ReturnType<typeof useCardActions>;
}) {
  if (action.type === "play-rkm") {
    return (
      <button
        type="button"
        onClick={() => actions.playInRkm(entry, action.itemId)}
        className="rounded-full bg-amber-400 px-5 py-2 text-sm font-bold text-black hover:bg-amber-300"
      >
        {HERO_ICON} {action.label}
      </button>
    );
  }
  if (action.type === "watch-link") {
    return (
      <button
        type="button"
        onClick={() => actions.watchLink(entry, action.url)}
        className="rounded-full bg-violet-500 px-5 py-2 text-sm font-bold text-white hover:bg-violet-400"
      >
        {HERO_ICON} {action.label}
      </button>
    );
  }
  if (action.type === "download") {
    return (
      <button
        type="button"
        onClick={() => actions.download(entry)}
        className="rounded-full bg-amber-400 px-5 py-2 text-sm font-bold text-black hover:bg-amber-300"
      >
        ↓ Download
      </button>
    );
  }
  if (action.type === "requested") {
    return (
      <button type="button" disabled className="rounded-full bg-sky-600/80 px-5 py-2 text-sm font-bold text-white">
        ✓ Requested
      </button>
    );
  }
  if (action.type === "downloading") {
    return (
      <button type="button" disabled className="rounded-full bg-sky-600/80 px-5 py-2 text-sm font-bold text-white">
        ↓ Downloading {action.progress}%
      </button>
    );
  }
  if (action.type === "available") {
    return (
      <button type="button" disabled className="rounded-full bg-emerald-600/80 px-5 py-2 text-sm font-bold text-white">
        ✓ Available
      </button>
    );
  }
  return (
    <button type="button" disabled className="rounded-full bg-zinc-700/80 px-5 py-2 text-sm font-bold text-zinc-400">
      Unavailable
    </button>
  );
}

/** Legacy "My Library" strip — counts + a door into /library/home. */
function LibraryStrip({
  lib,
  onOpen,
}: {
  lib: { available?: boolean; counts?: Record<string, number>; server?: string | null } | undefined;
  onOpen: () => void;
}) {
  if (!lib?.available) {
    return (
      <section className="flex flex-col gap-2">
        <h2 className="flex items-center gap-2 text-base font-semibold text-zinc-100">
          <span className="inline-block h-4 w-1 rounded-full bg-amber-400" aria-hidden="true" />
          My Library
        </h2>
        <div className="rounded-xl border border-dashed border-zinc-800 px-6 py-8 text-center">
          <div className="text-3xl" aria-hidden="true">
            📚
          </div>
          <h3 className="mt-2 font-semibold text-zinc-200">Library preview</h3>
          <p className="mx-auto mt-1 max-w-md text-sm text-zinc-500">
            Connect a library backend (PLEX_URL/PLEX_TOKEN, EMBY_URL/EMBY_API_KEY, or JELLYFIN_URL/JELLYFIN_API_KEY) and
            your library counts and recent additions appear here.
          </p>
        </div>
      </section>
    );
  }
  const counts = lib.counts ?? {};
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-end justify-between pr-1">
        <h2 className="flex items-center gap-2 text-base font-semibold text-zinc-100">
          <span className="inline-block h-4 w-1 rounded-full bg-amber-400" aria-hidden="true" />
          My Library · {lib.server || "Media server"}
        </h2>
        <button
          type="button"
          onClick={onOpen}
          className="text-xs font-semibold text-zinc-400 hover:text-amber-300"
          aria-label="Open My Library"
        >
          Open › <span className="text-zinc-500">{counts.movie || 0} films · {counts.show || 0} shows</span>
        </button>
      </div>
      <div className="flex gap-3">
        <div className="flex-1 rounded-xl border border-zinc-800 bg-zinc-900/60 px-5 py-4">
          <div className="text-2xl font-black text-white">{counts.movie || 0}</div>
          <div className="text-xs uppercase tracking-wide text-zinc-500">Films</div>
        </div>
        <div className="flex-1 rounded-xl border border-zinc-800 bg-zinc-900/60 px-5 py-4">
          <div className="text-2xl font-black text-white">{counts.show || 0}</div>
          <div className="text-xs uppercase tracking-wide text-zinc-500">Series</div>
        </div>
      </div>
    </section>
  );
}
