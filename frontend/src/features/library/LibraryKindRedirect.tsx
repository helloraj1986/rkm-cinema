import { Navigate, useLocation } from "react-router-dom";
import { useLibraryFolders } from "./api";

/**
 * Legacy /library/movies + /library/shows → the matching server folder
 * (MEDIA_LIBRARIES_PLAN Phase 5). Those paths predate configurable libraries;
 * they now resolve to the first server folder whose collection type is movies
 * / tvshows, preserving any ?genre=…&sort=… query so old deep links (e.g.
 * global-search genre hints) keep working. When the backend cannot enumerate
 * folders (provider not configured / not folder-aware) the redirect falls back
 * to /library/home — the sidebar's Libraries group is the real entry point.
 */
export function LibraryKindRedirect({ kind }: { kind: "movies" | "tvshows" }) {
  const { data } = useLibraryFolders();
  const location = useLocation();

  // While the folders query is still loading, render nothing (the redirect
  // lands once data arrives) — never guess a folder id.
  if (!data) return null;

  const folder = (data.folders ?? []).find(
    (f) => String(f.collection_type || "").toLowerCase() === kind,
  );
  const library = (data.libraries ?? []).find(
    (l) => l.ok && l.folder_id && String(l.collection_type || "").toLowerCase() === kind,
  );
  const folderId = library?.folder_id ?? folder?.id ?? null;

  if (!folderId) return <Navigate to="/library/home" replace />;
  const to = `/library/folder/${encodeURIComponent(folderId)}${location.search}`;
  return <Navigate to={to} replace />;
}
