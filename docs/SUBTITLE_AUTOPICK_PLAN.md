# Subtitles — the auto-pick and the popularity facts (his decision, 2026-09-21) — plan

> Branch: **`feat/tvos-player`** (where the player work lives). Companion to
> [`SUBTITLES_OPENSUBTITLES_PLAN.md`](SUBTITLES_OPENSUBTITLES_PLAN.md) — that file built the subtitle
> feature (Phases 0–5) and this one takes the two things it left out: the provider's **popularity number**
> is on the wire and never shown, and the *default* subtitle is still "whatever you chose last time".

His instruction, 2026-09-21: *"the subtitles ui looks good, can we also think of adding the no of times a
subtitle is being downloaded from the opensubtitles api to better inform me the user and apply the most
downloaded subtitle automatically by default.. user can choose to off it later"*.

---

## §0 — What this is, in one paragraph

**Two halves of one idea: make the best subtitle happen without being asked, and say why it is the best.**
The provider's `download_count` is already fetched, already decoded by both clients and already used for
ranking — and **displayed nowhere**; our own `used_count` is displayed in the web panel and **not on
tvOS**. So the panel can say *which* subtitle is best but not *why*, and a first play of a title gets no
subtitle at all. This phase prints both facts, **badges the pick**, and — his decision — has the **server**
choose and apply the top-ranked subtitle once per title, with a global switch, a per-title `Off` and a
per-audio-language exclusion.

---

## §1 — His four decisions, recorded (2026-09-21)

| # | Question | **His answer** |
|---|---|---|
| 1 | How far should "automatically" go? | **On first play, when the title has no subtitle of its own in that language** — the server downloads the top-ranked one once and remembers it (1 quota per title, ever; 0 or unknown quota → no attempt) |
| 2 | Where does the off switch live? | **Global switch + per-title `Off` + a per-language exclusion** |
| 3 | Which language does the auto-pick use? | **The first entry of the configured list** (`OPENSUBTITLES_LANGUAGES`, currently `en`) — one rule, always the same |
| 4 | Hearing-impaired (SDH) tracks? | **Excluded from the auto-pick** — they stay in the list, clearly marked, pickable by hand |

⚠ **Interpretation of decision 2's third clause, stated so it is not ambiguous** (and reversible in one
setting): the per-language exclusion is **`auto_pick_skip_audio`** — *a title whose AUDIO track is in one of
these languages is never auto-picked.* Empty by default. Its use case: add `en` and the auto-pick then only
ever applies to films whose audio is **not** English. It is about the title, not about which subtitle
language may be chosen, because that is already decision 3.

---

## §2 — The rule, exactly

`shouldAutoPick` runs on the server, on `POST /api/jellyfin/subtitle-auto`, and it applies **only** when all
of these hold — every one of them a named reason the API returns, so a client can say *why not*:

| # | Condition | Reason code when it fails |
|---|---|---|
| 1 | the global switch is ON (default: ON, his decision) | `disabled` |
| 2 | the item has **no stored preference** — and a stored **`disabled`** record counts as a choice (his decision 2) | `already_chosen` |
| 3 | the item has **no LOCAL subtitle track already in that language** (criterion 9: what the film has is never second-guessed) | `has_local_track` |
| 4 | the item's **audio language is not in `auto_pick_skip_audio`** (his decision 2) | `audio_excluded` |
| 5 | the quota is **known and > 0** — `remaining == nil` (anonymous, not yet reported) or `0` means **no attempt** | `quota_unknown` / `quota_exhausted` |
| 6 | a candidate exists: an **OpenSubtitles result in the auto language, not hearing-impaired** | `no_candidate` |

**The candidate is the first row of the SAME ranking the panel draws** — our usage first, then
`download_count`, then identity (`rank_results`) — filtered to the language and to non-SDH. ⚠ This is not
decoration: it is what makes the badge and the auto-pick **incapable of disagreeing**. If our usage put it
first the badge says *Your pick before*; otherwise *Most downloaded*.

⚠ **On success the api writes what a manual pick writes**: `subtitle-select`'s own path (download → attach →
refresh), then `set_preference` and `record_use` — so the auto-applied subtitle is a **stored choice from
that moment on**, it is indistinguishable from a hand pick in the pane (`Active`), and it costs **one
download per title ever**. `record_use` is called because the app applied it: the usage count is what
ranks next time.

---

## §3 — What is deliberately NOT built (so it is not relitigated)

