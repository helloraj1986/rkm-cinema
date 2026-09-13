# `Shared/` — RKMServerKit

A local Swift package holding the **only** code both Apple clients genuinely need:

```
Shared/
├── Package.swift
├── Sources/RKMServerKit/
│   ├── ServerAddress.swift    parse + normalise what a human typed (add scheme, strip trailing /)
│   ├── ServerStore.swift      persist it (UserDefaults)
│   ├── LogRedactor.swift      ⚠ the ONE place a URL/header/cookie/body is made safe to log
│   ├── CorrelationID.swift    the id that joins a screenshot to a log file
│   ├── LogEntry.swift         level · category · line format · byte/duration formatting
│   ├── RollingFileLog.swift   the capped rolling file (`LOGGING.md` §1, layer 2)
│   ├── LogRingBuffer.swift    the last N lines, for the debug HUD
│   └── RKMLog.swift           the facade: os_log + file + ring, redacted on the way in
└── Tests/RKMServerKitTests/   66 tests · `swift test` · the Phase 0 gate that needs no Mac
```

## ⚠ The rule for this folder

**Nothing goes in here unless BOTH apps need it.** The iOS shell has no API client, no models and no
auth flow — it loads the live web UI. The tvOS app has all of those.

If `Shared/` starts accumulating API models or networking, that is a design smell: one client is being
forced to look like the other. Split it out instead.

Both targets (iOS and tvOS) consume this as a **local package dependency** — no copy-paste of address
rules, no third copy to drift.

## Two decisions worth not re-litigating

**1. One library product, not two.** The logging code (redactor + rolling file + facade) lives in this
same `RKMServerKit` module rather than a second `RKMLogging` product. It qualifies for this folder by the
rule above — `LOGGING.md` §3 specifies logging for **both** apps — and a single product means one
checkbox in Xcode's *Add Local Package…* dialog instead of two. A forgotten second product is a compile
error on the Mac that I cannot fix from here, so the packaging favours his one-time GUI step.
The module is a *server kit* holding logging; that is a slightly imprecise name, and it is the right
trade.

**2. The redactor is a correctness requirement, not hygiene.** These apps hold a session cookie and the
server holds Jellyfin/OpenSubtitles/TMDB keys, and log files get pasted into chat. `LOGGING.md` §9 makes
`grep -iE "password|token|api_key|rkm_session"` over a real run's log an acceptance gate. The design that
makes it hold **by construction** rather than by care:

- a sensitive value is never emitted — a cookie **value** never becomes a string at all
  (`LogRedactor.redact(cookieNames:)` takes names, and nothing else exists for the job);
- every public entry point ends in a final safety sweep that removes a surviving sensitive **key name**
  together with the value bound to it, so a caller cannot forget to redact;
- `RKMLog` re-checks each finished line and **withholds it** rather than writing it, so the worst
  outcome of a redactor bug is a missing log line, never a leaked credential.

Sensitive key *names* are relabelled rather than printed (`cred`, `session`) so the log keeps its shape
while the §9 grep still passes. The tests cover all of this — that is what the 66 are mostly doing.
