---
title: "RKM Cinema — Premium Media Library Redesign"
document_type: "AI Agent UI/UX + Development Specification"
version: "1.0"
status: "Implementation Reference"
audience: "Hermes AI Development Agent"
---

# RKM Cinema — Premium Media Library Redesign

> **Implementation reference for Hermes**
>
> This document is the authoritative UI/UX and frontend design reference for redesigning RKM Cinema. Preserve existing media-library functionality while rebuilding the presentation as a premium personal streaming-library experience.

## How Hermes Should Use This Document

1. Treat explicit requirements in this document as design constraints, not suggestions.
2. Prefer reusable, data-driven components over page-specific implementations.
3. Use the centralized design tokens instead of arbitrary values.
4. Preserve existing backend/media functionality unless a requirement explicitly changes it.
5. When requirements conflict, prioritize: **usability → accessibility → consistency → performance → visual polish**.
6. Do not merely restyle the current UI; refactor information architecture and component structure where required.
7. Validate every major screen on desktop, tablet, and mobile.
8. Implement in the phases defined near the end of this document.
9. Do not invent new visual patterns when an existing pattern in this specification can be reused.
10. The final result should feel like a **private premium streaming service**, not a media database dashboard.

---

### Master UI/UX + Development Specification for the AI Hermes Agent

> **Purpose:** This document is intended to be sufficiently detailed that an AI development agent can use it as the primary product/design specification and implement the redesign without needing to infer major UX, visual, interaction, or component decisions.
>
> **Scope:** Personal movie + TV-show media library. The **Movies** and **TV Shows** experiences should share the same design system and interaction model while adapting their content appropriately.

---

# 1. PRODUCT VISION

Transform the existing RKM Cinema interface from a functional media dashboard into a **premium personal streaming-library experience**.

The new product should feel like a combination of:

-  Apple TV 
-  Netflix 
-  Plex 
-  Letterboxd 
-  modern macOS/iPadOS interfaces 
-  a high-end personal media-management application 

But it should **not copy any one product**.

The core design philosophy is:

> **Cinematic, calm, intelligent, information-rich, extremely easy to navigate, and visually premium.**

The current interface is functional but feels like an internal dashboard:

-  too much empty black space 
-  rigid card grid 
-  weak visual hierarchy 
-  limited metadata 
-  basic navigation 
-  inconsistent spacing 
-  filters feel like developer controls 
-  posters don't feel sufficiently cinematic 
-  Continue Watching does not feel like a primary experience 
-  insufficient distinction between browsing and managing a library 

The redesign should make the user feel:

> **“This is my private Netflix.”**

---

# 2. DESIGN PRINCIPLES

Hermes must follow these principles throughout the application.

## 2.1 Content is the hero

The interface should never visually compete with movie artwork.

Prioritize:

1.  Artwork 
2.  Title 
3.  Watching state 
4.  Important metadata 
5.  Actions 
6.  Secondary metadata 

Avoid excessive borders, decorative elements, and unnecessary UI chrome.

---

## 2.2 Cinematic rather than dashboard-like

The current UI uses a traditional application/dashboard layout.

Replace that feeling with:

-  large artwork 
-  subtle gradients 
-  soft shadows 
-  atmospheric backgrounds 
-  restrained typography 
-  large cinematic hero areas 
-  horizontal content rails 
-  elegant overlays 

The UI should feel closer to a streaming service than a database.

---

## 2.3 Dark does not mean pure black everywhere

Use multiple dark surfaces.

### Color foundation

```
Background:
#08090B

Primary Surface:
#101216

Secondary Surface:
#15171C

Elevated Surface:
#1B1E24

Card Surface:
#17191E

Border:
rgba(255,255,255,0.08)

Primary Text:
#F5F5F7

Secondary Text:
#A7AAB2

Muted Text:
#70747E

Accent:
#FFC400

Accent Hover:
#FFD43B

Success:
#35D07F

Warning:
#FFB020

Error:
#FF5B5B
```

Yellow should remain the application's signature accent because the current UI already establishes this visual language.

However:

> **Yellow should be used as an accent, not as a dominant color.**

---

# 3. TYPOGRAPHY

Use a premium modern sans-serif.

Preferred:

```
Inter
SF Pro Display
SF Pro Text
```

Fallback:

```
system-ui
-apple-system
BlinkMacSystemFont
Segoe UI
sans-serif
```

### Typography hierarchy

```
Display:
48–64px
font-weight: 700
letter-spacing: -0.04em

Page Heading:
32–40px
font-weight: 700
letter-spacing: -0.03em

Section Heading:
22–26px
font-weight: 650

Card Title:
15–17px
font-weight: 600

Metadata:
13–14px
font-weight: 500

Small metadata:
11–12px
font-weight: 500

Navigation:
14–15px
font-weight: 550
```

Do not use excessive bold text.

Premium interfaces rely on **weight + spacing + hierarchy**, not everything being bold.

---

# 4. GLOBAL APPLICATION STRUCTURE

The application should have five major layers.

```
┌───────────────────────────────────────────────┐
│                  TOP BAR                      │
├──────────────┬────────────────────────────────┤
│              │                                │
│              │                                │
│   SIDEBAR    │         CONTENT AREA           │
│              │                                │
│              │                                │
│              │                                │
└──────────────┴────────────────────────────────┘
```

