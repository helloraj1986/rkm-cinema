import type { MediaItem } from "../../lib/api/client";

/**
 * Minimal in-app player — proxies the item through the same-origin stream
 * endpoint (the backend holds the Jellyfin token server-side). Full playback
 * slice (resume reporting, mark-watched, up-next) lands in Phase 3b.
 */
export function Player({ item, onClose }: { item: MediaItem; onClose: () => void }) {
  const src = `/api/jellyfin/stream/${encodeURIComponent(item.item_id)}`;
  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/95" role="dialog" aria-label={`Play ${item.title}`}>
      <div className="flex items-center justify-between p-3">
        <div className="text-sm font-medium text-zinc-200">{item.title}</div>
        <button
          onClick={onClose}
          className="rounded-full bg-zinc-800 px-3 py-1 text-sm text-zinc-200 hover:bg-zinc-700"
        >
          Close
        </button>
      </div>
      <div className="flex flex-1 items-center justify-center p-4">
        <video controls autoPlay src={src} className="max-h-full max-w-full" onError={() => undefined}>
          Your browser does not support HTML5 video.
        </video>
      </div>
    </div>
  );
}