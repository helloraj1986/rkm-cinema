export function Header() {
  return (
    <header className="flex h-14 items-center justify-between border-b border-zinc-800 px-6">
      <h1 className="text-sm font-medium text-zinc-300">Dashboard</h1>
      <div className="flex items-center gap-2 text-xs">
        <span className="rounded-full bg-emerald-900/50 px-2.5 py-0.5 text-emerald-300 ring-1 ring-emerald-700">
          React shell
        </span>
      </div>
    </header>
  );
}