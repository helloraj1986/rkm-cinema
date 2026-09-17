import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { Sheet } from "../../components/ui/Sheet";
import { Icon } from "../../components/ui/Icon";
import { MediaCard } from "../../features/library/MediaCard";
import { useFolderItems, useLibraryFolders } from "../../features/library/api";
import { useLibraryOutlet } from "../../features/library/LibraryLayout";
import {
  filterLibraryItems,
  FOLDER_EMPTY_SUB,
  folderCountLabel,
  folderEmptyTitle,
  libraryByFolderId,
  libraryFilterFromParams,
  libraryFilterToParams,
  libraryGenres,
  LIBRARY_SORT_OPTIONS,
  NO_PROVIDER_SUB,
  NO_PROVIDER_TITLE,
  type LibrarySort,
} from "../../features/library/lib";
import { useProgressiveMount } from "../../features/library/useProgressiveMount";
import { MobileAction, MobileScreen } from "./MobileScreen";

/**
 * `/library/folder/:folderId` on a phone — the folder browse screen (`MOBILE_FIRST_UI_PLAN` §3.1, M3).
 *
 * ⚠ **What it is for, in one line:** the desktop view puts a ten-pill sort row and a genre row into a
 * phone-width line, and lays posters out at `minmax(158px, 1fr)` — two columns of a size that belongs
 * on a laptop. This screen is the same data with a **3–5 column thumb grid** (`--m-grid-cols`, the
 * M0 tokens) and the filters **behind a sheet** instead of wrapped across three lines.
 *
 * ⚠ Every RULE is imported, never re-derived (§3.4): the folder's identity and count, the filter and
 * sort parsing, the genre list, the sort options and the copy all come from `features/library/lib.ts`
 * and the shared hooks. This file holds layout, local UI state and markup — nothing else, which is
 * what `layouts/imports.test.ts` enforces.
 *
 * ⚠ The card is the SAME `MediaCard` the grid uses. A second card component would be a second copy of
 * the poster, the meta line and the actions — and the reason the plan wanted a distinct mobile card
 * (§7.3: actions hidden behind a hover) was fixed for every card by the `.rkm-reveal-hit` rule, which
 * makes the actions visible and tappable wherever there is no hover.
 */
