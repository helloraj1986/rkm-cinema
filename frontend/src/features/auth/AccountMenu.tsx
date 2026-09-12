import { useNavigate } from "react-router-dom";

import { Icon } from "../../components/ui/Icon";
import { PopupMenu } from "../../components/ui/PopupMenu";
import { useAuth } from "./AuthProvider";
import { useCurrentProfile } from "./useCurrentProfile";
import {
  accountDestinations,
  accountSubtitle,
  displayName,
  initials,
  watchingName,
} from "./lib";

/**
 * THE ACCOUNT MENU — the one place everything about the signed-in person lives
 * (his request, 2026-09-13: *"'my password' doesn't need to be sitting on the left side bar, it can
 * simply reside when user click its avatar … consolidate the ui elements to make it premium"*).
 *
 * Before this, four separate controls crowded the header (the name, an avatar that was only an
 * image, a "Switch profile" link and a "Sign out" button) and two more sat in the sidebar nav
 * (My password, for everyone; Household, for administrators) plus two in the mobile sheet — the
 * same three destinations offered in three different places, differently. Now: ONE trigger (the
 * avatar) with the identity it belongs to, and the destinations in `accountDestinations()`.
 *
 * Two surfaces share it, both from this component so a rule cannot drift between them:
 * * `variant="chip"` — the header avatar (every breakpoint, so the phone gets it too).
 * * `variant="wide"` — the sidebar footer, where the account conventionally lives on desktop
 *   (it replaces a purely decorative identity card, which told you who you were and offered
 *   nothing).
 *
 * Household comes from the SERVER's own answer about the profile in effect (`useCurrentProfile` →
 * `/api/auth/profiles`, whose `current` row carries `is_admin`), through `mayManageHousehold`, which
 * fails closed. A member is never invited to a screen that will refuse them, and the server refuses
 * those routes regardless — this only decides what is OFFERED.
 */
export function AccountMenu({ variant = "chip" }: { variant?: "chip" | "wide" }) {
  const navigate = useNavigate();
  const { status, user, profile, profileSelected, signOut } = useAuth();
  // ⚠ The SERVER's row for the profile in effect. It used to be a name-only stub, so `is_admin`
  // was always false and the gate hid Household from the administrator too (found 2026-09-13).
  const currentProfile = useCurrentProfile();
  const isAdmin = currentProfile?.is_admin;
  const signedIn = status === "signedIn" && !!user;

  if (!signedIn) {
    // Nothing about "the account" exists yet — the header keeps its own Sign in affordance, and the
    // sidebar keeps its neutral card (the app is fully usable signed out; enforcement is off).
    return null;
  }

  const name = watchingName(profile, user);
  const owner = displayName(user);
  const destinations = accountDestinations(isAdmin, profileSelected);

  return (
    <PopupMenu
      label={`Account menu for ${name}`}
      triggerLabel={`Watching as ${name}`}
      align={variant === "wide" ? "left" : "right"}
      triggerTestId={variant === "wide" ? "account-menu-trigger-wide" : "account-menu-trigger"}
      triggerClassName={
        variant === "wide"
          ? "flex w-full items-center gap-2.5 rounded-[10px] px-3 py-2 text-left transition-colors hover:bg-white/[.06]"
          : "grid h-9 w-9 shrink-0 place-items-center rounded-full bg-surface-3 text-xs font-bold text-accent ring-1 ring-white/10 transition hover:ring-accent/60"
      }
      header={
        <div className="flex items-center gap-2.5 px-1">
          <span
            aria-hidden="true"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-surface-2 to-surface-3 text-xs font-bold text-accent ring-1 ring-white/10"
          >
            {initials(name)}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[13px] font-semibold text-zinc-100">{name}</span>
            <span className="block truncate text-[10.5px] text-zinc-500">
              {accountSubtitle(name, profileSelected ? owner : "", isAdmin)}
            </span>
          </span>
        </div>
      }
      items={[
        ...destinations.map((destination) => ({
          key: destination.key,
          label: destination.label,
          icon: destination.icon,
          onSelect: () => navigate(destination.to),
        })),
        {
          key: "signout",
          label: "Sign out",
          icon: "logout" as const,
          // Destructive-ish and deliberately LAST, separated: signing out is not navigation, and it
          // must never sit next to "Switch profile" where a thumb could hit it by accident.
          danger: true,
          onSelect: () => void signOut(),
        },
      ]}
    >
      {variant === "wide" ? (
        <>
          <span
            data-testid="account-avatar"
            aria-hidden="true"
            className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-surface-3 text-[11px] font-bold text-accent ring-1 ring-white/10"
          >
            {initials(name)}
          </span>
          {/* The sidebar collapses to a 76px icon rail between md and xl, so the name, the role and
              the chevron appear only where there is room for them (the old card did the same). */}
          <span className="hidden min-w-0 flex-1 xl:block">
            <span className="block truncate text-xs font-semibold text-zinc-200">{name}</span>
            <span className="block truncate text-[10.5px] text-zinc-500">
              {accountSubtitle(name, profileSelected ? owner : "", isAdmin)}
            </span>
          </span>
          <Icon name="chevron-down" size={14} className="hidden shrink-0 text-zinc-500 xl:block" />
        </>
      ) : (
        <span data-testid="account-avatar" aria-hidden="true">
          {initials(name)}
        </span>
      )}
    </PopupMenu>
  );
}
