import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { MobileNav } from "./MobileNav";
import { Toaster } from "../../features/watchlist/Toaster";

/**
 * App shell (design spec §4/§38/§76): the sidebar is sticky with its own fixed
 * height (content scrolls past it), the 64px top bar is sticky/blurred, and a
 * mobile bottom navigation bar takes over under md. The full-screen player and
 * toasts layer above via the z-index system (spec §75).
 */
export function AppShell() {
  return (
    <div className="min-h-dvh bg-canvas text-zinc-100">
      <div className="flex min-h-dvh">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Header />
          <main className="min-w-0 flex-1">
            <div className="mx-auto w-full max-w-[1720px] px-4 pb-24 pt-4 sm:px-6 md:pb-12 lg:px-8 xl:px-10">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
      <MobileNav />
      <Toaster />
    </div>
  );
}
