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
    let onClose: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            rail
            content
        }
        .frame(width: drawerWidth, alignment: .leading)
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
    @ViewBuilder
    private var listPane: some View {
        Text(store.category.title)
            .font(.system(size: TVTokens.Player.paneTitleSize, weight: .regular, design: .serif))
            .foregroundStyle(RKMColour.primary)

        VStack(alignment: .leading, spacing: TVTokens.Player.listGap) {
            ForEach(Array(rows.enumerated()), id: \.offset) { index, row in
                Button {
                    row.apply()
                } label: {
                    HStack {
                        Text(row.title)
                        Spacer(minLength: 0)
                        if row.isSelected {
                            Image(systemName: "checkmark")
                                .font(.system(size: TVTokens.Player.checkSize, weight: .bold))
                        }
                    }
                }
                .buttonStyle(DrawerListStyle(isSelected: row.isSelected, isAction: row.isAction))
                .focused(focus, equals: .row(index))
            }
        }

        if store.category == .subtitles, store.isSearchingSubtitles {
            Text("Searching…")
                .font(.system(size: TVTokens.Player.paneDescSize))
                .foregroundStyle(RKMColour.muted)
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
        let isSelected: Bool
        let isAction: Bool
        let apply: () -> Void
    }

    private var rows: [Row] {
        switch store.category {
        case .audio:
            return store.audioRows.map { track in
                Row(title: track.name, isSelected: store.isSelectedAudio(track), isAction: false) {
                    store.setAudioIndex(track.index)
                }
            }
        case .subtitles:
            var rows: [Row] = [
                // ⚠⚠ **"Off" IS A WRITE, NOT A LOCAL TOGGLE.** The api's own description of
                // `POST /jellyfin/subtitle-disable`: *"Turn subtitles off for an item without forgetting which
                // one was chosen."* A client-side "off" would be undone by the next load, and the viewer would
                // watch the app re-apply a subtitle they had turned off — which is why this goes through the
                // store's `disableSubtitles()` (and why that call re-reads `playback-info` afterwards).
                Row(title: "Off", isSelected: store.subtitleIndex == nil, isAction: false) {
                    Task { await store.disableSubtitles() }
                },
            ]
            rows += store.localSubtitleRows.map { track in
                Row(title: track.name, isSelected: store.subtitleIndex == track.index, isAction: false) {
                    Task { await store.chooseLocalSubtitle(index: track.index) }
                }
            }
            if store.subtitleSearchEnabled {
                rows.append(Row(title: "Search OpenSubtitles…", isSelected: false, isAction: true) {
                    Task { await store.searchSubtitles() }
                })
            }
            rows += store.remoteSubtitleRows.map { row in
                Row(title: "\(row.displayTitle) · \(row.language.uppercased())",
                    isSelected: false, isAction: false) {
                    Task { await store.chooseRemoteSubtitle(row) }
                }
            }
            return rows
        case .picture, .speed, .quality:
            return []
        }
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

        var body: some View {
            configuration.label
                .foregroundStyle(isFocused || isCurrent ? RKMColour.primary : RKMColour.secondary)
                .padding(.horizontal, TVTokens.Player.navItemPaddingH)
                .padding(.vertical, TVTokens.Player.navItemPaddingV)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: TVTokens.Player.navItemRadius, style: .continuous)
                        .fill(isFocused ? Color.white.opacity(0.1)
                                        : (isCurrent ? Color.white.opacity(0.06) : .clear))
                )
                .animation(.timingCurve(0.34, 1.56, 0.64, 1, duration: 0.22), value: isFocused)
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

    let isSelected: Bool
    let isAction: Bool

    func makeBody(configuration: Configuration) -> some View {
        ListChrome(configuration: configuration, isSelected: isSelected, isAction: isAction)
    }

    private struct ListChrome: View {

        let configuration: ButtonStyle.Configuration
        let isSelected: Bool
        let isAction: Bool
        @Environment(\.isFocused) private var isFocused

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
                .animation(.timingCurve(0.34, 1.56, 0.64, 1, duration: 0.22), value: isFocused)
        }

        /// ⚠ `.settings-item.action { color: var(--gold-bright) }` — an ACTION reads as a different kind of
        /// row from a choice, which is what stops "Search OpenSubtitles…" from looking like a track you can
        /// select.
        private var colour: Color {
            if isAction { return RKMColour.accentHover }
            if isFocused { return RKMColour.primary }
            return isSelected ? RKMColour.primary : RKMColour.secondary
        }
    }
}
