import {
  useContinueWatching,
  useLibraryItems,
  useLibraryRecent,
  useRecentlyWatched,
  useScanLibrary,
} from "./api";
import { ContinueWatchingRow } from "./ContinueWatchingRow";
import { MediaCard } from "./MediaCard";
import { useLibraryOutlet } from "./LibraryLayout";
import { SectionHeader } from "../../components/ui/SectionHeader";
import { EmptyState } from "../watchlist/CardRow";
import { toast } from "../watchlist/toast";
import { Icon } from "../../components/ui/Icon";
import { api } from "../../lib/api/client";
import {
  artTone,
  episodeItemCode,
  fmtRuntime,
  isContinueWatching,
  isEpisodeItem,
  isSeries,
  pickHomeHero,
  posterUrl,
  resumePercent,
} from "./lib";
import { useState } from "react";
import type { MediaItem } from "../../lib/api/client";

/** Poster-rail helper shared by the Recently Added / Recently Played rows. */
type CardHandlers = {
  onQuickPlay: (item: MediaItem) => void;
  onOpenDetail: (item: MediaItem) => void;
  onToggleWatched?: (item: MediaItem) => void;
};

function PosterRail({ items, handlers }: { items: MediaItem[]; handlers: CardHandlers }) {
  return (
    <div className="no-scrollbar snap-rail flex gap-3.5 overflow-x-auto pb-1.5">
      {items.map((item) => (
        <MediaCard key={item.item_id} item={item} {...handlers} />
      ))}
    </div>
  );
}

function HeroSkeleton() {
  return (
    <div aria-hidden="true" className="skeleton relative aspect-[21/10] w-full overflow-hidden rounded-2xl">
      <div className="absolute inset-y-0 left-0 w-full max-w-xl p-10 sm:p-14">
        <div className="skeleton h-3 w-36 rounded" />
        <div className="skeleton mt-5 h-12 w-4/5 rounded-lg" />
        <div className="skeleton mt-3 h-4 w-2/5 rounded" />
        <div className="mt-7 flex gap-3">
          <div className="skeleton h-11 w-32 rounded-lg" />
          <div className="skeleton h-11 w-28 rounded-lg" />
        </div>
      </div>
    </div>
  );
}