However, the sidebar should become substantially more elegant than the current version.

---

# 5. SIDEBAR REDESIGN

## 5.1 Desktop sidebar

Width:

```
240px expanded
72px collapsed
```

The current 330-ish sidebar visual footprint is too heavy.

Use:

```
background: #0B0C0F
border-right: 1px solid rgba(255,255,255,.06)
```

### Structure

```
RKM
Cinema
────────────────

HOME

⌂ Home

LIBRARY

▣ Movies
▤ TV Shows

COLLECTIONS

♡ Watchlist
✦ Discover

TOOLS

⌕ Search
✦ Suggest

────────────────
Settings
Profile
```

The logo should become a **brand lockup** rather than just text.

Example:

```
[RKM icon]

RKM
Cinema
```

On collapsed mode:

```
[RKM]
⌂
▣
▤
♡
✦
⌕
⚙
```

---

# 6. SIDEBAR ACTIVE STATE

Current active state is too blocky.

Replace it with:

```
┌──────────────────────────────┐
│ ●  Movies                    │
└──────────────────────────────┘
```

Use:

```
background: rgba(255,255,255,.08)
border: 1px solid rgba(255,255,255,.04)
border-radius: 10px
```

Add a tiny yellow indicator:

```
width: 3px
height: 18px
background: #FFC400
border-radius: 4px
```

The active navigation item should feel **selected**, not like a button.

---

# 7. TOP BAR

The desktop content should have a lightweight top bar.

### Left

Breadcrumb/context:

```
Library / Movies
```

### Right

```
⌕ Search
＋ Add
↻ Scan
⋯
Avatar
```

Do not expose too many buttons.

The top bar should be approximately:

```
height: 64px
```

and visually disappear into the content area.

---

# 8. HOME PAGE — COMPLETE REDESIGN

The Home page should not simply be a collection of horizontal card rows.

It should be an **intelligent personal media dashboard**.

Recommended structure:

```
HOME

Hero / Continue Watching

Continue Watching

Recently Added

Because You Watched...

Your Movies

Your TV Shows

Recently Played

Watchlist

Genres
```

Not every section needs to appear simultaneously.

Hermes should allow the page to be configured based on available data.

---

# 9. HOME HERO

The first viewport should contain a large cinematic hero.

Example:

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│                  LARGE BACKDROP                          │
│                                                         │
│  CONTINUE WATCHING                                      │
│                                                         │
│  Mad Max: Fury Road                                     │
│                                                         │
│  2015 · Action · Adventure · 2h                         │
│                                                         │
│  ███████████████░░░░  15%                              │
│                                                         │
│  [▶ Resume]   [＋ Watchlist]   [⋯ More]                │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

Use a large backdrop image.

Apply gradients:

```
linear-gradient(
  90deg,
  #08090B 0%,
  rgba(8,9,11,.85) 35%,
  rgba(8,9,11,.2) 75%,
  rgba(8,9,11,.8) 100%
)
```

and:

```
linear-gradient(
  0deg,
  #08090B 0%,
  transparent 60%
)
```

This allows artwork to blend naturally into the interface.

---

# 10. CONTINUE WATCHING

This is one of the most important sections.

Cards should be larger than ordinary library cards.

### Card

```
width: 300–360px
aspect-ratio: 16 / 9
border-radius: 12px
```

Instead of poster-first cards, Continue Watching should primarily use **landscape backdrops**.

Overlay:

```
bottom gradient
title
episode/movie information
progress bar
```

Example:

```
┌─────────────────────────────────┐
│                                 │
│             ARTWORK              │
│                                 │
│                                 │
│─────────────────────────────────│
│ The Stars Our Destination       │
│ S01 E06 · 42 min                │
│ ████████████░░░░ 57%            │
└─────────────────────────────────┘
```

Hover:

```
scale: 1.025
```

Show:

```
▶ Resume
```

and secondary controls.

---

# 11. MOVIES PAGE

The Movies page should retain the basic concept from the current screenshot but become significantly more refined.

Recommended structure:

```
Movies

[ Search ]                     [Sort] [View]

All
Action
Adventure
Comedy
Crime
Drama
Romance
Sci-Fi
Thriller

────────────────────────────

6 Movies

[ Movie Grid ]
```

---

# 12. MOVIE PAGE HEADER

Use:

```
Movies
6 movies
```

rather than:

```
Movies
jellyfin · 6 titles
```

Technical source information should not be exposed prominently to the user.

If necessary, place it in settings/debug information.

---

# 13. SEARCH

Search should be prominent but elegant.

```
┌──────────────────────────────────────┐
│ ⌕  Search movies...                  │
└──────────────────────────────────────┘
```

Width:

```
280–360px
```

On focus:

```
border-color: rgba(255,196,0,.5)
box-shadow: 0 0 0 3px rgba(255,196,0,.08)
```

Search should support:

-  title 
-  actor 
-  director 
-  genre 
-  year 
-  collection 
-  watched state 

Examples:

```
mad max
2015
action
movies with Tom Hardy
unwatched sci-fi
```

---

# 14. FILTER SYSTEM

The current filter chips are good conceptually but need refinement.

Use a horizontally scrollable filter bar.

