import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { GlobalDiscoveryRow, GlobalHint, GlobalOwnedRow } from "../../lib/api/client";
import { Icon } from "../../components/ui/Icon";
import { useAddToWatchlist } from "../watchlist/api";
import { toast } from "../watchlist/toast";
import { useGlobalSearch } from "./api";
import { actionLabel, artUrl, detailsTarget, metaLine, playTarget } from "./lib";

const DEBOUNCE_MS = 200;
const KIND_TEXT: Record<string, string> = { movie: "Movie", tv: "TV Show" };

type Selectable =
  | { kind: "owned"; row: GlobalOwnedRow }
  | { kind: "genre"; hint: GlobalHint }
  | { kind: "collection"; hint: GlobalHint }
  | { kind: "discovery"; disc: GlobalDiscoveryRow };

/**
 * The ONE global search (GLOBAL_SEARCH_PLAN Phase 3): a command-palette
 * dropdown owned by the top bar. Library results first with state-aware
 * actions; TMDB DISCOVER only appears when the API reports no strong owned
 * match. `/` and ⌘K focus it from anywhere.
 */
export function GlobalSearch() {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const add = useAddToWatchlist();
  const [text, setText] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState(0);
  const [addingId, setAddingId] = useState<number | null>(null);

  // Debounce typing (fast, visually responsive).
  useEffect(() => {
    const t = setTimeout(() => setDebounced(text.trim()), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [text]);

  const { data, isFetching, isError } = useGlobalSearch(debounced);
  const active = open && debounced.length > 0;

  // Seed once from a shareable ?q= (old /search deep links land on Home).
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    if (q && !text) {
      setText(q);
      setOpen(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Global shortcuts: ⌘K / Ctrl+K or `/` focus search.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      } else if (e.key === "/" && !typing) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Close when clicking outside the widget.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setSel(0);
      }
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open]);

  const selectables: Selectable[] = useMemo(() => {
    if (!data) return [];
    const list: Selectable[] = [];
    for (const row of data.items) list.push({ kind: "owned", row });
    for (const row of data.person_titles) list.push({ kind: "owned", row });
    for (const g of data.genres) list.push({ kind: "genre", hint: g });
    for (const c of data.collections) list.push({ kind: "collection", hint: c });
    for (const disc of data.discovery) list.push({ kind: "discovery", disc });
    return list;
  }, [data]);

  useEffect(() => setSel(0), [debounced]);

  const goto = (path: string) => {
    setOpen(false);
    setSel(0);
    setText("");
    setDebounced("");
    navigate(path);
  };

  const addDisc = (disc: GlobalDiscoveryRow) => {
    setAddingId(disc.tmdb_id);
    add.mutate(
      { tmdbId: disc.tmdb_id, mediaType: disc.media_type === "tv" ? "tv" : "movie" },
      {
        onSettled: () => setAddingId(null),
        onSuccess: (r) => {
          if (r.ok) {
            toast("Added to library", `${disc.title} is now in your watchlist.`);
          } else {
            toast("Couldn't add", String((r as { message?: string }).message ?? "Unknown error"), "err");
          }
        },
        onError: () => toast("Couldn't add", "Check the backend connection.", "err"),
      },
    );
  };

  const activate = (s: Selectable) => {
    if (s.kind === "owned") {
      const t = playTarget(s.row);
      if (t) goto(t);
      return;
    }
    if (s.kind === "genre") {
      goto(`/library/movies?genre=${encodeURIComponent(s.hint.name)}`);
      return;
    }
    if (s.kind === "collection") {
      goto(`/library/item/${encodeURIComponent(s.hint.id)}`);
      return;
    }
    addDisc(s.disc);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!active) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSel((s) => (selectables.length ? (s + 1) % selectables.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSel((s) => (selectables.length ? (s - 1 + selectables.length) % selectables.length : 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const target = selectables[Math.min(sel, Math.max(0, selectables.length - 1))];
      if (target) activate(target);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      inputRef.current?.blur();
    }
  };

  const ownedCount = data ? data.items.length + data.person_titles.length : 0;
  const showDiscovery = Boolean(data && !data.strong_match && data.discovery.length);
  const personLabel = data?.people[0]?.name;

  return (
    <div ref={containerRef} className="relative min-w-0 flex-1">
      <span className="pointer-events-none absolute left-3 top-1/2 z-10 -translate-y-1/2 text-zinc-500">
        <Icon name="search" size={16} />
      </span>
      <input
        ref={inputRef}
        type="search"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder="Search movies, shows, people…"
        autoComplete="off"
        aria-label="Search movies, shows and people"
        role="combobox"
        aria-expanded={active}
        aria-controls="global-search-results"
        className="w-full rounded-[10px] border border-white/[.06] bg-surface-2 py-2 pl-9 pr-14 text-[13px] text-zinc-100 outline-none transition placeholder:text-zinc-500 focus:border-accent/50 focus:shadow-glow"
      />
      <kbd className="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 rounded border border-white/10 bg-white/[.04] px-1.5 py-0.5 text-[10.5px] font-medium text-zinc-500 sm:block">
        ⌘K
      </kbd>

      {active ? (
        <div
          id="global-search-results"
          className="absolute left-0 right-0 top-[calc(100%+8px)] z-[var(--z-header)] overflow-hidden rounded-2xl border border-white/10 bg-surface-2/95 shadow-[0_24px_80px_rgba(0,0,0,0.55)] backdrop-blur-2xl"
        >
          {isFetching && !data ? (
            <div className="flex items-center gap-3 px-4 py-3 text-[13px] text-zinc-500">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/15 border-t-accent" />
              Searching your library…
            </div>
          ) : isError ? (
            <p className="px-4 py-3 text-[13px] text-zinc-500">Search failed — try again shortly.</p>
          ) : data && selectables.length === 0 ? (
            <p className="px-4 py-3 text-[13px] text-zinc-500">No matches for “{debounced}”.</p>
          ) : data ? (
            <div className="max-h-[min(68vh,540px)] overflow-y-auto py-2" role="listbox" aria-label="Search results">
              {ownedCount > 0 ? <GroupLabel>In your library</GroupLabel> : null}
              {data.items.map((row, i) => (
                <OwnedRow key={`it-${row.id}`} row={row} selected={sel === i} onSelect={() => setSel(i)} onActivate={() => activate({ kind: "owned", row })} onDetails={() => { const t = detailsTarget(row); if (t) goto(t); }} />
              ))}
              {data.person_titles.length > 0 && personLabel ? <GroupLabel>Titles with {personLabel}</GroupLabel> : null}
              {data.person_titles.map((row, i) => {
                const idx = data.items.length + i;
                return <OwnedRow key={`pt-${row.id}`} row={row} selected={sel === idx} onSelect={() => setSel(idx)} onActivate={() => activate({ kind: "owned", row })} onDetails={() => { const t = detailsTarget(row); if (t) goto(t); }} />;
              })}

              {data.genres.length > 0 || data.collections.length > 0 ? <GroupLabel>People, genres & collections</GroupLabel> : null}
              {data.people.map((p) => (
                <HintRow key={`p-${p.id}`} title={p.name} sub={p.kind === "person" ? "Person" : ""} />
              ))}
              {data.genres.map((g, gi) => {
                const idx = ownedCount + gi;
                return <HintRow key={`g-${g.id}`} title={g.name} sub="Genre" selected={sel === idx} onSelect={() => setSel(idx)} onActivate={() => activate({ kind: "genre", hint: g })} />;
              })}
              {data.collections.map((c, ci) => {
                const idx = ownedCount + data.genres.length + ci;
                return <HintRow key={`c-${c.id}`} title={c.name} sub="Collection" selected={sel === idx} onSelect={() => setSel(idx)} onActivate={() => activate({ kind: "collection", hint: c })} />;
              })}

              {showDiscovery ? <GroupLabel>Discover · not in your library</GroupLabel> : null}
              {showDiscovery
                ? data.discovery.map((disc, di) => {
                    const idx = selectables.length - data.discovery.length + di;
                    return (
                      <DiscoveryRow
                        key={`d-${disc.tmdb_id}`}
                        disc={disc}
                        selected={sel === idx}
                        adding={addingId === disc.tmdb_id}
                        onSelect={() => setSel(idx)}
                        onAdd={() => addDisc(disc)}
                      />
                    );
                  })
                : null}
            </div>
          ) : null}

          <div className="flex items-center gap-4 border-t border-white/[.06] px-4 py-2 text-[10px] font-medium text-zinc-500">
            <span>↑↓ navigate · Enter select · Esc close</span>
            {!data?.tmdb_key && !data?.strong_match ? <span className="ml-auto">TMDB discovery off — library only</span> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-4 pb-1 pt-3 text-[10px] font-bold uppercase tracking-[0.16em] text-zinc-500">
      {children}
    </div>
  );
}

function OwnedRow({
  row, selected, onSelect, onActivate, onDetails,
}: {
  row: GlobalOwnedRow;
  selected: boolean;
  onSelect: () => void;
  onActivate: () => void;
  onDetails: () => void;
}) {
  const label = actionLabel(row);
  return (
    <div
      role="option"
      aria-selected={selected}
      onMouseEnter={onSelect}
      onClick={onActivate}
      className={`mx-2 flex cursor-pointer items-center gap-3 rounded-xl px-2 py-2 transition ${
        selected ? "bg-white/[.08]" : "hover:bg-white/[.04]"
      }`}
    >
      <img src={artUrl(row.id)} alt="" loading="lazy" className="h-14 w-10 shrink-0 rounded-md bg-surface-3 object-cover ring-1 ring-white/[.06]" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-semibold text-zinc-100">{row.title}</div>
        <div className="truncate text-[11px] text-zinc-500">{metaLine(row)}</div>
      </div>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onActivate(); }}
        className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg bg-accent px-3 text-[11px] font-bold text-black transition hover:bg-accent-hover"
      >
        <Icon name="play" size={11} filled />
        {label}
      </button>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onDetails(); }}
        className="shrink-0 rounded-lg border border-white/10 bg-white/[.06] px-2.5 py-1.5 text-[11px] font-semibold text-zinc-200 transition hover:bg-white/[.12]"
      >
        Details
      </button>
    </div>
  );
}

function HintRow({
  title, sub, selected, onSelect, onActivate,
}: {
  title: string;
  sub: string;
  selected?: boolean;
  onSelect?: () => void;
  onActivate?: () => void;
}) {
  return (
    <div
      role={onActivate ? "option" : undefined}
      aria-selected={selected}
      onMouseEnter={onSelect}
      onClick={onActivate}
      className={`mx-2 flex cursor-pointer items-center gap-3 rounded-xl px-2 py-2 transition ${
        selected ? "bg-white/[.08]" : onActivate ? "hover:bg-white/[.04]" : "cursor-default hover:bg-transparent"
      }`}
    >
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-white/[.06] text-zinc-400">
        <Icon name={sub === "Genre" ? "grid" : "sparkles"} size={16} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-semibold text-zinc-100">{title}</div>
        <div className="truncate text-[11px] text-zinc-500">{sub}</div>
      </div>
      {onActivate ? (
        <span className="shrink-0 rounded-lg border border-white/10 bg-white/[.06] px-2.5 py-1.5 text-[11px] font-semibold text-zinc-300">
          Browse
        </span>
      ) : null}
    </div>
  );
}

function DiscoveryRow({
  disc, selected, adding, onSelect, onAdd,
}: {
  disc: GlobalDiscoveryRow;
  selected: boolean;
  adding: boolean;
  onSelect: () => void;
  onAdd: () => void;
}) {
  return (
    <div
      role="option"
      aria-selected={selected}
      onMouseEnter={onSelect}
      onClick={onAdd}
      className={`mx-2 flex cursor-pointer items-center gap-3 rounded-xl px-2 py-2 transition ${
        selected ? "bg-white/[.08]" : "hover:bg-white/[.04]"
      }`}
    >
      {disc.poster ? (
        <img src={disc.poster} alt="" loading="lazy" className="h-14 w-10 shrink-0 rounded-md bg-surface-3 object-cover ring-1 ring-white/[.06]" />
      ) : (
        <span className="grid h-14 w-10 shrink-0 place-items-center rounded-md bg-surface-3 text-zinc-500 ring-1 ring-white/[.06]">
          <Icon name={disc.media_type === "tv" ? "tv" : "film"} size={14} />
        </span>
      )}
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-semibold text-zinc-100">{disc.title}</div>
        <div className="truncate text-[11px] text-zinc-500">
          {KIND_TEXT[disc.media_type] ?? "Title"}
          {disc.year ? ` · ${disc.year}` : ""} · <span className="text-amber-300/90">not in your library</span>
        </div>
      </div>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onAdd(); }}
        disabled={adding}
        className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-white/15 bg-white/[.06] px-3 text-[11px] font-bold text-zinc-100 transition hover:bg-white/[.12] disabled:opacity-60"
      >
        <Icon name="plus" size={12} />
        {adding ? "Adding…" : "Add to library"}
      </button>
    </div>
  );
}
