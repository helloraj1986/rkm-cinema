import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Icon } from "../../components/ui/Icon";
import { HighlightedTitle } from "../../features/search/HighlightedTitle";
import { useGlobalSearch } from "../../features/search/api";
import {
  actionLabel,
  artUrl,
  detailsTarget,
  discoveryEntryStub,
  metaLine,
  noMatchesText,
  playTarget,
  SEARCH_DEBOUNCE_MS,
  SEARCH_FAILED,
  SEARCH_PLACEHOLDER,
  type GlobalDiscoveryRow,
  type GlobalHint,
  type GlobalOwnedRow,
} from "../../features/search/lib";
import { useRecentSearches } from "../../features/search/recent";
import { useAddToWatchlist } from "../../features/watchlist/api";
import { useCardActions } from "../../features/watchlist/actions";
import { toast } from "../../features/watchlist/toast";

/**
 * `/search` on a PHONE (MOBILE_FIRST_UI_PLAN §3.1, M3 — the wireframe on §7.4).
 *
 * ⚠ **Why the palette was not enough.** The desktop's global search is a command palette: a
 * `max-w-[430px]` field in the top bar that opens a dropdown under it. On a phone that dropdown is
 * 390px wide inside a 64px bar, its rows carry TWO rendered buttons apiece ("Watch Now" +
 * "Details"), and it was built for a keyboard (↑↓ navigate, Enter, ⌘K). None of that survives a
 * thumb. So the phone gets a SCREEN: the field at the top, the results as a full-width list, and
 * every action a ≥44px target that is visible without a hover.
 *
 * ⚠ **No input is duplicated and no rule is re-derived.** The data is the same `useGlobalSearch`
 * hook; the debounce, the placeholder, the failure sentence, the "no matches" sentence, the row's
 * action label, its meta line and its navigation targets are all `features/search/lib.ts` — the
 * values the palette reads. This file is layout, local UI state and markup (§3.4), which is what
 * `layouts/imports.test.ts` enforces on this directory.
 *
 * ⚠ **The two-button row became a two-zone row.** On a phone, the row BODY opens the title's details
 * and the trailing pill plays/resumes it (`actionLabel(row)` is the same state-aware verb the palette
 * uses) — one tap each, no hover, nothing smaller than a thumb.
 *
 * ⚠ **Recent searches happen when a search WORKS**, not on every keystroke: the query is remembered
 * when the person acts on a result, so RECENT is a list of searches that led somewhere rather than a
 * transcript of half-typed words.
 */
