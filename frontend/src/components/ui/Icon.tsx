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
  | "plus"
  | "more"
  | "check"
  | "scan"
  | "chevron-left"
  | "chevron-right"
  | "arrow-right"
  | "close"
  | "star"
  | "clock"
  | "external"
  | "menu"
  | "grid"
  | "back";

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
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  scan: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
  "chevron-left": '<path d="m15 18-6-6 6-6"/>',
  "chevron-right": '<path d="m9 18 6-6-6-6"/>',
  "arrow-right": '<path d="M5 12h14M12 5l7 7-7 7"/>',
  close: '<path d="M18 6 6 18M6 6l12 12"/>',
  star: '<path d="M12 2.6 14.9 8.7l6.6.9-4.9 4.6 1.2 6.5L12 17.5l-5.8 3.2 1.2-6.5L2.5 9.6l6.6-.9Z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
  external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14 21 3"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  back: '<path d="M19 12H5"/><path d="m12 19-7-7 7-7"/>',
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
