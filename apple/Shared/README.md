# `Shared/` — RKMServerKit

A local Swift package holding the **only** code both Apple clients genuinely need: the server
**address**.

```
Shared/
├── Package.swift
└── Sources/RKMServerKit/
    ├── ServerAddress.swift   parse + normalise what a human typed (add scheme, strip trailing /)
    └── ServerStore.swift     persist it (UserDefaults; Keychain only if it ever holds a secret)
```

## ⚠ The rule for this folder

**Nothing goes in here unless BOTH apps need it.** The iOS shell has no API client, no models and no
auth flow — it loads the live web UI. The tvOS app has all of those.

If `Shared/` starts accumulating API models or networking, that is a design smell: one client is being
forced to look like the other. Split it out instead.

Both targets (iOS and tvOS) consume this as a **local package dependency** — no copy-paste of address
rules, no third copy to drift.
