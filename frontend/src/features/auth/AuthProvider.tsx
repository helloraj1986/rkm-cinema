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

import { api, setUnauthorizedHandler, type AuthUser, type ProfileUserShape } from "../../lib/api/client";
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
  signIn: (username: string, password: string) => Promise<AuthUser>;
  signOut: () => Promise<void>;
  /** Switch who is watching (POST /api/auth/profile). Rejects with the server's refusal. */
  selectProfile: (userId: string, password: string) => Promise<ProfileUserShape>;
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
    setProfile(me.profile?.id ? me.profile : me.user);
    setProfileSelected(Boolean(me.profile_selected));
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const me = await api.me();
        if (cancelled) return;
        applyMe(me);
        setStatus("signedIn");
        return;
      } catch {
        // 401 from /api/auth/me is the ordinary signed-out answer, not an error.
      }
      let enforced = false;
      try {
        await api.getConfig();
      } catch (err) {
        enforced = (err as { status?: number } | null)?.status === 401;
      }
      if (cancelled) return;
      if (enforced) setEnforcementSeen(true);
      setStatus("signedOut");
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
      queryClient.clear(); // the previous session's rows must not linger
    });
    return () => setUnauthorizedHandler(null);
  }, [queryClient]);

  const signIn = useCallback(
    async (username: string, password: string) => {
      const result = await api.login(username, password);
      queryClient.clear(); // a new session never inherits the old cache
      setUser(result.user);
      // A fresh session has NO profile (the server stores none until POST /api/auth/profile), so
      // the honest next screen is the picker. Confirm against `me()` rather than assuming it —
      // and if that call fails, stay with the server's own definition instead of inventing one.
      setProfile(result.user);
      setProfileSelected(false);
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
      queryClient.clear(); // the next person's rows must not flash
      setProfile(result.profile);
      setProfileSelected(true);
      // The response IS the server saying "this profile is now in effect", so `me()` need not be
      // asked again here. Keep the owner: only a sign-in may change who holds the session.
      return result.profile;
    },
    [queryClient],
  );

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // The session is revoked server-side; a failed call must not trap the user in a
      // signed-in UI. Clearing locally is the honest fallback.
    }
    queryClient.clear();
    setUser(null);
    setProfile(null);
    setProfileSelected(false);
    setStatus("signedOut");
  }, [queryClient]);

  // Keep the latest callbacks reachable from the memo without re-creating it every render.
  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      profile,
      profileSelected,
      enforcementSeen,
      signIn,
      signOut,
      selectProfile,
    }),
    [status, user, profile, profileSelected, enforcementSeen, signIn, signOut, selectProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