```
[All] [Action] [Adventure] [Comedy] [Crime] [Drama]
```

Selected:

```
background: #FFC400
color: #111
```

Unselected:

```
background: rgba(255,255,255,.06)
border: 1px solid rgba(255,255,255,.08)
color: #B7BAC2
```

Border radius:

```
999px
```

This creates a pill system.

---

# 15. ADVANCED FILTERS

Add a filter button:

```
⚙ Filters
```

Opening it produces a popover/drawer:

```
FILTERS

Genres
☐ Action
☐ Adventure
☐ Comedy
☐ Drama

Year
[ 2000 ] — [ 2026 ]

Rating
──────●──────

Watch status
○ All
○ Watched
○ Unwatched
○ In progress

Duration
○ Any
○ < 90 min
○ 90–120 min
○ 120+ min

[Reset]                 [Apply]
```

---

# 16. SORTING

Sort options:

```
Recently Added
Title A–Z
Title Z–A
Release Date
Rating
Recently Played
Progress
Runtime
```

Dropdown should be compact and elegant.

---

# 17. VIEW MODE

Allow:

```
▦ Grid
☷ Compact
```

Default:

```
Grid
```

Compact mode can show:

```
Poster | Title | Year | Genre | Runtime | Rating | Status
```

This is particularly useful for large libraries.

---

# 18. MOVIE GRID

The grid should be responsive.

### Desktop

```
5–7 cards depending on viewport width
```

### Large desktop

```
7–9 cards
```

### Tablet

```
4–5 cards
```

### Mobile

```
2 cards
```

Do not hardcode five columns.

Use CSS Grid:

```
grid-template-columns:
repeat(auto-fill, minmax(180px, 1fr));
```

But use sensible maximum widths so posters do not become oversized.

---

# 19. MOVIE CARD

The current card is functional but should become significantly more polished.

Structure:

```
┌───────────────────────────┐
│                           │
│       POSTER              │
│                           │
│                  ⋯        │
│                           │
│            ▶              │
└───────────────────────────┘
Movie Title
2015 · 2h 0m
```

Poster:

```
aspect-ratio: 2 / 3
border-radius: 10px
overflow: hidden
```

Do not put excessive information over the poster.

---

# 20. MOVIE CARD BADGES

Top-left:

```
MOVIE
```

should be replaced with a subtle icon/type indicator.

Example:

```
🎬 Movie
```

But preferably use an icon rather than emoji.

For TV:

```
▣ TV
```

Use:

```
font-size: 10px
text-transform: uppercase
letter-spacing: .08em
```

---

# 21. WATCH PROGRESS

Progress should always be visible when applicable.

At bottom of poster:

```
████████████░░░░
```

Color:

```
#FFC400
```

Height:

```
3px
```

For completed content:

```
#35D07F
```

For unwatched:

```
no progress bar
```

---

# 22. MOVIE CARD HOVER

Desktop hover should create a premium interaction.

Transition:

```
250ms cubic-bezier(.2,.8,.2,1)
```

Card:

```
transform: translateY(-4px) scale(1.02)
```

Add subtle shadow:

```
0 20px 40px rgba(0,0,0,.35)
```

Display:

```
▶ Play
＋ Watchlist
⋯ More
```

in a floating overlay.

Do not cause the grid layout to shift.

---

# 23. MOVIE DETAIL PAGE

Clicking a movie should open a full detail experience.

Do **not** immediately open a small modal.

Use a dedicated route/page.

Example:

```
← Back to Movies

┌──────────────────────────────────────────────┐
│                                              │
│             BACKDROP                         │
│                                              │
│  Poster       Mad Max: Fury Road             │
│               2015 · 2h · Action             │
│                                              │
│               ★ 8.1                          │
│                                              │
│               [▶ Play] [＋ Watchlist]        │
│                                              │
└──────────────────────────────────────────────┘
```

---

# 24. DETAIL PAGE INFORMATION

Include:

### Primary

-  title 
-  year 
-  runtime 
-  genres 
-  rating 
-  age rating 
-  play status 
-  progress 

### Secondary

-  director 
-  cast 
-  studio 
-  release date 
-  language 
-  subtitles 
-  audio 
-  file quality 
-  resolution 
-  bitrate 
-  file size 

Technical information should be hidden under:

```
Technical details
```

rather than occupying the primary interface.

---

# 25. DETAIL ACTIONS

Primary:

```
▶ Play
```

Secondary:

```
＋ Watchlist
✓ Mark Watched
⋯ More
```

More menu:

```
Play from beginning
Resume
Mark watched
Mark unwatched
Add to watchlist
Edit metadata
Open file location
Refresh metadata
Delete
```

Destructive actions must be separated visually.

---

# 26. TV SHOW PAGE

The TV Shows page must share the same architecture as Movies.

```
TV Shows

Search
Filters
Sort
View

[Show grid]
```

But TV cards should communicate:

-  number of seasons 
-  number of episodes 
-  current progress 
-  next episode 

Example:

```
3 Body Problem
2024
1 Season · 8 Episodes
```

---

# 27. TV SHOW CARD

Poster card:

```
┌───────────────────────┐
│                       │
│       POSTER          │
│                       │
│                       │
│ █████████░░░          │
└───────────────────────┘

3 Body Problem
1 Season · 8 Episodes
S01 E05 · 57%
```

