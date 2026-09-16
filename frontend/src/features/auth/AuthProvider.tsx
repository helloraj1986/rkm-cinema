/**
 * Session state for the whole app (AUTH_MULTIUSER_PLAN Phase 1, PLEX_PROFILE_AUTH_PLAN Phase B).
 *
 * Three facts are kept separately, and the separation is the point:
 *
 *   * `status` — what `GET /api/auth/me` said. `loading` until it answers, and a 401 is
 *     the ORDINARY signed-out answer (not an error, and never a sign-out event).
 *   * `enforcementSeen` — set the first time an ordinary APP call comes back 401. That
 *     refusal is the only evidence the server enforces sessions, and it is how Phase 2
 *     arms the frontend without the frontend changing: nothing is enforced today, so the
 *     app must keep working signed-out; the day it IS enforced, the first 401 flips this.
 *   * `profile` + `profileSelected` — WHO is watching. The server decides whether anybody has
 *     actually been chosen yet (`me().profile_selected`); this file only reports it. The session
 *     lasts 30 days and is the same one every device sees, so "I remember you picked the admin"
 *     is not something a browser may assert on its own.
 *
 * Signing in or out PURGES the React Query cache, so one person's rows cannot flash for the
 * next — the plan's §8.8. Switching profile does the same, for the same reason: Continue Watching
 * and resume rows belong to a person, not to the device.
 *
 * ⚠ Since A1 (`lib/query/persist.ts`) the cache also exists ON DISK, so every one of those events
 * goes through `clearCacheForIdentityChange()` — memory AND storage, in one call. A purge that
 * cleared only memory would leave one person's rows on a shared iPad for the next person's launch,
 * which is an identity leak rather than a stale render. See `persist-wiring.test.ts`.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";

import { api, setStaleProfileHandler, setUnauthorizedHandler, type AuthUser, type ProfileUserShape } from "../../lib/api/client";
import { adoptPersistedCache, clearCacheForIdentityChange, setPersistedCacheOwner } from "../../lib/query/persist";
import type { AuthStatus } from "./lib";

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  /** The profile in effect. Falls back to the session's owner until somebody picks one. */
  profile: AuthUser | null;
  /** Has the SERVER said a profile was chosen? False right after a fresh sign-in. */
  profileSelected: boolean;
  /** True once the server has refused an app call for want of a session. */
  enforcementSeen: boolean;
  /**
   * Phase 5: the server refused the credential the PROFILE was acting as while the session itself
   * is fine. The app keeps the session and asks "who's watching?" again — signing out would be the
   * wrong answer (see `client.ts::noteUnauthorized`).
   */
  profileStale: boolean;
  /** The server's own sentence about that refusal, shown on the picker. */
  staleReason: string;
  signIn: (username: string, password: string) => Promise<AuthUser>;
  signOut: () => Promise<void>;
  /** Switch who is watching (POST /api/auth/profile). Rejects with the server's refusal. */
  selectProfile: (userId: string, password: string) => Promise<ProfileUserShape>;
}

/**
 * Did this failure come from the SERVER (it answered, whatever it said) or from the NETWORK (nothing
 * answered)? The client's own `ApiError` carries the status; a `fetch` that never connected throws a
 * `TypeError` with none. ⚠ The check is `typeof status === "number"`, not truthiness: a 0 or a `null`
 * from some future wrapper must not be read as "the server answered".
 */