| Not built | Why |
|---|---|
| **Library-wide / background subtitle fetching** | Still the separate decision `SUBTITLES_OPENSUBTITLES_PLAN.md` §7–§8 parked (Bazarr's job). ⚠ This phase is **per title, on first play, once** — the difference is a queue of thousands of downloads vs one |
| **Auto-picking an SDH track when it is the most downloaded** | His decision 4. They stay in the list, marked `SDH`, and are one press away |
| **A per-title language override** ("English subs for this one, Hindi for that one") | Decision 3 is one language from `.env`. Adding a per-title language is a different feature (it needs a UI to choose it) and nothing has asked for it |
| **A second popularity metric** (`new_download_count`, ratings) | ⚠ One number, and it is the one the provider documents as its own total. A second number that can contradict the first is a badge nobody can act on |
| **Showing a count the provider did not send** | ⚠ A row with no `download_count` **omits the fact**. It never prints `0 downloads` — that is a claim the app cannot make |

---

## §4 — The UI

### 4.1 The tvOS Subtitles pane (and the web panel reaches parity later)

```
Subtitles
──────────────────────────────────────────────────────────────
[ Off                                                     ✓ ]
[ English                                    on disk         ]
[ Search OpenSubtitles…                                      ]
──────────────────────────────────────────────────────────────
[ The.Mummy.1999.1080p.BluRay.x264-AC3-ETRG ]  ▸ Most downloaded
[ EN · srt · 42.4k downloads · used 2×                       ]
[ The.Mummy.1999.720p.BRRip.x264.YIFY                        ]
[ EN · srt · 8.1k downloads · SDH                            ]
Showing 19 of 31 results
```

* **the count on the row** — exact under 1000 (`312 downloads`), `k`/`M` above (`42.4k`). A **provider**
  fact, so it is stated in the provider's words; a row without one omits it (§3).
* **`used 2×`** — **our** count (criterion 7), so the two numbers are never confused: one says how popular
  the release is with the world, the other says how often *you* have picked it.
* **the badge on the row the rule would take** — `Most downloaded`, or `Your pick before` when our usage is
  what put it first, or `Auto-applied` once it has been taken.
* ⚠ **`SDH`, never `HI`.** The web panel already made this call and the reason is in its comment: **`HI` is
  the language code for Hindi**, so a bare `HI` marker on a Hindi row reads as a language. The tvOS line
  shipped `HI` in Phase P3 — a defect of that phase, corrected here.
* **the toggle row**, in this pane because this is where the decision is met: `Auto-subtitles — Most
  downloaded (en) / Off` — ⚠ it is the **server's** setting, so it is drawn from the server's answer and
  both clients show the same state.
* **the exclusion**, under it, as its own row: `Skip languages — English (audio)` — the same setting, the
  other half. It is on tvOS rather than only in the web app because a television is where a wrong-language
  subtitle is noticed.

### 4.2 The web player

The same three facts in its subtitle list (label + badge + `SDH`), and the same two settings rows in its
player panel. ⚠ **One state, two renderers** — the settings are read from and written to the api, never
held in either client.

---

## §5 — Phases

| Phase | Scope | Deploy needed? |
|---|---|---|
| **A — the server** | the store's `settings` block, the rules, `GET/POST /api/jellyfin/subtitle-settings`, `POST /api/jellyfin/subtitle-auto`, `subtitle-search` gaining `settings` + `auto`, the contract (`client.ts`), backend tests | **yes** — `backend/` changed, so RKM-HP needs `setup-watchlist.ps1` |
| **B — tvOS** | the row's second line, the badge, the `SDH` fix, the two settings rows, the `subtitle-auto` call on load | no |
| **C — the web player** | the same facts and rows in the player slice, vitest | no (volume mount), but the api must be deployed first or the calls 404 |

⚠ A and B/C are **separate commits**: A is invisible until he deploys, and B/C is invisible until the Mac
build. Neither is verified by a gate on this machine beyond types and rules.

---

## §6 — His round: the falsifiers

| # | Falsifier | What disproves it |
|---|---|---|
| **A-F1** | **a subtitle row shows its download count** (`EN · srt · 42.4k downloads · SDH`) and **`used 2×`** appears only after he has picked that release twice | a count on no row at all (the field never arrives), or a `0 downloads` on a row the provider sent nothing for |
| **A-F2** | **the row the rule picks carries the badge** — `Most downloaded`, or `Your pick before` when his own usage put it first | no badge, or a badge on a row that is not the one the auto-pick takes |
| **A-F3** | **a title he has never touched gets a subtitle by itself on first play**: opening it shows the subtitle already there, and `Continue Watching`/the pane shows it as `Active` | no subtitle; or a subtitle applied and NOT remembered (it must survive a second play) |
| **A-F4** | **the auto-pick spends nothing when the film already has an English subtitle of its own** | a download that should not have happened (check `remaining` before/after in the footer) |
| **A-F5** | **`Auto-subtitles → Off` stops it** for the next untouched title, and **`Skip languages → English (audio)`** stops it for English-audio films | either control appears to work and the next first-play still downloads |
| **A-F6** | **an SDH-only result does not get auto-applied**, and the same row is still listed and pickable | an SDH track applied by itself |
| **A-F7** | **`Off` for one title sticks**: re-opening that title applies nothing, and the auto-pick does not re-arm | the title re-applies on the next play (the `disabled` record was ignored) |

⚠ **What this round cannot prove:** nothing about a fresh OpenSubtitles account's quota behaviour; and a
`BUILD FAILED` on the Mac proves nothing about A-F1…A-F7.

---

## §7 — As built (Phase A — the server, 2026-09-21)

| | |
|---|---|
| **Rules** (`backend/services/subtitles.py`, pure) | `auto_pick_language(languages)` — the first entry of the configured list, normalised, falling back to `en` · `normalise_auto_pick_settings(raw)` — `{auto_pick: True, auto_pick_skip_audio: []}`, the switch defaulting ON and the skip list reduced to ISO codes so `English`/`eng`/`en` are one language · `has_local_track_in(tracks, language)` — ⚠ through `normalise_language`, because Jellyfin says `eng` and OpenSubtitles says `en` · `auto_pick_candidate(results, language, counts, allow_sdh=False)` — **the first row of the SAME ranking the panel draws**, filtered to the language and to non-SDH · `auto_pick_basis` — `used-before` / `most-downloaded` · `auto_pick_blocked(...)` and `auto_pick_shortfall(...)` — the two halves, split so **every gate knowable locally answers before a single request is made** · `AUTO_PICK_REASONS` — the one vocabulary of codes and sentences |
| **Store** | `load()` now returns a `settings` block too — ⚠⚠ **because `_mutate` writes back what `load()` returned**: a block only `settings()` could read would be **erased by the next subtitle the user chose**, and nothing about that write would look wrong (a test pins it) · `settings()` (normalised) · `update_settings(auto_pick=…, auto_pick_skip_audio=…)` — **a partial update**, so one client cannot reset the other's field |
| **Endpoints** | `GET`/`POST /api/jellyfin/subtitle-settings` · `POST /api/jellyfin/subtitle-auto` · `subtitle-search` gains `settings`, `auto_language` and `auto` (`{subtitle_id, basis, blocked, reason}`) — **the badge and the settings rows come from the listing the pane already fetches**, so they cannot render disagreeing. ⚠ **A decline is a 200**, always: the viewer did not ask for this download, so the answer is `decision` + `reason`. Only a malformed request is a 4xx |
| **Contract** | `docs/api/openapi.v1.json` regenerated from `app.openapi()` (**additive: 3 routes, 2 schemas, 0 removals** — checked with `git diff` for deletions) · `frontend/src/lib/api/types.ts` regenerated (`npm run generate:types`) · `client.ts` gains `SubtitleAutoPickSettings`, `SubtitleSettingsShape`, `SubtitleAutoFacts`, `SubtitleAutoResult` and three client methods — **these are the shape source `check-tvos-models.py` R6/R7 will hold the Swift against in Phase B** |
| **Tests** | `backend/tests/test_subtitles_api.py` +**25** (rules, store, route) — including the two that would be missed by an optimistic implementation: **a blocked title spends nothing** (`transport.count("/subtitles") == 0` for `disabled`, `audio_excluded`, `has_local_track`, `title_off`) and **an anonymous key answers `quota_unknown` rather than attempting** · `test_route_protection.py` — the three routes declared `SESSION` in `ROUTE_LEVELS`, so a route cannot ship without that decision |
| **Backend suite** | **1366 passed** (was 1341) · frontend `tsc --noEmit` clean · **vitest 589 passed / 23 files** |
| **⚠ NOT verified** | the vendor's own answer: **this sandbox has no `OPENSUBTITLES_API_KEY`**, so no live search was made and **`download_count` arriving on every row is assumed from the parser, not observed here**. His round (A-F1) is what settles it — and if the field is absent the row simply shows no count, which is the rule in §3 |

### ⚠ A consequence of his decision 1, stated before he meets it

**With an API key and no account login, `quota_unknown` is what the feature will answer** — the OpenSubtitles
allowance is only reported *on a download*, so the api cannot promise the next one will succeed, and his
decision was *no attempt*. The fix is one line in `.env` (`OPENSUBTITLES_USERNAME` + `OPENSUBTITLES_PASSWORD`,
which also raises the allowance from ~5 to ~20/day). ⚠ The pane says exactly that, in the sentence for the
code — a silent no-op is the outcome this design refuses.