If there is an active episode:

```
Next:
S01 E06 · The Stars Our Destination
```

---

# 28. TV SHOW DETAIL PAGE

TV detail page should be:

```
Backdrop
↓
Show information
↓
Continue Watching
↓
Seasons
↓
Episodes
↓
Cast
↓
Related
```

---

# 29. SEASON SELECTOR

Use a horizontal or dropdown selector:

```
Season 1
Season 2
Season 3
```

Example:

```
SEASONS

[Season 1 ▼]
```

---

# 30. EPISODE LIST

Episodes should not use movie-style cards.

Use a rich list.

```
┌─────────────────────────────────────────────────────┐
│ [thumbnail]  01  Pilot                              │
│              S01 E01 · 55 min                       │
│              Description...                         │
│                                  ▶ Resume           │
├─────────────────────────────────────────────────────┤
│ [thumbnail]  02  The Arrival                        │
│              S01 E02 · 49 min                       │
└─────────────────────────────────────────────────────┘
```

Episode currently being watched gets:

```
yellow left border
```

---

# 31. HOME — RECENTLY ADDED

Recently Added should use poster cards.

```
Recently Added                         See all →
```

Horizontal rail.

Card dimensions:

```
180 × 270 approximately
```

Use:

```
overflow-x: auto
scroll-snap-type: x mandatory
```

Hide scrollbar visually.

---

# 32. SECTION HEADERS

Every section should use this pattern:

```
Section Name                         See all →
```

Example:

```
Recently Added                      See all →
```

The arrow should only appear when navigation exists.

---

# 33. EMPTY STATES

Never display an empty blank page.

Example Movies:

```
No movies yet

Your movie library is empty.
Scan your media folders to discover movies.

[Scan Library]
```

Search:

```
No results for “interstellar”

Try another title, genre, actor, or year.

[Clear Search]
```

Watchlist:

```
Your watchlist is empty

Save movies and shows here so you can
find them later.

[Explore Library]
```

---

# 34. LOADING STATES

Do not use generic spinners everywhere.

Use skeleton loaders.

Movie:

```
████████
████████
████████
```

Use animated gradient:

```
background:
linear-gradient(
  90deg,
  #15171C,
  #20232A,
  #15171C
);
```

Skeletons should preserve the exact final layout dimensions.

---

# 35. ERROR STATES

Example:

```
Something went wrong

We couldn't load your movie library.

[Try Again]
```

If metadata fails:

```
Metadata unavailable

The movie is still available in your library.

[Play]
[Retry Metadata]
```

Do not expose stack traces or backend errors.

---

# 36. GLOBAL SEARCH

Search should become a first-class experience.

Keyboard shortcut:

```
/
```

or:

```
⌘ K
```

Search overlay:

```
┌────────────────────────────────────────────┐
│ ⌕  Search your library...                  │
├────────────────────────────────────────────┤
│                                            │
│ Recent                                     │
│ Mad Max: Fury Road                         │
│ Prisoners                                  │
│                                            │
│ Movies                                     │
│ ...                                        │
│                                            │
└────────────────────────────────────────────┘
```

Results should be grouped:

```
Movies
TV Shows
Episodes
People
Genres
```

---

# 37. KEYBOARD NAVIGATION

The interface must be keyboard friendly.

Required shortcuts:

```
/
Search

Esc
Close modal / drawer / search

Enter
Open selected item

Space
Play / pause where appropriate

Arrow keys
Navigate

⌘ K / Ctrl K
Global command/search

?
Show keyboard shortcuts
```

Focus states must always be visible.

---

# 38. RESPONSIVE DESIGN

The application must not simply shrink the desktop UI.

## Desktop ≥ 1200px

Sidebar:

```
240px
```

Large content.

Multi-column grids.

---

## Tablet 768–1199px

Sidebar:

```
80px
```

Icon-only navigation.

Content:

```
padding: 24px
```

Grid:

```
4–5 columns
```

---

## Mobile < 768px

Sidebar disappears.

Use bottom navigation:

```
┌─────────────────────────────────────────┐
│ Home  Movies  Shows  Search  More       │
└─────────────────────────────────────────┘
```

Content:

```
padding: 16px
```

Grid:

```
2 columns
```

Hero becomes smaller.

---

# 39. MOBILE MOVIE CARD

On mobile:

-  no hover-only actions 
-  use tap to reveal actions 
-  title limited to 2 lines 
-  poster remains dominant 
-  metadata simplified 

Long press can optionally open action sheet.

---

# 40. MOTION SYSTEM

Animations should be subtle.

Never make the application feel like a gaming UI.

### Standard transition

```
180–250ms
ease-out
```

### Page transitions

```
250–350ms
```

### Card hover

```
200ms
```

### Modal

```
fade + translateY(8px)
```

### Drawer

```
translateX()
300ms
```

Respect:

```
prefers-reduced-motion
```

---

# 41. DESIGN TOKENS

Create centralized tokens.

```
:root {
  --bg: #08090B;
  --surface-1: #101216;
  --surface-2: #15171C;
  --surface-3: #1B1E24;

  --text-primary: #F5F5F7;
  --text-secondary: #A7AAB2;
  --text-muted: #70747E;

  --accent: #FFC400;
  --accent-hover: #FFD43B;

  --success: #35D07F;
  --danger: #FF5B5B;

  --border: rgba(255,255,255,.08);

  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --radius-xl: 20px;

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 48px;
  --space-8: 64px;
}
```

