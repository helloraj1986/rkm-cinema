import { useState } from "react";
import { Outlet, useNavigate, useOutletContext } from "react-router-dom";
import { Player, type PlayTarget } from "../playback/Player";
import { startPosition, type QueueEntry } from "../playback/lib";
import { useMutateItemState } from "./api";
import { isSeries } from "./lib";
import type { EpisodeShape, MediaItem } from "../../lib/api/client";

/** Full-screen player state owned here so it overlays EVERY library route
 *  (home/folders AND the routed item page — exactly how Plex plays over the
 *  item page). Player is keyed by item so an Up-Next switch remounts cleanly. */
export interface LibraryPlayerState {
  item: PlayTarget;
  resume: number;
  queue: QueueEntry[];
  runtime: number;
}

/** Shared context the library routes consume (PLEX_VIEWS_PLAN Phases 0–1). */
export interface LibraryOutletContext {
  player: LibraryPlayerState | null;
  /** Movie Play/Resume from any surface. */
  startMovie: (itemId: string, title: string, resume: number, runtime: number) => void;
  /** Episode Play/Resume (queue rides along for Up Next). */
  startEpisode: (episode: EpisodeShape, queue: QueueEntry[]) => void;
  switchEntry: (entry: QueueEntry) => void;
  closePlayer: () => void;
  /** Whole-card click → the item's dedicated page (/library/item/:id). */
  openItem: (item: MediaItem) => void;
  /** Hover primary action: movies play now; series open their page (episodes live there). */
  quickPlay: (item: MediaItem) => void;
  toggleWatched: (item: MediaItem) => void;
}

export function useLibraryOutlet(): LibraryOutletContext {
  return useOutletContext<LibraryOutletContext>();
}

/**
 * Library section layout: every /library/* route renders inside this element,
 * so the player + shared handlers live in ONE place and the views stay thin.
 * URL is the source of truth for navigation (no overlay state anywhere).
 */
export function LibraryLayout() {
  const navigate = useNavigate();
  const mutateState = useMutateItemState();
  const [player, setPlayer] = useState<LibraryPlayerState | null>(null);

  const openItem = (item: MediaItem) =>
    navigate(`/library/item/${encodeURIComponent(item.item_id)}`);

  const startMovie = (itemId: string, title: string, resume: number, runtime: number) =>
    setPlayer({ item: { item_id: itemId, title }, resume, queue: [], runtime });

  const startEpisode = (episode: EpisodeShape, queue: QueueEntry[]) =>
    setPlayer({
      item: { item_id: episode.id, title: episode.name },
      resume: startPosition(episode),
      queue,
      runtime: episode.runtime || 0,
    });

  const switchEntry = (entry: QueueEntry) =>
    setPlayer((p) => ({
      item: { item_id: entry.id, title: entry.name },
      resume: entry.position,
      queue: p?.queue ?? [],
      runtime: entry.runtime ?? p?.runtime ?? 0,
    }));

  const closePlayer = () => setPlayer(null);

  /** Card hover primary action: movie → play now; series → its page (episodes). */
  const quickPlay = (item: MediaItem) => {
    if (isSeries(item)) {
      openItem(item);
      return;
    }
    startMovie(item.item_id, item.title, item.playback_position || 0, item.runtime || 0);
  };

  const toggleWatched = (item: MediaItem) =>
    mutateState.mutate({ itemId: item.item_id, watched: !item.played });

  const ctx: LibraryOutletContext = {
    player,
    startMovie,
    startEpisode,
    switchEntry,
    closePlayer,
    openItem,
    quickPlay,
    toggleWatched,
  };

  return (
    <div className="flex flex-col gap-8">
      <Outlet context={ctx} />
      {player && (
        <Player
          key={player.item.item_id}
          item={player.item}
          resume={player.resume}
          queue={player.queue}
          runtime={player.runtime}
          onSwitch={switchEntry}
          onClose={closePlayer}
        />
      )}
    </div>
  );
}
