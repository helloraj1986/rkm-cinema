import { useToasts } from "./toast";

const KIND_STYLE: Record<string, string> = {
  ok: "border-emerald-500/40 text-emerald-100",
  err: "border-red-500/50 text-red-100",
  warn: "border-amber-500/50 text-amber-100",
};

const KIND_ICON: Record<string, string> = { ok: "✓", err: "✕", warn: "!" };

/** Renders the shared toast stack (mount once in the AppShell). */
export function Toaster() {
  const toasts = useToasts((s) => s.toasts);
  const dismiss = useToasts((s) => s.dismiss);
  if (!toasts.length) return null;
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className={`pointer-events-auto flex items-start gap-2.5 rounded-lg border bg-zinc-900/95 px-3 py-2.5 text-sm shadow-2xl shadow-black/60 backdrop-blur ${KIND_STYLE[t.kind] ?? KIND_STYLE.ok}`}
        >
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-black/40 text-xs font-bold">
            {KIND_ICON[t.kind] ?? "✓"}
          </span>
          <div className="min-w-0 flex-1">
            <div className="font-semibold text-zinc-100">{t.title}</div>
            {t.sub ? <div className="truncate text-xs text-zinc-400">{t.sub}</div> : null}
          </div>
          <button
            type="button"
            aria-label="Dismiss notification"
            onClick={() => dismiss(t.id)}
            className="rounded px-1 text-zinc-500 hover:text-zinc-200"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
