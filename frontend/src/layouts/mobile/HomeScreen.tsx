import { useState } from "react";
import { Icon } from "../../components/ui/Icon";
import { SectionHeader } from "../../components/ui/SectionHeader";
import { ContinueWatchingRow } from "../../features/library/ContinueWatchingRow";
import { PosterRail, type CardHandlers } from "../../features/library/PosterRail";
import { useHomeRows } from "../../features/library/useHomeRows";
import { useLibraryOutlet } from "../../features/library/LibraryLayout";
import { useScanLibrary } from "../../features/library/api";
import { useCurrentProfile } from "../../features/auth/useCurrentProfile";
import { mayScanLibrary } from "../../features/auth/lib";
import {
  artTone,
  episodeItemCode,
  fmtRuntime,
  heroEyebrow,
  heroPrimaryLabel,
  isEpisodeItem,
  isSeries,
  NO_PROVIDER_SUB,
  NO_PROVIDER_TITLE,
  posterUrl,
  resumePercent,
  scanFailure,
} from "../../features/library/lib";
import { toast } from "../../features/watchlist/toast";
import { api } from "../../lib/api/client";

/**
 * `/library/home` on a PHONE (MOBILE_FIRST_UI_PLAN §3.1, phase M3) — the same page the desktop
 * renders, laid out for a held device.
 *
 * ⚠ What is shared and what is not. The DATA is `useHomeRows()` — the desktop Home's own view model
 * (extraction E4), so the two Homes cannot disagree about what Continue Watching means, how long a
 * rail is, or which title becomes the hero. The RULES are `lib.ts` — the hero's eyebrow and its
 * primary label are functions (M3), not strings written twice. The RAIL is `PosterRail` (E9). Only
 * the SHAPE of this page is new: a full-bleed backdrop, a thumb-reachable primary, and rails that
 * scroll sideways because a rail is the one place sideways movement is right.
 *
 * ⚠ The hero is deliberately NOT the desktop hero component. That one is built around a 21:10
 * letterbox with a left-to-right gradient for a wide window, and its copy column is anchored
 * bottom-left; on a 390px screen that composition is mostly empty image. This one is 4:3 with a
 * bottom-up gradient, the copy under the art, and one full-width primary — the phone's own
 * composition, from the same data and the same rules.
 */