function answered(error: unknown): boolean {
  return typeof (error as { status?: unknown } | null)?.status === "number";
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [profile, setProfile] = useState<AuthUser | null>(null);
  const [profileSelected, setProfileSelected] = useState(false);
  const [enforcementSeen, setEnforcementSeen] = useState(false);
  const [profileStale, setProfileStale] = useState(false);
  const [staleReason, setStaleReason] = useState("");

  /** Any of the events that make a "stale profile" answer obsolete clears it, together. */
  const clearStale = useCallback(() => {
    setProfileStale(false);
    setStaleReason("");
  }, []);

  // Who is this browser — and, if nobody, does the SERVER even want a session?
  //
  // The second half is what keeps the enforced world from flashing: asking `me()` alone
  // would leave a signed-out visitor "usable" until their first data call came back 401,
  // so the app would mount and then be bounced to the login view. ONE probe call (a real
  // app route, the same one the app itself uses) answers it up front, and the guard can
  // then go straight to the login view. In the unenforced world the probe simply succeeds
  // and nothing changes.
  const applyMe = useCallback((me: { user: AuthUser; profile: AuthUser; profile_selected: boolean }) => {
    setUser(me.user);
    // Fall back to the owner when the server sent no profile row (an older api): that is the
    // server's own definition of "no profile chosen", so the two stay in agreement.
    const who = me.profile?.id ? me.profile : me.user;
    setProfile(who);
    setProfileSelected(Boolean(me.profile_selected));
    // ⚠ THE ONE MOMENT THE DISK CACHE MAY BE ADOPTED (NATIVE_FEEL plan §3.2/A1). The server has just
    // said who is watching, so a snapshot written FOR THIS PROFILE can be restored; a snapshot
    // belonging to anybody else (or another server, or an older schema) is dropped on the spot.
    // This is also the first moment app content can paint, so it costs nothing — `RequireSession`
    // holds a skeleton until `status` leaves "loading" (see `lib/query/persist.ts`).
    adoptPersistedCache(queryClient, who.id);
    // A fresh answer from the server about who is watching supersedes a stale-profile notice: if
    // `me()` can be read at all, the credential it authenticated with is not stale any more.
    clearStale();
  }, [clearStale, queryClient]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      // ⚠ TWO FACTS, NEVER ONE (B4, 2026-09-16). "The server refused this session" and "we could not
      // reach the server" used to arrive as the same answer — both fell out of the `catch` and became
      // `signedOut` — so a phone with the Wi-Fi off showed the SIGN-IN screen to somebody who is
      // signed in, with a form that cannot even be submitted (the server that would accept it is the
      // unreachable thing). `reachable` is set by any answer that carries an HTTP status; a 401 IS an
      // answer, a dropped connection is not.
      let reachable = false;
      try {
        const me = await api.me();
        if (cancelled) return;
        applyMe(me);
        setStatus("signedIn");
        return;
      } catch (error) {
        // 401 from /api/auth/me is the ordinary signed-out answer, not an error — but it is still an
        // ANSWER, and that is the difference that matters here.
        reachable = answered(error);
      }
      let enforced = false;
      try {
        await api.getConfig();
        reachable = true;
      } catch (err) {
        enforced = (err as { status?: number } | null)?.status === 401;
        if (answered(err)) reachable = true;
      }
      if (cancelled) return;
      if (enforced) setEnforcementSeen(true);
      setStatus(reachable ? "signedOut" : "unreachable");
    })();
    return () => {
      cancelled = true;
    };
  }, [applyMe]);

  // The ONE forced sign-out path: a 401 on an app call (the client fires it once per
  // burst, so six queries failing together are one sign-out).
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      setProfile(null);
      setProfileSelected(false);
      setStatus("signedOut");
      setEnforcementSeen(true);
      clearCacheForIdentityChange(queryClient); // the previous session's rows must not linger — memory OR disk
    });
    return () => setUnauthorizedHandler(null);
  }, [queryClient]);

  // The OTHER 401 (Phase 5): the session is alive and the credential the app was ACTING as is not,
  // so the client does NOT sign out — it calls this instead. A live session is kept, the rows that
  // came from the dead credential are dropped, and the guard sends the person to the picker (which
  // is the fix: choosing a profile is what re-authenticates it). The picker shows `staleReason`.
  useEffect(() => {
    setStaleProfileHandler((detail: string) => {
      clearCacheForIdentityChange(queryClient);
      setProfileStale(true);
      setStaleReason(detail);
    });
    return () => setStaleProfileHandler(null);
  }, [queryClient]);

  const signIn = useCallback(
    async (username: string, password: string) => {
      const result = await api.login(username, password);
      clearCacheForIdentityChange(queryClient); // a new session never inherits the old cache, memory or disk
      setUser(result.user);
      // A fresh session has NO profile (the server stores none until POST /api/auth/profile), so
      // the honest next screen is the picker. Confirm against `me()` rather than assuming it —
      // and if that call fails, stay with the server's own definition instead of inventing one.
      setProfile(result.user);
      setProfileSelected(false);
      clearStale();
      try {
        applyMe(await api.me());
      } catch {
        /* keep the fresh-session defaults above */
      }
      setStatus("signedIn");
      return result.user;
    },
    [applyMe, queryClient],
  );

  const selectProfile = useCallback(
    async (userId: string, password: string) => {
      const result = await api.selectProfile(userId, password);
      clearCacheForIdentityChange(queryClient); // the next person's rows must not flash (memory or disk)
      // ⚠ The purge above forgets who was watching, and this is the line that remembers the NEW
      // person: without it nothing would be written for the rest of the session, and the next
      // launch would restore nothing at all — a silent no-op, which is this repo's house failure.
      setPersistedCacheOwner(result.profile.id);
      setProfile(result.profile);
      setProfileSelected(true);
      // Choosing a profile IS the remedy for a refused credential — the notice has done its job.
      clearStale();
      // The response IS the server saying "this profile is now in effect", so `me()` need not be
      // asked again here. Keep the owner: only a sign-in may change who holds the session.
      return result.profile;
    },
    [clearStale, queryClient],
  );

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // The session is revoked server-side; a failed call must not trap the user in a
      // signed-in UI. Clearing locally is the honest fallback.
    }
    clearCacheForIdentityChange(queryClient);
    setUser(null);
    setProfile(null);
    setProfileSelected(false);
    clearStale();
    setStatus("signedOut");
  }, [clearStale, queryClient]);

  // Keep the latest callbacks reachable from the memo without re-creating it every render.
  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      profile,
      profileSelected,
      enforcementSeen,
      profileStale,
      staleReason,
      signIn,
      signOut,
      selectProfile,
    }),
    [status, user, profile, profileSelected, enforcementSeen, profileStale, staleReason,
     signIn, signOut, selectProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
