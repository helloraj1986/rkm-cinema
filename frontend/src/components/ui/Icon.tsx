import type { SVGProps } from "react";

/**
 * RKM Cinema icon system (design spec §72): one consistent modern outline
 * icon set (Lucide-style geometry), stroke ~1.75px, no emoji / mixed glyphs.
 * All icons inherit currentColor and scale via the `size` prop.
 */
export type IconName =
  | "home"
  | "film"
  | "tv"
  | "heart"
  | "compass"
  | "search"
  | "sparkles"
  | "settings"
  | "play"
  | "pause"
  | "plus"
  | "more"
  | "check"
  | "download"
  | "scan"
  | "chevron-left"
  | "chevron-right"
  | "arrow-right"
  | "close"
  | "star"
  | "clock"
  | "volume"
  | "volume-x"
  | "skip-back-10"
  | "skip-forward-10"
  | "maximize"
  | "minimize"
  | "external"
  | "menu"
  | "grid"
  | "list"
  | "back"
  | "folder"
  | "users"
  | "lock";

const OUTLINE: Record<string, string> = {
  home: '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
  film: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M7 4v16M17 4v16M2 9h5M2 15h5M17 9h5M17 15h5"/>',
  tv: '<rect x="2" y="7" width="20" height="15" rx="2"/><polyline points="17 2 12 7 7 2"/>',
  heart: '<path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2C10.5 3.5 9.3 3 7.5 3A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z"/>',
  compass:
    '<circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.35-4.35"/>',
  sparkles:
    '<path d="M12 3l1.9 5.8 5.8 1.9-5.8 1.9L12 18.4l-1.9-5.8-5.8-1.9 5.8-1.9Z"/><path d="M19 3v4M17 5h4"/>',
  settings:
    '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  pause: '<path d="M7 5v14M17 5v14"/>',
  // Household (AUTH_MULTIUSER_PLAN 1b): two heads + shoulders, Lucide's "users" outline.
  users:
    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  // "Who's watching?" (PLEX_PROFILE_AUTH_PLAN Phase B): a profile that asks for a password.
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/>',
  scan: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
  "chevron-left": '<path d="m15 18-6-6 6-6"/>',
  "chevron-right": '<path d="m9 18 6-6-6-6"/>',
  "arrow-right": '<path d="M5 12h14M12 5l7 7-7 7"/>',
  close: '<path d="M18 6 6 18M6 6l12 12"/>',
  star: '<path d="M12 2.6 14.9 8.7l6.6.9-4.9 4.6 1.2 6.5L12 17.5l-5.8 3.2 1.2-6.5L2.5 9.6l6.6-.9Z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
  volume: '<path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/>',
  "volume-x":
    '<path d="M11 5 6 9H2v6h4l5 4z"/><path d="m16 9 6 6M22 9l-6 6"/>',
  // ±10s transport skips (Lucide rotate-ccw/cw arcs with the step in the middle):
  // the one control a phone needs and the bar alone cannot give (a thumb drag on a
  // 320px-wide bar is 3-minute granularity).
  "skip-back-10":
    '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><text x="12" y="15.4" text-anchor="middle" font-size="7.5" font-weight="700" fill="currentColor" stroke="none">10</text>',
  "skip-forward-10":
    '<path d="M21 12a9 9 0 1 1-9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><text x="12" y="15.4" text-anchor="middle" font-size="7.5" font-weight="700" fill="currentColor" stroke="none">10</text>',
  maximize: '<path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3"/>',
  minimize: '<path d="M5 12h14"/>',
  external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14 21 3"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
  back: '<path d="M19 12H5"/><path d="m12 19-7-7 7-7"/>',
  folder:
    '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
};

const FILLED: Record<string, string> = {
  play: '<path d="M7 4.8v14.4c0 .9 1 1.5 1.8 1L20.4 13a1.2 1.2 0 0 0 0-2L8.8 3.8c-.8-.5-1.8.1-1.8 1Z"/>',
  star: '<path d="M12 2.6 14.9 8.7l6.6.9-4.9 4.6 1.2 6.5L12 17.5l-5.8 3.2 1.2-6.5L2.5 9.6l6.6-.9Z"/>',
};

export function Icon({
  name,
  size = 20,
  filled = false,
  strokeWidth = 1.75,
  className,
  ...rest
}: {
  name: IconName;
  size?: number;
  /** Filled variant (play/star glyphs). */
  filled?: boolean;
  strokeWidth?: number;
  className?: string;
} & SVGProps<SVGSVGElement>) {
  const paths = filled ? FILLED[name] : OUTLINE[name];
  if (!paths) return null;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke={filled ? "none" : "currentColor"}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
      {...rest}
    >
      <g dangerouslySetInnerHTML={{ __html: paths }} />
    </svg>
  );
}
