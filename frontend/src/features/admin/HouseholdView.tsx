/**
 * Household accounts (AUTH_MULTIUSER_PLAN Phase 1b) — Settings → Household.
 *
 * The app's own front end for **Jellyfin's** user management: who exists, who may see which
 * library, and the same jobs an admin would do in the Jellyfin dashboard — add a member, tick
 * their folders, reset a password, disable or remove them.
 *
 * Two things this screen deliberately does NOT do:
 *  * it never invents authority — every call goes to a route that re-checks, LIVE, that the
 *    signed-in account is an enabled Jellyfin administrator, so a non-admin who lands here
 *    sees the refusal, not a broken screen;
 *  * it never shows or stores a password. One is typed, sent once, and never comes back.
 *
 * The rails the server enforces (no self-delete, no last-admin delete, typed-name
 * confirmation) are mirrored here by `deleteDecision`/`confirmsName` so the button is honest
 * BEFORE it is pressed — the server is still the authority.
 */
import { useState, type FormEvent, type ReactNode } from "react";

import { useAuth } from "../auth/AuthProvider";
import { useGrantableLibraries, useHousehold, useHouseholdMutations } from "./api";
import {
  accessSummary,
  confirmsName,
  defaultLibrarySelection,
  deleteDecision,
  householdErrorMessage,
  lastLoginLabel,
  type GrantableLibrary,
  type HouseholdUser,
} from "./lib";

const BUTTON =
  "rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-zinc-200 transition hover:border-accent hover:text-accent disabled:opacity-50";
const PRIMARY =
  "rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-canvas transition disabled:opacity-60";
const INPUT =
  "w-full rounded-lg border border-white/10 bg-canvas px-3 py-2 text-sm outline-none focus:border-accent";
const PANEL = "mt-3 rounded-xl border border-white/[.08] bg-surface p-4";

export function HouseholdView() {
  const { user: sessionUser } = useAuth();
  const household = useHousehold();
  const libraries = useGrantableLibraries();
  const { create, policy, setPassword, remove } = useHouseholdMutations();

  const [showAdd, setShowAdd] = useState(false);

  const users: HouseholdUser[] = household.data?.users ?? [];
  const grantable: GrantableLibrary[] = libraries.data?.libraries ?? [];
  const signedInAs = household.data?.signed_in_as ?? sessionUser?.id ?? "";

  return (
    <div className="space-y-5">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Household</h1>
          <p className="mt-1 max-w-2xl text-sm text-zinc-400">
            Each member signs in with their own Jellyfin account and gets their own Continue
            Watching, resume points and libraries. Tick which libraries a member may see — the
            server enforces it, exactly as Jellyfin&apos;s own apps do.
          </p>
        </div>
        <button type="button" className={BUTTON} onClick={() => setShowAdd((v) => !v)}>
          {showAdd ? "Cancel" : "+ Add member"}
        </button>
      </header>

      {showAdd ? (
        <AddMemberForm
          libraries={grantable}
          busy={create.isPending}
          onSubmit={async (payload) => {
            await create.mutateAsync(payload);
            setShowAdd(false);
          }}
        />
      ) : null}

      {household.isPending ? (
        <p className="text-sm text-zinc-400" role="status">
          Loading the household…
        </p>
      ) : null}

      {household.isError ? (
        <p role="alert" className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-300">
          {householdErrorMessage(household.error)}
        </p>
      ) : null}

      {household.data && users.length === 0 ? (
        <p className="text-sm text-zinc-400">
          {household.data.warning || "No accounts on this server yet."}
        </p>
      ) : null}

      <ul className="space-y-3">
        {users.map((member) => (
          <MemberRow
            key={member.id}
            member={member}
            libraries={grantable}
            signedInAs={signedInAs}
            household={users}
            busy={policy.isPending || setPassword.isPending || remove.isPending}
            onSaveFolders={(ids) => policy.mutateAsync({ userId: member.id, library_ids: ids })}
            onToggleDisabled={(disabled) =>
              policy.mutateAsync({ userId: member.id, disabled })
            }
            onSetPassword={(newPassword) =>
              setPassword.mutateAsync({ userId: member.id, newPassword })
            }
            onDelete={(confirmName) =>
              remove.mutateAsync({ userId: member.id, confirmName })
            }
          />
        ))}
      </ul>
    </div>
  );
}

