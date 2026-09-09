/** Premium surface card (design spec §52): layered surface, hairline border. */
export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-white/[.06] bg-surface-2/70 ${className}`}>{children}</div>
  );
}
