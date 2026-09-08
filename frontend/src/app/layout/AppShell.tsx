import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { Toaster } from "../../features/watchlist/Toaster";

/**
 * App shell: sidebar + header + routed content. The React port is the only UI
 * (the legacy vanilla app was removed), so the shell always renders.
 */
export function AppShell() {
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
      <Toaster />
    </div>
  );
}
