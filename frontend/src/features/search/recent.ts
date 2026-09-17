import { useCallback, useState } from "react";

import { parseRecent, pushRecent, RECENT_KEY } from "./lib";

/**
 * The phone search screen's RECENT row (`MOBILE_FIRST_UI_PLAN` M3 §7.4).
 *
 * ⚠ The RULES are in `lib.ts` (`parseRecent`, `pushRecent`, `RECENT_MAX`) — this file is only the two
 * things a pure function cannot do: hold the list in React state, and talk to `localStorage`. That
 * split is deliberate, because storage is the half that can fail (Safari in private mode, a full
 * quota, a value written by a previous version) and it must not be able to corrupt what the list
 * MEANS.
 *
 * ⚠ Recent searches are PER DEVICE, not per profile — there is no endpoint for them, and inventing
 * shared history server-side would make one household member's searches visible to another. Kept
 * local on purpose; a phone that is handed to someone else shows that phone's own history.
 */
export function useRecentSearches(): {
  recent: string[];
  remember: (query: string) => void;
  clear: () => void;
} {
  // Read once, lazily: a corrupt or absent value yields [] rather than an exception on first render.
  const [recent, setRecent] = useState<string[]>(() => parseRecent(readRaw()));

  const remember = useCallback((query: string) => {
    setRecent((prev) => {
      const next = pushRecent(prev, query);
      writeRaw(next);
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    setRecent([]);
    writeRaw([]);
  }, []);

  return { recent, remember, clear };
}

/** Never throws: storage can be refused (private mode) or absent (a web view with no storage). */
function readRaw(): string | null {
  try {
    return window.localStorage.getItem(RECENT_KEY);
  } catch {
    return null;
  }
}

function writeRaw(list: string[]): void {
  try {
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(list));
  } catch {
    /* A screen that cannot remember is still a screen that searches. */
  }
}
