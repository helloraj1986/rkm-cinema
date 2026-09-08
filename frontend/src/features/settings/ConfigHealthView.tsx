import { useConfig, useHealth } from "./api";
import { Card } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { REACT_FLAG_NAME } from "../../lib/flags";

const SERVICES = ["radarr", "sonarr", "tmdb", "plex", "jellyfin", "emby"] as const;

export function ConfigHealthView() {
  const config = useConfig();
  const health = useHealth();

  if (config.isLoading || health.isLoading) {
    return <div className="text-sm text-zinc-400">Loading backend status…</div>;
  }
  if (config.isError || health.isError) {
    return (
      <Card>
        <p className="text-sm text-red-400">
          Couldn&apos;t reach the backend. If you ran the legacy app check, the React shell
          needs its own build: <code className="rounded bg-zinc-800 px-1">npm run build</code> then serve with{" "}
          <code className="rounded bg-zinc-800 px-1">{REACT_FLAG_NAME}=1</code>, or run{" "}
          <code className="rounded bg-zinc-800 px-1">npm run dev</code> (dev proxy → :8000).
        </p>
      </Card>
    );
  }

  const services = config.data?.services;
  const detail = health.data?.serviceDetail ?? {};

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div>
        <h2 className="text-base font-semibold text-white">Backend status</h2>
        <p className="mt-1 text-xs text-zinc-500">
          Read from the frozen <code className="rounded bg-zinc-800 px-1">/api/config</code> +{" "}
          <code className="rounded bg-zinc-800 px-1">/api/health</code> contract. Watchlist updated{" "}
          {config.data?.updated || "—"} · {health.data?.titleCount ?? 0} titles.
        </p>
        {health.data?.degraded && (
          <p className="mt-2 inline-block rounded bg-amber-900/30 px-2 py-1 text-xs text-amber-300 ring-1 ring-amber-700">
            ⚠ Degraded — at least one service is unhealthy.
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {SERVICES.map((name) => {
          const enabled = Boolean(services?.[name]);
          const d = detail[name];
          return (
            <Card key={name}>
              <div className="flex items-center justify-between">
                <span className="text-sm capitalize text-zinc-300">{name}</span>
                <div className="flex items-center gap-2">
                  {d && <Badge ok={d.ok} label={d.ok ? "ok" : "down"} />}
                  <Badge ok={enabled} label={enabled ? "configured" : "unconfigured"} />
                </div>
              </div>
              {d?.error && <p className="mt-2 text-xs text-red-400">{d.error}</p>}
              {d?.detail && <p className="mt-2 text-xs text-zinc-500">{d.detail}</p>}
            </Card>
          );
        })}
      </div>
    </div>
  );
}