function RailSkeletons() {
  return (
    <div aria-hidden="true" className="flex flex-col gap-10">
      {[0, 1].map((r) => (
        <div key={r}>
          <div className="skeleton mb-3.5 h-5 w-44 rounded" />
          <div className="flex gap-3.5">
            {[0, 1, 2, 3, 4].map((c) => (
              <div key={c} className="skeleton aspect-[2/3] w-40 shrink-0 rounded-xl" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * /library/home — the redesigned Home (NEW_UX spec §8–10, §31, §64): an
 * intelligent personal dashboard. The first viewport is a cinematic hero
 * (Continue Watching first, else Recently Added), then Continue Watching
 * landscape cards, Recently Played and Recently Added poster rails. Technical
 * source labels (provider names) are gone from the primary UX.
 */
export function LibraryHomeView() {
  const items = useLibraryItems();
  const continueWatching = useContinueWatching();
  const recentlyWatched = useRecentlyWatched();
  const recent = useLibraryRecent();
  const scan = useScanLibrary();
  const { quickPlay, openItem, toggleWatched } = useLibraryOutlet();

  const all = items.data?.items ?? [];
  const cwItems = (continueWatching.data?.items ?? []).filter(isContinueWatching);
  const recentlyAdded = (recent.data?.recent ?? []).filter((i) => Boolean(i.item_id));
  const hero = pickHomeHero(cwItems, recentlyAdded, all);
  const heroIsCw = Boolean(hero && cwItems.some((i) => i.item_id === hero.item_id));

  const cardProps: CardHandlers = {
    onQuickPlay: quickPlay,
    onOpenDetail: openItem,
    onToggleWatched: toggleWatched,
  };

  const runScan = () => {
    scan.mutate(undefined, {
      onSuccess: () => toast("Library scan complete", "New titles will appear as they are discovered."),
      onError: () => toast("Scan failed", "Could not reach the scan job — check the backend.", "err"),
    });
  };

  const firstLoad = items.isLoading && all.length === 0;
  if (firstLoad) {
    return (
      <div className="flex flex-col gap-10">
        <HeroSkeleton />
        <RailSkeletons />
      </div>
    );
  }

  const unavailable = items.isError || (!items.isLoading && !items.data?.provider && all.length === 0);

  if (unavailable) {
    return (
      <EmptyState
        title={items.isError ? "Something went wrong" : "No media server connected"}
        sub={
          items.isError
            ? "We couldn't load your library."
            : "Connect Jellyfin, Plex or Emby in the repo .env, then redeploy the stack."
        }
      />
    );
  }

  if (all.length === 0 && !hero) {
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center gap-5 py-24 text-center">
        <div className="grid h-16 w-16 place-items-center rounded-2xl bg-surface-2 text-zinc-500 ring-1 ring-white/[.06]">
          <Icon name="film" size={26} />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-100">Your library is empty</h1>
          <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-zinc-500">
            Add movies and shows to your media folders, then scan your library to discover them.
          </p>
        </div>
        <button
          type="button"
          onClick={runScan}
          disabled={scan.isPending}
          className="inline-flex items-center gap-2 rounded-lg bg-accent px-5 py-2.5 text-sm font-bold text-black transition hover:bg-accent-hover disabled:opacity-60"
        >
          <Icon name="scan" size={16} />
          {scan.isPending ? "Scanning…" : "Scan Library"}
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-10">
      {hero ? (
        <HomeHero
          key={hero.item_id}
          item={hero}
          cw={heroIsCw}
          onPrimary={quickPlay}
          onDetails={openItem}
          scan={runScan}
          scanPending={scan.isPending}
        />
      ) : null}

      {scan.isError && !scan.isPending && (
        <p className="text-xs text-red-400">Scan failed — check the backend, then try again.</p>
      )}

      {cwItems.length > 0 && (
        <ContinueWatchingRow
          items={cwItems}
          onQuickPlay={quickPlay}
          onOpenDetail={openItem}
        />
      )}

      {recentlyWatched.data && recentlyWatched.data.items.length > 0 && (
        <section aria-label="Recently played">
          <SectionHeader title="Recently Played" />
          <PosterRail items={recentlyWatched.data.items.slice(0, 14)} handlers={cardProps} />
        </section>
      )}

      {recentlyAdded.length > 0 && (
        <section aria-label="Recently added">
          <SectionHeader title="Recently Added" seeAllLabel="See library" />
          <PosterRail items={recentlyAdded.slice(0, 16)} handlers={cardProps} />
        </section>
      )}

      {items.isLoading && <p className="text-xs text-zinc-500">Loading the rest of your library…</p>}
    </div>
  );
}

/**
 * Cinematic hero (spec §9): full-width backdrop, layered gradients so the
 * artwork blends into the UI, eyebrow + title + meta + progress + actions.
 */
function HomeHero({
  item,
  cw,
  onPrimary,
  onDetails,
  scan,
  scanPending,
}: {
  item: MediaItem;
  /** True when this title came from Continue Watching (drives the eyebrow). */
  cw: boolean;
  onPrimary: (item: MediaItem) => void;
  onDetails: (item: MediaItem) => void;
  scan: () => void;
  scanPending: boolean;
}) {
  // Remounted per title (key=item_id) — the fallback state resets naturally.
  const [backdropFailed, setBackdropFailed] = useState(false);
  const episode = isEpisodeItem(item);
  const series = isSeries(item);
  const percent = resumePercent(item);
  const epCode = episodeItemCode(item);
  const title = episode && item.episode?.series_name ? item.episode.series_name : item.title;
  const meta = [
    item.year ? String(item.year) : "",
    episode && item.episode ? `S${item.episode.season} E${item.episode.number}` : "",
    ...(item.genres ?? []).slice(0, 2),
  ]
    .filter(Boolean)
    .join(" · ");
  const runtimeLeft =
    !series && !episode && percent > 0 && item.runtime && item.runtime > item.playback_position!
      ? fmtRuntime(item.runtime - item.playback_position!)
      : "";
  const showProgress = percent > 0 && (runtimeLeft || episode);
  const backdropUrl = api.backdropUrl(item.item_id, 1600);
  const poster = posterUrl(item);
  const primaryLabel = episode
    ? `${percent > 0 ? "Resume" : "Play"} ${epCode ?? ""}`.trim()
    : series
      ? "Explore Episodes"
      : percent > 0
        ? "Resume"
        : "Play";
  const primaryGoesToPage = series;

  return (
    <section
      aria-label={`Continue watching ${title}`}
      className="relative -mx-4 overflow-hidden rounded-b-2xl sm:-mx-6 lg:-mx-8 xl:-mx-10"
    >
      <div className="relative aspect-[21/10] min-h-[340px] w-full sm:min-h-[420px] lg:min-h-[470px]">
        {/* Seeded art base + poster/backdrop layers (each degrades gracefully). */}
        <div aria-hidden="true" className={`absolute inset-0 art-${artTone(title)}`} />
        {!backdropFailed ? (
          <img
            src={backdropUrl}
            alt=""
            referrerPolicy="no-referrer"
            onError={() => setBackdropFailed(true)}
            className="absolute inset-0 h-full w-full object-cover"
          />
        ) : poster ? (
          <img
            src={poster}
            alt=""
            referrerPolicy="no-referrer"
            className="absolute inset-0 h-full w-full object-cover object-[center_22%]"
          />
        ) : null}

        {/* Spec §9 gradient blends */}
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-gradient-to-r from-canvas via-canvas/85 via-35% to-transparent"
        />
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-gradient-to-t from-canvas via-transparent to-black/30"
        />
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-gradient-to-b from-canvas/70 via-transparent to-canvas/40"
        />

        {/* Copy */}
        <div className="absolute inset-x-0 bottom-0 max-w-2xl p-6 sm:p-10 lg:p-12">
          <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.18em] text-accent">
            <Icon name={episode ? "tv" : "play"} size={13} filled={!episode} />
            {cw ? (episode ? "Continue episode" : "Continue Watching") : "Recently Added"}
          </div>
          <h1 className="mt-2.5 line-clamp-2 text-4xl font-bold leading-[1.02] tracking-[-0.02em] text-white drop-shadow-[0_4px_24px_rgba(0,0,0,.6)] sm:text-6xl">
            {title}
          </h1>
          {meta && <div className="mt-3 text-[13px] font-medium text-zinc-300">{meta}</div>}
          {showProgress && (
            <div className="mt-4 flex max-w-xs items-center gap-3">
              <div className="h-[3px] flex-1 rounded-full bg-white/15">
                <div className="h-full rounded-full bg-accent" style={{ width: `${percent}%` }} />
              </div>
              <span className="text-[11px] font-semibold tabular-nums text-zinc-300">
                {percent}%{runtimeLeft ? ` · ${runtimeLeft} left` : ""}
              </span>
            </div>
          )}
          <div className="mt-6 flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              onClick={() => (primaryGoesToPage ? onDetails(item) : onPrimary(item))}
              className="inline-flex h-11 items-center gap-2 rounded-[10px] bg-accent px-5 text-sm font-bold text-black shadow-lg shadow-accent/20 transition hover:bg-accent-hover"
            >
              <Icon name="play" size={15} filled />
              {primaryLabel}
            </button>
            {!primaryGoesToPage && (
              <button
                type="button"
                onClick={() => onDetails(item)}
                className="inline-flex h-11 items-center gap-2 rounded-[10px] border border-white/10 bg-white/[.09] px-4 text-sm font-semibold text-zinc-100 backdrop-blur transition hover:bg-white/[.15]"
              >
                Details
              </button>
            )}
          </div>
        </div>

        {/* Scan — subtle, never dashboard-y (spec §49). */}
        <button
          type="button"
          onClick={scan}
          disabled={scanPending}
          title="Scan Library"
          aria-label="Scan Library"
          className="absolute right-4 top-4 z-10 inline-flex h-9 items-center gap-2 rounded-full border border-white/10 bg-black/35 px-3.5 text-xs font-semibold text-zinc-200 backdrop-blur-md transition hover:bg-black/60 hover:text-white disabled:opacity-60 sm:right-6 sm:top-5"
        >
          <Icon name="scan" size={15} className={scanPending ? "animate-spin" : ""} />
          <span className="hidden sm:inline">{scanPending ? "Scanning…" : "Scan Library"}</span>
        </button>
      </div>
    </section>
  );
}
