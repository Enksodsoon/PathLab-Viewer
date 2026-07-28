# Compact Library Shell Design

## Goal

Make the PathLab administrator library denser, clearer, and extensible while preserving all existing folder, slide, upload, theme, authentication, sharing, and viewer contracts.

## Layout

- Replace the fixed 72 px multi-destination rail with a collapsible navigation rail.
- Collapsed width: 52 px. Expanded width: approximately 176 px.
- Rail contains only PathLab brand, collapse toggle, Slide library, and Upload.
- Slide library opens the existing navigator, which owns All slides, Processing, Failed, Trash, folders, collections, saved views, and recent slides.
- Move Light, Dark, System, Account, and Sign out into a compact utility cluster at the top-right of the command bar.
- Reduce desktop command-bar height, padding, type scale, gaps, and folder-card size without reducing interactive targets below 44 px.
- Mobile keeps a two-action bottom bar for Slide library and Upload plus the navigator overlay; top-right utilities remain reachable without horizontal overflow.

## View Modes

The existing `grid | list | table` URL preference controls both direct child folders and slides.

- Grid: folder cards followed by slide cards.
- List: full-width compact folder rows followed by slide rows.
- Table: a folder table with Name, Slides, Subfolders, and Updated columns, followed by the existing slide table.

Folders remain visually distinct from slides through folder icons and count metadata. All folder presentations use one `FolderViews` component and the same `onOpen(folder)` contract.

## Folder Behavior

- Opening a folder loads its direct children and slides independently.
- Empty state appears only when both requests succeed and both result sets are empty.
- Mixed folders and slides render together in the selected view.
- Breadcrumbs, direct-child navigation, lazy navigator expansion, create, rename, move, trash, restore, and subtree preservation keep existing API behavior.
- A child-folder request failure shows the existing error alert and suppresses the false empty state.
- No backend, schema, storage, conversion, publication, sharing, or viewer changes.

## Components

- `AppRail`: collapsed state, two primary actions, accessible toggle.
- `LibraryToolbar`: top-right `ThemeControl` and account actions.
- `LibraryNavigator`: owns all library destinations and organization trees.
- `FolderViews`: mode-aware grid, list, and table renderers.
- `AdminPage`: persists rail preference, passes view mode, and keeps current folder-loading flow.
- `library.css`: compact tokens and responsive layouts.

## State and Accessibility

- Persist rail state in versioned local storage; default collapsed on desktop.
- Toggle exposes `aria-expanded` and an explicit accessible name.
- Active library destination keeps `aria-current`.
- Theme keeps persisted `light | dark | system` behavior.
- Folder controls remain keyboard-focusable buttons with visible focus.
- Reduced-motion preference disables rail transition.

## Validation

Test-first coverage will prove:

- folders render correctly in Grid, List, and Table;
- view selection affects folders and slides together;
- compact rail exposes only Slide library and Upload;
- rail expands/collapses and persists;
- Processing, Failed, and Trash remain available through the navigator;
- theme/account/sign-out utilities render in the command bar;
- folder empty, child-only, mixed-content, navigation, create, move, trash, and restore flows remain correct.

Run focused explorer tests, full web tests, lint, production build, backend folder tests, and in-app browser QA at desktop plus mobile width. Browser QA checks console health, overflow, focus, theme switching, rail switching, all three folder layouts, and child-folder navigation.

## Delivery Boundary

Commit implementation on `codex/compact-library-shell`, push, and open a new pull request after validation. Do not merge or deploy without explicit authorization.
