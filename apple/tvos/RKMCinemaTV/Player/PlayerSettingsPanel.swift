import SwiftUI

/// The player's settings drawer — his `.settings-panel`: a category rail on the left and the open pane on the
/// right, over the film.
///
/// ⚠⚠ **EVERY CONTROL IN IT IS BACKED BY SOMETHING THE SERVER (OR THE CLIENT) CAN ACTUALLY DO**, which is the
/// measurement in `docs/TVOS_PLAYER_PLAN.md` §7.3: speed and picture are client-side, quality and the audio
/// track ride parameters the api honours, and subtitles come from `playback-info` / `subtitle-search` /
/// `subtitle-select` / `subtitle-disable`. ⚠ **"Search OpenSubtitles…" is drawn only when the server says its
/// search half is enabled** — with no OpenSubtitles key configured the api turns it off by design, and a row
/// that offered it anyway would be offering what the server will refuse.
struct PlayerSettingsPanel: View {

    // ⚠⚠ **`focus` IS A PASSED `FocusState` BINDING, AND ALL THREE OF ITS RULES COST A BUILD ROUND
    // (2026-09-20, round 2):** (1) it is **not** a property wrapper here, so there is **no `$focus`** —
    // `$` exists only where the wrapper is DECLARED (`PlayerView`); (2) assigning goes through
    // `focus.wrappedValue = …`, because the binding itself is a `let`; (3) `.focused(focus, equals:)` takes
    // the binding, which is why every call site passes `focus`. ⚠ All three failures are compile errors on the
    // Mac and invisible to every gate on this machine — `check-tvos-members.py` sees the file's MEMBER NAMES,
    // and `$`/`wrappedValue` are syntax, not a namespaced member.

    @ObservedObject var store: PlaybackStore
    /// ⚠⚠ **A `FocusState` BINDING, NOT A `@Binding`** — `.focused(_:equals:)` takes only
    /// `FocusState<Value?>.Binding`, and a plain `Binding<DrawerFocus?>` compiles right up until that call.
    /// The screen owns the state (`@FocusState private var drawerFocus`) and passes `$drawerFocus`.
    let focus: FocusState<DrawerFocus?>.Binding
    // ⚠⚠ **THERE IS NO `onClose` HERE ANY MORE, AND IT WAS THE DEFECT.** The panel declared one, the screen
    // passed `closePanel()` to it, and **nothing in the panel ever called it** — so the drawer had NO exit of
    // its own, and the root `.onExitCommand` went straight to `leave()`: MENU with the drawer open left the
    // film. His report: *"how does the user comes out of it, the back button should close it automatically"*.
    // ⚠ The way out is MENU, the ladder is `PlaybackRules.menuTarget`, and it is executed by the SCREEN — so
    // the parameter that promised a close the panel never performed is gone rather than left named.

    var body: some View {
        // ⚠⚠ **THE DRAWER IS A COLUMN WITH A HEADER — AND THE HEADER WAS THE MOST VISIBLE THING MISSING.**
        // His screenshot's panel opens with **"PLAYER SETTINGS"** in small uppercase letterspaced type, and
        // `TVTokens.Player.settingsHeaderSize` / `settingsHeaderTop` were transcribed for exactly that line
        // (`…player.html:234`: `.settings-header { position:absolute; top:2.6%; left:2.6em; right:2.6em;
        // font-size:.78rem; letter-spacing:.09em; … text-transform:uppercase }`) **and read by nothing**. An
        // untitled rail of five words reads as a stray menu; the title is what says it is the player's settings.
        // ⚠ His `position:absolute` means the header does NOT push the nav down, which is why it is a `VStack`
        // header rather than an overlay: the nav's own inset (`settingsHeaderTop`) is what sits under it.
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: TVTokens.Player.contentGap) {
                Text("Player Settings")
                    .font(.system(size: TVTokens.Player.settingsHeaderSize, weight: .bold))
                    .tracking(TVTokens.Player.settingsHeaderTracking)
                    .textCase(.uppercase)
                    .foregroundStyle(RKMColour.muted)
                Spacer(minLength: 0)
                // ⚠⚠ **THE WAY OUT, WRITTEN DOWN — his report: *"once the headphone icon is clicked and overlay
                // opens how does the user comes out of it, the back button should close it automatically"*.**
                // It DOES now (`PlaybackRules.menuTarget`: MENU closes the drawer before it ever closes the
                // film, and `PlayerView.closePanel()` puts the ring back on the headphone button) — but a control
                // nobody is told about is a control that does not exist, and the panel had no line saying so.
                // ⚠ Muted and un-focusable on purpose: it is furniture, not a row, and a viewer must never be
                // able to land the ring on a hint.
                Text("MENU closes")
                    .font(.system(size: TVTokens.Player.sectionHeaderSize, weight: .semibold))
                    .tracking(TVTokens.Player.settingsHeaderTracking)
                    .textCase(.uppercase)
                    .foregroundStyle(RKMColour.muted.opacity(0.7))
            }
            .padding(.horizontal, TVTokens.Player.settingsHeaderInset)
            .padding(.top, TVTokens.Player.settingsHeaderTop)