Hermes should **never scatter arbitrary colors throughout components**.

---

# 42. COMPONENT ARCHITECTURE

Build reusable components rather than page-specific implementations.

Recommended structure:

```
AppShell
├── Sidebar
├── TopBar
├── ContentArea
└── MobileNavigation
```

Content:

```
PageHeader
SearchBar
FilterBar
FilterDrawer
SortMenu
ViewSwitcher
SectionHeader
MediaRail
MediaGrid
MediaCard
ContinueWatchingCard
EpisodeCard
Hero
ProgressBar
Badge
Rating
ActionButton
ContextMenu
Modal
Drawer
Toast
Skeleton
EmptyState
ErrorState
```

---

# 43. MEDIA CARD MUST BE DATA-DRIVEN

Do not create separate hardcoded cards for each movie.

Use a single reusable component.

Conceptually:

```
<MediaCard
  type="movie"
  title="Mad Max: Fury Road"
  year={2015}
  poster={...}
  progress={15}
  genres={...}
  rating={...}
  watched={false}
/>
```

For TV:

```
<MediaCard
  type="show"
  title="3 Body Problem"
  seasons={1}
  episodes={8}
  progress={57}
  poster={...}
/>
```

---

# 44. DATA MODEL EXPECTATIONS

The frontend should consume normalized media data.

Movie:

```
Movie {
  id
  title
  originalTitle
  year
  poster
  backdrop
  overview
  genres[]
  runtime
  rating
  ageRating
  directors[]
  cast[]
  studio
  releaseDate

  playback {
    progress
    duration
    lastPlayed
    playCount
    completed
  }

  library {
    addedAt
    path
  }

  technical {
    resolution
    videoCodec
    audioCodec
    bitrate
    fileSize
  }
}
```

TV Show:

```
TVShow {
  id
  title
  year
  poster
  backdrop
  overview
  genres[]
  rating

  seasons[]
  
  playback {
    currentSeason
    currentEpisode
    progress
  }

  library {
    addedAt
  }
}
```

---

# 45. PLAYBACK UX

When clicking Play:

If progress exists:

```
▶ Resume 23:14
```

and:

```
Restart
```

If not:

```
▶ Play
```

For TV:

```
▶ Resume S01 E06
```

If an episode is complete:

```
▶ Play Next Episode
```

---

# 46. CONTEXT MENUS

Every media item should have a `⋯` menu.

Example:

```
Play
Resume
Add to Watchlist
Mark as Watched
Mark as Unwatched
View Details
Refresh Metadata
```

TV:

```
Play Next Episode
Mark Season Watched
Mark Show Watched
View Show
Add to Watchlist
```

---

# 47. WATCHLIST

Watchlist should be a dedicated page.

Structure:

```
Watchlist

Movies | TV Shows | All

[Cards]
```

Add sorting:

```
Added Recently
Title
Release Date
```

---

# 48. DISCOVER PAGE

Discover should not be confused with library.

It can contain:

```
Recommended for You
Popular in Your Library
Recently Added
Unwatched
Hidden Gems
```

Recommendations should be based on actual library/playback data if available.

---

# 49. SCAN EXPERIENCE

The existing Scan button should be redesigned.

Click:

```
Scan Library
```

opens a modal:

```
Scan Library

We'll scan your configured media folders
for new movies and TV shows.

[Cancel]                     [Start Scan]
```

During scan:

```
Scanning your library...

Movies discovered       142
TV Shows discovered      28
Episodes discovered     341

██████████████░░░░░ 72%

Currently:
Finding metadata for...
```

Completion:

```
Scan Complete

12 new movies
3 new TV shows
27 new episodes

[View New Items]
[Done]
```

---

# 50. TOAST SYSTEM

Use subtle bottom-right notifications.

Example:

```
✓ Added to Watchlist
```

or:

```
✓ Library scan complete
```

Duration:

```
3–5 seconds
```

---

# 51. MODAL DESIGN

Modals:

```
background: #15171C
border: 1px solid rgba(255,255,255,.08)
border-radius: 16px
box-shadow: 0 24px 80px rgba(0,0,0,.5)
```

Backdrop:

```
rgba(0,0,0,.65)
backdrop-filter: blur(8px)
```

Do not make modals unnecessarily large.

---

# 52. PREMIUM VISUAL DETAILS

Hermes should deliberately add small visual details.

### Artwork

Use subtle image treatment:

```
object-fit: cover;
```

Never stretch posters.

### Shadows

Use layered shadows instead of heavy borders.

### Gradients

Use gradients only where they improve readability.

### Borders

Borders should be nearly invisible.

### Corners

Use consistent radius.

### Spacing

Use generous whitespace.

Premium does **not** mean filling every empty area.

---

# 53. WHAT TO REMOVE FROM THE CURRENT UI

Hermes should specifically eliminate/reduce:

### ❌ Excessive technical labels

For example:

```
jellyfin · 6 titles
```

should not be a prominent UI element.

### ❌ Oversized navigation footprint

### ❌ Heavy card borders

### ❌ Excessive black empty areas

