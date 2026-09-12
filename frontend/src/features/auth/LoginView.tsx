/**
 * Sign-in screen (AUTH_MULTIUSER_PLAN Phase 1).
 *
 * Deliberately OUTSIDE the app shell (no sidebar, no header): it has to render when
 * nothing else can, including on the day enforcement is switched on and every other
 * route is refusing.
 *
 * What it does not do: it never stores the password, never puts it in a URL, and never
 * invents a difference between "no such user" and "wrong password" (`loginErrorMessage`
 * is generic on 401 by design — the API is too).
 */
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "./AuthProvider";
import { loginErrorMessage } from "./lib";

interface LocationState {
  /** Where the guard interrupted, so a deep link survives the sign-in. */
  from?: string;
}

export function LoginView() {
  const { status, user, enforcementSeen, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Already signed in (or a back-navigation) — do not show a form that would replace a
  // working session.
  if (status === "signedIn" && user) return <Navigate to="/library/home" replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await signIn(username.trim(), password);
      const from = (location.state as LocationState | null)?.from;
      navigate(from && from !== "/login" ? from : "/library/home", { replace: true });
    } catch (err) {
      setError(loginErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-dvh place-items-center bg-canvas px-4 py-10 text-zinc-100">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-3">
          <span
            className="grid h-10 w-10 place-items-center rounded-full bg-surface-3 text-sm font-bold text-accent ring-1 ring-white/10"
            aria-hidden="true"
          >
            R
          </span>
          <div>
            <h1 className="text-lg font-semibold">RKM Cinema</h1>
            <p className="text-xs text-zinc-400">Sign in with your Jellyfin account</p>
          </div>
        </div>

        <form
          onSubmit={onSubmit}
          className="space-y-4 rounded-2xl border border-white/[.08] bg-surface p-5"
        >
          <div className="space-y-1.5">
            <label htmlFor="rkm-username" className="block text-xs font-medium text-zinc-300">
              Username
            </label>
            <input
              id="rkm-username"
              name="username"
              type="text"
              autoComplete="username"
              autoFocus
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-canvas px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="rkm-password" className="block text-xs font-medium text-zinc-300">
              Password
            </label>
            {/* NOT `required`: a Jellyfin account can legitimately have NO password (that is
                how a household member can be added without one), and the browser would block
                an empty submit — making that account impossible to sign in with. The API
                decides; the form must not. */}
            <input
              id="rkm-password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-canvas px-3 py-2 text-sm outline-none focus:border-accent"
            />
            <p className="text-[11px] leading-relaxed text-zinc-500">
              Leave this blank if your Jellyfin account has no password.
            </p>
          </div>

          {error ? (
            <p role="alert" className="text-sm text-red-400">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-canvas transition disabled:opacity-60"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>

          <p className="text-xs leading-relaxed text-zinc-500">
            {enforcementSeen
              ? "This app needs a signed-in session. Use your Jellyfin account — the same one your other devices use."
              : "Signing in gives THIS browser its own Continue Watching, resume points and libraries. Nothing is enforced yet: the app stays usable signed out."}
          </p>
        </form>
      </div>
    </div>
  );
}
