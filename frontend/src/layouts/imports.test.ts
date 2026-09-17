import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  BANS,
  findForbiddenSources,
  isMobileViewFile,
  describeViolations,
} from "./importRule";

/**
 * The import ban, falsified before it is trusted — MOBILE_FIRST_UI_PLAN §3.4.
 *
 * ⚠ The fixtures below are the point of this file. A checker whose only evidence is "the run
 * was green" has not been tested at all (this repo has shipped two of those), so every ban is
 * proved here by feeding it a source that violates it AND a source that does not. The second
 * half matters as much as the first: a rule that flags ordinary React is a rule people route
 * around.
 */

describe("every ban fires on a source that breaks it", () => {
  const cases: { rule: string; source: string }[] = [
    { rule: "no-second-http-client", source: `const r = await fetch("/api/library");` },
    { rule: "no-second-http-client", source: `const x = new XMLHttpRequest();` },
    { rule: "no-second-http-client", source: `import axios from "axios";` },
    {
      rule: "no-direct-api-client",
      source: `import { api } from "../../lib/api/client";`,
    },
    { rule: "no-local-formatting", source: `{n.toLocaleString()} items` },
    { rule: "no-local-formatting", source: `d.toLocaleDateString("en-AU")` },
    { rule: "no-local-date-maths", source: `const t = new Date(iso).getTime();` },
    { rule: "no-second-layout-source", source: `const m = window.matchMedia("(max-width: 900px)");` },
    { rule: "no-second-layout-source", source: `if (window.innerWidth < 600) {` },
    { rule: "no-local-percent-maths", source: `const pct = (pos / total) * 100;` },
  ];

  it.each(cases)("$rule catches: $source", ({ rule, source }) => {
    const found = findForbiddenSources("layouts/mobile/X.tsx", source);
    expect(found.map((v) => v.rule)).toContain(rule);
    // Every violation must carry the reason — a failure that does not say why gets "fixed"
    // by deleting the check.
    expect(found[0].why.length).toBeGreaterThan(40);
  });

  it("reports a usable file:line and the offending text", () => {
    const source = `import { api } from "./x";\nconst a = 1;\nconst b = n.toLocaleString();\n`;
    const found = findForbiddenSources("layouts/mobile/Home.tsx", source);
    expect(found).toHaveLength(1);
    expect(found[0].line).toBe(3);
    expect(found[0].text).toBe("const b = n.toLocaleString();");
    expect(describeViolations(found)).toContain("layouts/mobile/Home.tsx:3");
  });
});

describe("and stays quiet on sources that obey the rule", () => {
  const allowed = [
    `import { useLayoutMode } from "../LayoutMode";`,
    `import { fmtBytes, rowStatusText, actionsFor } from "../../features/offline/lib";`,
    `import { useLibraryFolders } from "../../features/library/api";`,
    `const rows = items.filter(isContinueWatching);`,
    `useEffect(() => { setOpen(false); }, [location.pathname]);`,
    // ⚠ A comment that NAMES a banned pattern is documentation, not a use of it. This is the
    // one case where the rule would otherwise punish the reasoning that justifies it.
    `// never call fetch() here — see MOBILE_FIRST_UI_PLAN §3.4`,
    ` * the plan forbids window.innerWidth in a mobile view`,
  ];

  it.each(allowed)("allows: %s", (source) => {
    expect(findForbiddenSources("layouts/mobile/X.tsx", source)).toEqual([]);
  });

  it("finds nothing in an empty file", () => {
    expect(findForbiddenSources("layouts/mobile/X.tsx", "")).toEqual([]);
  });
});

describe("the ban list is not accidentally empty or duplicated", () => {
  it("has every rule, each with a reason", () => {
    expect(BANS.length).toBeGreaterThanOrEqual(6);
    for (const ban of BANS) {
      expect(ban.rule).toMatch(/^no-/);
      expect(ban.why.length).toBeGreaterThan(40);
    }
  });

  it("has no duplicate rule names", () => {
    const names = BANS.map((b) => b.rule);
    expect(new Set(names).size).toBe(names.length);
  });
});

describe("which files the rule governs", () => {
  it.each([
    ["src/layouts/mobile/HomeScreen.tsx", true],
    ["src/layouts/mobile/nested/Deep.ts", true],
    // Tests read source as a string, so they are exempt or they police themselves.
    ["src/layouts/mobile/imports.test.ts", false],
    ["src/layouts/mobile/types.d.ts", false],
    // The desktop shell and the shared layers are NOT governed — they are allowed to own rules.
    ["src/layouts/desktop/index.ts", false],
    ["src/layouts/LayoutMode.tsx", false],
    ["src/features/library/lib.ts", false],
  ])("%s → %s", (path, expected) => {
    expect(isMobileViewFile(path)).toBe(expected);
  });
});

/**
 * ⚠ THE HALF THAT WAS MISSING, and it mattered: until M4 this file tested the RULE against fixture
 * strings and never read a real mobile file. So the ban was documentation with unit tests next to it,
 * and `HomeScreen.tsx` — a file in this directory — imported `lib/api/client` directly for a backdrop
 * URL for a whole phase without anything going red. A check nobody points at the tree is a check that
 * only knows what its author remembered to plant.
 *
 * The scanner is the same pure function the fixtures above exercise; what is new is that it is fed
 * every file in `src/layouts/mobile`.
 */
describe("the ban, applied to the REAL mobile files", () => {
  const dir = fileURLToPath(new URL("./mobile", import.meta.url));

  const files = readdirSync(dir)
    .filter((name) => /\.(?:ts|tsx)$/.test(name))
    .map((name) => ({ path: `src/layouts/mobile/${name}`, source: readFileSync(`${dir}/${name}`, "utf8") }))
    .filter((f) => isMobileViewFile(f.path));

  it("reads the directory it is supposed to police", () => {
    // ⚠ Without this, a rename or a wrong path makes the scan below pass by finding nothing — the
    // exact failure mode this whole block exists to fix.
    expect(files.length).toBeGreaterThanOrEqual(5);
    expect(files.map((f) => f.path)).toContain("src/layouts/mobile/HomeScreen.tsx");
    expect(files.map((f) => f.path)).toContain("src/layouts/mobile/SearchScreen.tsx");
  });

  it("finds no violation in any of them", () => {
    const violations = files.flatMap((f) => findForbiddenSources(f.path, f.source));
    expect(describeViolations(violations)).toBe("");
  });

  it("⚠ would FIND one — the same scanner, fed a file that breaks the rule", () => {
    // Falsification, kept permanently: proving the scan CAN fail is the only thing that makes the
    // green run above evidence rather than a print statement.
    const planted = [
      { path: "layouts/mobile/Planted.tsx", source: `import { api } from "../../lib/api/client";` },
    ];
    const violations = planted.flatMap((f) => findForbiddenSources(f.path, f.source));
    expect(violations).toHaveLength(1);
    expect(violations[0].rule).toBe("no-direct-api-client");
  });
});
