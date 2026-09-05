import { REACT_FLAG_NAME } from "../lib/flags";

export function LegacyPlaceholder() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-950 p-6 text-center text-zinc-300">
      <h1 className="text-lg font-semibold text-white">RKM Cinema</h1>
      <p className="mt-3 max-w-md text-sm leading-relaxed text-zinc-400">
        The React shell is disabled right now, so the legacy app continues to serve this route.
        Build &amp; serve with the port enabled to preview the shell:
      </p>
      <pre className="mt-4 max-w-full overflow-x-auto rounded-lg bg-zinc-900 p-4 text-xs text-zinc-200">
        {`cd web\nVITE_ENABLE_REACT=1 npm run build\nnpm run preview`}
      </pre>
      <p className="mt-3 text-xs text-zinc-500">
        Set <code className="rounded bg-zinc-800 px-1">{REACT_FLAG_NAME}</code> once a view reaches
        parity (Phase 3–4) to hand that route to React.
      </p>
    </div>
  );
}