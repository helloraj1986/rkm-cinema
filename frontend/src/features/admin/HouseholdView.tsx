/**
 * Household accounts — Settings → Household (AUTH_MULTIUSER_PLAN Phase 1b; redesigned 2026-09-13
 * from his `household_UX/` brief, HOUSEHOLD_UX_PLAN.md Phase 1).
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
 * The rails the server enforces (no self-delete, no last-admin delete, typed-name confirmation)
 * are mirrored here by `deleteDecision`/`confirmsName` so the button is honest BEFORE it is
 * pressed — the server is still the authority.
 *
 * ── The redesign, in one line ────────────────────────────────────────────────────────────────
 * Four layers, each quieter than the one above it: a bold page header, three summary cards
 * derived from the payload already in hand, one card per profile, and — the quietest layer — the
 * card's own actions, with everything that used to be an inline form behind a modal. The
 * mutations are untouched: same routes, same bodies.
 */
import { useState } from "react";

import { Icon } from "../../components/ui/Icon";
import { PopupMenu, type PopupMenuItem } from "../../components/ui/PopupMenu";
import { useAuth } from "../auth/AuthProvider";
import { initials } from "../auth/lib";
import { useGrantableLibraries, useHousehold, useHouseholdMutations } from "./api";
import {
  AddMemberModal,
  LibraryAccessModal,
  PasswordModal,
  RemoveModal,
  RenameModal,
} from "./HouseholdModals";
import {
  accessSummary,
  avatarToneIndex,
  deleteDecision,
  householdErrorMessage,
  householdSummary,
  lastLoginLabel,
  memberBadges,
  memberLibraryChips,
  passwordActionLabel,
  type GrantableLibrary,
  type HouseholdUser,
  type MemberBadgeTone,
} from "./lib";
import {
  CARD_BUTTON,
  CARD_SURFACE,
  GROUP_LABEL,
  PRIMARY_BUTTON,
  PRIMARY_SMALL_BUTTON,
} from "./ui";

/** Which modal is open, and for whom. */
interface DialogState {
  kind: "library" | "password" | "rename" | "remove";
  userId: string;
}

/**
 * The avatar palette: a person keeps the same colour because the index comes from their NAME
 * (`avatarToneIndex`, a pure function) rather than from their position in the list — a re-sorted
 * or re-fetched list must not repaint everybody.
 */
const AVATAR_TONES = [
  "bg-accent/[.14] text-accent ring-accent/25",
  "bg-emerald-500/[.14] text-emerald-300 ring-emerald-500/25",
  "bg-sky-500/[.14] text-sky-300 ring-sky-500/25",
  "bg-violet-500/[.14] text-violet-300 ring-violet-500/25",
  "bg-rose-500/[.14] text-rose-300 ring-rose-500/25",
];

const BADGE_TONES: Record<MemberBadgeTone, string> = {
  accent: "border-accent/40 bg-accent/[.08] text-accent",
  neutral: "border-white/15 bg-surface-3 text-zinc-300",
  warn: "border-transparent bg-amber-400/[.12] text-amber-300",
  muted: "border-white/10 text-zinc-500",
};

