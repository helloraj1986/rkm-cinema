/**
 * Session state for the whole app (AUTH_MULTIUSER_PLAN Phase 1).
 *
 * Two facts are kept separately, and the separation is the point:
 *
 *   * `status` — what `GET /api/auth/me` said. `loading` until it answers, and a 401 is
 *     the ORDINARY signed-out answer (not an error, and never a sign-out event).
 *   * `enforcementSeen` — set the first time an ordinary APP call comes back 401. That
 *     refusal is the only evidence the server enforces sessions, and it is how Phase 2
 *     arms the frontend without the frontend changing: nothing is enforced today, so the
 *     app must keep working signed-out; the day it IS enforced, the first 401 flips this.
 *
 * Signing in or out PURGES the React Query cache, so one person's rows cannot flash for
 * the next — the plan's §8.8.
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

import { api, setUnauthorizedHandler, type AuthUser } from "../../lib/api/client";
import type { AuthStatus } from "./lib";

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  /** True once the server has refused an app call for want of a session. */
  enforcementSeen: boolean;
  signIn: (username: string, password: string) => Promise<AuthUser>;
  signOut: () => Promise<void>;
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
  const [enforcementSeen, setEnforcementSeen] = useState(false);

  // Who is this browser — and, if nobody, does the SERVER even want a session?
  //
  // The second half is what keeps the enforced world from flashing: asking `me()` alone
  // would leave a signed-out visitor "usable" until their first data call came back 401,
  // so the app would mount and then be bounced to the login view. ONE probe call (a real
  // app route, the same one the app itself uses) answers it up front, and the guard can
  // then go straight to the login view. In the unenforced world the probe simply succeeds
  // and nothing changes.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const me = await api.me();
        if (cancelled) return;
        setUser(me.user);
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
  }, []);

  // The ONE forced sign-out path: a 401 on an app call (the client fires it once per
  // burst, so six queries failing together are one sign-out).
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
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
      setStatus("signedIn");
      return result.user;
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
    setStatus("signedOut");
  }, [queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, enforcementSeen, signIn, signOut }),
    [status, user, enforcementSeen, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