export function BrowseScreen() {
  const { folderId = "" } = useParams();
  const foldersQ = useLibraryFolders();
  const items = useFolderItems(folderId || null);
  const { quickPlay, openItem, toggleWatched } = useLibraryOutlet();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filtersOpen, setFiltersOpen] = useState(false);

  const parsed = libraryFilterFromParams(searchParams);
  const libraries = foldersQ.data?.libraries ?? [];
  const lib = libraryByFolderId(libraries, folderId);
  const folderName = lib?.name ?? foldersQ.data?.folders.find((f) => f.id === folderId)?.name ?? "";
  const label = lib?.name || folderName || "Library";

  const folderItems = items.data?.items ?? [];
  const genres = libraryGenres(folderItems);
  const list = filterLibraryItems(folderItems, { genre: parsed.genre, sort: parsed.sort });
  const provider = items.data?.provider ?? null;
  // ⚠ The same mounting rule as the desktop grid (M3): a screenful first, the rest in separate
  // commits. A phone is the device where that matters most, and it is a shared rule, not a copy.
  const mounted = useProgressiveMount(list.length, `${folderId}|${parsed.genre}|${parsed.sort}`);

  const apply = (patch: { genre?: string; sort?: LibrarySort }) => {
    setSearchParams(
      libraryFilterToParams({ genre: parsed.genre, sort: parsed.sort, ...patch }),
      { replace: true },
    );
  };

  const activeFilters = Number(parsed.genre !== "") + Number(parsed.sort !== "recent");

  return (
    <MobileScreen
      title={label}
      subtitle={provider ? folderCountLabel(folderItems.length) : undefined}
      actions={
        <>
          <MobileAction
            label="Filters and sorting"
            active={filtersOpen || activeFilters > 0}
            onClick={() => setFiltersOpen(true)}
          >
            <Icon name="menu" size={15} />
            Filters
            {activeFilters > 0 ? (
              <span className="grid h-4 min-w-4 place-items-center rounded-full bg-black/25 px-1 text-[10px] font-bold">
                {activeFilters}
              </span>
            ) : null}
          </MobileAction>
          {parsed.genre ? (
            <MobileAction label="Clear the genre filter" onClick={() => apply({ genre: "" })}>
              {parsed.genre}
              <Icon name="close" size={13} />
            </MobileAction>
          ) : null}
        </>
      }
    >
      {items.isLoading ? (
        <div className="m-grid" aria-hidden="true">
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} className="skeleton aspect-[2/3] rounded-[10px]" />
          ))}
        </div>
      ) : !provider ? (
        <Notice title={NO_PROVIDER_TITLE} sub={NO_PROVIDER_SUB} />
      ) : folderItems.length === 0 ? (
        <Notice title={folderEmptyTitle(label)} sub={FOLDER_EMPTY_SUB} />
      ) : list.length === 0 ? (
        <Notice title={`No ${label.toLowerCase()} match in ${parsed.genre}`} sub="Try another genre." />
      ) : (
        <>
          <div className="m-grid" data-testid="mobile-grid">
            {list.slice(0, mounted).map((item) => (
              <MediaCard
                key={item.item_id}
                item={item}
                fluid
                onQuickPlay={quickPlay}
                onOpenDetail={openItem}
                onToggleWatched={toggleWatched}
              />
            ))}
          </div>
          <p className="text-[11px] text-zinc-500">
            {parsed.genre ? `${folderCountLabel(list.length)} in ${parsed.genre} · ` : ""}
            {folderCountLabel(folderItems.length)} in this library
          </p>
        </>
      )}

      {filtersOpen ? (
        <Sheet labelledBy="mobile-filters-title" onClose={() => setFiltersOpen(false)}>
          {/* ⚠ `max-w-lg mx-auto`, and the aligned layouts below — his iPad report, 2026-09-17:
              "the filter card UI is not aligned properly". On a tablet the sheet spans the width of
              an iPad, so a wrapped row of text-sized chips left a ragged right edge and made every
              chip a different width; a fixed-width column of full-width sort ROWS (the iOS idiom,
              with a tick on the active one) and an even genre GRID are aligned by construction
              rather than by luck. */}
          <div className="mx-auto flex w-full max-w-lg flex-col gap-5 px-1 pb-2">
            <h2 id="mobile-filters-title" className="text-base font-bold text-zinc-100">
              Filters
            </h2>

            <section className="flex flex-col gap-1.5">
              <h3 className="text-[11px] font-bold uppercase tracking-[0.14em] text-zinc-500">
                Sort by
              </h3>
              <div className="flex flex-col">
                {LIBRARY_SORT_OPTIONS.map((o) => {
                  const active = parsed.sort === o.key;
                  return (
                    <button
                      key={o.key}
                      type="button"
                      aria-pressed={active}
                      onClick={() => apply({ sort: o.key })}
                      className={`flex h-12 items-center justify-between rounded-[10px] px-3 text-left text-sm font-medium transition ${
                        active ? "bg-accent/15 text-accent" : "text-zinc-300 active:bg-white/[.06]"
                      }`}
                    >
                      <span>{o.label}</span>
                      {active ? <Icon name="check" size={16} strokeWidth={2.5} /> : null}
                    </button>
                  );
                })}
              </div>
            </section>

            {genres.length > 0 ? (
              <section className="flex flex-col gap-2">
                <h3 className="text-[11px] font-bold uppercase tracking-[0.14em] text-zinc-500">
                  Genre
                </h3>
                <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                  {genres.map((g) => (
                    <button
                      key={g}
                      type="button"
                      aria-pressed={parsed.genre === g}
                      onClick={() => apply({ genre: parsed.genre === g ? "" : g })}
                      className={`h-11 min-w-0 truncate rounded-[10px] px-2 text-[13px] font-semibold transition ${
                        parsed.genre === g
                          ? "bg-accent text-black"
                          : "border border-white/[.08] bg-white/[.06] text-zinc-300 active:bg-white/[.12]"
                      }`}
                    >
                      {g}
                    </button>
                  ))}
                </div>
              </section>
            ) : null}

            <button
              type="button"
              onClick={() => setFiltersOpen(false)}
              className="h-12 rounded-[10px] bg-accent text-sm font-bold text-black transition active:bg-accent-hover"
            >
              Show {folderCountLabel(list.length)}
            </button>
          </div>
        </Sheet>
      ) : null}
    </MobileScreen>
  );
}

/** The screen's empty/unavailable states — the copy comes from `features/library/lib.ts`, shared with
 *  the desktop view so the two can never say different things about the same folder. */
function Notice({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="flex flex-col items-start gap-1.5 rounded-2xl border border-dashed border-white/[.08] px-5 py-10">
      <h2 className="font-semibold text-zinc-200">{title}</h2>
      <p className="text-sm leading-relaxed text-zinc-500">{sub}</p>
    </div>
  );
}