export function SearchScreen() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [debounced, setDebounced] = useState("");
  const { recent, remember } = useRecentSearches();
  const add = useAddToWatchlist();
  const cardActions = useCardActions();
  const { data, isFetching, isError } = useGlobalSearch(debounced);
  const [added, setAdded] = useState<Record<number, boolean>>({});
  const [busy, setBusy] = useState<number | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(text.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [text]);

  const inWatchlist = (disc: GlobalDiscoveryRow) => added[disc.tmdb_id] ?? disc.in_watchlist ?? false;

  /** Navigating away from a search IS the signal that the search was useful. */
  const go = (path: string) => {
    if (debounced) remember(debounced);
    navigate(path);
  };

  const openOwned = (row: GlobalOwnedRow) => {
    const target = detailsTarget(row);
    if (target) go(target);
  };

  const playOwned = (row: GlobalOwnedRow) => {
    const target = playTarget(row);
    if (target) go(target);
  };

  const addDisc = (disc: GlobalDiscoveryRow) => {
    setBusy(disc.tmdb_id);
    add.mutate(
      { tmdbId: disc.tmdb_id, mediaType: disc.media_type === "tv" ? "tv" : "movie" },
      {
        onSettled: () => setBusy(null),
        onSuccess: (r) => {
          if (r.ok) {
            setAdded((m) => ({ ...m, [disc.tmdb_id]: true }));
            toast("Added to watchlist", `${disc.title} is on your watchlist.`);
          } else {
            toast("Couldn't add", String((r as { message?: string }).message ?? "Unknown error"), "err");
          }
        },
        onError: () => toast("Couldn't add", "Check the backend connection.", "err"),
      },
    );
  };

  const ownedCount = data ? data.items.length + data.person_titles.length : 0;
  // ⚠ The server decides whether the external section exists (`discovery` arrives already filtered
  // and deduped) — the palette repeats no part of that decision, and neither does this screen.
  const showDiscovery = Boolean(data && data.discovery.length);
  const personLabel = data?.people[0]?.name;
  const empty = debounced.length === 0;
  const selectables = useMemo(() => (data ? data.items.length + data.person_titles.length : 0), [data]);

  return (
    <div className="flex flex-col gap-4">
      {/* The screen's own search bar — sticky, above the results, below the shell's chrome. It is the
          one control that must never scroll away, because every other control depends on it. */}
      <div className="sticky top-0 z-20 -mx-4 -mt-4 flex items-center gap-2 border-b border-white/[.05] bg-canvas/90 px-4 py-2 backdrop-blur-xl">
        <button
          type="button"
          onClick={() => navigate(-1)}
          aria-label="Back"
          className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-zinc-300 transition active:bg-white/[.08]"
        >
          <Icon name="back" size={19} />
        </button>
        <div className="relative min-w-0 flex-1">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500">
            <Icon name="search" size={16} />
          </span>
          {/* ⚠ No `autoFocus` (plan §7.3): the keyboard is raised by the field the person TAPS, not by
              arriving on a screen. The field carries no `type="search"` either — iOS renders its own
              clear button, which cannot be styled to the app's 44px floor. */}
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={SEARCH_PLACEHOLDER}
            autoComplete="off"
            aria-label="Search movies, shows and people"
            className="h-11 w-full rounded-[10px] border border-white/[.08] bg-white/[.06] pl-9 pr-9 text-zinc-100 outline-none transition placeholder:text-zinc-500 focus:border-accent/50"
          />
          {text ? (
            <button
              type="button"
              onClick={() => setText("")}
              aria-label="Clear the search"
              className="absolute right-1 top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-full text-zinc-400 transition active:bg-white/[.08]"
            >
              <Icon name="close" size={16} />
            </button>
          ) : null}
        </div>
      </div>

      {empty ? (
        <RecentRow recent={recent} onPick={setText} />
      ) : isFetching && !data ? (
        <div className="flex flex-col gap-2" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="skeleton h-14 w-10 shrink-0 rounded-md" />
              <div className="flex flex-1 flex-col gap-2">
                <div className="skeleton h-4 w-2/3 rounded" />
                <div className="skeleton h-3 w-1/3 rounded" />
              </div>
            </div>
          ))}
        </div>
      ) : isError ? (
        <Notice text={SEARCH_FAILED} />
      ) : data && selectables === 0 && !showDiscovery ? (
        <Notice text={noMatchesText(debounced)} />
      ) : data ? (
        <div className="flex flex-col gap-6" data-testid="mobile-search-results">
          {ownedCount > 0 ? (
            <section className="flex flex-col gap-2">
              <GroupHeading>In your library</GroupHeading>
              {data.items.map((row) => (
                <OwnedRowM key={`it-${row.id}`} row={row} onOpen={() => openOwned(row)} onPlay={() => playOwned(row)} />
              ))}
              {data.person_titles.length > 0 && personLabel ? (
                <GroupHeading>Titles with {personLabel}</GroupHeading>
              ) : null}
              {data.person_titles.map((row) => (
                <OwnedRowM key={`pt-${row.id}`} row={row} onOpen={() => openOwned(row)} onPlay={() => playOwned(row)} />
              ))}
            </section>
          ) : null}

          {data.genres.length > 0 || data.collections.length > 0 || data.people.length > 0 ? (
            <section className="flex flex-col gap-2">
              <GroupHeading>People, genres &amp; collections</GroupHeading>
              {data.people.map((p) => (
                <HintRowM key={`p-${p.id}`} hint={p} onGo={go} />
              ))}
              {data.genres.map((g) => (
                <HintRowM key={`g-${g.id}`} hint={g} onGo={go} />
              ))}
              {data.collections.map((c) => (
                <HintRowM key={`c-${c.id}`} hint={c} onGo={go} />
              ))}
            </section>
          ) : null}

          {showDiscovery ? (
            <section className="flex flex-col gap-2">
              <GroupHeading>Discover · not in your library</GroupHeading>
              {data.discovery.map((disc) => (
                <DiscoveryRowM
                  key={`d-${disc.tmdb_id}`}
                  disc={disc}
                  added={inWatchlist(disc)}
                  busy={busy === disc.tmdb_id}
                  onAdd={() => addDisc(disc)}
                  onDownload={() => cardActions.download(discoveryEntryStub(disc))}
                />
              ))}
            </section>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** The RECENT row — chips, tappable, and nothing else. It appears only while the field is empty. */
function RecentRow({ recent, onPick }: { recent: string[]; onPick: (q: string) => void }) {
  if (recent.length === 0) {
    return (
      <p className="px-1 text-[13px] leading-relaxed text-zinc-500">
        Search your library by title, or by the people in it. Titles you do not own yet are offered
        underneath, with the option to add them to your watchlist.
      </p>
    );
  }
  return (
    <section className="flex flex-col gap-2">
      <GroupHeading>Recent</GroupHeading>
      <div className="flex flex-wrap gap-2">
        {recent.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => onPick(q)}
            data-testid="recent-chip"
            className="inline-flex h-11 max-w-full items-center gap-2 rounded-full border border-white/[.08] bg-white/[.06] px-3.5 text-[13px] font-semibold text-zinc-200 transition active:bg-white/[.12]"
          >
            <Icon name="clock" size={14} />
            <span className="truncate">{q}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function GroupHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="px-1 text-[11px] font-bold uppercase tracking-[0.16em] text-zinc-500">{children}</h2>
  );
}

function Notice({ text }: { text: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-white/[.08] px-5 py-8">
      <p className="text-[13px] leading-relaxed text-zinc-400">{text}</p>
    </div>
  );
}

/**
 * A library result. ⚠ TWO ZONES, not two buttons in one: the body opens the title, the pill plays it.
 * The pill is `h-11` (44px) — the thumb floor — and carries the same state-aware verb the palette's
 * button carries, because `actionLabel` is the one place that decides what that verb is.
 */
function OwnedRowM({
  row,
  onOpen,
  onPlay,
}: {
  row: GlobalOwnedRow;
  onOpen: () => void;
  onPlay: () => void;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-white/[.05] bg-surface/60 p-2.5">
      <button type="button" onClick={onOpen} className="flex min-w-0 flex-1 items-center gap-3 text-left">
        <img
          src={artUrl(row.id)}
          alt=""
          loading="lazy"
          className="h-14 w-10 shrink-0 rounded-md bg-surface-3 object-cover ring-1 ring-white/[.06]"
        />
        <span className="min-w-0 flex-1">
          {/* ⚠ The matched span comes from the SERVER (`row.ranges`); the phone does not search
              the title again — a second implementation of that decision is what this directory is
              banned from holding (§3.4). The component is shared with the palette. */}
          <HighlightedTitle
            text={row.title}
            ranges={row.ranges}
            className="block truncate text-[14px] font-semibold text-zinc-100"
          />
          <span className="block truncate text-[12px] text-zinc-500">{metaLine(row)}</span>
        </span>
      </button>
      <button
        type="button"
        onClick={onPlay}
        data-testid="owned-action"
        className="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-[10px] bg-accent px-3.5 text-[13px] font-bold text-black transition active:bg-accent-hover"
      >
        <Icon name="play" size={13} filled />
        <span className="max-w-24 truncate">{actionLabel(row)}</span>
      </button>
    </div>
  );
}

/**
 * A person, a genre or a collection. ⚠ A person has NO action on either surface (the server's hints
 * carry a person's titles separately, in `person_titles`) — so the row is not a button, because a
 * row that looks tappable and does nothing is the defect M3-part-4 fixed on the details page.
 */
function HintRowM({ hint, onGo }: { hint: GlobalHint; onGo: (path: string) => void }) {
  const genre = hint.kind === "genre";
  const collection = hint.kind === "collection";
  const path = genre
    ? `/library/movies?genre=${encodeURIComponent(hint.name)}`
    : collection
      ? `/library/item/${encodeURIComponent(hint.id)}`
      : "";
  return (
    <div className="flex items-center gap-3 rounded-xl border border-white/[.05] bg-surface/60 p-2.5">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-white/[.06] text-zinc-400">
        <Icon name={genre ? "grid" : "sparkles"} size={16} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[14px] font-semibold text-zinc-100">{hint.name}</span>
        <span className="block text-[12px] text-zinc-500">
          {genre ? "Genre" : collection ? "Collection" : "Person"}
        </span>
      </span>
      {path ? (
        <button
          type="button"
          onClick={() => onGo(path)}
          className="inline-flex h-11 shrink-0 items-center rounded-[10px] border border-white/10 bg-white/[.07] px-3.5 text-[13px] font-bold text-zinc-100 transition active:bg-white/[.12]"
        >
          Browse
        </button>
      ) : null}
    </div>
  );
}

/**
 * A title the household does NOT own. ⚠ One action, and it tells the truth about where the person
 * is: "Add" while it is only on the watchlist, "Download" once the server knows about it. Both go
 * through the SAME mutation the desktop cards use, so "Add" cannot mean two different things.
 *
 * ⚠ Deliberately NOT tappable as a row: on the desktop, tapping a discovery row opens
 * `SuggestDetailModal` — a centred `Dialog`, which is the thing mobile replaces with a sheet. Until
 * M4's sheet exists, the honest phone answer is the action, not a desktop modal on a phone.
 */
function DiscoveryRowM({
  disc,
  added,
  busy,
  onAdd,
  onDownload,
}: {
  disc: GlobalDiscoveryRow;
  added: boolean;
  busy: boolean;
  onAdd: () => void;
  onDownload: () => void;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-white/[.05] bg-surface/60 p-2.5">
      {disc.poster ? (
        <img
          src={disc.poster}
          alt=""
          loading="lazy"
          className="h-14 w-10 shrink-0 rounded-md bg-surface-3 object-cover ring-1 ring-white/[.06]"
        />
      ) : (
        <span className="grid h-14 w-10 shrink-0 place-items-center rounded-md bg-surface-3 text-zinc-500 ring-1 ring-white/[.06]">
          <Icon name={disc.media_type === "tv" ? "tv" : "film"} size={14} />
        </span>
      )}
      <span className="min-w-0 flex-1">
        <HighlightedTitle
          text={disc.title}
          ranges={disc.ranges}
          className="block truncate text-[14px] font-semibold text-zinc-100"
        />
        <span className="block truncate text-[12px] text-zinc-500">
          {disc.media_type === "tv" ? "TV Show" : "Movie"}
          {disc.year ? ` · ${disc.year}` : ""}
          {added ? " · in watchlist" : " · not in your library"}
        </span>
      </span>
      {added ? (
        <button
          type="button"
          onClick={onDownload}
          data-testid="discovery-action"
          className="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-[10px] bg-accent px-3.5 text-[13px] font-bold text-black transition active:bg-accent-hover"
        >
          <Icon name="download" size={13} />
          Download
        </button>
      ) : (
        <button
          type="button"
          onClick={onAdd}
          disabled={busy}
          data-testid="discovery-action"
          className="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-[10px] bg-accent px-3.5 text-[13px] font-bold text-black transition active:bg-accent-hover disabled:opacity-60"
        >
          <Icon name="plus" size={13} />
          {busy ? "Adding…" : "Add"}
        </button>
      )}
    </div>
  );
}
