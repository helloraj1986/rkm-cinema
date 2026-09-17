import { IconAction } from "../../components/ui/IconAction";
import type { MediaItem } from "../../lib/api/client";
import { useMutateItemState } from "./api";

/**
 * The Watched control — ONE component, for the desktop details modal/page and the phone's screen.
 *
 * ⚠ **His finding, 2026-09-17 (`KNOWN_ISSUES` §1, reproduced on device):** *"the Watched button gives
 * no indication of its default (unwatched) state, and on tap the button itself shows no state change
 * or feedback — only a green tick and label appear elsewhere."* The POST was fine; the CONTROL was
 * unreadable. So this fixes three things at once, and each is a rule rather than a style:
 *
 *   1. **The state is ON the control.** `Unwatched` / `Watched` — two words, not one word and an
 *      absence. `IconAction`'s `active` fill is the same fact, so the tile reads correctly even before
 *      the label is read.
 *   2. **The tap is ACKNOWLEDGED.** While the request is in flight the tile says `Saving…` and is
 *      disabled — a control that does nothing visible for 300ms is a control people tap twice, and
 *      the second tap flips it back.
 *   3. **The failure is surfaced.** The mutation's `onError` toasts the server's own sentence
 *      (`library/api.ts`) — one place, for every watched toggle in the app, because the ⋯ menu and the
 *      home rails' handler go through the same hook.
 *
 * ⚠ It owns the mutation rather than taking a handler, for the reason above: a caller that passes its
 * own handler is a caller that can forget the pending state, and then the tile is silent again.
 *
 * ⚠ **The poster is NOT this control** (his rule, same day): the grid's cards *reflect* watched state
 * with the tick marker and no longer offer the toggle at all. One fact, one owner — see
 * `MediaCard`'s note and `KNOWN_ISSUES` §2.
 */
export function WatchedAction({
  item,
  played,
  className,
}: {
  /** The library item, as the list query knows it (its `played` is what the server last said). */
  item: MediaItem;
  /** The played state the surface is rendering — the detail probe's answer wins over the list's. */
  played: boolean;
  /** Only used by the desktop presentation, which lays its tiles out in its own row. */
  className?: string;
}) {
  const mutate = useMutateItemState();
  const pending = mutate.isPending;

  return (
    <span className={className}>
      <IconAction
        icon="check"
        label={pending ? "Saving…" : played ? "Watched" : "Unwatched"}
        title={played ? "Mark as unwatched" : "Mark as watched"}
        active={played}
        disabled={pending}
        onClick={() => mutate.mutate({ itemId: item.item_id, watched: !played })}
      />
    </span>
  );
}
