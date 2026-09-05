import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { LegacyPlaceholder } from "../../components/LegacyPlaceholder";

/**
 * App shell: sidebar + header + routed content. When the React port is not yet
 * enabled (feature flag off), it renders a pointer to the legacy app instead.
 */
export function AppShell({ enabled }: { enabled: boolean }) {
  if (!enabled) {
    return <LegacyPlaceholder />;
  }
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Header />
          <main className="flex-1 p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}