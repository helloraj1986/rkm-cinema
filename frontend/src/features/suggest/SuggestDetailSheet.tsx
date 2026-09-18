import type { SuggestResult } from "../../lib/api/client";
import { Sheet } from "../../components/ui/Sheet";
import { SuggestDetailBody } from "./SuggestDetailBody";

/**
 * A title the household does NOT own, opened from the phone's search screen.
 *
 * ⚠ **Why a Sheet and not the page.** `/library/item/:itemId` is addressed by a
 * LIBRARY item id, and a discovered title has none — it is a TMDB id, so the
 * library detail endpoint cannot answer for it (404, then "not found"). The
 * app's answer for these titles has always been the suggest-detail payload;
 * the desktop shows it in a `Dialog`, and on a 390px screen a centred 90vh
 * dialog with a backdrop hero is the wrong composition — which is exactly why
 * the phone's search screen used to leave the row untappable instead.
 *
 * The content is `SuggestDetailBody`, the SAME component the desktop modal
 * renders, so the two surfaces cannot disagree about a film's runtime, its
 * scores or its actions. This file adds only the phone's chrome.
 *
 * ⚠ The sheet is full-width by design. The iPad alignment fix in
 * `BrowseScreen` uses `max-w-lg mx-auto` for a column of CHIPS; a media detail
 * wants the full bleed for its backdrop, so it deliberately does not copy that.
 */
export function SuggestDetailSheet({
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
    <Sheet labelledBy="suggest-detail-title" onClose={onClose}>
      <SuggestDetailBody
        item={item}
        busyAdd={busyAdd}
        busyDownload={busyDownload}
        onClose={onClose}
        onAdd={onAdd}
        onDownload={onDownload}
      />
    </Sheet>
  );
}