export function HomeScreen() {
  const rows = useHomeRows();
  const { quickPlay, openItem, toggleWatched } = useLibraryOutlet();
  const scan = useScanLibrary();
  const isAdmin = useCurrentProfile()?.is_admin;
  const [backdropFailed, setBackdropFailed] = useState(false);

  const mayScan = mayScanLibrary(isAdmin);
  const scanning = scan.isPending;

  // ⚠ The outlet's own handlers, not re-shaped ones: `quickPlay` knows how a movie and an episode
  // start (they are not the same call), and this screen has no business knowing that.
  const handlers: CardHandlers = {
    onQuickPlay: quickPlay,
    onOpenDetail: openItem,
    onToggleWatched: toggleWatched,
  };

  // ---- the three query states the desktop Home also has, in the same order ----------------------
  if (rows.items.isLoading) {
    return (
      <div className="flex flex-col gap-5">
        <div className="skeleton -mx-4 aspect-[4/3] rounded-b-2xl" />
        {[0, 1].map((i) => (
          <div key={i} className="flex flex-col gap-3">
            <div className="skeleton h-4 w-32 rounded" />
            <div className="flex gap-3.5">
              {[0, 1, 2].map((j) => (
                <div key={j} className="skeleton aspect-[2/3] w-28 shrink-0 rounded-[10px]" />
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  const provider = rows.items.data?.provider;
  if (rows.items.isError || !provider) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-2xl border border-white/[.08] bg-surface p-5">
        <Icon name="film" size={20} className="text-zinc-500" />
        <h1 className="text-[17px] font-bold text-zinc-100">{NO_PROVIDER_TITLE}</h1>
        <p className="text-[13px] leading-relaxed text-zinc-400">{NO_PROVIDER_SUB}</p>
      </div>
    );
  }

  const hero = rows.hero;
  if (!hero) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-[26px] font-bold leading-none tracking-[-0.02em] text-zinc-50">Home</h1>
        <div className="rounded-2xl border border-white/[.08] bg-surface p-5 text-[13px] leading-relaxed text-zinc-400">
          Nothing to watch yet — once the library has titles, they will appear here.
        </div>
      </div>
    );
  }

  // ---- the hero ----------------------------------------------------------------------------------
  const isCw = rows.heroIsCw;
  const episode = isEpisodeItem(hero);
  const series = isSeries(hero);
  const percent = resumePercent(hero);
  const title = hero.title || "Untitled";
  const epCode = episode ? episodeItemCode(hero) : "";
  const meta = [
    hero.year ? String(hero.year) : "",
    series ? "TV" : fmtRuntime(hero.runtime),
    hero.episode?.series_name && episode ? hero.episode.series_name : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const poster = posterUrl(hero);
  const primaryLabel = heroPrimaryLabel({
    isEpisode: episode,
    episodeCode: epCode ?? "",
    isSeries: series,
    percent,
  });
  const primaryGoesToPage = series;
  const runtimeLeft =
    !series && !episode && percent > 0 && hero.runtime && hero.runtime > (hero.playback_position ?? 0)
      ? fmtRuntime(hero.runtime - (hero.playback_position ?? 0))
      : "";

  return (
    <div className="flex flex-col gap-8">
      <section aria-label={`Continue watching ${title}`} className="-mx-4 -mt-4">
        <div className="relative aspect-[4/3] w-full overflow-hidden">
          <div aria-hidden="true" className={`absolute inset-0 art-${artTone(title)}`} />
          {!backdropFailed ? (
            <img
              src={api.backdropUrl(hero.item_id, 1200)}
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
              className="absolute inset-0 h-full w-full object-cover object-[center_20%]"
            />
          ) : null}
          <div
            aria-hidden="true"
            className="absolute inset-0 bg-gradient-to-t from-canvas via-canvas/55 to-black/25"
          />
          <div className="absolute inset-x-0 bottom-0 p-4">
            <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.18em] text-accent">
              <Icon name={episode ? "tv" : "play"} size={12} filled={!episode} />
              {heroEyebrow(isCw, episode)}
            </div>
            <h1 className="mt-2 line-clamp-2 text-[26px] font-bold leading-[1.05] tracking-[-0.02em] text-white drop-shadow-[0_4px_24px_rgba(0,0,0,.6)]">
              {title}
            </h1>
            {meta ? <div className="mt-1.5 text-[12px] font-medium text-zinc-300">{meta}</div> : null}
            {percent > 0 ? (
              <div className="mt-2.5 flex items-center gap-2.5">
                <div className="h-[3px] flex-1 rounded-full bg-white/15">
                  <div className="h-full rounded-full bg-accent" style={{ width: `${percent}%` }} />
                </div>
                <span className="text-[11px] font-semibold tabular-nums text-zinc-300">
                  {percent}%{runtimeLeft ? ` · ${runtimeLeft} left` : ""}
                </span>
              </div>
            ) : null}
          </div>
        </div>

        {/* ⚠ Full-width primary, then Details beside it — the same shape as the details page's action
            bar, so the two screens teach one gesture. */}
        <div className="mt-4 flex flex-col gap-2.5 px-4">
          <button
            type="button"
            onClick={() => (primaryGoesToPage ? openItem(hero) : quickPlay(hero))}
            className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-[10px] bg-accent text-[15px] font-bold text-black shadow-lg shadow-accent/20 transition active:scale-[.99]"
          >
            <Icon name="play" size={16} filled />
            {primaryLabel}
          </button>
          {!primaryGoesToPage ? (
            <button
              type="button"
              onClick={() => openItem(hero)}
              className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-[10px] border border-white/10 bg-white/[.09] text-[15px] font-semibold text-zinc-100 backdrop-blur transition active:scale-[.99]"
            >
              Details
            </button>
          ) : null}
        </div>
      </section>

      {rows.cwItems.length > 1 ? (
        <section className="flex flex-col gap-3">
          <SectionHeader title="Continue Watching" />
          <ContinueWatchingRow
            items={rows.cwItems}
            onQuickPlay={handlers.onQuickPlay}
            onOpenDetail={handlers.onOpenDetail}
          />
        </section>
      ) : null}

      {rows.hasRecentlyPlayed ? (
        <section className="flex flex-col gap-3">
          <SectionHeader title="Recently Played" />
          <PosterRail items={rows.recentlyPlayed} handlers={handlers} />
        </section>
      ) : null}

      {rows.hasRecentlyAdded ? (
        <section className="flex flex-col gap-3">
          <SectionHeader title="Recently Added" />
          <PosterRail items={rows.recentlyAdded} handlers={handlers} />
        </section>
      ) : null}

      {/* Administrators only (Phase E): the scan route refuses everybody else, so the control is not
          offered to them. ⚠ It sits on its own at the end rather than in a section header — the
          mobile Home is for watching, and a library-maintenance button does not belong in the way. */}
      {mayScan ? (
        <section className="flex flex-col gap-3 border-t border-white/[.06] pt-4">
          <button
            type="button"
            disabled={scanning}
            onClick={() =>
              scan.mutate(undefined, {
                onSuccess: () => toast("Library scan complete", "New titles appear as they are discovered."),
                onError: (e) => {
                  const f = scanFailure(e);
                  toast(f.title, f.sub, "err");
                },
              })
            }
            className="inline-flex h-11 items-center justify-center gap-2 rounded-[10px] border border-white/10 bg-white/[.07] text-[14px] font-semibold text-zinc-200 transition disabled:opacity-60"
          >
            <Icon name="scan" size={15} />
            {scanning ? "Scanning…" : "Scan library for new titles"}
          </button>
        </section>
      ) : null}
    </div>
  );
}