### ❌ Tiny unreadable metadata

### ❌ Inconsistent card widths

### ❌ Developer-looking filter controls

### ❌ Excessive information directly under cards

### ❌ Browser-like dashboard feeling

---

# 54. WHAT TO PRESERVE

The redesign should retain useful aspects of the current interface:

-  dark theme 
-  yellow accent 
-  clear Movies / TV Shows separation 
-  Continue Watching 
-  Recently Added 
-  genre filters 
-  search 
-  sorting 
-  progress indicators 
-  library scanning 
-  Jellyfin/media-library integration 
-  desktop sidebar navigation 

The goal is **evolution, not a completely alien interface**.

---

# 55. INFORMATION HIERARCHY

Every screen should follow this hierarchy:

```
LEVEL 1
What am I looking at?

LEVEL 2
What should I do?

LEVEL 3
What information is important?

LEVEL 4
What additional information is available?

LEVEL 5
What technical information exists?
```

Example movie:

```
Mad Max: Fury Road              ← Level 1

▶ Play                           ← Level 2

2015 · Action · 2h               ← Level 3

Tom Hardy · Charlize Theron      ← Level 4

1080p · H264 · 8.2 Mbps          ← Level 5
```

---

# 56. ACCESSIBILITY

Required:

-  WCAG AA contrast 
-  keyboard navigation 
-  visible focus states 
-  semantic buttons 
-  semantic navigation 
-  alt text for artwork where appropriate 
-  aria labels for icon-only buttons 
-  reduced-motion support 
-  no information communicated by color alone 

Minimum touch target:

```
44 × 44px
```

---

# 57. PERFORMANCE

Because the application may contain many media items:

### Images

Use:

```
lazy loading
responsive images
appropriate image sizes
```

### Grid

Virtualize very large libraries if necessary.

### Horizontal rails

Only render what is necessary for very large datasets.

### Search

Debounce:

```
150–250ms
```

### Artwork

Do not download full-resolution backdrops when a thumbnail is sufficient.

---

# 58. IMAGE LOADING

Use progressive loading:

```
skeleton
↓
low-resolution image
↓
full image
```

If artwork is unavailable:

```
dark neutral placeholder
subtle film icon
title
```

Never show a broken-image icon.

---

# 59. MOBILE NAVIGATION

Bottom navigation:

```
Home
Movies
Shows
Search
More
```

More:

```
Watchlist
Discover
Suggest
Settings
```

This prevents mobile from becoming navigation-heavy.

---

# 60. PAGE TRANSITION MODEL

Navigation should feel like one application rather than independent pages.

For example:

```
Movies
   ↓
Movie Detail
   ↓
Back
   ↓
same scroll position
```

Preserve:

-  filters 
-  search 
-  sorting 
-  scroll position 
-  view mode 

when navigating back.

---

# 61. STATE MANAGEMENT

Media state should be separated from UI state.

### Media state

```
library
movies
shows
episodes
playback
metadata
```

### UI state

```
searchQuery
selectedGenre
sort
viewMode
sidebarState
modal
drawer
```

Do not mix API/media data with transient UI state.

---

# 62. ROUTING

Recommended:

```
/
 /movies
 /movies/:id

 /shows
 /shows/:id

 /watchlist
 /discover
 /search

 /settings
```

TV episode route can optionally be:

```
/shows/:showId/season/:seasonId/episode/:episodeId
```

---

# 63. URL STATE

Search/filter state should ideally be represented in the URL.

Example:

```
/movies?genre=action&sort=recent
```

Search:

```
/movies?q=mad+max
```

This allows:

-  refresh without losing state 
-  browser back/forward 
-  shareable views 
-  predictable navigation 

---

# 64. HOME PAGE INTELLIGENCE

Hermes should dynamically determine which sections deserve prominence.

For example:

If the user has active playback:

```
Continue Watching
```

appears first.

If no active playback:

```
Recently Added
```

becomes the hero section.

If the library is empty:

```
Library setup
```

becomes the primary experience.

---

# 65. PERSONALIZATION

The UI should eventually support:

```
Continue Watching
Recently Watched
Most Played
Recently Added
Unwatched
Watchlist
Because You Watched X
```

But do not display every section simply because it exists.

The home page should remain **curated**.

---

# 66. DESIGN FOR DIFFERENT LIBRARY SIZES

### 0–10 items

Use larger cards and more explanatory UI.

### 10–100 items

Normal grid/rails.

### 100–1000 items

Prioritize:

-  search 
-  filters 
-  sorting 
-  compact mode 
-  pagination/virtualization 

### 1000+ items

Search becomes extremely important.

Consider:

```
A–Z navigation
advanced filters
collections
smart categories
```

---

# 67. COLLECTIONS

Allow future support for collections:

```
Marvel
Christopher Nolan
Oscar Winners
Favorites
Sci-Fi
To Watch
```

Collections can appear as horizontal rails.

Collection page:

```
Collection

Christopher Nolan

12 Movies

[Grid]
```

---

# 68. PLAYER EXPERIENCE

The media player itself should eventually follow the same design language.

Controls:

```
← Back
Title / Episode

               video

▶  ━━━━━━━━━━━━━━━━━━━━━  42:18

🔊
CC
Settings
Fullscreen
```