            HStack(alignment: .top, spacing: 0) {
                rail
                content
            }
        }
        .frame(width: drawerWidth, alignment: .leading)
        // ⚠ `padding:5.5% 0 4.5%` — the panel's own vertical inset, also read by nothing until now. Without it
        // the drawer's first row sat against the top edge of a 1080 pt screen, where tvOS's overscan crops.
        .padding(.top, TVTokens.Player.settingsTopPad)
        .padding(.bottom, TVTokens.Player.settingsBottomPad)
        .background(RKMColour.background.opacity(0.86))
        .overlay(alignment: .leading) {
            Rectangle().fill(Color.white.opacity(0.09)).frame(width: 1)
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
        .transition(.move(edge: .trailing))
    }

    /// `.settings-panel { width: min(58%, 760px) }` — resolved here the way CSS resolves it, and the
    /// comment in `TVTokens.Player` records which of the two values wins on a 1920 pt screen.
    private var drawerWidth: CGFloat {
        min(1920 * TVTokens.Player.settingsFraction, TVTokens.Player.settingsMaxWidth)
    }

    // MARK: - The rail (`.settings-nav`)

    private var rail: some View {
        VStack(alignment: .leading, spacing: TVTokens.Player.navGap) {
            ForEach(PlaybackRules.SettingsCategory.allCases, id: \.self) { category in
                Button {
                    store.selectCategory(category)
                    focus.wrappedValue = .category(category)
                } label: {
                    Text(category.title)
                        .font(.system(size: TVTokens.Player.navItemSize, weight: .semibold))
                }
                .buttonStyle(DrawerNavStyle(isCurrent: store.category == category))
                .focused(focus, equals: .category(category))
            }
        }
        .frame(width: TVTokens.Player.navWidth, alignment: .leading)
        .padding(.leading, TVTokens.Player.settingsHeaderInset)
        // ⚠⚠ **THE RAIL IS A SECTION, AND SO IS THE PANE — THIS IS WHAT MAKES THE DRAWER NAVIGABLE AT ALL.**
        // His spec (§"Settings panel"): *"Left/Right moves between the rail and whichever content is on the
        // right"*. Without a section on each side the two are just siblings in an `HStack`, and `Right` from
        // the rail has no section to be aimed at — the same class of defect as `KNOWN_ISSUES` #15, and the
        // reason a drawer that LOOKS right can be unusable. ⚠ A hypothesis (falsifier **P2-F4**).
        .focusSection()
    }

    // MARK: - The content (`.settings-content`)

    private var content: some View {
        VStack(alignment: .leading, spacing: TVTokens.Player.contentGap) {
            switch store.category.pane {
            case .segmented:
                segmentedPane
            case .list:
                listPane
            }
            Spacer(minLength: 0)
            footer
        }
        .padding(.horizontal, TVTokens.Player.contentPaddingH)
        .frame(maxWidth: .infinity, alignment: .leading)
        // ⚠ The pane is the drawer's OTHER section — the order matters (`frame` THEN `focusSection`), because
        // a section is aimed at by its frame and must take up more space than its contents (round 12).
        .focusSection()
        .overlay(alignment: .leading) {
            Rectangle().fill(Color.white.opacity(0.09)).frame(width: 1)
        }
    }

    /// Picture / Speed / Quality — each is a row of small mutually exclusive choices.
    @ViewBuilder
    private var segmentedPane: some View {
        Text(store.category.title)
            .font(.system(size: TVTokens.Player.paneTitleSize, weight: .regular, design: .serif))
            .foregroundStyle(RKMColour.primary)

        HStack(spacing: TVTokens.Player.segGap) {
            ForEach(Array(segments.enumerated()), id: \.offset) { index, segment in
                Button {
                    segment.apply()
                    // ⚠ After a choice the focus goes back to the RAIL, which is what his prototype's
                    // `activateSettingsItem` leaves the viewer able to do next (up/down changes category).
                    // Nothing about this is retro-fitted maths: the platform moves focus, the app only says
                    // where it should be.
                    focus.wrappedValue = .category(store.category)
                } label: {
                    Text(segment.title)
                        .font(.system(size: TVTokens.Player.segSize, weight: .bold))
                }
                .buttonStyle(DrawerSegmentStyle(isSelected: segment.isSelected))
                .focused(focus, equals: .row(index))
            }
        }

        Text(store.category == .picture ? store.pictureCaption
             : store.category == .quality ? store.qualityCaption
             : "Playback speed for this session.")
            .font(.system(size: TVTokens.Player.paneDescSize))
            .foregroundStyle(RKMColour.muted)
    }

    /// Audio Track / Subtitles — the item's own tracks, and (for subtitles) the api's own actions.
    ///
    /// ⚠⚠ **THE LIST IS BOUNDED AND IT SCROLLS, AND THAT IS THE FIX FOR HIS ROUND.** It used to be a bare
    /// `VStack` of every row it had, so **19 OpenSubtitles results grew the whole drawer to 1875.2 pt on a
    /// 1080 pt screen** — and a child taller than its container overflows BOTH ways, so the panel's header and
    /// all five rail items were drawn ABOVE the top edge. His words: *"i click on subtitles all the other
    /// control vanishes"*. ⚠ The region's ceiling is `PlaybackRules.paneListHeight`, which is arithmetic against
    /// `Metric.screenHeight` (`settingsPanelFits`), not a taste.
    ///
    /// ⚠ On tvOS a `ScrollView` scrolls when focus moves onto something INSIDE it (the app's own recorded rule,
    /// and the reason the title screen has none) — every row here is a focusable `Button`, so it scrolls.
    @ViewBuilder
    private var listPane: some View {
        Text(store.category.title)
            .font(.system(size: TVTokens.Player.paneTitleSize, weight: .regular, design: .serif))
            .foregroundStyle(RKMColour.primary)

        ScrollView {
            VStack(alignment: .leading, spacing: TVTokens.Player.listGap) {
                ForEach(Array(rows.enumerated()), id: \.offset) { index, row in
                    // ⚠⚠ **A SECTION LABEL IS NOT A ROW.** It is drawn as text and carries NO `.focused`, so the
                    // focus engine steps over it — a header a viewer could land on would be a press that does
                    // nothing, which is the defect this repo keeps finding in overlays.
                    if row.isSection {
                        Text(row.title.uppercased())
                            .font(.system(size: TVTokens.Player.sectionHeaderSize, weight: .semibold))
                            .kerning(TVTokens.Player.sectionHeaderSize * 0.09)
                            .foregroundStyle(RKMColour.muted)
                            .padding(.top, index == 0 ? 0 : TVTokens.Player.sectionHeaderTopPad)
                    } else {
                        Button {
                            row.apply()
                        } label: {
                            HStack(alignment: .center, spacing: TVTokens.Player.contentGap) {
                                // ⚠ WHAT CAN BE DONE — a leading glyph on an action row, in the accent the
                                // style already gives its text.
                                if let glyph = row.glyph {
                                    Image(systemName: glyph)
                                        .font(.system(size: TVTokens.Player.actionGlyphSize,
                                                      weight: .semibold))
                                        .frame(width: TVTokens.Player.actionGlyphSize)
                                }
                                VStack(alignment: .leading, spacing: TVTokens.Player.subtitleRowGap) {
                                    Text(row.title)
                                        .lineLimit(1)
                                        // ⚠ Truncating from the MIDDLE: a subtitle release name's tail
                                        // (`.1080p.BluRay.x264-AC3`) is what tells two results apart, and the head is
                                        // the film's own title, which is on every row.
                                        .truncationMode(.middle)
                                    // ⚠ The second line only exists for a row that HAS a second fact — `Off`, a
                                    // local track and the search action are one-liners, so they stay one line.
                                    if let detail = row.detail {
                                        Text(detail)
                                            .font(.system(size: TVTokens.Player.subtitleDetailSize))
                                            .foregroundStyle(RKMColour.muted)
                                            .lineLimit(1)
                                    }
                                }
                                Spacer(minLength: 0)
                                // ⚠⚠ **THE SETTING'S VALUE — accent FILLED**, the third of the accent's three
                                // jobs. A control that is doing something is a filled pill; a control that is not
                                // (or a value that excludes nothing) is plain muted text.
                                if let value = row.value {
                                    Text(value)
                                        .font(.system(size: TVTokens.Player.subtitleDetailSize,
                                                      weight: .semibold))
                                        .foregroundStyle(row.role == .applied
                                                         ? RKMColour.background : RKMColour.muted)
                                        .padding(.horizontal, TVTokens.Player.badgePaddingH)
                                        .padding(.vertical, TVTokens.Player.badgePaddingV)
                                        .background(
                                            Capsule().fill(row.role == .applied
                                                           ? RKMColour.accent : Color.white.opacity(0.08))
                                        )
                                }
                                // ⚠⚠ **THE BADGE — accent OUTLINED**: the row the auto-pick would take. A
                                // different SHAPE from the applied row's filled bar, so "what will be picked" and
                                // "what is on" can never be confused at three metres.
                                if let badge = row.badge {
                                    Text(badge)
                                        .font(.system(size: TVTokens.Player.subtitleDetailSize,
                                                      weight: .semibold))
                                        .foregroundStyle(RKMColour.accent)
                                        .padding(.horizontal, TVTokens.Player.badgePaddingH)
                                        .padding(.vertical, TVTokens.Player.badgePaddingV)
                                        .overlay(
                                            RoundedRectangle(cornerRadius: TVTokens.Player.badgeRadius,
                                                             style: .continuous)
                                                .stroke(RKMColour.accent, lineWidth: TVTokens.Player.pillStrokeWidth)
                                        )
                                }
                                if row.role == .applied {
                                    Image(systemName: "checkmark")
                                        .font(.system(size: TVTokens.Player.checkSize, weight: .bold))
                                        .foregroundStyle(RKMColour.accent)
                                }
                            }
                        }
                        .buttonStyle(DrawerListStyle(role: row.role, isAction: row.isAction))
                        .focused(focus, equals: .row(index))
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        // ⚠ The bound. `rows.count` drives it, and the rule caps it — so a pane can never outgrow the drawer.
        .frame(maxHeight: PlaybackRules.paneListHeight(rowCount: rows.count))

        if store.category == .subtitles, store.isSearchingSubtitles {
            Text("Searching…")
                .font(.system(size: TVTokens.Player.paneDescSize))
                .foregroundStyle(RKMColour.muted)
        }
        // ⚠⚠ **AND WHEN THE LIST IS HELD BACK, IT SAYS SO** — `Showing 8 of 19 results`. A capped list that says
        // nothing is a truncation the viewer cannot see, which is the defect this line exists to prevent.
        if store.category == .subtitles, let shown = store.subtitleShownLine {
            Text(shown)
                .font(.system(size: TVTokens.Player.paneDescSize))
                .foregroundStyle(RKMColour.muted)
        }
        // ⚠⚠ **AND WHEN THE AUTO-PICK COULD NOT DO ITS JOB, IT SAYS THAT TOO** — but only for the answers a
        // viewer can ACT on (`quota_unknown` names the OpenSubtitles sign-in that fixes it). ⚠ The states he
        // created himself — a choice, a per-title `Off`, the switch — are visible in the rows above, and
        // printing them would put a line under every title he has ever touched.
        if store.category == .subtitles,
           let notice = PlaybackRules.autoPickNotice(decision: store.autoDecision,
                                                     reason: store.autoReason) {
            Text(notice)
                .font(.system(size: TVTokens.Player.paneDescSize))
                .foregroundStyle(RKMColour.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// `.settings-footer` — the mode badge, the real track counts, and the position save state.
    ///
    /// ⚠⚠ **The save line is the app's own, and it is the reason this footer is not just his badge.** Two
    /// writes in this repo answered `204` and stored nothing, so the store re-reads what the server now holds
    /// and says which of the three things happened: saved · refused · *could not check*. A viewer who sees
    /// "Saved 2:40:02" knows; one who sees nothing at all assumes it worked.
    private var footer: some View {
        VStack(alignment: .leading, spacing: TVTokens.Player.paneDescSize * 0.5) {
            HStack {
                Text(store.modeBadge)
                    .font(.system(size: TVTokens.Player.footerSize, weight: .semibold))
                    .foregroundStyle(RKMColour.muted)
                    .padding(.horizontal, TVTokens.Player.badgePaddingH)
                    .padding(.vertical, TVTokens.Player.badgePaddingV)
                    .overlay(
                        RoundedRectangle(cornerRadius: TVTokens.Player.badgeRadius, style: .continuous)
                            .stroke(Color.white.opacity(0.09), lineWidth: 1)
                    )
                Spacer(minLength: 0)
                Text(store.trackSummary)
                    .font(.system(size: TVTokens.Player.footerSize))
                    .foregroundStyle(RKMColour.muted)
            }
            if let save = store.saveSentence {
                Text(save)
                    .font(.system(size: TVTokens.Player.footerSize))
                    .foregroundStyle(RKMColour.muted)
            }
            if !store.subtitleWarning.isEmpty {
                Text(store.subtitleWarning)
                    .font(.system(size: TVTokens.Player.footerSize))
                    .foregroundStyle(RKMColour.muted)
            }
            if let remaining = store.remainingDownloads {
                Text("\(remaining) subtitle downloads left today")
                    .font(.system(size: TVTokens.Player.footerSize))
                    .foregroundStyle(RKMColour.muted)
            }
        }
        .padding(.top, TVTokens.Player.footerTopPad)
        .overlay(alignment: .top) {
            Rectangle().fill(Color.white.opacity(0.09)).frame(height: 1)
        }
    }

    // MARK: - Rows

    /// One choice in a segmented pane.
    private struct Segment {
        let title: String
        let isSelected: Bool
        let apply: () -> Void
    }

    private var segments: [Segment] {
        switch store.category {
        case .picture:
            return PlaybackRules.PictureMode.allCases.map { mode in
                Segment(title: mode.title, isSelected: store.picture == mode) { store.setPicture(mode) }
            }
        case .speed:
            return PlaybackRules.rates.map { rate in
                Segment(title: PlaybackRules.rateLabel(rate), isSelected: store.rate == rate) {
                    store.setRate(rate)
                }
            }
        case .quality:
            return PlaybackRules.qualities.map { quality in
                Segment(title: quality.label, isSelected: store.quality == quality.label) {
                    store.setQuality(quality.label)
                }
            }
        case .audio, .subtitles:
            return []
        }
    }

    /// One row in a list pane.
    private struct Row {
        let title: String
        /// ⚠⚠ **THE ROW'S SECOND LINE — `EN · srt · opensubtitles · 42.4k downloads · used 2×`, or `nil`
        /// for a row that has only one fact.**
        ///
        /// ⚠ It exists because a remote result's *title* is its release filename
        /// (`.The.Mummy.1999.1080p.BluRay.x264.AC3-ETRG`), which is nineteen near-identical strings to a viewer
        /// and tells him nothing he needs: **his own round's screenshot is exactly that list.** The language,
        /// the format, the provider, the download count and our own usage are the fields that separate one
        /// result from another, and all five are on the wire. ⚠ Built by `PlaybackRules.subtitleRowDetail`,
        /// so the line cannot invent a fact.
        var detail: String? = nil
        /// **The trailing badge** — `Most downloaded` / `Your pick before` / `Auto-applied` on the row the
        /// auto-pick is about, and `nil` on every other row. ⚠ Accent-OUTLINED, which is what makes it a
        /// different object from an applied row's accent FILLED bar.
        var badge: String? = nil
        /// **A SETTING's current value** (`Most downloaded (en)`, `None`) — the accent-filled pill, so a
        /// control that is doing something looks different from one that is not.
        var value: String? = nil
        /// **A leading glyph — the mark of an ACTION row** (`magnifyingglass`, `wand.and.stars`, `speaker.slash`).
        /// ⚠ What can be DONE reads as an affordance, not as a state.
        var glyph: String? = nil
        /// **A section label.** ⚠ Drawn as muted, NON-FOCUSABLE text: the pane's structure is the other half of
        /// *"hard to understand"*, and a header a viewer could focus would be a row that does nothing.
        var isSection: Bool = false
        /// **Which of the accent's three jobs this row has** (see `PlaybackRules.rowRole`).
        var role: PlaybackRules.RowRole = .plain
        var isAction: Bool = false
        let apply: () -> Void
    }

    private var rows: [Row] {
        switch store.category {
        case .audio:
            return store.audioRows.map { track in
                Row(title: track.name,
                    role: PlaybackRules.rowRole(isApplied: store.isSelectedAudio(track),
                                                isCandidate: false)) {
                    store.setAudioIndex(track.index)
                }
            }
        case .subtitles:
            var rows: [Row] = []
            // ⚠⚠ **THE PANE'S STRUCTURE, AND IT IS NOT DECORATION.** Twelve rows of five different KINDS used
            // to sit in one column — the film's own tracks, an api action, a provider's catalogue and two
            // settings — and his words were *"the subtitle ux is a bit hard to understand"*. A label per group
            // is the cheapest half of the answer (the accent language is the other): it says where "things I can
            // choose" ends and "things I can do" begins.
            rows.append(section("Your choice"))
            // ⚠⚠ **"Off" IS A WRITE, NOT A LOCAL TOGGLE.** The api's own description of
            // `POST /jellyfin/subtitle-disable`: *"Turn subtitles off for an item without forgetting which
            // one was chosen."* A client-side "off" would be undone by the next load, and the viewer would
            // watch the app re-apply a subtitle they had turned off — which is why this goes through the
            // store's `disableSubtitles()` (and why that call re-reads `playback-info` afterwards).
            rows.append(Row(title: "Off",
                            role: PlaybackRules.rowRole(isApplied: store.subtitleIndex == nil,
                                                        isCandidate: false)) {
                Task { await store.disableSubtitles() }
            })
            rows += store.localSubtitleRows.map { track in
                Row(title: track.name,
                    detail: "on disk",
                    role: PlaybackRules.rowRole(isApplied: store.subtitleIndex == track.index,
                                                isCandidate: false)) {
                    Task { await store.chooseLocalSubtitle(index: track.index) }
                }
            }
            if store.subtitleSearchEnabled || !store.remoteSubtitleRows.isEmpty {
                rows.append(section("From OpenSubtitles"))
            }
            if store.subtitleSearchEnabled {
                rows.append(Row(title: "Search OpenSubtitles…", glyph: "magnifyingglass",
                                isAction: true) {
                    Task { await store.searchSubtitles() }
                })
            }
            // ⚠⚠ **ONE ROW PER RESULT, TWO LINES EACH, AND ONLY AFTER HE ASKED.** `store.remoteSubtitleRows`
            // is empty until `searchSubtitles()` — so this list starts as the rows that matter (`Off`, the
            // film's own tracks) and grows only on the viewer's own action.
            rows += store.remoteSubtitleRows.map { row in
                Row(title: row.displayTitle,
                    // ⚠ The facts that separate two release names: language, format, provider,
                    // downloads, our own usage, SDH.
                    detail: PlaybackRules.subtitleRowDetail(row),
                    badge: autoBadge(for: row),
                    // ⚠ The badge says what the rule WOULD take; the BAR says what is ON. ⚠ `row.active` is the
                    // SERVER's answer to "is this the chosen one" (`merge_subtitle_rows` writes it from the
                    // stored identity), so the bar and the playing subtitle cannot disagree — and `rowRole`'s
                    // precedence (applied first) is what keeps one row from claiming both.
                    role: PlaybackRules.rowRole(isApplied: row.active,
                                                isCandidate: row.subtitleID == (store.autoFacts?.subtitleID ?? ""))) {
                    Task { await store.chooseRemoteSubtitle(row) }
                }
            }
            // ⚠⚠ **THE TWO CONTROLS HIS DECISION NAMED** — the global switch and the per-AUDIO-language
            // exclusion — and they live HERE, at the foot of the pane the rule acts on, rather than in a
            // settings screen three screens away from the moment he wants to turn it off.
            // ⚠ Each row states its CURRENT state in its VALUE PILL (accent-filled when the setting is doing
            // something, muted when it is not): a control that reports what it will do rather than what is true
            // is the thing this repo keeps having to fix elsewhere.
            // ⚠ Both are WRITES to the api — one state, two clients — so the web panel shows the same value.
            rows.append(section("Automatic"))
            rows.append(Row(title: "Auto-subtitles",
                            detail: "Applies the best result when a title has none of its own",
                            value: PlaybackRules.autoPickSettingLabel(
                                settings: store.subtitleSettings, language: store.autoLanguage),
                            glyph: "wand.and.stars",
                            role: store.subtitleSettings.autoPick ? .applied : .plain,
                            isAction: true) {
                Task { await store.setAutoPick(!store.subtitleSettings.autoPick) }
            })
            if !store.autoLanguage.isEmpty {
                let excluded = store.subtitleSettings.autoPickSkipAudio.contains(store.autoLanguage)
                rows.append(Row(
                    title: "Skip audio language",
                    detail: excluded
                        ? "Titles whose audio is \(PlaybackRules.languageName(store.autoLanguage)) are never auto-picked"
                        : "Auto-subtitles applies to every language",
                    value: PlaybackRules.autoPickSkipLabel(
                        codes: store.subtitleSettings.autoPickSkipAudio),
                    glyph: "globe",
                    role: excluded ? .applied : .plain,
                    isAction: true) {
                    Task { await store.setAutoSkipAudio(store.autoLanguage, included: !excluded) }
                })
            }
            return rows
        case .picture, .speed, .quality:
            return []
        }
    }

    /// ⚠ A section label is a `Row` with no action, so the pane keeps ONE ordered list — its labels cannot
    /// drift out of step with the rows they describe.
    private func section(_ title: String) -> Row {
        Row(title: title, isSection: true) {}
    }

    /// Which badge a row earns — ⚠ **and it is the SERVER's answer, never a local guess.**
    ///
    /// `store.autoFacts.subtitleID` is the row the api's own rule would take (it ranks, filters to the
    /// auto language, and excludes SDH) — so this badge and the subtitle the api applies **cannot disagree**.
    /// `Auto-applied` is the identity that actually landed, which the response names.
    private func autoBadge(for row: SubtitleRow) -> String? {
        guard !row.subtitleID.isEmpty else { return nil }
        if row.subtitleID == store.autoAppliedID { return "Auto-applied" }
        guard let facts = store.autoFacts, row.subtitleID == facts.subtitleID else { return nil }
        let badge = PlaybackRules.autoPickBadge(basis: facts.basis)
        return badge.isEmpty ? nil : badge
    }
}

// MARK: - The drawer's styles (each owns its own box — the U7 rule)

/// `.settings-nav-item` / `.is-focused`.
struct DrawerNavStyle: ButtonStyle {

    let isCurrent: Bool

    func makeBody(configuration: Configuration) -> some View {
        NavChrome(configuration: configuration, isCurrent: isCurrent)
    }

    private struct NavChrome: View {

        let configuration: ButtonStyle.Configuration
        let isCurrent: Bool
        @Environment(\.isFocused) private var isFocused
        @Environment(\.accessibilityReduceMotion) private var reduceMotion

        var body: some View {
            configuration.label
                // ⚠⚠ **THE RAIL ANSWERS THE SAME QUESTION AS THE LIST: *what am I looking at?*** — so the
                // current category is ACCENT, like a selected segment and an applied row. ⚠ Before this it was
                // `primary` at 6 % white, which is the same colour the focused row's text uses: on a near-black
                // panel at three metres, "which pane is open" and "where the ring is" were the same picture.
                // ⚠ `DrawerSegmentStyle` had already settled this for the segmented panes (his own drawer's
                // `seg-btn.is-selected` is filled with the accent) — this is the list/rail half of the same rule.
                .foregroundStyle(isFocused ? RKMColour.primary
                                           : (isCurrent ? RKMColour.accent : RKMColour.secondary))
                .padding(.horizontal, TVTokens.Player.navItemPaddingH)
                .padding(.vertical, TVTokens.Player.navItemPaddingV)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: TVTokens.Player.navItemRadius, style: .continuous)
                        .fill(isFocused ? Color.white.opacity(0.1)
                                        : (isCurrent ? RKMColour.accent.opacity(0.12) : .clear))
                )
                // ⚠⚠ **THE RAIL'S FOCUS LIFT, WHICH NO VIEW EVER DREW** — his `.settings-nav-item.is-focused
                // { transform:scale(1.06) }` (`…player.html:246`). `TVTokens.Player.navFocusScale` had **zero
                // readers** from the day it was transcribed, so the drawer's rail gave NO feedback on focus: the
                // background tint was the only cue, and against a near-black panel at three metres it is not
                // one. ⚠ Drawn INSIDE the style, which is the U7 rule — the style owns its box.
                .scaleEffect(isFocused && !reduceMotion ? TVTokens.Player.navFocusScale : 1)
                .animation(reduceMotion ? nil : .timingCurve(0.34, 1.56, 0.64, 1, duration: 0.22),
                           value: isFocused)
        }
    }
}

/// `.seg-btn` / `.selected` / `.is-focused`.
struct DrawerSegmentStyle: ButtonStyle {

    let isSelected: Bool

    func makeBody(configuration: Configuration) -> some View {
        SegmentChrome(configuration: configuration, isSelected: isSelected)
    }

    private struct SegmentChrome: View {

        let configuration: ButtonStyle.Configuration
        let isSelected: Bool
        @Environment(\.isFocused) private var isFocused

        var body: some View {
            configuration.label
                .foregroundStyle(isSelected ? RKMColour.background : RKMColour.secondary)
                .padding(.horizontal, TVTokens.Player.segPaddingH)
                .padding(.vertical, TVTokens.Player.segPaddingV)
                .background(
                    RoundedRectangle(cornerRadius: TVTokens.Player.segRadius, style: .continuous)
                        .fill(isSelected ? RKMColour.accent : Color.white.opacity(0.06))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: TVTokens.Player.segRadius, style: .continuous)
                        .stroke(isFocused ? RKMColour.accentHover : Color.clear,
                                lineWidth: TVTokens.Player.focusRingWidth)
                )
                .scaleEffect(isFocused ? TVTokens.Player.segFocusScale : 1)
                .animation(.timingCurve(0.34, 1.56, 0.64, 1, duration: 0.22), value: isFocused)
        }
    }
}

/// `.settings-item` / `.selected` / `.action` / `.is-focused`.
struct DrawerListStyle: ButtonStyle {

    let role: PlaybackRules.RowRole
    let isAction: Bool

    func makeBody(configuration: Configuration) -> some View {
        ListChrome(configuration: configuration, role: role, isAction: isAction)
    }

    private struct ListChrome: View {

        let configuration: ButtonStyle.Configuration
        let role: PlaybackRules.RowRole
        let isAction: Bool
        @Environment(\.isFocused) private var isFocused
        @Environment(\.accessibilityReduceMotion) private var reduceMotion

        var body: some View {
            configuration.label
                .font(.system(size: TVTokens.Player.listItemSize))
                .foregroundStyle(colour)
                .padding(.horizontal, TVTokens.Player.listItemPaddingH)
                .padding(.vertical, TVTokens.Player.listItemPaddingV)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: TVTokens.Player.listItemRadius, style: .continuous)
                        .fill(isFocused ? Color.white.opacity(0.1) : .clear)
                )
                // ⚠⚠ **THE ACCENT BAR IS *WHAT IS APPLIED* — and it is a SHAPE, not a colour, on purpose.**
                // The focus ring is accent-coloured too, so a row that was merely FOCUSED and a row that was
                // SELECTED would be the same picture if the distinction were colour alone. The bar cannot be
                // confused with anything: it is on the row's leading edge, it is there when the ring is
                // elsewhere, and it survives a scroll. His report: *"use the accent color on what is selected
                // what is applied"*.
                .overlay(alignment: .leading) {
                    if role == .applied {
                        Capsule()
                            .fill(RKMColour.accent)
                            .frame(width: TVTokens.Player.rowAccentBarWidth)
                            .padding(.vertical, TVTokens.Player.listItemPaddingV * 0.5)
                    }
                }
                // ⚠⚠ **AND THE LIST ROWS' OWN LIFT** — his `.settings-item.is-focused { transform:scale(1.04) }`
                // (`…player.html:273`). `TVTokens.Player.listFocusScale` was the second of the drawer's two
                // dead focus tokens, and it is the one that matters most: Audio Track and Subtitles are LISTS
                // (`DetailRules`-style rows), so on those two panes the focused row was pixel-identical to
                // every other row. ⚠ Both scales are his numbers, not the app's.
                .scaleEffect(isFocused && !reduceMotion ? TVTokens.Player.listFocusScale : 1)
                .animation(reduceMotion ? nil : .timingCurve(0.34, 1.56, 0.64, 1, duration: 0.22),
                           value: isFocused)
        }

        /// ⚠⚠ **THREE QUESTIONS, THREE COLOURS — and the ORDER is the meaning.**
        ///
        /// * **action** → `accentHover`: his own file's rule (`.settings-item.action { color:
        ///   var(--gold-bright) }`), and the answer to *"what can be done?"* — a row that DOES something is not
        ///   a row that sets a value.
        /// * **applied** → `accent`: the answer to *"what is on now?"*. ⚠ It outranks focus, because a viewer
        ///   scrolling past the current subtitle should still see which one it is.
        /// * **everything else** → primary (focused) / secondary: no accent at all.
        private var colour: Color {
            if isAction { return RKMColour.accentHover }
            if role == .applied { return RKMColour.accent }
            if isFocused { return RKMColour.primary }
            return RKMColour.secondary
        }
    }
}
