/**
 * Settings → My password (ADMIN_CREDENTIALS_PLAN.md §6, Phase 3).
 *
 * The one screen every profile can use, and the reason it exists: until now a password could only
 * be changed by an ADMINISTRATOR, from the Household screen, for somebody else. A member — whose
 * password is their own Jellyfin credential, and the lock on their profile on a shared device —
 * had no way to change it themselves.
 *
 * What it does NOT do, deliberately:
 *  * it never shows a password, and never stores one — the value is typed, sent once, and never
 *    comes back;
 *  * it never decides whether the current password is required — the SERVER does. `hasPassword`
 *    only decides what the screen SAYS, so a password-less account is not blocked from changing a
 *    password it does not have;
 *  * it cannot target another account: the route changes the profile in effect, and the provider's
 *    call takes no user id at all.
 */
import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../lib/api/client";
import { useAuth } from "../auth/AuthProvider";
import { changeErrorMessage, changeIssue, MIN_HINT, type HasPassword } from "./password";

const INPUT =
  "w-full rounded-lg border border-white/10 bg-canvas px-3 py-2 text-sm outline-none focus:border-accent";
const PRIMARY =
  "rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-canvas transition disabled:opacity-60";

export function PasswordView() {
  const { profile } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  // Which profile this is, and whether it HAS a password — the server's answer, not a guess. The
  // same route the picker uses; null until it arrives, and null is treated as "don't require the
  // current password" (see password.ts).
  const profiles = useQuery({
    // The picker's own key, so the two screens share one answer.
    queryKey: ["auth", "profiles"],
    queryFn: () => api.profiles(),
  });
  const mine = profiles.data?.profiles?.find((p) => p.id === profile?.id);
  const hasPassword: HasPassword = profiles.data ? Boolean(mine?.has_password) : null;

  const decision = changeIssue(current, next, confirm, hasPassword);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api.changeMyPassword(next, current);
      setDone(true);
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setError(changeErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6 pb-8" data-testid="password-view">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100">My password</h1>
        <p className="mt-1 text-sm text-zinc-400">
          {profile?.name ? <>Signed in as {profile.name}. </> : null}
          This changes the password for the profile in effect — the one the app plays as. It is your
          media server credential too, so it also works in Jellyfin&apos;s own apps.
        </p>
      </div>

      <form
        onSubmit={onSubmit}
        className="max-w-md rounded-xl border border-white/[.08] bg-surface p-4"
      >
        {hasPassword === false ? (
          <p className="mb-3 text-xs text-zinc-400">
            Your account has no password yet. Leave the current one blank and choose a new one to
            set it — the profile picker will then ask for it.
          </p>
        ) : null}

        <label htmlFor="current-password" className="block text-xs font-medium text-zinc-300">
          Current password{" "}
          <span className="text-zinc-500">
            {hasPassword === true ? "(required)" : "(blank if you have none)"}
          </span>
        </label>
        <input
          id="current-password"
          type="password"
          className={`${INPUT} mt-1.5`}
          value={current}
          autoComplete="current-password"
          onChange={(e) => setCurrent(e.target.value)}
        />

        <label htmlFor="new-password" className="mt-3 block text-xs font-medium text-zinc-300">
          New password
        </label>
        <input
          id="new-password"
          type="password"
          className={`${INPUT} mt-1.5`}
          value={next}
          autoComplete="new-password"
          onChange={(e) => {
            setNext(e.target.value);
            setDone(false);
          }}
        />

        <label htmlFor="confirm-password" className="mt-3 block text-xs font-medium text-zinc-300">
          Repeat new password
        </label>
        <input
          id="confirm-password"
          type="password"
          className={`${INPUT} mt-1.5`}
          value={confirm}
          autoComplete="new-password"
          onChange={(e) => setConfirm(e.target.value)}
        />
        <p className="mt-2 text-[11px] text-zinc-500">{MIN_HINT}</p>

        {/* The reason doubles as a note when the change IS allowed (e.g. "your account has no
            password yet, so anything works here") — refusing is not the only thing worth saying. */}
        {decision.reason ? (
          <p data-testid="password-notice" className="mt-2 text-[11px] text-amber-300">
            {decision.reason}
          </p>
        ) : null}

        <div className="mt-4 flex items-center gap-3">
          <button type="submit" className={PRIMARY} disabled={!decision.allowed || busy}>
            {busy ? "Saving…" : "Change password"}
          </button>
          {done ? (
            <span
              role="status"
              data-testid="password-done"
              className="text-xs text-emerald-400"
            >
              Password changed.
            </span>
          ) : null}
        </div>

        {error ? (
          <p role="alert" data-testid="password-error" className="mt-3 text-sm text-red-400">
            {error}
          </p>
        ) : null}
      </form>
    </div>
  );
}
