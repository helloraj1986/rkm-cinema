# tvOS player — Phase P (polish: the defects the code already has, and Up Next) — plan

> Branch: **`feat/tvos-player`** (the player's own branch; `dev` does not have it).
> Companion to `docs/TVOS_PLAYER_PLAN.md` — that file brought the player into existence (C1–C3) and this one
> starts from the code as it actually stands after his round 6 (the film **plays** and **resumes**).

His instruction, 2026-09-20: *"for rkm-cinema app, in tv-os work on the media player now on every aspect of it
make it perfect for a tv os app… go through the code and find out what else can be done on this"*.

---

## §0 — What this phase is, in one paragraph

**An audit of the player as built, and the fixes it turned up.** Three of the findings are **defects with a
line number** — a tooltip that is hardcoded to `0:00`, a scrub-row jog that is described in a comment but
implemented nowhere, and a mode-escalation ladder that is fully built, fully pinned, and **called by nothing**.
The rest is what a television transport needs and the screen does not have: a failure notice you cannot press,
a stall with no spinner, no reduced-motion path, no pause when the app goes to the background, and **no Up
Next** — the one thing that separates "a player" from "a TV app" for anybody watching a series.

---

## §1 — The audit (measured against the code on `feat/tvos-player`, 2026-09-20)

Every row below was read off the file, not remembered. `file:line` is the evidence.

### 1.1 Defects — the code contradicts itself or its own prototype

| # | Finding | Where | Why it is a defect |
|---|---|---|---|
| **D1** | **The scrub tooltip always reads `0:00`.** `PlayerScrubStyle` draws `Text(PlaybackRules.fmtTime(0))` — a literal zero where the seek preview time belongs. | `Player/PlayerChrome.swift:205` | His prototype writes `tooltipTime.textContent = fmt(cur)` (`rkm-cinema-tvos-player.html:518`). The app's tooltip is a **claim about where the playhead will land**, and it says the same wrong thing on every film. |
| **D2** | **The scrub row's ±30 s jog does not exist.** `PlaybackRules.jogSeconds` (30) is declared, documented, and referenced by a comment that says the screen "wires it up" — and no code in `Player/` reads it. `PlayerScrubber`'s `Button` has an **empty action** and `onSeek` is never called. | `Core/PlaybackRules.swift:84`, `Player/PlayerChrome.swift:140-147`, `Player/PlayerView.swift:164` | His prototype's whole row-1 model is *"left/right jog time by 30 s"* (`moveItem`, `…html:573`). Today, pressing left/right with the track focused asks the focus engine for a neighbour and — there being none to the right — does nothing at all. The screen's most-used gesture is dead. |
| **D3** | **The mode-escalation ladder is unreachable.** `PlaybackStore.escalateMode()` and `PlaybackRules.hlsLadder` / `nextHLSMode(after:)` are built and pinned, and **nothing calls them**. A stream that fails is reported as a sentence and the viewer is stuck. | `Core/PlaybackStore.swift:451`, `Core/PlaybackRules.swift:240-246` | This is the phase's own stated reason for the ladder's existence (`TVOS_PLAYER_PLAN.md` §C2's audio-aware order). A direct play of an HEVC/EAC3 title is exactly the `[hypothesis]` `PlaybackCodecs.tvOS` warns about — and today, when the hypothesis is wrong, the app does not take the next rung. |
| **D4** | **A stream that fails to START is never noticed at all.** Only `.AVPlayerItemFailedToPlayToEndTime` is observed — that is a stream that died **mid-film**. An item whose `status` becomes `.failed` (the classic black screen) fires no notification this screen listens to. | `Player/PlayerView.swift:105` | *"A black screen with nothing on it is the outcome this app refuses to ship"* — `PlaybackStore`'s own header. The one failure that produces exactly that is the one not watched. |
| **D5** | **`start()` attaches an item with no credential.** `player.replaceCurrentItem(with: AVPlayerItem(url: url))` — a bare URL, evaluated before the Mac-only `makeAsset(url:session:)` path exists. | `Player/PlayerView.swift:296` | This is **round 4's defect class**, kept as a second attach path. It is inert today only because `store.url` is `nil` at `onAppear`; the moment anything makes it non-nil the player plays unauthenticated and draws black. |
| **D6** | **The stop write is fired twice on `Back`.** `leave()` calls `store.finish()`, and `onDisappear` calls it again. | `Player/PlayerView.swift:101`, `:374` | Two `stopped` reports, two `GET /jellyfin/detail` verification reads, and two save toasts racing each other — for one viewer pressing Back once. |
| **D7** | **The player is never stopped on the way out.** `onDisappear` removes the time observer and fires the write, but does not `pause()` or detach the item. | `Player/PlayerView.swift:95-102` | Audio and decoding continue behind whatever is next on screen; the `AVPlayer` is retained by the leaked item. |
| **D8** | **`saveHintDelay` is declared and never read.** | `Core/PlaybackRules.swift:359` | Dead constant in the file whose whole point is that its rules are executed. Either something reads it or it goes. |

### 1.2 Gaps — what a tvOS transport has that this one does not

| # | Gap | Why it matters on a television |
|---|---|---|
| **P1** | **The failure notice is a dead end.** It is `Text` only — nothing is focusable, and the chrome's own hide rule keeps the *controls* up but nothing on the notice can be pressed. | A television's only input is the remote. A message with no control is a screen you can only leave with MENU — `ARCHITECTURE.md` ranks a dead end above any cosmetic rule. |
| **P2** | **No buffering indicator.** `isSwitching` is tracked (from `timeControlStatus`) and used for exactly one thing: keeping the chrome visible. | A stall on a transcode is a frozen frame with no explanation. The web player shows a spinner; this one shows nothing. |
| **P3** | **Reduced Motion is not honoured.** His prototype specifies it (`--focus-scale` animations off under `prefers-reduced-motion`, spec §"Accessibility & robustness"); the app animates the focus lift unconditionally. | It is the one accessibility affordance the design input actually names, and it is a one-line environment read. |
| **P4** | **No pause when the app leaves the foreground.** `scenePhase` is read, but only to write a log line. | Pressing HOME on the Siri Remote leaves the film playing behind the tvOS Home screen. |
| **P5** | **No Now Playing information.** Nothing publishes title/duration/position to `MPNowPlayingInfoCenter`. | The system's own "what's playing" surface, the Siri Remote's play/pause when the app is not frontmost, and *"Hey Siri, pause"* all read from it. It is a platform integration a native tvOS player is expected to have. |
| **P6** | **No row semantics.** The player never uses `.focusSection()`, while `DetailView` and `ProfilesView` both do — and `KNOWN_ISSUES` #15 is the round this repo spent learning why. | The bar, the scrubber and the transport row are three rows of one screen. A section is how a directional gesture is aimed at one of them. |
| **P7** | **No Up Next.** At the end of an episode the film simply stops. | The single biggest difference between a player and a TV app for series viewing — and the data is already on the wire (`GET /api/library/series/{id}/episodes`, which `DetailStore` already fetches for the title screen). |
| **P8** | **An episode's top bar says only its own name.** | `"Chapter 4"` over a film that belongs to a series names nothing a viewer recognises. The series name is in the same `ItemDetail` (`series.name`), already decoded, unused by this screen. |

### 1.3 What is deliberately NOT built (and why) — so it is not relitigated

| Not built | Why |
|---|---|
| **Chapter ticks + the scrub thumbnail** | ⚠ **Unchanged from `TVOS_PLAYER_PLAN.md` §7.3 and re-measured today: there is nothing on the wire.** `grep -rn "Chapters\|chapter" backend/api backend/services` finds no chapter data and no trickplay endpoint. An invented marker is a lie a viewer can check. |
| **`AVAudioSession` configuration** | ⚠ Considered and **not taken**. For a *video* app whose audio is entirely `AVPlayer`'s, tvOS manages the session; the explicit `setCategory(.playback)` dance exists for apps that own audio in the background (music/podcasts). It would be added risk on an unverifiable Mac round for no behaviour this app can name. The knob if a round ever shows a problem is one call in `PlayerView.start()`. |
| **`MPRemoteCommandCenter` handlers** | The Siri Remote's play/pause is already `.onPlayPauseCommand`, and there is no background-audio mode to serve. `MPNowPlayingInfoCenter` (P5) **publishes**; nothing needs to be subscribed. |
| **Skip-intro / skip-credits** | Same class as chapters: Jellyfin intro markers are not proxied by this api. Not a client decision. |
| **A "next episode" request from the player for a MOVIE's sequel** | Nothing on the wire ties two films together except `/api/jellyfin/similar`, which carries a *TMDB* id and **no Jellyfin item id** (recorded in `TVOS_TITLE_SCREEN_PLAN.md` §3). Up Next is therefore **series-only**, and honest about it. |

---

## §2 — The changes *(BUILT — this section is now the record of what landed, not a proposal)*

### Phase P1 — the defects, and the screen a viewer falls back on

**Pure rules (`Core/PlaybackRules.swift` — compiled and RUN here):**

* `jogTarget(from:direction:total:)` — **D2's rule**: `skipTarget` with the jog's own 30 s, named so the screen
  says what it is doing instead of passing a bare `30` into a general rule. It composes the already-pinned
  `skipTarget`; it is not a second clamp.
* `ladderStep(_:)` / `ladderLength` / `attemptSentence(_:)` — **D3's copy**. The escalation must be *visible*
  ("Trying Remux · HLS (2 of 3)…"), and the numbers in that sentence are the ladder's, derived not typed.
* `failedItemSentence` — **D4's** one sentence for an item that never started, so the store and the view
  cannot disagree about it.

**The store (`Core/PlaybackStore.swift`):**

* **D3:** `reportPlaybackFailure(_:)` **escalates before it reports** — if `nextHLSMode(after: mode)` exists it
  climbs and says so; only at the end of the ladder does the sentence become permanent state. This is a
  single funnel, so the notification path and the item-status path cannot diverge.
* **D4:** `escalationAttempt` is published; `hasFailed` stays the screen's one question.
* **P1:** `retryPlayback()` — clears the failure and **re-requests**, climbing the ladder when there is a rung
  left and otherwise re-attaching the same URL. It publishes `reloadToken`, because `url` is `Equatable` and
  re-assigning an equal value fires no `onChange` — a retry that silently does nothing is worse than none.
* **D6:** `finish()` is **idempotent** (`didFinish`), because there are two legitimate callers (Back, and
  `onDisappear`) and the platform does not promise which fires first.

**The views (`Player/PlayerView.swift`, `Player/PlayerChrome.swift`):**

* **D1:** the tooltip takes the target time; `PlayerScrubStyle` gains the label it draws.
* **D2:** `.onMoveCommand` on the focused track → `onJog(±1)` → `store.jog(direction:)`.
* **D4/P1:** the item's `status == .failed` is **polled by the existing 0.5 s ticker** — the only mechanism
  that catches "it never started", and the one that needs no new notification name.
* **P1:** the failure notice becomes a **focusable** card: `Try again` (and the way back), the ring moved onto
  it when it appears, and MENU still leaves. A message is not allowed to be the only thing on a screen.
* **P2:** a `ProgressView` while `isSwitching`.
* **P3:** `@Environment(\.accessibilityReduceMotion)` — the pulse and the three focus lifts lose their spring,
  keeping the colour/ring change so focus stays visible.
* **P4:** `scenePhase` → pause (and a paused film is a film whose chrome stays up, by the existing rule).
* **P5:** `MPNowPlayingInfoCenter` published from the ticker — title, duration, elapsed, rate — and cleared on
  the way out. ⚠ `import MediaPlayer`, and `check-imports.py` gains a **`MediaPlayer` rule** in the same commit
  (the `RKMServerKit` lesson: a framework the app uses and no gate watches is a blind spot by construction).
* **P6:** `.focusSection()` on the bar and on the transport row — the fix his own round confirmed on the title
  screen (`KNOWN_ISSUES` #15).
* **D5:** `start()`'s bare-item path is **deleted**; `attachItem` is the only place an item is created, so the
  credential cannot be forgotten by one of two paths.
* **D7:** `onDisappear` pauses and detaches.

### Phase P2 — Up Next

* **Rules:** `nextEpisode(after:in:)` — ⚠⚠ **POSITIONAL, not `episode + 1`**. The server's list is the only
  authority on what comes next: a season boundary, a mid-season special, or a gap in the numbering all break
  arithmetic, and the list is already in hand. `upNextRemaining(deadline:now:)` for the countdown, and
  `upNextCardFacts(...)` for the copy. `finished(positionTicks:runtimeTicks:)` — the server's own 0.95 — is the
  trigger, **reused rather than re-stated**.
* **Store:** fetches the series' episodes once, when the item is an episode; computes `nextEpisode`; starts the
  countdown the moment the position crosses the finish fraction; `cancelUpNext()`; and publishes a
  **handoff** when the countdown expires or *Play now* is pressed (the store does not know `AppModel` exists).
* **Views:** the Up Next card (thumbnail, `S2E5 · name`, *Play now*, *Cancel*), focus defaulted to *Play now*
  when it appears — the platform's own behaviour, and the only sane default on a screen whose countdown expires.
* **`AppModel`/`AppRootView`:** a one-line identity on the player view (`.id(playback.itemID)`) so an episode
  handed off in place **re-runs the screen's own start path** rather than silently keeping the old store — the
  alternative is a new `PlaybackStore` with no `onAppear`, which is a frozen "Preparing…" screen.

---

## §3 — Gates

```bash
python3 apple/scripts/check-tvos-core.py              # the rules above RUN here
python3 apple/scripts/check-tvos-members.py           # rules 1–9 (a name this file gets wrong costs a round)
python3 apple/scripts/check-tvos-models.py            # models + endpoints
python3 apple/scripts/check-imports.py apple/tvos/RKMCinemaTV
python3 apple/scripts/check-design-tokens.py
TMPDIR=/root/tmp bash apple/scripts/check-apple-typecheck.sh
python3 tools/check_md_links.py
```

⚠ **`--falsify` is NOT run** — his standing rule is *dev + unit tests, then his round*. The new mutations are
**written**, and unexercised until he asks for them.

---

## §4 — His round: the falsifiers, written before the build

⚠ Anything not listed here that the round shows is a bonus; anything listed that fails names its own cause.

| # | Falsifier | What disproves it |
|---|---|---|
| **P-F1** | **the scrub tooltip reads the seek time, not `0:00`** | it reads `0:00` on every film (D1 survived) |
| **P-F2** | **with the track focused, left/right jog ±30 s** and the times update | the ring moves to another control, or nothing happens (D2 survived) |
| **P-F3** | **a stream that fails climbs the ladder**: the toast says `Trying Remux · HLS (2 of 3)…` and playback restarts | it goes straight to the failure sentence, or it loops without progress (D3) |
| **P-F4** | **an unreachable/black stream produces the failure notice rather than a silent black frame** (D4) | a black frame with no notice |
| **P-F5** | **the failure notice is pressable**: focus lands on `Try again` and pressing it re-attempts | nothing is focusable; MENU is the only way out |
| **P-F6** | **a stall shows a spinner** (P2) | a frozen frame with no indicator |
| **P-F7** | **pressing HOME pauses the film**, and returning to the app shows it still paused (P4) | audio continues over the tvOS Home screen |
| **P-F8** | **an episode that finishes shows the Up Next card**, the countdown runs, and *Play now* plays the next episode — which then appears in Continue Watching in the web app | no card; a card whose countdown does nothing; the next episode opens on a frozen `Preparing…` |
| **P-F9** | **the last episode of a series shows no card** (the rule must be able to say "there is no next") | a card for an episode that does not exist |
| **P-F10** | **MENU still leaves the player from every state** — playing, paused, notice up, Up Next up, drawer open | any state where MENU does nothing (the dead-end rule) |

⚠ **What this round CANNOT prove:** nothing about real Apple TV hardware (the simulator is not one), and a
`BUILD FAILED` proves nothing about any of P-F1…P-F10 — it is a build round.

---

## §5 — As built (2026-09-20)

| | |
|---|---|
| **Files** | `Core/PlaybackRules.swift` (`jogTarget`, `ladderStep`/`ladderLength`/`attemptSentence`, `failedToStartSentence`, the Up Next block; **`saveHintDelay` DELETED** — D8) · `Core/PlaybackStore.swift` (`reportPlaybackFailure` as the funnel, `escalateMode() -> Bool`, `retryPlayback`, `reloadToken`, `reportItemFailed`, `jog(direction:)`, idempotent `finish()`, `baseURL`, `seriesName`/`episodeCode`/`hasFinished`/`upNextLabel`/`upNextCountdownLabel`, `loadNextEpisode`, `tickUpNext`, `playNextNow`/`cancelUpNext`/`clearUpNextHandoff`, `PlaybackFacts.from(EpisodeItem)`) · `Player/PlayerChrome.swift` (three new `PlayerFocus` cases, the series eyebrow, the jog via `onMoveCommand`, `onSeek` **deleted**, the tooltip's real time + centring, `.focusSection()` ×2, reduced motion ×2, and the three new surfaces: `PlayerStallIndicator`, `PlayerFailureNotice` + `PlayerNoticeButtonStyle`, `PlayerUpNextCard`) · `Player/PlayerView.swift` (`MediaPlayer` import, `scenePhase`/`reduceMotion`, the notice/card/stall overlays, the `.failed`-status poll, `tickUpNext`, `publishNowPlaying`, `handOff(to:)`, `jog(_:)`, `leave()`/`onDisappear` cleanup, `start()` with one attach path, `chromeVisible` pins on the card, the chrome `.disabled` behind the notice) · `App/AppRootView.swift` (`.id(playback.itemID)`) · `Design/TVTokens.swift` (the Phase P block) |
| **Gates** | `check-tvos-core.py` **687 / 0** · `check-tvos-members.py` **PASS — 36 pairs** · `check-tvos-models.py` **PASS — 180 keys, 25 endpoints** · `check-imports.py <tvos>` **PASS — 51 files** · `check-imports.py --selftest` **12/12** · `check-design-tokens.py` **PASS** · `check-apple-typecheck.sh` **PASS** · `check_md_links.py` **79 files** |
| **Mutations** | **11 written · 11 EXERCISED** (applied to the real sources, compiled, required to go RED on the named line). ⚠ `--falsify` was **not** run — his standing rule — and this narrower pass is not a substitute for it |
| **⚠ NOT verified** | **not one SwiftUI view compiles here.** `PlayerView`, `PlayerChrome`, `PlaybackStore`, `AppRootView` and `DesignColours` are Mac-only. What IS executed: the jog and the clamp, the ladder's arithmetic and its termination, the episode selection (including the season boundary and the last episode), the countdown's rounding, and the two new surfaces' placement arithmetic |

---

## §6 — PHASE P2: HIS ROUND ON P, AND THE FOUR THINGS IT FOUND (2026-09-20)

He ran a round and reported four defects. **Three of them are in code this phase did not touch, and one is a
defect phase P *introduced*** — so they are recorded here rather than folded into §5 as if they had always been
part of the plan. ⚠ **His words are the report; the mechanism is the diagnosis; every one is a line number.**

### 6.1 · BUG 1 — the transport said *Play* over a film that was playing

> *"when i resume any title, i can see play button icon on the title while its playing in the background (its
> should be pause button, since its already playing). Then when i click on the play icon it changes to pause
> button, but the titles keeps playing, i click again the pause button turns to play and then finally the title
> stops the play."*

⚠⚠ **ONE DESYNCHRONISED FLAG, AND HIS THREE SENTENCES ARE ITS THREE SYMPTOMS.** `PlaybackStore.isPlaying`
started **`false`** (`PlaybackStore.swift:111`) while `PlayerView.attachItem` started the film with
`player.rate = Float(store.rate)` — **`rate = 1` IS `play()` in `AVPlayer`**. So: the glyph described a state the
app was not in; the first press therefore called `play()` on a film that was already playing (nothing visible,
which is why he pressed again); and **the second press did the pausing he had asked for on the first.**

⚠ **His file is the authority for the value, and it says so in one line** — `…player.html:489`:
`let isPlaying = true;`. Opening this screen is what the `Play` / `Resume (9%)` verb promised, and round 6
confirmed the film resumes and plays.

### 6.2 · BUG 2 — the controls never auto-hid

> *"the controls never auto hide and always on the screen"*

⚠⚠ **TWO INDEPENDENT CAUSES, AND EITHER ONE ALONE WOULD HAVE DONE IT.**

| | Cause | Where |
|---|---|---|
| **a** | the same `isPlaying` desync — `shouldHideChrome(playing: false, …)` returns at its SECOND line, so the 4 s clock was never consulted | §6.1 |
| **b** | ⚠⚠ **INTRODUCED BY PHASE P**: the screen passed `isAnythingFocused` as `panelOpen` — *"a focused control keeps the chrome on"*. **On a television something is ALWAYS focused** (the focus engine puts a ring on something the instant `.defaultFocus($focus, .play)` applies), so that condition is a constant `true` and the rule could never fire for any film, ever | `PlayerView.chromeVisible` |

⚠ **His own JS, verbatim** (`…player.html:706`): `if(isPlaying && !settingsOpen && !infoOpen)` — a drawer, an
info panel, or nothing. **No focus condition exists in it**, and `resetIdle()` is called from the `keydown`
handler at `:721`, i.e. on **every key press, whatever it does**.

⇒ **Two mechanisms, two jobs.** What PINS the chrome is a MODE with no timeout (a drawer, the Up Next card) —
now `PlaybackRules.chromePinned`, which deliberately has **no focus parameter**. What RESTARTS its clock is
*input*, and the app had no equivalent of `resetIdle()` at all: `lastInteraction` was written by `togglePlay`,
`skip` and `jog` only, so crossing the transport with Up/Down/Left/Right would not have touched it — the
controls would then have vanished *while the viewer was using them*, which is the bug that fixing (b) alone
would have created.

### 6.3 · BUG 3 — *"i cant use touch control … to move forward or backward wherever i want"*

⚠ **Two things were true at once, and only one of them was ours.**

1. **The scrub existed and was unreachable in one press.** His file's row 1 is the whole track and left/right
   *inside it* jogs — phase P wired that — but the viewer lands on `play`, so left/right moved focus to
   `Back 10s` / `Forward 10s` and the only verbs he ever met were the ±10 s buttons.
2. ⚠⚠ **AND PHASE P MADE IT WORSE**: it gave the transport row `.focusSection()` and left the track outside it.
   The engine prefers targets INSIDE the section the ring is in (`KNOWN_ISSUES` #15's lesson), so a row that is
   a section can hold the ring and make `Up` do nothing — killing the one gesture that reaches the scrubber.
   **The track and the transport are one section again.**

⇒ And his *"wherever i want"* is answered by **`PlaybackRules.jogSteps`**: 30 s on a single press (his file's
own step), then 60 · 120 · 300 · 600 while the presses keep coming, resetting to 30 s after a 1.2 s pause.
⚠ **This ladder is the APP'S OWN — his file has one step**, and it is declared as an addition, not transcribed.
At a flat 30 s a 2h40 film is **320 presses** end to end; at the top step it is 16. ⚠ The FIRST step is still
his, so a single press behaves exactly as the prototype does.

### 6.4 · BUG 4 — *"where is the other control which was there in the html file"* (the settings drawer)

⚠⚠ **THE DRAWER WAS BUILT AND NEVER FINISHED, AND THE EVIDENCE IS SIX TOKENS WITH ZERO READERS.** All six were
transcribed from his file and then read by nothing — the same class as `saveHintDelay` (D8), at six times the
size:

| Dead token | His line | What it was for |
|---|---|---|
| `settingsHeaderSize`, `settingsHeaderTop` | `…player.html:234` | **the "PLAYER SETTINGS" title** — the most visible thing missing from the panel, and the label that says what the rail of five words IS |
| `settingsTopPad`, `settingsBottomPad` | `:229` (`padding:5.5% 0 4.5%`) | the panel's own inset, so its first row is not against the screen edge where tvOS crops |
| **`navFocusScale` (1.06)** | `:246` | the rail's **focus lift** — the drawer's rail gave no feedback on focus beyond a 10 % background tint, against a near-black panel, at three metres |
| **`listFocusScale` (1.04)** | `:273` | the same for the **Audio Track / Subtitles lists** — the two panes that ARE lists had a focused row pixel-identical to every other row |

⚠⚠ **AND THE ONE THAT IS NOT A TOKEN: the drawer never claimed focus.** It is drawn as an `.overlay`, and
**an overlay is VISUAL ONLY** — the lesson `KNOWN_ISSUES` #17 already bought on the profile picker. So the
panel appeared over the transport with the transport still in the focus chain: the ring stayed on the headphone
button *behind* the panel, and a direction press either did nothing or went somewhere invisible. A drawer that
looks right and cannot be used — which is exactly what *"where is the other control"* describes.

⚠ **Also fixed with it:** the trigger's glyph was `speaker.wave.2.fill`, and his file draws a **headphone**
(`:340`) — the very icon he pointed at in his screenshot. His file is the spec for the shape, so the trigger is
now `headphones`. And `left/right moves between the rail and the pane` (his spec) now has a `.focusSection()` on
each side, without which the two are just siblings in an `HStack` and `Right` from the rail has nowhere to go.

### 6.5 · The instrument, so the next round is not another guess

`PlaybackStore.openSettings()` / `closePanel()` now log **`player: drawer opened on <category>`** /
**`player: drawer closed`**. ⚠ The one fact that splits *"the trigger never fired"* from *"the panel drew and he
could not tell"* is whether the app was ever ASKED to open it, and that line is the answer. Run the round **with
`-RKMDebugHUD YES`** and read it from the FILE log (`find "$(xcrun simctl get_app_container booted
com.helloraj1986.RKMCinemaTV data)" -name rkm-tvos.log`).

### 6.6 · His round, on P2

| # | Falsifier | What disproves it |
|---|---|---|
| **P2-F1** | **a resumed film shows `pause.fill` immediately**, and ONE press pauses it | the glyph says *Play* while the picture moves (bug 1 survives) |
| **P2-F2** | **the controls hide ~4 s into playback**, and **come back on any arrow press** — including a press that moves the ring nowhere | they never hide, or they vanish while he is navigating them |
| **P2-F3** | **`Up` from `Play` reaches the scrub track**, and left/right there jogs — 30 s, then 60, 120, 300, 600 as he keeps pressing | `Up` does nothing (the section split is back) |
| **P2-F4** | **the headphone button opens the drawer and the ring is INSIDE it**: the rail lifts as it moves, `Right` enters the pane, `Left` returns, and **Audio Track / Subtitles rows lift on focus** | the panel opens with the ring still behind it, or a focused row is indistinguishable |
| **P2-F5** | **the panel opens with a "PLAYER SETTINGS" header**, inset from the top edge | no header (the panel is unlabelled again) |
| **P2-F6** | **MENU still leaves the player** from playing, paused, notice-up, drawer-open and Up-Next-up | any state where MENU does nothing |

⚠ **What this round cannot prove:** nothing about real Apple TV hardware, and a `BUILD FAILED` proves nothing
about any of P2-F1…P2-F6. ⚠ **And if his round had not yet included phase P**, a build failure has to be
bisected by commit — the four boundaries are named in `PROGRESS.md`.

## §7 — As built (P2)

| | |
|---|---|
| **Rules** | `PlaybackRules.chromePinned(panelOpen:upNextCardVisible:)` — **no focus parameter, deliberately** · `jogSteps` / `jogAccelerationWindow` / `jogRepeats(current:gapSinceLastJog:)` / `jogStep(repeats:)`, and `jogTarget(…:step:)` with his 30 s as the default |
| **Store** | `isPlaying` starts **`true`** (his `:489`) · `jog(direction:)` walks the ladder and toasts the step once it exceeds 30 s · `endJogRun()` (the ±10 s buttons end a run) · `openSettings`/`closePanel` log |
| **Views** | `chromeVisible` asks `chromePinned` · `noteInput()` on `focus`, `drawerFocus` AND the root `onMoveCommand` (three routes, because a press reaches the app by one of exactly three) · the track + transport are ONE section · the headphone glyph · the drawer's header, inset, two focus scales, focus claim and two sections |
| **Gates** | `check-tvos-core.py` **712 / 0** (was 687) · members **36 pairs** · models · imports **51 files** · selftest 12/12 · tokens · typecheck · md-links |
| **Mutations** | **6 new** (1 re-pointed, because `jogTarget`'s signature moved its anchor) — **all exercised**: applied, compiled, RED on the named line |
| **⚠ NOT verified** | the same as §5 — **no SwiftUI view compiles here**. The four focus changes (one section around track + transport; two sections plus a focus claim in the drawer) are **hypotheses** with falsifiers P2-F3 / P2-F4, and no gate on this machine can run a focus engine |