Controls should fade away when inactive.

---

# 69. PLAYER RESUME

When leaving the player:

```
Continue watching?

Your progress will be saved.

[Continue] [Exit]
```

Prefer automatic saving without interrupting playback.

---

# 70. MICROCOPY

Use human language.

Instead of:

```
6 titles
```

Prefer:

```
6 movies
```

Instead of:

```
Scan
```

Prefer:

```
Scan Library
```

Instead of:

```
No data
```

Prefer:

```
Nothing here yet
```

Instead of:

```
Playback error
```

Prefer:

```
We couldn't start playback
```

---

# 71. BUTTON HIERARCHY

Only one primary button per major region.

### Primary

Yellow:

```
▶ Play
```

### Secondary

Dark translucent:

```
＋ Watchlist
```

### Tertiary

Text:

```
More
```

Avoid having five yellow buttons on one screen.

---

# 72. ICON SYSTEM

Use a consistent icon library such as:

```
Lucide
```

or an equivalent modern outline icon system.

Do not mix:

-  Font Awesome 
-  random SVGs 
-  emojis 
-  platform icons 

unless there is a deliberate reason.

Icon stroke:

```
1.75–2px
```

---

# 73. CARD TITLE HANDLING

Titles should never destroy grid alignment.

Use:

```
display: -webkit-box;
-webkit-line-clamp: 2;
-webkit-box-orient: vertical;
overflow: hidden;
```

Example:

```
One Battle After Another
```

rather than truncating too aggressively to:

```
One Battle After Anot...
```

Give cards enough width or use a tooltip on hover.

---

# 74. TOOLTIP SYSTEM

For icon-only buttons:

```
hover 500ms
↓
tooltip
```

Example:

```
↻
Refresh Library
```

Tooltips should not be used for obvious text buttons.

---

# 75. Z-INDEX SYSTEM

Define predictable layers:

```
Base: 0
Sticky: 10
Header: 20
Dropdown: 50
Popover: 100
Drawer: 200
Modal: 300
Toast: 400
Player: 500
```

Do not use arbitrary:

```
z-index: 999999
```

values.

---

# 76. SCROLL BEHAVIOR

Desktop:

-  content scrolls independently from sidebar 
-  sidebar remains fixed 
-  top navigation can remain sticky 

Horizontal rails:

```
scroll-snap
```

Optional left/right controls appear on hover.

Mobile:

-  normal vertical page scrolling 
-  horizontal rails use touch scrolling 

---

# 77. HORIZONTAL RAIL CONTROLS

On desktop:

```
Recently Added                         ‹  ›
```

Controls should appear only when the rail can scroll.

Don't display disabled arrows permanently.

---

# 78. BACKDROP BLUR

Use carefully:

```
backdrop-filter: blur(16px);
```

Good for:

-  top bar 
-  menus 
-  floating controls 

Avoid applying blur to huge content areas because it can hurt performance.

---

# 79. PREMIUM DETAIL PAGE BACKGROUND

The detail page can extract a subtle color from the backdrop.

For example:

```
backdrop dominant color
↓
very subtle radial gradient
↓
dark base
```

Result:

```
background:
radial-gradient(
  circle at 70% 20%,
  rgba(accentColor,.16),
  transparent 45%
),
#08090B;
```

This creates an atmospheric cinematic experience.

Keep opacity extremely low.

---

# 80. DESIGN SYSTEM DOCUMENTATION

Hermes should create a central design-system layer:

```
/design-system

colors
typography
spacing
radius
shadows
icons
buttons
inputs
cards
navigation
modals
toasts
skeletons
```

Every component should use these tokens.

---

# 81. COMPONENT VARIANTS

Example:

```
MediaCard
├── movie
├── show
├── episode
├── continueWatching
├── compact
└── featured
```

Buttons:

```
Button
├── primary
├── secondary
├── ghost
├── destructive
└── icon
```

Do not duplicate components when a variant can solve the requirement.

---

# 82. DEVELOPMENT PHASES

Hermes should implement in this order.

## Phase 1 — Foundation

Build:

-  design tokens 
-  typography 
-  colors 
-  spacing 
-  icons 
-  application shell 
-  responsive breakpoints 

---

## Phase 2 — Navigation

Build:

-  desktop sidebar 
-  collapsed sidebar 
-  mobile bottom navigation 
-  top bar 
-  routing 

---

## Phase 3 — Media primitives

Build:

-  MediaCard 
-  MediaGrid 
-  MediaRail 
-  ProgressBar 
-  Rating 
-  Badges 
-  skeletons 
-  empty states 

---

## Phase 4 — Movies

Implement:

```
Movies
Search
Filters
Sort
Grid
Compact view
Movie detail
```

---

## Phase 5 — TV Shows

Implement:

```
TV Shows
Show grid
Show detail
Seasons
Episodes
Playback state
```

---

## Phase 6 — Home

Implement:

```
Hero
Continue Watching
Recently Added
Dynamic rails
Personalized sections
```

---

## Phase 7 — Search

Implement:

```
Global search
Keyboard shortcut
Search suggestions
Grouped results
```

---

## Phase 8 — Library operations

Implement:

```
Scan
Refresh metadata
Watch state
Watchlist
```

---

## Phase 9 — Polish

Perform:

