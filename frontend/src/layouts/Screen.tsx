import type { ReactNode } from "react";
import { useLayoutMode } from "./LayoutMode";

/**
 * The per-route chooser — `MOBILE_FIRST_UI_PLAN` §3.3.
 *
 *     <Screen desktop={<LibraryFolderView />} mobile={<BrowseScreen />} />
 *
 * ⚠ **Only the chosen subtree is rendered — never both.** Two live trees would double every
 * `useEffect`, every observer and every `aria-*` surface, and would make the desktop gates measure a
 * page that also contains a phone.
 *
 * ⚠ A route renders through this rather than branching on `useLayoutMode()` itself, so the decision
 * lives in ONE place and the two trees stay siblings of the router's element instead of being the
 * route's own conditionals. The pages are different components, so crossing the boundary here DOES
 * swap the tree (unlike the shell, which M1 built to keep the page mounted): a phone screen and a
 * desktop screen are not the same page at two sizes.
 */
export function Screen({ desktop, mobile }: { desktop: ReactNode; mobile: ReactNode }) {
  return <>{useLayoutMode() === "mobile" ? mobile : desktop}</>;
}
