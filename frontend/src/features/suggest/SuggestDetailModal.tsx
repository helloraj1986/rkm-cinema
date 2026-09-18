import type { SuggestResult } from "../../lib/api/client";
import { Dialog } from "../../components/ui/Dialog";
import { SuggestDetailBody } from "./SuggestDetailBody";

/**
 * Suggest detail modal (legacy `openSuggestDetail` parity): fetches full
 * TMDB + IMDb metadata on demand (/api/suggest/detail), shows backdrop hero,
 * chips, IMDb/TMDB scores, synopsis, director/cast/votes facts, and the
 * Add-to-Watchlist + Download actions (shared with the grid card).
 *
 * Premium pass (2026-09): Dialog shell (§51 modal chrome + focus trap/restore),
 * §14 pill chips, §71 button hierarchy, seeded-art fallback (no emoji).
 *
 * ⚠ 2026-09-18: the CONTENT moved to `SuggestDetailBody` so the phone can render the
 * same facts in a `Sheet` without a second copy. This file is now the DESKTOP shell
 * (the centred `Dialog`) and nothing else.
 */
export function SuggestDetailModal({
  item,
  busyAdd,
  busyDownload,
  onClose,
  onAdd,
  onDownload,
}: {
  item: SuggestResult;
  busyAdd: boolean;
  busyDownload: boolean;
  onClose: () => void;
  onAdd: () => void;
  onDownload: () => void;
}) {
  return (
    <Dialog onClose={onClose} labelledBy="suggest-detail-title">
      <SuggestDetailBody
        item={item}
        busyAdd={busyAdd}
        busyDownload={busyDownload}
        onClose={onClose}
        onAdd={onAdd}
        onDownload={onDownload}
      />
    </Dialog>
  );
}