/** The add form: a name, an OPTIONAL password, and the folder tick-boxes. */
function AddMemberForm({
  libraries,
  busy,
  onSubmit,
}: {
  libraries: GrantableLibrary[];
  busy: boolean;
  onSubmit: (payload: { name: string; password: string; library_ids: string[] }) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [selected, setSelected] = useState<string[]>(() => defaultLibrarySelection(libraries));
  const [error, setError] = useState("");

  // The library list can arrive after this form mounts (two requests) — pre-tick everything
  // until the person touches the boxes, so the default really is "all".
  const [touched, setTouched] = useState(false);
  const effective = touched ? selected : defaultLibrarySelection(libraries);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await onSubmit({ name: name.trim(), password, library_ids: effective });
      setName("");
      setPassword("");
      setTouched(false);
    } catch (err) {
      setError(householdErrorMessage(err));
    }
  }

  return (
    <form onSubmit={submit} className={PANEL} data-testid="add-member-form">
      <h2 className="text-sm font-semibold text-zinc-200">New household member</h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label htmlFor="member-name" className="block text-xs font-medium text-zinc-300">
            Name
          </label>
          <input
            id="member-name"
            className={INPUT}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Priya"
            required
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="member-password" className="block text-xs font-medium text-zinc-300">
            Password <span className="font-normal text-zinc-500">(optional)</span>
          </label>
          <input
            id="member-password"
            type="password"
            className={INPUT}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
          />
          <p className="text-[11px] leading-relaxed text-zinc-500">
            Leave blank to create the member with <strong>no password</strong> — they sign in
            with just their username. Only do that while this app stays on your tailnet: anyone
            who can reach it could use that account.
          </p>
        </div>
      </div>

      <fieldset className="mt-4">
        <legend className="text-xs font-medium text-zinc-300">Libraries this member can see</legend>
        <div className="mt-2 flex flex-wrap gap-x-5 gap-y-2">
          {libraries.length === 0 ? (
            <p className="text-xs text-zinc-500">No libraries were reported by the server.</p>
          ) : null}
          {libraries.map((library) => (
            <label key={library.id} className="flex items-center gap-2 text-sm text-zinc-200">
              <input
                type="checkbox"
                className="h-4 w-4 accent-[#FFC400]"
                checked={effective.includes(library.id)}
                onChange={(e) => {
                  setTouched(true);
                  setSelected((current) => {
                    const base = current.length ? current : effective;
                    return e.target.checked
                      ? [...new Set([...base, library.id])]
                      : base.filter((id) => id !== library.id);
                  });
                }}
              />
              {library.name}
            </label>
          ))}
        </div>
      </fieldset>

      {error ? (
        <p role="alert" className="mt-3 text-sm text-red-400">
          {error}
        </p>
      ) : null}

      <div className="mt-4">
        <button type="submit" className={PRIMARY} disabled={busy || !name.trim()}>
          {busy ? "Creating…" : "Create member"}
        </button>
      </div>
    </form>
  );
}

