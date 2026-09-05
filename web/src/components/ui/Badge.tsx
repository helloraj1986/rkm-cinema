export function Badge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${
        ok
          ? "bg-emerald-900/40 text-emerald-300 ring-emerald-700"
          : "bg-red-900/40 text-red-300 ring-red-800"
      }`}
    >
      {label}
    </span>
  );
}