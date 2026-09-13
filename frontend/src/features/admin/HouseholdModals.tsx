/**
 * The Household screen's modals (HOUSEHOLD_UX_PLAN.md Phase 1, 2026-09-13).
 *
 * His brief, verbatim: *"All three should submit to the same existing endpoints … this is purely
 * moving those calls behind a modal instead of an inline row or separate view."* So every one of
 * these is a THIN shell: it collects the value, mirrors the rails the server enforces so the button
 * is honest before it is pressed, and hands the same payload to the same mutation the old inline
 * form called.
 *
 * `Dialog` (components/ui) is reused rather than rebuilt — it already owns the focus trap, the
 * backdrop, Escape and focus restore (design spec §51), and it is what the mockup expects. Two
 * dialogs beyond his three (Rename, Remove) exist because deleting the inline forms without a home
 * for those actions would remove the capability, not the clutter.
 */
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { Icon } from "../../components/ui/Icon";
import { Dialog } from "../../components/ui/Dialog";
import {
  confirmsName,
  defaultLibrarySelection,
  folderSelectionPayload,
  passwordConfirmIssue,
  passwordModalTitle,
  renameIssue,
  type GrantableLibrary,
  type HouseholdUser,
} from "./lib";
import { DANGER_BUTTON, FIELD_LABEL, INPUT, PRIMARY_BUTTON, SUBTLE_BUTTON } from "./ui";

/**
 * A close handler with a STABLE identity.
 *
 * ⚠ `Dialog`'s effect depends on `onClose`, so an inline arrow from the page re-runs it on every
 * parent render — which re-focuses the panel (stealing focus out of the field being typed in) and
 * re-registers its listeners. Holding the callback in a ref keeps the dialog's effect to one run.
 */
function useStableCallback(fn: () => void): () => void {
  const ref = useRef(fn);
  useEffect(() => {
    ref.current = fn;
  }, [fn]);
  return useCallback(() => ref.current(), []);
}

/** The chrome every modal here shares: title, one-line purpose, close, body, actions. */
function ModalChrome({
  title,
  subtitle,
  titleId,
  onClose,
  children,
  footer,
  testId,
}: {
  title: string;
  subtitle: string;
  titleId: string;
  onClose: () => void;
  children: ReactNode;
  footer: ReactNode;
  testId: string;
}) {
  const close = useStableCallback(onClose);
  return (
    <Dialog labelledBy={titleId} onClose={close} panelClassName="max-w-md p-6">
      <div data-testid={testId} className="flex flex-col">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h2 id={titleId} className="text-lg font-semibold text-zinc-100">
              {title}
            </h2>
            <p className="mt-0.5 text-[13px] text-zinc-400">{subtitle}</p>
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={close}
            className="-mr-1 -mt-1 rounded-md p-1 text-zinc-500 transition hover:bg-white/[.06] hover:text-zinc-200"
          >
            <Icon name="close" size={18} />
          </button>
        </div>
        <div className="min-w-0">{children}</div>
        <div className="mt-5 flex justify-end gap-2.5">{footer}</div>
      </div>
    </Dialog>
  );
}

function ErrorLine({ message }: { message: string }) {
  if (!message) return null;
  return (
    <p role="alert" className="mt-3 text-sm text-red-400">
      {message}
    </p>
  );
}

/** One checkbox row. `data-testid` lets a browser check tick a library by NAME, not by index. */
function LibraryChecklist({
  libraries,
  checked,
  disabled = false,
  onToggle,
}: {
  libraries: GrantableLibrary[];
  checked: string[];
  disabled?: boolean;
  onToggle: (id: string, next: boolean) => void;
}) {
  if (libraries.length === 0) {
    return <p className="text-xs text-zinc-500">No libraries were reported by the server.</p>;
  }
  return (
    <div className="flex flex-col gap-0.5">
      {libraries.map((library) => (
        <label
          key={library.id}
          data-testid={`library-row-${library.name}`}
          className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-zinc-200 transition hover:bg-white/[.03]"
        >
          <input
            type="checkbox"
            className="h-4 w-4 accent-[#FFC400]"
            disabled={disabled}
            checked={disabled || checked.includes(library.id)}
            onChange={(event) => onToggle(library.id, event.target.checked)}
          />
          {library.name}
        </label>
      ))}
    </div>
  );
}

