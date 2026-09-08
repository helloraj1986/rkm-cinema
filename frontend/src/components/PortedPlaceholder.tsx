export function PortedPlaceholder({ label }: { label: string }) {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center text-center">
      <div className="text-sm font-medium text-zinc-300">{label}</div>
      <p className="mt-2 max-w-sm text-xs leading-relaxed text-zinc-500">
        This view is still served by the legacy app. It ports to this React shell in Phase 3
        (feature slice), then turns on behind the flag at parity.
      </p>
    </div>
  );
}