export function HouseholdView() {
  const { user: sessionUser } = useAuth();
  const household = useHousehold();
  const libraries = useGrantableLibraries();
  const { create, policy, rename, setPassword, remove } = useHouseholdMutations();

  const [dialog, setDialog] = useState<DialogState | null>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  const users: HouseholdUser[] = household.data?.users ?? [];
  const grantable: GrantableLibrary[] = libraries.data?.libraries ?? [];
  const signedInAs = household.data?.signed_in_as ?? sessionUser?.id ?? "";
  const summary = householdSummary(users, grantable);
  const target = dialog ? users.find((user) => user.id === dialog.userId) : undefined;

  function close() {
    setDialog(null);
    setAdding(false);
    setError("");
  }

  /** Run one mutation: on success the modal closes, on failure it stays open and says why. */
  async function run(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
      close();
      return true;
    } catch (err) {
      setError(householdErrorMessage(err));
      return false;
    }
  }

  return (
    <div className="flex flex-col gap-8 pb-8" data-testid="household-view">
      {/* ── Layer 1: the header. The boldest text on the page. ── */}
      <header className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[.12em] text-accent">
            Account · Household
          </p>
          <h1 className="mt-2 text-[32px] font-semibold leading-tight tracking-[-0.01em] text-zinc-100">
            Household
          </h1>
          <p className="mt-2 max-w-[560px] text-[14.5px] leading-relaxed text-zinc-400">
            Everyone signs in with their own account and keeps their own watch history and resume
            points. Choose which libraries each person can see — it&apos;s enforced the same way
            across every device.
          </p>
        </div>
        <button
          type="button"
          className={`${PRIMARY_BUTTON} shrink-0`}
          onClick={() => {
            setError("");
            setAdding(true);
          }}
        >
          <Icon name="plus" size={15} />
          Add member
        </button>
      </header>

      {/* ── Layer 2: the summary. Secondary weight, and computed from what is already here. ── */}
      <section aria-label="Household summary" className="grid gap-3.5 sm:grid-cols-3">
        <SummaryCard testId="summary-members" label="Household members" value={summary.members} />
        <SummaryCard testId="summary-active" label="Active profiles" value={summary.active} />
        <SummaryCard
          testId="summary-libraries"
          label="Libraries shared"
          value={summary.librariesShared}
        />
      </section>

      {household.isPending ? (
        <p className="text-sm text-zinc-400" role="status">
          Loading the household…
        </p>
      ) : null}

      {household.isError ? (
        <p
          role="alert"
          className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-300"
        >
          {householdErrorMessage(household.error)}
        </p>
      ) : null}

      {household.data && users.length === 0 ? (
        <p className="text-sm text-zinc-400">
          {household.data.warning || "No accounts on this server yet."}
        </p>
      ) : null}

      {/* ── Layer 3: one card per profile. ── */}
      {users.length > 0 ? (
        <section aria-label="Members">
          <p className={`${GROUP_LABEL} mb-3.5`}>Members</p>
          <ul className="flex flex-col gap-2.5">
            {users.map((member) => (
              <ProfileCard
                key={member.id}
                member={member}
                libraries={grantable}
                household={users}
                signedInAs={signedInAs}
                busy={policy.isPending || setPassword.isPending || remove.isPending}
                onOpen={(kind) => {
                  setError("");
                  setDialog({ kind, userId: member.id });
                }}
                onToggleDisabled={() =>
                  void run(() =>
                    policy.mutateAsync({ userId: member.id, disabled: !member.disabled }),
                  )
                }
              />
            ))}
          </ul>
        </section>
      ) : null}

      {/* ── Layer 4: the modals. Same mutations, same payloads — only the surface moved. ── */}
      {adding ? (
        <AddMemberModal
          libraries={grantable}
          busy={create.isPending}
          error={error}
          onClose={close}
          onCreate={(payload) => void run(() => create.mutateAsync(payload))}
        />
      ) : null}

      {target && dialog?.kind === "library" ? (
        <LibraryAccessModal
          member={target}
          libraries={grantable}
          busy={policy.isPending}
          error={error}
          onClose={close}
          onSave={(ids) =>
            void run(() => policy.mutateAsync({ userId: target.id, library_ids: ids }))
          }
        />
      ) : null}

      {target && dialog?.kind === "password" ? (
        <PasswordModal
          member={target}
          signedInAs={signedInAs}
          busy={setPassword.isPending}
          error={error}
          onClose={close}
          onSave={(newPassword) =>
            void run(() => setPassword.mutateAsync({ userId: target.id, newPassword }))
          }
        />
      ) : null}

      {target && dialog?.kind === "rename" ? (
        <RenameModal
          member={target}
          household={users}
          busy={rename.isPending}
          error={error}
          onClose={close}
          onSave={(name) => void run(() => rename.mutateAsync({ userId: target.id, name }))}
        />
      ) : null}

      {target && dialog?.kind === "remove" ? (
        <RemoveModal
          member={target}
          busy={remove.isPending}
          error={error}
          onClose={close}
          onConfirm={(confirmName) =>
            void run(() => remove.mutateAsync({ userId: target.id, confirmName }))
          }
        />
      ) : null}
    </div>
  );
}

function SummaryCard({ label, value, testId }: { label: string; value: number; testId: string }) {
  return (
    <div className={`${CARD_SURFACE} px-5 py-5`} data-testid={testId}>
      <p className="text-[30px] font-bold leading-none tracking-[-0.02em] text-zinc-100">{value}</p>
      <p className="mt-1 text-[13px] text-zinc-400">{label}</p>
    </div>
  );
}

