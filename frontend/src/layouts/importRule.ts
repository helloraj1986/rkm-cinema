/**
 * The import ban that makes `layouts/mobile/` safe — MOBILE_FIRST_UI_PLAN §3.4.
 *
 * The rule the whole architecture rests on is *one implementation of every business rule*.
 * A mobile view is allowed to hold layout, markup, styling, interaction and local UI state —
 * and nothing else. This file is that sentence turned into something a test can fail on,
 * because a convention nobody can check is a convention that lasts until the first deadline.
 *
 * ⚠ It is a PURE function of `(file, source)` on purpose: that makes the rule itself
 * falsifiable with fixture strings (see `imports.test.ts`), instead of being a checker whose
 * only evidence is that it once printed nothing.
 *
 * ⚠ What it deliberately does NOT police: strings. A mobile file that re-words an empty state
 * is a copy that no regex can catch, and a rule that pretended to would be worse than none.
 * That one is held by the two rules that ARE checkable here — no second HTTP client and no
 * second formatter — plus review.
 */

export interface Violation {
  file: string;
  line: number;
  rule: string;
  /** The offending line, trimmed, for the failure message. */
  text: string;
  /** Why the rule exists, in one sentence, so the fix is obvious without reading this file. */
  why: string;
}

interface Ban {
  rule: string;
  pattern: RegExp;
  why: string;
}

/**
 * Every entry is a way a mobile view can become a SECOND source of truth.
 *
 * ⚠ Adding a ban is cheap; removing one needs a reason written next to it. The two that would
 * be tempting to remove are `matchMedia`/`innerWidth` (a component that "just wants to know if
 * it is a tablet") and `toLocaleString` (a component that "just needs a comma") — and those are
 * exactly the two this file exists to stop.
 */
export const BANS: readonly Ban[] = [
  {
    rule: "no-second-http-client",
    pattern: /\b(?:fetch\s*\(|new\s+XMLHttpRequest|from\s+["'][^"']*axios)/,
    why: "there is ONE HTTP client (`lib/api/client.ts`); it holds the 401 / X-RKM-Auth-Problem rule, so a second one silently loses the profile-stale behaviour.",
  },
  {
    rule: "no-direct-api-client",
    pattern: /from\s+["'][^"']*lib\/api\/client["']/,
    why: "a mobile view consumes a shared hook from `features/*/api.ts`, never the client itself — importing the client is how a second cache key and a second staleness rule appear.",
  },
  {
    rule: "no-local-formatting",
    pattern: /\.toLocale(?:String|DateString|TimeString)\s*\(/,
    why: "sizes, dates and durations are formatted once, in the owning `lib.ts` (`fmtBytes`, `timeAgo`, `fmtRuntime` …) — a local copy drifts from the screen next to it.",
  },
  {
    rule: "no-local-date-maths",
    pattern: /new\s+Date\s*\(/,
    why: "same rule as above: `addedTime()` / `timeAgo()` / `daySeed()` own this, and two clocks is two answers.",
  },
  {
    rule: "no-second-layout-source",
    pattern: /\bmatchMedia\s*\(|window\.innerWidth\b/,
    why: "`useLayoutMode()` is the ONE place the viewport is read into React; a component that asks again is a second source of truth, and the two will disagree during a rotate.",
  },
  {
    rule: "no-local-percent-maths",
    pattern: /\*\s*100\b/,
    why: "progress percentages are derived once (`resumePercent`, `percentOf`, `detailResumePercent`) — an inline one is how two screens come to show different numbers for the same film.",
  },
];

/** Files that ARE the mobile views. Tests are exempt (they read source as a string). */
export function isMobileViewFile(path: string): boolean {
  const normalised = path.replace(/\\/g, "/");
  return (
    normalised.includes("/layouts/mobile/") &&
    /\.(?:ts|tsx)$/.test(normalised) &&
    !/\.test\.(?:ts|tsx)$/.test(normalised) &&
    !/\.d\.ts$/.test(normalised)
  );
}

/** Every way `source` breaks the rule, in file order. Empty = clean. */
export function findForbiddenSources(file: string, source: string): Violation[] {
  const violations: Violation[] = [];
  const lines = source.split("\n");

  lines.forEach((raw, index) => {
    // A line that is entirely a comment is prose ABOUT the rule, not a use of it. The plan,
    // the ADRs and the docblocks above all quote these patterns, and a rule that flags its own
    // documentation teaches people to delete the documentation.
    const line = raw.trim();
    const isComment =
      line.startsWith("//") || line.startsWith("*") || line.startsWith("/*") || line.startsWith("*/");
    if (isComment) return;

    for (const ban of BANS) {
      if (ban.pattern.test(raw)) {
        violations.push({
          file,
          line: index + 1,
          rule: ban.rule,
          text: line.slice(0, 200),
          why: ban.why,
        });
      }
    }
  });

  return violations;
}

/** The one-line report a failing test prints. */
export function describeViolations(violations: Violation[]): string {
  return violations
    .map((v) => `${v.file}:${v.line}  [${v.rule}]\n    ${v.text}\n    ↳ ${v.why}`)
    .join("\n");
}