export function LibraryAccessModal({
  member,
  libraries,
  busy,
  error,
  onClose,
  onSave,
}: {
  member: HouseholdUser;
  libraries: GrantableLibrary[];
  busy: boolean;
  error: string;
  onClose: () => void;
  onSave: (ids: string[]) => void;
}) {
  const [all, setAll] = useState(member.enable_all_folders);
  const [ids, setIds] = useState<string[]>(
    member.enable_all_folders ? defaultLibrarySelection(libraries) : member.enabled_folders,
  );

  const toggle = (id: string, next: boolean) =>
    setIds((current) =>
      next ? [...new Set([...current, id])] : current.filter((value) => value !== id),
    );

  return (
    <ModalChrome
      titleId="library-modal-title"
      title="Library access"
      subtitle="Choose which libraries this profile can see."
      onClose={onClose}
      testId="library-modal"
      footer={
        <>
          <button type="button" className={SUBTLE_BUTTON} onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className={PRIMARY_BUTTON}
            disabled={busy}
            onClick={() => onSave(folderSelectionPayload(all, ids, libraries))}
          >
            Save access
          </button>
        </>
      }
    >
      <LibraryChecklist libraries={libraries} checked={ids} disabled={all} onToggle={toggle} />
      <label
        data-testid="library-every"
        className="mt-1 flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-zinc-200 transition hover:bg-white/[.03]"
      >
        <input
          type="checkbox"
          className="h-4 w-4 accent-[#FFC400]"
          checked={all}
          onChange={(event) => setAll(event.target.checked)}
        />
        Every library
      </label>
      {!all && ids.length === 0 ? (
        <p className="mt-2 px-2.5 text-xs text-amber-300">
          With nothing ticked this member sees no libraries at all.
        </p>
      ) : null}
      <ErrorLine message={error} />
    </ModalChrome>
  );
}

export function PasswordModal({
  member,
  signedInAs,
  busy,
  error,
  onClose,
  onSave,
}: {
  member: HouseholdUser;
  signedInAs: string;
  busy: boolean;
  error: string;
  onClose: () => void;
  onSave: (newPassword: string) => void;
}) {
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const issue = passwordConfirmIssue(next, confirm);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (issue) return;
    onSave(next);
  }

  return (
    <ModalChrome
      titleId="password-modal-title"
      title={passwordModalTitle(member, signedInAs)}
      subtitle="This profile will use it to sign in on any device."
      onClose={onClose}
      testId="password-modal"
      footer={
        <>
          <button type="button" className={SUBTLE_BUTTON} onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            form="password-modal-form"
            className={PRIMARY_BUTTON}
            disabled={busy || Boolean(issue)}
          >
            Save password
          </button>
        </>
      }
    >
      <form id="password-modal-form" onSubmit={submit}>
        <label htmlFor="modal-new-password" className={FIELD_LABEL}>
          New password
        </label>
        <input
          id="modal-new-password"
          type="password"
          className={`${INPUT} mt-1.5`}
          value={next}
          autoComplete="new-password"
          onChange={(event) => setNext(event.target.value)}
        />
        <label htmlFor="modal-confirm-password" className={`${FIELD_LABEL} mt-3 block`}>
          Confirm password
        </label>
        <input
          id="modal-confirm-password"
          type="password"
          className={`${INPUT} mt-1.5`}
          value={confirm}
          autoComplete="new-password"
          onChange={(event) => setConfirm(event.target.value)}
        />
        {/* The issue doubles as the note that explains the disabled button — never a silent block. */}
        {issue && next ? <p className="mt-2 text-xs text-amber-300">{issue}</p> : null}
        <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">
          Sent once to the media server and never stored here, and never shown again. Tell the
          member yourself.
        </p>
      </form>
      <ErrorLine message={error} />
    </ModalChrome>
  );
}

