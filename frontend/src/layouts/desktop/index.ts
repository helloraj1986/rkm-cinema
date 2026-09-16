/**
 * `layouts/desktop/` — a THIN index, and deliberately nothing more (MOBILE_FIRST_UI_PLAN §2.2,
 * brief §2a).
 *
 * ⚠ **No view moved.** Every one of these re-exports reads from exactly where it lived before
 * this phase. That is the whole point: a physical move into `layouts/desktop/` would be a large
 * diff with zero behaviour change, it would break every existing import path and every
 * reviewer's mental map, and it would put the mature web layout at risk for a filing
 * preference.
 *
 * What it buys is that a route can read symmetrically:
 *
 *     <Screen desktop={<desktop.LibraryHomeView />} mobile={<mobile.HomeScreen />} />
 *
 * …and that a future move, if it is ever actually wanted, is a one-file change here rather
 * than a sweep of the router.
 *
 * ⚠ `layouts/desktop/` is NOT governed by `layouts/importRule.ts`. These files ARE the product's
 * rules — the ban exists to stop the mobile shell re-deriving them, not to handicap the shell
 * that owns them.
 */

export { LoginView } from "../../features/auth/LoginView";
export { ProfilesView } from "../../features/profiles/ProfilesView";
export { ConfigHealthView } from "../../features/settings/ConfigHealthView";
export { PasswordView } from "../../features/settings/PasswordView";
export { HouseholdView } from "../../features/admin/HouseholdView";
export { LibraryLayout } from "../../features/library/LibraryLayout";
export { LibraryHomeView } from "../../features/library/LibraryHomeView";
export { LibraryFolderView } from "../../features/library/LibraryFolderView";
export { LibraryKindRedirect } from "../../features/library/LibraryKindRedirect";
export { ItemDetailPage } from "../../features/library/ItemDetailPage";
export { DiscoverView } from "../../features/discover/DiscoverView";
export { WatchlistView } from "../../features/watchlist/WatchlistView";
export { SuggestView } from "../../features/suggest/SuggestView";
export { DownloadsView } from "../../features/offline/DownloadsView";