-  animation pass 
-  accessibility pass 
-  responsive pass 
-  performance pass 
-  empty-state pass 
-  error-state pass 
-  keyboard navigation pass 

---

# 83. IMPLEMENTATION RULES FOR HERMES

**IMPORTANT: Hermes must follow these rules during development.**

### Rule 1

Do not simply restyle the existing components.

Refactor the UI architecture where necessary.

### Rule 2

Do not hardcode media cards.

Everything must be data-driven.

### Rule 3

Do not introduce random colors.

Use design tokens.

### Rule 4

Do not introduce random spacing.

Use the spacing scale.

### Rule 5

Do not duplicate Movies and TV Shows components unnecessarily.

Build shared components with variants.

### Rule 6

Do not expose backend implementation details in the primary UX.

### Rule 7

Do not sacrifice usability for visual effects.

### Rule 8

Do not use hover as the only way to access functionality.

### Rule 9

Every interactive element must have a clear state:

```
default
hover
focus
active
disabled
loading
error
```

### Rule 10

Every page must work at:

```
desktop
tablet
mobile
```

---

# 84. VISUAL ACCEPTANCE CRITERIA

The finished application should visually satisfy these criteria:

### Navigation

-  Sidebar is substantially lighter visually than current implementation 
-  Active page is immediately obvious 
-  Navigation hierarchy is clear 
-  Mobile navigation exists 

### Home

-  First viewport feels cinematic 
-  Continue Watching is prominent 
-  Content rails are visually consistent 
-  Recently Added is easy to scan 

### Movies

-  Search is obvious 
-  Filters are easy to understand 
-  Grid is responsive 
-  Posters are consistently sized 
-  Hover interaction feels premium 
-  Progress is visible 
-  Sorting is easy 

### TV Shows

-  Same visual language as Movies 
-  Seasons/episodes are clearly differentiated 
-  Continue Watching works at episode level 
-  Current episode is obvious 

### Detail

-  Artwork is cinematic 
-  Play action is dominant 
-  Metadata hierarchy is clear 
-  Technical details don't dominate 
-  Back navigation is obvious 

### General

-  No unnecessary borders 
-  No huge unexplained empty areas 
-  No tiny unreadable text 
-  No inconsistent spacing 
-  No layout shifts 
-  No broken image states 
-  Loading states preserve layout 
-  Keyboard navigation works 
-  Mobile experience is intentional 

---

# 85. TARGET VISUAL CHARACTER

Hermes should optimize for the following adjectives:

```
Premium
Cinematic
Minimal
Intelligent
Calm
Modern
Personal
Fast
Elegant
Immersive
Organized
Discoverable
```

Avoid:

```
Dashboard-like
Corporate
Generic
Over-designed
Gaming-like
Cluttered
Developer-tool-like
Bright
Noisy
```

---

# 86. FINAL MASTER INSTRUCTION TO HERMES

Use the following as the **implementation directive**:

> **Redesign RKM Cinema as a premium personal streaming-library application.**
>
> Preserve the existing media-library functionality, dark aesthetic, yellow accent, Movies/TV Shows architecture, Continue Watching, Recently Added, filtering, searching, sorting, playback progress, and library scanning functionality.
>
> However, rebuild the presentation around a cinematic streaming-service UX rather than a conventional dashboard.
>
> Create a centralized design system with dark layered surfaces, restrained yellow accents, modern typography, consistent spacing, subtle borders, cinematic gradients, premium shadows, responsive grids, horizontal media rails, polished interactions, skeleton loading, empty states, error states, accessible controls, and deliberate mobile behavior.
>
> Build reusable data-driven components rather than page-specific implementations.
>
> Movies and TV Shows must share the same visual system and component architecture while supporting their different metadata and playback models.
>
> Make artwork the dominant visual element. Make Play/Resume the dominant action. Keep technical metadata secondary.
>
> The Home page should feel personalized and cinematic, with Continue Watching and Recently Added as primary experiences. The Movies and TV Shows pages should function as highly efficient discovery and library-management interfaces with search, filters, sorting, responsive grids, and optional compact views.
>
> Every interaction must have complete visual states: default, hover, focus, active, disabled, loading, success, and error.
>
> Every page must work on desktop, tablet, and mobile.
>
> Do not merely change colors or CSS on the existing UI. Refactor the information architecture, component hierarchy, spacing system, navigation, media cards, detail experiences, and responsive behavior where required.
>
> **The final product should feel like a beautifully designed private Netflix/Plex-style library belonging to the user, while remaining technically efficient, intuitive, maintainable, accessible, and scalable to a library containing thousands of movies and episodes.**

---

## 87. MOST IMPORTANT VISUAL CHANGE

The single biggest change Hermes should make is this:

### Current mental model

```
Dashboard
   ↓
Page
   ↓
Grid
   ↓
Card
```

### New mental model

```
Personal Cinema
       ↓
   What should I
   watch next?
       ↓
 ┌───────────────┐
 │ Cinematic Hero│
 └───────────────┘
       ↓
 Continue Watching
       ↓
 Recently Added
       ↓
 My Movies
       ↓
 My Shows
       ↓
 Discover
```

The application should stop feeling like **“a database showing my media files”** and start feeling like **“my own premium streaming service.”**

That should be the north-star principle behind every design and implementation decision.