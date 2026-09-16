import { useEffect } from "react";

import { useAuth } from "../auth/AuthProvider";
import { startOfflineSession, stopOfflineSession } from "./session";

/**
 * Starts the offline session, and renders nothing (B4, `docs/adr/ADR-0010-offline-page.md`).
 *
 * ⚠ It is mounted by the SHELL rather than by the offline screens, and that is the whole reason it
 * exists as a component: the spool's replay loop has to be running when no offline surface is on
 * screen. He watches a film with the Wi-Fi off in the evening, closes the app, and opens it in the
 * lounge the next day — the position must find its way to Continue Watching without him first
 * opening a downloaded title to nudge it.
 *
 * ⚠ And it is keyed on WHO IS WATCHING: the queue on disk outlives a sign-out, so the session is
 * stamped with the profile id and refuses to replay another person's positions under this one
 * (`session.ts::startOfflineSession`, `spool.ts::parseSpoolEnvelope`).
 */
export function OfflineWiring() {
  const { status, profile, user } = useAuth();
  const owner = profile?.id ?? user?.id ?? "";

  // ⚠ IT STARTS ON `unreachable` TOO, and that is the whole point of the state existing: offline is
  // when a downloaded film is the only thing that plays, and a feature that only came alive once the
  // server answered would be a feature that never came alive at the moment it was needed. With no
  // answer from `/api/auth/me` there is no owner to stamp the queue with, so the session runs WITHOUT
  // one: the rows and the playback work, the queue is held in memory, and nothing is written to disk
  // under nobody's name (`spool.ts::writeSpool` refuses, and `readSpool` leaves an existing queue
  // untouched rather than deleting it).
  useEffect(() => {
    if (status === "loading") return;
    startOfflineSession(owner);
  }, [status, owner]);

  // One teardown for the session, which also makes a final best-effort attempt to replay what is
  // queued (the shell unmounts on sign-out — see the note in `stopOfflineSession`).
  useEffect(() => () => stopOfflineSession(), []);

  return null;
}
