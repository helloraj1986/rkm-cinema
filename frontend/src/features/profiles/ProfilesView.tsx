/**
 * "Who's watching?" — the profile picker (PLEX_PROFILE_AUTH_PLAN Phase B).
 *
 * Deliberately OUTSIDE the app shell, like the login view: it has to render when nothing else can,
 * including the instant after a sign-in and in the enforced world where every other route is
 * refusing.
 *
 * What it is: the Plex Home step. ONE credential (the administrator's) opened the server, and
 * everybody else arrives by picking a profile here. Each row says only what the SERVER said —
 * whether a password is needed, whether the profile is switched off, and whether it is the one in
 * effect right now (`profile_selected`, never a locally-remembered click).
 *
 * What it does NOT do:
 *  * it never offers an administrative route to a non-administrator profile — the household
 *    library list is refused while somebody else's profile is selected (decision 3), so this
 *    screen makes no such call at all; a profile's OWN libraries come with the selection response;
 *  * it never guesses why a selection was refused — `pickerErrorMessage` reports what the server
 *    answered, including the two refusals that are easy to mistake for a broken app: a protected
 *    profile's wrong password (401) and a disabled profile (403);
 *  * it never sends the password anywhere but POST /api/auth/profile, and never stores it.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { Icon } from "../../components/ui/Icon";
import { api, type ProfileUserShape } from "../../lib/api/client";
import { useAuth } from "../auth/AuthProvider";
import { initials } from "../auth/lib";
import { SessionSkeleton } from "../auth/RequireSession";
import {
  blockedReason,
  isSelectable,
  pickerErrorMessage,
  pickerSubtitle,
  requiresPassword,
  safeNext,
  watchingNow,
} from "./lib";

export function ProfilesView() {
  const { status, user, profileSelected, profileStale, staleReason, signOut, selectProfile } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Where to land once somebody has been chosen. A deep link that the guard interrupted is carried
  // through here, so "open that film" survives sign-in AND the picker.
  const query = new URLSearchParams(location.search);
  const next = safeNext(query.get("next"));
  // `?switch=1` is the header's "Switch profile". Without it, arriving here with somebody already
  // chosen means the visit was redundant (a back-navigation, say) and belongs back in the app —
  // but a person who ASKED to switch must not be bounced straight back out again.
  const switching = query.get("switch") === "1";

  const [askFor, setAskFor] = useState<ProfileUserShape | null>(null);
  const [password, setPassword] = useState("");
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");

  const { data, isPending } = useQuery({
    queryKey: ["auth", "profiles"],
    queryFn: () => api.profiles(),
    enabled: status === "signedIn",
  });

  if (status === "loading") return <SessionSkeleton />;
  if (status === "signedOut") return <Navigate to="/login" replace />;
  // Nothing to pick: somebody is already watching and nobody ASKED to switch, so this screen has no
  // business being seen. `switch=1` keeps the deliberate visit (the header's switcher) here.
  if (profileSelected && !switching && !askFor) return <Navigate to={next} replace />;

  async function choose(target: ProfileUserShape) {
    if (!isSelectable(target) || busyId) return;
    setError("");
    /**
     * ⚠ Picking the profile that is ALREADY watching is a no-op, not a sign-in — so it asks for
     * nothing and posts nothing. His report (2026-09-17): *"if you are already in one profile you
     * shouldn't be needing password to reenter"*. Asking here was the screen insisting on a password
     * to keep the state it was already in.
     *
     * ⚠ Gated on `profile_selected`, exactly as `watchingNow` is. `data.current` names the
     * LAST-USED profile even when nobody has been chosen yet, so keying off it alone would make the
     * server's own recommendation unselectable — the first version of this change did that, and the
     * picker simply refused to complete (caught before it shipped).
     */
    if (data?.profile_selected && currentRow && target.id === currentRow.id) {
      navigate(next, { replace: true });
      return;
    }
    if (requiresPassword(target)) {
      // Ask FIRST, always. The server refuses a blank attempt on the administrator's profile even
      // when that account has no password set, so a picker that posted straight away would look
      // broken on the admin row.
      setAskFor(target);
      setPassword("");
      return;
    }
    await submit(target.id, "");
  }

  async function submit(userId: string, value: string) {
    setBusyId(userId);
    setError("");
    try {
      await selectProfile(userId, value);
      setAskFor(null);
      setPassword("");
      navigate(next, { replace: true });
    } catch (err) {
      setError(pickerErrorMessage(err));
    } finally {
      setBusyId("");
    }
  }

  const rows = data?.profiles ?? [];
  const currentId = data?.current?.id ?? "";
  /** The profile watching right now, when there is one — the way back names it. */
  const currentRow = rows.find((row) => row.id === currentId) ?? null;

  return (
    <div className="grid min-h-dvh place-items-center bg-canvas px-4 py-10 text-zinc-100">
      {/* ⚠ `min-w-0` IS LOAD-BEARING, not tidying (measured 2026-09-17). This element is a GRID ITEM
          of the `place-items-center` grid above, so its automatic minimum size is its MIN-CONTENT
          width — and the subtitle inside it (`truncate` = `white-space: nowrap`) has a min-content
          width of the WHOLE SENTENCE: 348px for "pick who is watching", 494px for the signed-in
          variant. The grid track is floored there, and the document with it: `scrollWidth` measured
          416 (picker) and 562 (Switch Profile) at EVERY phone width from 320 to 430, i.e. content-
          driven, and it is what his iPhone pans on. The `min-w-0` on the flex row inside does not
          help; `max-w-full` here does not either; both were measured. This one closes it to exactly 0
          at 320/375/390/414/430 and lets the subtitle actually ellipsise.
          ⚠ The root `overflow-x: clip` guard in `styles/index.css` does NOT fix this — it was verified
          applied and the document still scrolled the full 172px by script. That rule's own note says
          it is "a GUARD, not a diagnosis"; this is the cause it was hiding. */}
      <div className="w-full max-w-2xl min-w-0" data-testid="profile-picker">
        <div className="mb-6 flex items-center gap-3">
          <span
            className="grid h-10 w-10 place-items-center rounded-full bg-surface-3 text-sm font-bold text-accent ring-1 ring-white/10"
            aria-hidden="true"
          >
            R
          </span>
          <div className="min-w-0">
            <h1 className="text-lg font-semibold">Who&apos;s watching?</h1>
            <p className="truncate text-xs text-zinc-400">
              {pickerSubtitle(rows.length, Boolean(data?.profile_selected))}
              {user ? ` Signed in to the server as ${user.name}.` : ""}
            </p>
          </div>
        </div>

        {/* ⚠ HIS REPORT (2026-09-17): *"once you clicked on Switch profile, you cannot escape without
            really switching to a user profile"*. Every other route out of this screen needed a
            selection to complete, so changing your mind had no answer. Whenever somebody is ALREADY
            watching, the way back is now part of the screen — first, above the list, named after who
            you would be going back to. */}
        {switching && currentRow ? (
          <button
            type="button"
            data-testid="picker-cancel"
            onClick={() => navigate(next, { replace: true })}
            className="mb-4 flex w-full items-center justify-center gap-2 rounded-2xl border border-white/[.08] bg-surface px-4 py-3 text-sm font-semibold text-zinc-200 transition hover:border-accent"
          >
            <Icon name="chevron-left" size={16} />
            Keep watching as {currentRow.name}
          </button>
        ) : null}

        {profileStale ? (
          <div
            role="alert"
            data-testid="stale-profile-notice"
            className="mb-4 rounded-2xl border border-amber-400/20 bg-amber-400/10 p-4 text-sm text-amber-100"
          >
            <p className="font-medium">Your profile&apos;s sign-in has expired.</p>
            <p className="mt-1 text-amber-200/80">
              {staleReason || "Pick it again to continue."}
            </p>
          </div>
        ) : null}

        {isPending ? (
          <p role="status" className="text-sm text-zinc-400">
            Loading profiles…
          </p>
        ) : null}

        {/* An empty list must say WHY — a refused or unreachable server reads exactly like
            "there are no profiles on this server", which is a different and alarming thing. */}
        {!isPending && rows.length === 0 ? (
          <div
            role="alert"
            className="rounded-2xl border border-white/[.08] bg-surface p-5 text-sm text-zinc-300"
          >
            <p className="font-medium text-zinc-100">No profiles could be listed.</p>
            <p className="mt-1 text-zinc-400">
              {data?.warning || "The media server did not report any accounts."}
            </p>
          </div>
        ) : null}

        <ul
          className="grid grid-cols-2 gap-3 sm:grid-cols-3"
          data-testid="profile-rows"
          aria-label="Profiles on this server"
        >
          {rows.map((row) => {
            const here = watchingNow(row.id, currentId, Boolean(data?.profile_selected));
            const locked = requiresPassword(row);
            const selectable = isSelectable(row);
            const reason = blockedReason(row);
            return (
              <li key={row.id}>
                <button
                  type="button"
                  data-testid={`profile-${row.id}`}
                  data-profile-name={row.name}
                  onClick={() => void choose(row)}
                  disabled={!selectable || Boolean(busyId)}
                  aria-describedby={reason ? `why-${row.id}` : undefined}
                  className={`w-full rounded-2xl border p-4 text-left transition ${
                    selectable
                      ? "border-white/[.08] bg-surface hover:border-accent"
                      : "cursor-not-allowed border-white/[.06] bg-surface opacity-50"
                  }`}
                >
                  <span className="flex items-center gap-3">
                    <span
                      className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-surface-3 text-sm font-bold text-accent ring-1 ring-white/10"
                      aria-hidden="true"
                    >
                      {initials(row.name)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{row.name}</span>
                      <span className="block text-[11px] text-zinc-500">
                        {here ? "Watching now" : row.is_admin ? "Administrator" : "Profile"}
                        {locked ? " · password" : ""}
                      </span>
                    </span>
                    {locked ? (
                      <Icon
                        name="lock"
                        size={15}
                        className="shrink-0 text-zinc-400"
                        data-testid={`lock-${row.id}`}
                        role="img"
                        aria-label={`${row.name} needs a password`}
                      />
                    ) : null}
                  </span>
                  {reason ? (
                    <span id={`why-${row.id}`} className="mt-2 block text-[11px] text-amber-400">
                      {reason}
                    </span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>

        {askFor ? (
          <form
            data-testid="profile-password-form"
            className="mt-4 space-y-3 rounded-2xl border border-white/[.08] bg-surface p-5"
            onSubmit={(event) => {
              event.preventDefault();
              if (busyId) return;
              void submit(askFor.id, password);
            }}
          >
            <p className="text-sm font-medium">
              {askFor.name} needs its password
              <span className="block text-[11px] font-normal text-zinc-500">
                {askFor.is_admin
                  ? "The administrator's own profile always asks — that is what keeps a shared device from walking into it."
                  : "This profile is password-protected."}
              </span>
            </p>
            <label htmlFor="rkm-profile-password" className="block text-xs font-medium text-zinc-300">
              Password
            </label>
            {/* NOT `required`: the API decides. A blank attempt is refused by the SERVER on the
                administrator's profile, and a password-less profile must open with nothing typed. */}
            {/* ⚠ NO `autoFocus` — the §7.3 trap, and the likely cause of his "horizontal scrolling"
                on this screen (2026-09-17): raising the keyboard on arrival inside a
                `min-h-dvh place-items-center` frame shifts the visual viewport, and iOS pans the page
                sideways to keep the focused field visible. The field is one tap away and the person
                just tapped the profile that owns it; on iOS the keyboard should arrive when they say
                so, not when the page does. */}
            <input
              id="rkm-profile-password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-lg border border-white/10 bg-canvas px-3 py-2 text-sm outline-none focus:border-accent"
            />
            <div className="flex items-center gap-2">
              <button
                type="submit"
                disabled={Boolean(busyId)}
                className="rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-canvas transition disabled:opacity-60"
              >
                {busyId ? "Switching…" : `Watch as ${askFor.name}`}
              </button>
              <button
                type="button"
                onClick={() => {
                  setAskFor(null);
                  setPassword("");
                  setError("");
                }}
                className="rounded-lg border border-white/10 px-3 py-2 text-sm font-medium text-zinc-300 transition hover:border-accent hover:text-accent"
              >
                Cancel
              </button>
            </div>
          </form>
        ) : null}

        {error ? (
          <p role="alert" className="mt-4 text-sm text-red-400">
            {error}
          </p>
        ) : null}

        <div className="mt-6 flex items-center gap-3">
          {/* Nobody is trapped here: a household profile has no sign-out of its own, but a guest on
              the device must be able to hand it back. There is deliberately no "skip" — while
              somebody is signed in to the server, choosing who is watching IS the way in. */}
          <button
            type="button"
            onClick={() => void signOut()}
            className="rounded-full border border-white/10 px-3 py-1.5 text-xs font-medium text-zinc-300 transition hover:border-accent hover:text-accent"
          >
            Sign out
          </button>
        </div>

        <p className="mt-6 text-xs leading-relaxed text-zinc-500">
          Only the administrator signs in to this server. Everyone else picks their profile — the
          same Jellyfin account, so the phone and TV apps show the same watching history.
        </p>
      </div>
    </div>
  );
}
