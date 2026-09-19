import SwiftUI

/// The Home screen — Phase B's first real content screen, and the replacement for Phase A's
/// `SessionReadyView` placeholder.
///
/// ⚠ **THE WAYS OUT STAY.** Phase A's note applies unchanged: a TV screen with no focusable exit is a dead
/// end, and a dead end on a TV is a phone call. So `Change profile`, `Sign out` and `Change server` sit at
/// the top of this screen exactly as they did on the placeholder — the middle of the screen changed, the
/// exits did not.
///
/// ⚠ **Everything this screen SHOWS is decided in `HomeRails.swift`**, which is pure and executed on Linux:
/// which rails exist, their order, their caps, and which of the four states (loading / content / empty /
/// failed) the screen is in. This type lays that out, and nothing else. A state decision made here would be
/// a decision no test could reach.
///
/// ⚠ **A hero is deliberately absent** — the plan's two rows, nothing more (`TVOS_LIBRARY_PLAN.md` §B2),
/// and `PosterCard`/`RailView` keep the rail's own layout so a hero can be added above them later without
/// touching either.
struct HomeView: View {

    @EnvironmentObject private var app: AppModel
    @ObservedObject var store: HomeStore
    let base: URL

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header

            Group {
                if !store.hasLoaded && store.isLoading {
                    loading
                } else if let placeholder = store.snapshot.placeholder {
                    message(placeholder.title, placeholder.sub)
                } else {
                    rails
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)

            footer
        }
        // ⚠ `.task` and not `.onAppear`: the load is async and the screen must not be re-fetched by a
        // re-render — `HomeStore.load()` is idempotent in effect but each call is two requests.
        .task {
            await store.load()
        }
    }

    // MARK: - The exits, and who is watching

    private var header: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline, spacing: 20) {
                Text("RKMCinemaTV")
                    .font(.system(size: 44, weight: .bold))
                Spacer(minLength: 20)
                // ⚠ The profile is on screen on purpose. `signed in as X` + `watching as Y` is precisely the
                // state the server's identity seam exists for, and the one a wrong implementation gets
                // silently wrong — so the screen names who it is showing a library for.
                Text(watchingAs)
                    .font(.system(size: 24))
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 18) {
                Button("Change profile") { Task { await app.changeProfile() } }
                Button("Sign out") { Task { await app.signOut() } }
                Button("Change server") { app.changeServer() }
                Button("Refresh") { Task { await store.load() } }
            }
            .font(.system(size: 22))
        }
        .padding(.horizontal, 60)
        .padding(.top, 44)
        .padding(.bottom, 10)
        .buttonStyle(.bordered)
    }

    private var watchingAs: String {
        let profile = app.session?.currentProfile?.name
        let user = app.session?.signedInUser?.name
        switch (user, profile) {
        case (let user?, let profile?):
            return "Signed in as \(user) · watching as \(profile)"
        case (let user?, nil):
            return "Signed in as \(user)"
        default:
            return ""
        }
    }

    // MARK: - The three non-content states

    private var loading: some View {
        VStack(alignment: .leading, spacing: 16) {
            ProgressView()
                .controlSize(.large)
            Text("Loading your library…")
                .font(.system(size: 24))
                .foregroundStyle(.secondary)
        }
        .padding(60)
    }

    private func message(_ title: String, _ sub: String) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(title)
                .font(.system(size: 36, weight: .semibold))
            Text(sub)
                .font(.system(size: 24))
                .foregroundStyle(.secondary)
            // ⚠ The retry is a real Button, so it is focusable — an error screen whose only action cannot
            // be reached with the remote is the dead end this app keeps designing out.
            Button("Try again") { Task { await store.load() } }
                .font(.system(size: 22))
                .padding(.top, 6)
        }
        .padding(60)
        .buttonStyle(.borderedProminent)
    }

    // MARK: - The rails

    private var rails: some View {
        ScrollView(.vertical, showsIndicators: false) {
            VStack(alignment: .leading, spacing: 42) {
                ForEach(store.snapshot.rails) { rail in
                    RailView(rail: rail, base: base, onSelect: open)
                }
            }
            .padding(.vertical, 10)
        }
    }

    /// ⚠ The rows that FAILED, said out loud. A row that did not load and a row that is genuinely empty look
    /// identical on screen, and only one of them is worth pressing `Refresh` about — so the difference is
    /// written down rather than left to the viewer to guess. Hidden when nothing failed.
    @ViewBuilder
    private var footer: some View {
        if !store.snapshot.failedRowTitles.isEmpty {
            Text("Couldn't load: \(store.snapshot.failedRowTitles.joined(separator: ", "))")
                .font(.system(size: 20))
                .foregroundStyle(.orange)
                .padding(.horizontal, 60)
                .padding(.bottom, 30)
        }
    }

    // MARK: - Select

    /// ⚠ **B2 has no item detail screen, so the honest thing is to say so.** The card is a real Button and
    /// Select must do *something* the viewer can see — but opening nothing at all reads as a broken remote.
    /// The detail screen is B4, and this is the one line that changes when it lands.
    private func open(_ item: MediaItem) {
        RKMLog.info("home: selected \(item.title) (\(item.itemID.prefix(8))) — the detail screen is Phase B4",
                    category: .app)
    }
}