/** One account: who it is, what it can see, and its actions. */
function ProfileCard({
  member,
  libraries,
  household,
  signedInAs,
  busy,
  onOpen,
  onToggleDisabled,
}: {
  member: HouseholdUser;
  libraries: GrantableLibrary[];
  household: HouseholdUser[];
  signedInAs: string;
  busy: boolean;
  onOpen: (kind: DialogState["kind"]) => void;
  onToggleDisabled: () => void;
}) {
  const isYou = member.id === signedInAs;
  const badges = memberBadges(member, signedInAs);
  const chips = memberLibraryChips(member, libraries);
  const access = accessSummary(member, libraries);
  const decision = deleteDecision(member, { signedInAs, household });
  const passwordLabel = passwordActionLabel(member, signedInAs);
  const avatar = member.disabled
    ? "bg-surface-3 text-zinc-500 ring-white/10"
    : AVATAR_TONES[avatarToneIndex(member.name, AVATAR_TONES.length)];

  // The overflow is for actions on SOMEBODY ELSE'S account: renaming, disabling or removing the
  // account you are signed in as is exactly what the server refuses, so a card that offered them
  // would be inviting a refusal (his §7 checklist: "no overflow menu" on your own row).
  const overflow: PopupMenuItem[] = [
    { key: "rename", label: "Rename", onSelect: () => onOpen("rename"), disabled: busy },
    {
      key: "toggle",
      label: member.disabled ? "Enable" : "Disable",
      onSelect: onToggleDisabled,
      disabled: busy,
    },
    {
      key: "remove",
      label: "Remove",
      onSelect: () => onOpen("remove"),
      disabled: busy || !decision.allowed,
      danger: true,
    },
  ];

  return (
    <li
      className={`${CARD_SURFACE} flex flex-wrap items-start gap-4 p-5`}
      data-testid={`member-${member.name}`}
    >
      <span
        aria-hidden="true"
        className={`grid h-12 w-12 shrink-0 place-items-center rounded-full text-base font-bold ring-1 ${avatar}`}
      >
        {initials(member.name)}
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-base font-semibold text-zinc-100">{member.name}</span>
          {badges.map((badge) => (
            <span
              key={badge.key}
              data-testid={`badge-${badge.key}`}
              className={`rounded-full border px-2 py-0.5 text-[10.5px] font-medium tracking-[.04em] ${BADGE_TONES[badge.tone]}`}
            >
              {badge.label}
            </span>
          ))}
        </div>

        <p className="mt-1 text-[13px] text-zinc-400">{lastLoginLabel(member.last_login)}</p>

        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {chips.map((chip) => (
            <span
              key={chip.key}
              data-testid="library-chip"
              className={`rounded-full border px-2.5 py-1 text-xs ${
                chip.every
                  ? "border-accent/30 bg-accent/[.06] text-accent"
                  : "border-white/[.06] bg-surface text-zinc-400"
              }`}
            >
              {chip.label}
            </span>
          ))}
        </div>

        {access.unknown.length > 0 ? (
          <p className="mt-2 text-xs text-amber-300">
            {access.unknown.length} granted library id(s) are not on this server any more — that
            grant currently does nothing. Re-tick the folders to fix it.
          </p>
        ) : null}

        {isYou ? (
          <p className="mt-2 text-xs text-zinc-500">
            This is the account you are signed in as — renaming, disabling and removing it are not
            offered.
          </p>
        ) : null}
        {!isYou && !decision.allowed ? (
          <p className="mt-2 text-xs text-zinc-500">{decision.reason}</p>
        ) : null}
      </div>

      {/* The quietest layer on the page. */}
      <div className="flex shrink-0 flex-wrap items-center gap-1.5">
        <button type="button" className={CARD_BUTTON} onClick={() => onOpen("library")}>
          Library access
        </button>
        <button
          type="button"
          className={member.has_password ? CARD_BUTTON : PRIMARY_SMALL_BUTTON}
          onClick={() => onOpen("password")}
        >
          {passwordLabel}
        </button>
        {isYou ? null : (
          <PopupMenu
            label={`More actions for ${member.name}`}
            triggerTestId={`member-more-${member.name}`}
            triggerClassName={CARD_BUTTON}
            items={overflow}
          />
        )}
      </div>
    </li>
  );
}
