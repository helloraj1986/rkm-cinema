import { useConfig, useHealth } from "./api";
import { useLibraryFolders } from "../library/api";
import { libraryIconFor } from "../library/lib";
import { Card } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Icon, type IconName } from "../../components/ui/Icon";
import { artTone } from "../library/lib";

// One media server (Jellyfin) plus the acquisition/metadata services the api
// reports on. /api/health is the source of truth and no longer reports the
// retired backends.
const SERVICES = ["radarr", "sonarr", "tmdb", "jellyfin"] as const;

const SERVICE_ICON: Record<(typeof SERVICES)[number], IconName> = {
  radarr: "film",
  sonarr: "tv",
  tmdb: "star",
  jellyfin: "play",
};

/**
 * Settings (design spec §5/§82 polish): page header with the live status
 * summary, then per-service health cards. Premium states — skeleton while the
 * backend answers, EmptyState-style error when it can't, human copy only.
 */
export function ConfigHealthView() {
  const config = useConfig();
  const health = useHealth();
  const folders = useLibraryFolders();

  if (config.isLoading || health.isLoading) {
    return (
      <div className="flex flex-col gap-6 pb-8" aria-busy="true" aria-label="Loading settings">
        <div>
          <div className="skeleton h-8 w-40 rounded-lg" />
          <div className="skeleton mt-2 h-4 w-72 rounded" />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {SERVICES.map((name) => (
            <div key={name} className="flex items-center justify-between rounded-xl border border-white/[.06] bg-surface-2/70 p-4">
              <div className="flex items-center gap-3">
                <span className="grid h-9 w-9 place-items-center rounded-lg bg-surface-3 text-zinc-500">
                  <Icon name={SERVICE_ICON[name]} size={16} />
                </span>
                <span className="capitalize text-zinc-400">{name}</span>
              </div>
              <div className="skeleton h-5 w-20 rounded-full" />
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (config.isError || health.isError) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-white/[.08] py-20 text-center">
        <div className="grid h-14 w-14 place-items-center rounded-2xl bg-surface-2 text-zinc-500">
          <Icon name="settings" size={24} />
        </div>
        <div className="max-w-sm">
          <h2 className="font-semibold text-zinc-200">Couldn't reach the backend</h2>
          <p className="mt-1 text-sm leading-relaxed text-zinc-500">
            Settings read the live /api/config + /api/health contract. Check the api container, then reload.
          </p>
        </div>
      </div>
    );
  }

  const services = config.data?.services;
  const detail = health.data?.serviceDetail ?? {};
  const degraded = Boolean(health.data?.degraded);
  const tone = artTone("settings");

  return (
    <div className="flex flex-col gap-7 pb-8">
      <div className="flex flex-wrap items-end justify-between gap-4 pt-2">
        <div>
          <h1 className="text-[32px] font-bold leading-none tracking-[-0.02em] text-zinc-50">Settings</h1>
          <p className="mt-2 text-[13px] text-zinc-500">
            Backend status & services — watchlist updated {config.data?.updated || "—"} · {health.data?.titleCount ?? 0} titles.
          </p>
        </div>
        <div
          className={`inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-xs font-semibold ring-1 ${
            degraded
              ? "bg-amber-900/30 text-amber-300 ring-amber-700"
              : "bg-emerald-900/30 text-emerald-300 ring-emerald-700"
          }`}
          role="status"
        >
          <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${degraded ? "bg-amber-400" : "bg-emerald-400"}`} />
          {degraded ? "Degraded — a service needs attention" : "All services healthy"}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {SERVICES.map((name) => {
          const enabled = Boolean(services?.[name]);
          const d = detail[name];
          return (
            <Card key={name} className="p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <span
                    aria-hidden="true"
                    className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg art-${tone} text-white/70 ring-1 ring-white/10`}
                  >
                    <Icon name={SERVICE_ICON[name]} size={16} />
                  </span>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold capitalize text-zinc-100">{name}</div>
                    {d?.detail ? <div className="truncate text-[11px] text-zinc-500">{d.detail}</div> : null}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  {d && <Badge ok={d.ok} label={d.ok ? "ok" : "down"} />}
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${
                      enabled
                        ? "bg-white/[.04] text-zinc-400 ring-white/10"
                        : "bg-white/[.02] text-zinc-600 ring-white/5"
                    }`}
                  >
                    {enabled ? "configured" : "not set"}
                  </span>
                </div>
              </div>
              {d?.error ? (
                <p className="mt-2.5 rounded-lg border border-red-500/20 bg-red-500/[.07] px-2.5 py-1.5 text-xs text-red-300">
                  {d.error}
                </p>
              ) : null}
            </Card>
          );
        })}
      </div>

      {/* Media libraries (MEDIA_LIBRARIES_PLAN): what the sidebar shows + why.
          Configured MEDIA_LIBRARY_N_NAME values; warnings make a misconfigured
          path visible here as well as on the folder page. */}
      {(folders.data?.libraries?.length ?? 0) > 0 || (folders.data?.warnings?.length ?? 0) > 0 ? (
        <section aria-label="Media libraries">
          <h2 className="mb-2 text-[11px] font-bold uppercase tracking-[0.14em] text-zinc-500">
            Media libraries
          </h2>
          <div className="flex flex-col gap-2">
            {(folders.data?.warnings ?? []).map((w) => (
              <p
                key={w}
                className="rounded-lg border border-amber-500/20 bg-amber-500/[.06] px-3 py-2 text-xs text-amber-300"
              >
                ⚠ {w}
              </p>
            ))}
            {(folders.data?.libraries ?? []).map((lib) => (
              <div
                key={lib.name}
                className="flex items-center gap-3 rounded-xl border border-white/[.06] bg-surface-2/70 px-3.5 py-2.5"
              >
                <Icon name={libraryIconFor(lib.collection_type)} size={16} className="shrink-0 text-zinc-400" />
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-100">{lib.name}</span>
                <span className="hidden truncate text-[11px] text-zinc-600 sm:block">{lib.path}</span>
                {lib.ok ? (
                  <Badge ok label="ok" />
                ) : (
                  <Badge ok={false} label="unresolved" />
                )}
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
