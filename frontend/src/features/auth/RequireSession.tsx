/**
 * The route guard (AUTH_MULTIUSER_PLAN Phase 1).
 *
 * All the thinking is in `guardDecision` (pure, unit-tested); this component only renders
 * its answer. While the session check is in flight it shows a SKELETON — never the app
 * (which might then be replaced by a login form) and never a login form for someone who
 * is already signed in.
 */
import { Navigate } from "react-router-dom";

import { useAuth } from "./AuthProvider";
import { guardDecision } from "./lib";

export function RequireSession({ children }: { children: React.ReactNode }) {
  const { status, enforcementSeen } = useAuth();
  const decision = guardDecision({ status, enforcementSeen });

  if (decision === "skeleton") return <SessionSkeleton />;
  if (decision === "login") return <Navigate to="/login" replace />;
  return <>{children}</>;
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