/** One account: what it is, what it can see, and its actions. */
function MemberRow({
  member,
  libraries,
  household,
  signedInAs,
  busy,
  onSaveFolders,
  onToggleDisabled,
  onSetPassword,
  onDelete,
}: {
  member: HouseholdUser;
  libraries: GrantableLibrary[];
  household: HouseholdUser[];
  signedInAs: string;
  busy: boolean;
  onSaveFolders: (ids: string[]) => Promise<unknown>;
  onToggleDisabled: (disabled: boolean) => Promise<unknown>;
  onSetPassword: (newPassword: string) => Promise<unknown>;
  onDelete: (confirmName: string) => Promise<unknown>;
}) {
  const [open, setOpen] = useState<"folders" | "password" | "remove" | null>(null);
  const [error, setError] = useState("");
  const access = accessSummary(member, libraries);
  const decision = deleteDecision(member, { signedInAs, household });
  const isYou = member.id === signedInAs;

  async function run(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
      setOpen(null);
    } catch (err) {
      setError(householdErrorMessage(err));
    }
  }

  return (
    <li className={PANEL} data-testid={`member-${member.name}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-zinc-100">
            {member.name}
            {isYou ? <Tag tone="accent">You</Tag> : null}
            {member.is_admin ? <Tag>Administrator</Tag> : null}
            {member.disabled ? <Tag tone="warn">Disabled</Tag> : null}
            {member.has_password ? null : <Tag>No password</Tag>}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            Sees: <span className="text-zinc-300">{access.label}</span> ·{" "}
            {lastLoginLabel(member.last_login)}
          </p>
          {access.unknown.length > 0 ? (
            <p className="mt-1 text-xs text-amber-300">
              {access.unknown.length} granted library id(s) are not on this server any more — that
              grant currently does nothing. Re-tick the folders to fix it.
            </p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className={BUTTON}
            onClick={() => setOpen(open === "folders" ? null : "folders")}
          >
            Folders
          </button>
          <button
            type="button"
            className={BUTTON}
            onClick={() => setOpen(open === "password" ? null : "password")}
          >
            {member.has_password ? "Reset password" : "Set a password"}
          </button>
          {!isYou ? (
            <button
              type="button"
              className={BUTTON}
              disabled={busy}
              onClick={() => void run(() => onToggleDisabled(!member.disabled))}
            >
              {member.disabled ? "Enable" : "Disable"}
            </button>
          ) : null}
          <button
            type="button"
            className={BUTTON}
            disabled={!decision.allowed || busy}
            title={decision.allowed ? "" : decision.reason}
            onClick={() => setOpen(open === "remove" ? null : "remove")}
          >
            Remove
          </button>
        </div>
      </div>

      {!decision.allowed ? (
        <p className="mt-2 text-xs text-zinc-500">{decision.reason}</p>
      ) : null}

      {open === "folders" ? (
        <FolderTicks
          libraries={libraries}
          member={member}
          onCancel={() => setOpen(null)}
          onSave={(ids) => void run(() => onSaveFolders(ids))}
        />
      ) : null}

      {open === "password" ? (
        <InlinePassword
          onCancel={() => setOpen(null)}
          onSave={(value) => void run(() => onSetPassword(value))}
        />
      ) : null}

      {open === "remove" ? (
        <InlineRemove
          name={member.name}
          onCancel={() => setOpen(null)}
          onConfirm={(typed) => void run(() => onDelete(typed))}
        />
      ) : null}

      {error ? (
        <p role="alert" className="mt-3 text-sm text-red-400">
          {error}
        </p>
      ) : null}
    </li>
  );
}

function FolderTicks({
  libraries,
  member,
  onSave,
  onCancel,
}: {
  libraries: GrantableLibrary[];
  member: HouseholdUser;
  onSave: (ids: string[]) => void;
  onCancel: () => void;
}) {
  const [all, setAll] = useState(member.enable_all_folders);
  const [ids, setIds] = useState<string[]>(
    member.enable_all_folders ? defaultLibrarySelection(libraries) : member.enabled_folders,
  );

  return (
    <div className="mt-3 border-t border-white/[.06] pt-3" data-testid="folder-ticks">
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        {libraries.map((library) => (
          <label key={library.id} className="flex items-center gap-2 text-sm text-zinc-200">
            <input
              type="checkbox"
              className="h-4 w-4 accent-[#FFC400]"
              disabled={all}
              checked={all || ids.includes(library.id)}
              onChange={(e) =>
                setIds((current) =>
                  e.target.checked
                    ? [...new Set([...current, library.id])]
                    : current.filter((id) => id !== library.id),
                )
              }
            />
            {library.name}
          </label>
        ))}
        <label className="flex items-center gap-2 text-sm text-zinc-200">
          <input
            type="checkbox"
            className="h-4 w-4 accent-[#FFC400]"
            checked={all}
            onChange={(e) => setAll(e.target.checked)}
          />
          Every library
        </label>
      </div>
      <div className="mt-3 flex gap-2">
        <button type="button" className={PRIMARY} onClick={() => onSave(all ? [] : ids)}>
          Save folders
        </button>
        <button type="button" className={BUTTON} onClick={onCancel}>
          Cancel
        </button>
      </div>
      {!all && ids.length === 0 ? (
        <p className="mt-2 text-xs text-amber-300">
          With nothing ticked this member sees no libraries at all.
        </p>
      ) : null}
    </div>
  );
}

function InlinePassword({
  onSave,
  onCancel,
}: {
  onSave: (value: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState("");
  return (
    <div className="mt-3 border-t border-white/[.06] pt-3" data-testid="password-panel">
      <label htmlFor="reset-password" className="block text-xs font-medium text-zinc-300">
        New password
      </label>
      <input
        id="reset-password"
        type="password"
        className={`${INPUT} mt-1.5 max-w-sm`}
        value={value}
        autoComplete="new-password"
        onChange={(e) => setValue(e.target.value)}
      />
      <p className="mt-1 text-[11px] text-zinc-500">
        Sent once to the media server and never stored here. Tell the member yourself.
      </p>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          className={PRIMARY}
          disabled={!value}
          onClick={() => onSave(value)}
        >
          Save password
        </button>
        <button type="button" className={BUTTON} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function InlineRemove({
  name,
  onConfirm,
  onCancel,
}: {
  name: string;
  onConfirm: (typed: string) => void;
  onCancel: () => void;
}) {
  const [typed, setTyped] = useState("");
  return (
    <div className="mt-3 border-t border-white/[.06] pt-3" data-testid="remove-panel">
      <p className="text-sm text-zinc-300">
        Type <strong className="text-zinc-100">{name}</strong> to confirm. This removes the
        account from the media server and cannot be undone.
      </p>
      <input
        id="confirm-name"
        className={`${INPUT} mt-1.5 max-w-sm`}
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
      />
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          className="rounded-lg bg-red-500/90 px-3 py-2 text-sm font-semibold text-white transition disabled:opacity-50"
          disabled={!confirmsName(typed, name)}
          onClick={() => onConfirm(typed)}
        >
          Remove member
        </button>
        <button type="button" className={BUTTON} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function Tag({ children, tone = "default" }: { children: ReactNode; tone?: "default" | "accent" | "warn" }) {
  const styles =
    tone === "accent"
      ? "border-accent/40 text-accent"
      : tone === "warn"
        ? "border-amber-400/40 text-amber-300"
        : "border-white/15 text-zinc-400";
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${styles}`}>
      {children}
    </span>
  );
}
