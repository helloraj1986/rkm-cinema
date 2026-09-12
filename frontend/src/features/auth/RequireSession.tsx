/**
 * The route guard (AUTH_MULTIUSER_PLAN Phase 1; PLEX_PROFILE_AUTH_PLAN Phase B).
 *
 * All the thinking is in `guardDecision` (pure, unit-tested); this component only renders
 * its answer. While the session check is in flight it shows a SKELETON — never the app
 * (which might then be replaced by a login form) and never a login form for someone who
 * is already signed in.
 *
 * Phase B adds the third answer: a session with NO PROFILE CHOSEN goes to the picker, carrying the
 * page the visitor asked for (`?next=`) so a deep link survives the question of who is watching.
 */
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "./AuthProvider";
import { guardDecision } from "./lib";

export function RequireSession({ children }: { children: React.ReactNode }) {
  const { status, enforcementSeen, profileSelected } = useAuth();
  const location = useLocation();
  const decision = guardDecision({ status, enforcementSeen, profileSelected });

  if (decision === "skeleton") return <SessionSkeleton />;
  if (decision === "login") {
    return <Navigate to="/login" replace state={{ from: here(location) }} />;
  }
  if (decision === "picker") {
    return <Navigate to={`/profiles?next=${encodeURIComponent(here(location))}`} replace />;
  }
  return <>{children}</>;
}

/** The page being asked for, path + query, for the login/picker round trip. */
function here(location: { pathname: string; search: string }): string {
  return `${location.pathname}${location.search || ""}`;
}

/** Shown only for the instant the session check takes, on app startup. */
export function SessionSkeleton() {
  return (
    <div
      className="grid min-h-dvh place-items-center bg-canvas text-zinc-400"
      role="status"
      aria-live="polite"
      aria-label="Checking your session"
    >
      <div className="flex flex-col items-center gap-3">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-white/15 border-t-accent" />
        <p className="text-sm">Checking your session…</p>
      </div>
    </div>
  );
}