export function AddMemberModal({
  libraries,
  busy,
  error,
  onClose,
  onCreate,
}: {
  libraries: GrantableLibrary[];
  busy: boolean;
  error: string;
  onClose: () => void;
  onCreate: (payload: { name: string; password: string; library_ids: string[] }) => void;
}) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [touched, setTouched] = useState(false);

  // The library list can arrive after this modal mounts (two requests) — pre-tick everything until
  // the person touches the boxes, so the default really is "all" (the administrator's own access).
  // ⚠ `touched` (not "is anything ticked") is what switches over: unticking every box is a
  // legitimate choice — it creates a member who sees nothing — and must not snap back to all.
  const effective = touched ? selected : defaultLibrarySelection(libraries);

  function submit(event: FormEvent) {
    event.preventDefault();
    onCreate({ name: name.trim(), password, library_ids: effective });
  }

  return (
    <ModalChrome
      titleId="add-member-title"
      title="Add a member"
      subtitle="Create a new profile for your household."
      onClose={onClose}
      testId="add-member-modal"
      footer={
        <>
          <button type="button" className={SUBTLE_BUTTON} onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            form="add-member-form"
            className={PRIMARY_BUTTON}
            disabled={busy || !name.trim()}
          >
            {busy ? "Creating…" : "Create member"}
          </button>
        </>
      }
    >
      <form id="add-member-form" onSubmit={submit}>
        <label htmlFor="member-name" className={FIELD_LABEL}>
          Name
        </label>
        <input
          id="member-name"
          className={`${INPUT} mt-1.5`}
          value={name}
          placeholder="e.g. Priya"
          autoComplete="off"
          onChange={(event) => setName(event.target.value)}
          required
        />
        <label htmlFor="member-password" className={`${FIELD_LABEL} mt-3 block`}>
          Password <span className="font-normal text-zinc-500">(optional)</span>
        </label>
        <input
          id="member-password"
          type="password"
          className={`${INPUT} mt-1.5`}
          value={password}
          autoComplete="new-password"
          onChange={(event) => setPassword(event.target.value)}
        />
        <p className="mt-1.5 text-[11px] leading-relaxed text-zinc-500">
          Leave blank to create the member with <strong className="font-semibold">no password</strong>{" "}
          — they sign in with just their username. Only do that while this app stays on your
          tailnet: anyone who can reach it could use that account.
        </p>

        <p className={`${FIELD_LABEL} mt-4`}>Libraries this member can see</p>
        <div className="mt-1">
          <LibraryChecklist
            libraries={libraries}
            checked={effective}
            onToggle={(id, next) => {
              setTouched(true);
              setSelected((current) => {
                const base = current.length ? current : effective;
                return next
                  ? [...new Set([...base, id])]
                  : base.filter((value) => value !== id);
              });
            }}
          />
        </div>
      </form>
      <ErrorLine message={error} />
    </ModalChrome>
  );
}

export function RenameModal({
  member,
  household,
  busy,
  error,
  onClose,
  onSave,
}: {
  member: HouseholdUser;
  household: HouseholdUser[];
  busy: boolean;
  error: string;
  onClose: () => void;
  onSave: (name: string) => void;
}) {
  const [value, setValue] = useState(member.name);
  const decision = renameIssue(value, member.name, household);

  return (
    <ModalChrome
      titleId="rename-modal-title"
      title="Rename"
      subtitle="How this person is shown everywhere — the picker, the top bar, this list."
      onClose={onClose}
      testId="rename-modal"
      footer={
        <>
          <button type="button" className={SUBTLE_BUTTON} onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className={PRIMARY_BUTTON}
            disabled={busy || !decision.allowed}
            onClick={() => onSave(value)}
          >
            Save name
          </button>
        </>
      }
    >
      <label htmlFor="rename-member-name" className={FIELD_LABEL}>
        Name
      </label>
      <input
        id="rename-member-name"
        className={`${INPUT} mt-1.5`}
        value={value}
        autoComplete="off"
        onChange={(event) => setValue(event.target.value)}
      />
      <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">
        It changes nothing else: not their libraries, not their password, not their watch state.{" "}
        {member.is_admin ? "The Administrator tag rides with the account, not the name." : ""}
      </p>
      {!decision.allowed ? <p className="mt-1 text-[11px] text-zinc-500">{decision.reason}</p> : null}
      <ErrorLine message={error} />
    </ModalChrome>
  );
}

export function RemoveModal({
  member,
  busy,
  error,
  onClose,
  onConfirm,
}: {
  member: HouseholdUser;
  busy: boolean;
  error: string;
  onClose: () => void;
  onConfirm: (typed: string) => void;
}) {
  const [typed, setTyped] = useState("");
  return (
    <ModalChrome
      titleId="remove-modal-title"
      title="Remove member"
      subtitle="This removes the account from the media server and cannot be undone."
      onClose={onClose}
      testId="remove-modal"
      footer={
        <>
          <button type="button" className={SUBTLE_BUTTON} onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className={DANGER_BUTTON}
            disabled={busy || !confirmsName(typed, member.name)}
            onClick={() => onConfirm(typed)}
          >
            Remove member
          </button>
        </>
      }
    >
      <p className="text-sm text-zinc-300">
        Type <strong className="font-semibold text-zinc-100">{member.name}</strong> to confirm.
      </p>
      <input
        id="confirm-name"
        className={`${INPUT} mt-2`}
        value={typed}
        autoComplete="off"
        onChange={(event) => setTyped(event.target.value)}
      />
      <ErrorLine message={error} />
    </ModalChrome>
  );
}
