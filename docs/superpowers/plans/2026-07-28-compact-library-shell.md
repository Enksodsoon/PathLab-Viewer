# Compact Library Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a compact collapsible PathLab library shell whose folders honor Grid, List, and Table views.

**Architecture:** Keep `AdminPage` as state coordinator, move persisted rail preference into a small pure helper, keep navigation destinations inside `LibraryNavigator`, and make `FolderViews` mode-aware. Existing APIs and folder data flow remain unchanged.

**Tech Stack:** React 19, TypeScript, React Router, Phosphor Icons, CSS, Vitest, Testing Library, Playwright Browser runtime, FastAPI/pytest.

## Global Constraints

- Start from current `origin/main` in linked worktree `codex/compact-library-shell`.
- Rail widths: 52 px collapsed, approximately 176 px expanded.
- Rail primary actions: Slide library and Upload only.
- Top-right utilities: Light, Dark, System, Account, Sign out.
- Interactive targets remain at least 44 px.
- Preserve `light | dark | system`, folder, slide, upload, auth, storage, conversion, sharing, and viewer contracts.
- No new dependency, backend route, schema, service, merge, or deployment.

## File Map

- Create `apps/web/src/components/library/libraryShellPreferences.ts`: safe versioned rail preference persistence.
- Create `apps/web/src/test/library-shell-preferences.test.ts`: helper unit tests.
- Modify `apps/web/src/components/library/AppRail.tsx`: collapsible two-action rail.
- Modify `apps/web/src/components/library/LibraryToolbar.tsx`: theme/account/sign-out utility cluster.
- Modify `apps/web/src/components/library/FolderViews.tsx`: Grid/List/Table folder rendering.
- Modify `apps/web/src/pages/AdminPage.tsx`: state wiring and mode propagation.
- Modify `apps/web/src/library.css`: compact desktop/mobile shell and folder modes.
- Modify `apps/web/src/test/library-explorer.test.tsx`: integration and folder regressions.

---

### Task 1: Persist Collapsible Rail Preference

**Files:**
- Create: `apps/web/src/components/library/libraryShellPreferences.ts`
- Create: `apps/web/src/test/library-shell-preferences.test.ts`

**Interfaces:**
- Produces: `getStoredRailExpanded(): boolean`
- Produces: `persistRailExpanded(expanded: boolean): void`
- Storage key: `pathlab-library-rail:v1`

- [ ] **Step 1: Write failing unit tests**

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getStoredRailExpanded,
  persistRailExpanded,
  RAIL_STORAGE_KEY,
} from '../components/library/libraryShellPreferences'

describe('library shell preferences', () => {
  beforeEach(() => localStorage.clear())

  it('defaults to collapsed and restores an expanded rail', () => {
    expect(getStoredRailExpanded()).toBe(false)
    localStorage.setItem(RAIL_STORAGE_KEY, 'expanded')
    expect(getStoredRailExpanded()).toBe(true)
  })

  it('persists state without failing when storage is blocked', () => {
    persistRailExpanded(true)
    expect(localStorage.getItem(RAIL_STORAGE_KEY)).toBe('expanded')
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked')
    })
    expect(() => persistRailExpanded(false)).not.toThrow()
  })
})
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
pnpm.cmd --dir apps/web exec vitest run src/test/library-shell-preferences.test.ts --pool=threads --maxWorkers=1
```

Expected: FAIL because `libraryShellPreferences` does not exist.

- [ ] **Step 3: Implement minimal helper**

```ts
export const RAIL_STORAGE_KEY = 'pathlab-library-rail:v1'

export function getStoredRailExpanded() {
  try {
    return window.localStorage.getItem(RAIL_STORAGE_KEY) === 'expanded'
  } catch {
    return false
  }
}

export function persistRailExpanded(expanded: boolean) {
  try {
    window.localStorage.setItem(RAIL_STORAGE_KEY, expanded ? 'expanded' : 'collapsed')
  } catch {
    // Blocked storage must not block navigation.
  }
}
```

- [ ] **Step 4: Verify GREEN**

Run same focused command. Expected: 2 PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/components/library/libraryShellPreferences.ts apps/web/src/test/library-shell-preferences.test.ts
git commit -m "feat(web): persist compact rail preference"
```

### Task 2: Consolidate Navigation and Move Utilities

**Files:**
- Modify: `apps/web/src/components/library/AppRail.tsx`
- Modify: `apps/web/src/components/library/LibraryToolbar.tsx`
- Modify: `apps/web/src/pages/AdminPage.tsx`
- Modify: `apps/web/src/test/library-explorer.test.tsx`

**Interfaces:**
- `AppRail` consumes `expanded`, `navigatorOpen`, `onToggleExpanded`, `onNavigator`, `onUpload`.
- `LibraryToolbar` consumes `onSecurity` and `onSignOut`.
- `AdminPage` initializes with `getStoredRailExpanded`, persists changes, and adds `rail-expanded` to shell.

- [ ] **Step 1: Replace rail composition test with failing compact-shell assertions**

```tsx
it('uses a collapsible two-action rail and top-right utilities', async () => {
  renderCanvasFocusAdmin()
  await screen.findAllByText('Colon adenocarcinoma')
  const rail = screen.getByRole('complementary', { name: /product navigation/i })
  expect(within(rail).getByRole('button', { name: /slide library/i })).toBeVisible()
  expect(within(rail).getByRole('button', { name: /^upload$/i })).toBeVisible()
  expect(within(rail).queryByRole('button', { name: /^processing$/i })).not.toBeInTheDocument()
  expect(within(rail).queryByRole('group', { name: /theme preference/i })).not.toBeInTheDocument()
  expect(screen.getByRole('group', { name: /theme preference/i })).toBeVisible()
  expect(screen.getByRole('button', { name: /^account$/i })).toBeVisible()
  expect(screen.getByRole('button', { name: /^sign out$/i })).toBeVisible()
  const toggle = within(rail).getByRole('button', { name: /expand navigation rail/i })
  await userEvent.click(toggle)
  expect(toggle).toHaveAttribute('aria-expanded', 'true')
  expect(document.querySelector('.library-shell')).toHaveClass('rail-expanded')
  expect(localStorage.getItem('pathlab-library-rail:v1')).toBe('expanded')
})
```

Extend navigator test:

```tsx
const navigator = screen.getByRole('complementary', { name: /library navigator/i })
expect(within(navigator).getByRole('button', { name: /processing 1/i })).toBeVisible()
expect(within(navigator).getByRole('button', { name: /failed 0/i })).toBeVisible()
expect(within(navigator).getByRole('button', { name: /trash 0/i })).toBeVisible()
```

- [ ] **Step 2: Verify RED**

Run explorer test filtered to `two-action rail|quick views`. Expected: old six-action rail and rail-owned theme fail.

- [ ] **Step 3: Implement compact component contracts**

`AppRail.tsx`:

```ts
interface AppRailProps {
  expanded: boolean
  isInert: boolean
  navigatorOpen: boolean
  navigatorButtonRef: Ref<HTMLButtonElement>
  onToggleExpanded: () => void
  onNavigator: () => void
  onUpload: () => void
}
```

Render brand, toggle, Slide library button, Upload button only. Toggle label changes between `Expand navigation rail` and `Collapse navigation rail`; use `aria-expanded={expanded}`.

`LibraryToolbar.tsx`:

```ts
onSecurity: () => void
onSignOut: () => void
```

Import `ThemeControl`, `Key`, and `SignOut`; append `.library-toolbar-utilities` to breadcrumb row:

```tsx
<div className="library-toolbar-utilities">
  <ThemeControl compact />
  <button type="button" aria-label="Account" onClick={onSecurity}><Key /></button>
  <button type="button" aria-label="Sign out" onClick={onSignOut}><SignOut /></button>
</div>
```

`AdminPage.tsx`:

```ts
const [railExpanded, setRailExpanded] = useState(getStoredRailExpanded)

function toggleRail() {
  setRailExpanded((current) => {
    persistRailExpanded(!current)
    return !current
  })
}
```

Pass new props and set shell class to `rail-expanded` when true.

- [ ] **Step 4: Verify GREEN**

Run focused explorer tests. Expected: compact rail and navigator destination assertions pass.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/components/library/AppRail.tsx apps/web/src/components/library/LibraryToolbar.tsx apps/web/src/pages/AdminPage.tsx apps/web/src/test/library-explorer.test.tsx
git commit -m "feat(web): consolidate library navigation"
```

### Task 3: Make Folders Honor Grid, List, and Table

**Files:**
- Modify: `apps/web/src/components/library/FolderViews.tsx`
- Modify: `apps/web/src/pages/AdminPage.tsx`
- Modify: `apps/web/src/test/library-explorer.test.tsx`

**Interfaces:**
- `FolderViews` consumes `view: LibraryViewMode`, `folders`, and `onOpen`.
- Grid/List use folder buttons; Table uses a semantic table with one button per folder name.

- [ ] **Step 1: Add failing folder mode test**

```tsx
it('renders child folders in grid, list, and table modes with working navigation', async () => {
  api.getLibraryItems.mockResolvedValue({ items: [], nextCursor: null, total: 0 })
  renderCanvasFocusAdmin('/admin?location=folder%3Afolder-organs')
  const region = await screen.findByRole('region', { name: 'Folders' })
  expect(region).toHaveAttribute('data-view', 'grid')
  await userEvent.click(screen.getByRole('button', { name: /list view/i }))
  expect(region).toHaveAttribute('data-view', 'list')
  await userEvent.click(screen.getByRole('button', { name: /table view/i }))
  expect(screen.getByRole('table', { name: 'Folders' })).toBeVisible()
  expect(screen.getByRole('columnheader', { name: 'Subfolders' })).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Open folder GI' }))
  expect(await screen.findByRole('heading', { name: 'GI' })).toBeVisible()
})
```

Add mixed-content assertion by leaving the default two slides in the folder response and checking folder region plus `Colon adenocarcinoma` in each mode.

- [ ] **Step 2: Verify RED**

Run filtered explorer test. Expected: `data-view` missing and no Folders table.

- [ ] **Step 3: Implement mode-aware `FolderViews`**

Update props:

```ts
interface FolderViewsProps {
  folders: LibraryFolder[]
  view: LibraryViewMode
  onOpen: (folder: LibraryFolder) => void
}
```

For `table`, render:

```tsx
<div className="library-folder-table-wrap">
  <table className="library-folder-table" aria-label="Folders">
    <thead><tr><th>Name</th><th>Slides</th><th>Subfolders</th><th>Updated</th></tr></thead>
    <tbody>{folders.map((folder) => (
      <tr key={folder.id}>
        <td><button type="button" aria-label={`Open folder ${folder.name}`} onClick={() => onOpen(folder)}><Folder />{folder.name}</button></td>
        <td>{folder.itemCount}</td><td>{folder.childCount}</td>
        <td>{new Date(folder.updatedAt).toLocaleDateString()}</td>
      </tr>
    ))}</tbody>
  </table>
</div>
```

For Grid/List, retain cards and add `data-view={view}` plus `list-view` class. Pass `view={view}` from `AdminPage`.

- [ ] **Step 4: Verify GREEN**

Run filtered test, then entire explorer file. Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/components/library/FolderViews.tsx apps/web/src/pages/AdminPage.tsx apps/web/src/test/library-explorer.test.tsx
git commit -m "feat(web): add folder view modes"
```

### Task 4: Compact and Polish Responsive Shell

**Files:**
- Modify: `apps/web/src/library.css`
- Modify: `apps/web/src/test/library-explorer.test.tsx`

**Interfaces:**
- `.library-shell`: 52 px rail.
- `.library-shell.rail-expanded`: 176 px rail.
- `.library-folder-grid.list-view`: one-column rows.
- `.library-folder-table-wrap`: bounded horizontal overflow.

- [ ] **Step 1: Add failing structural class assertions**

```tsx
expect(document.querySelector('.library-shell')).not.toHaveClass('rail-expanded')
expect(screen.getByRole('region', { name: 'Folders' })).toHaveClass('library-folder-section')
await userEvent.click(screen.getByRole('button', { name: /list view/i }))
expect(screen.getByRole('region', { name: 'Folders' }).querySelector('.library-folder-grid'))
  .toHaveClass('list-view')
```

- [ ] **Step 2: Verify RED**

Run filtered tests. Expected: compact/list structure assertion fails.

- [ ] **Step 3: Implement CSS**

Apply:

```css
.library-shell { --library-rail-width: 52px; }
.library-shell.rail-expanded { --library-rail-width: 176px; }
.library-app-rail { padding: 8px 4px; transition: width 180ms ease; }
.library-rail-brand { width: 44px; height: 44px; }
.library-rail-primary > button { min-height: 44px; grid-template-columns: 28px minmax(0,1fr); }
.library-shell:not(.rail-expanded) .library-rail-primary > button span,
.library-shell:not(.rail-expanded) .library-rail-toggle span { display: none; }
.library-toolbar { padding: 10px clamp(14px, 1.8vw, 24px); }
.library-breadcrumb-row { min-height: 36px; margin-bottom: 8px; }
.library-command-row { gap: 8px; }
.library-content { padding: clamp(18px, 2vw, 28px) clamp(14px, 1.8vw, 24px) 96px; }
.library-content-heading h2 { font-size: clamp(30px, 2.6vw, 42px); }
.library-folder-card { min-height: 68px; padding: 10px 12px; }
.library-folder-grid.list-view { grid-template-columns: 1fr; }
.library-folder-grid.list-view .library-folder-card { grid-template-columns: 36px minmax(0,1fr) 20px; }
.library-folder-table-wrap { overflow-x: auto; border: 1px solid var(--border); }
```

Keep all controls 44 px minimum. At `max-width: 600px`, keep two bottom actions, hide rail expand toggle, use full viewport main, and keep toolbar utilities compact. Add reduced-motion rule for rail transition.

- [ ] **Step 4: Verify GREEN**

Run explorer test, lint, and build.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/library.css apps/web/src/test/library-explorer.test.tsx
git commit -m "style(web): compact library workspace"
```

### Task 5: Folder Regression and Browser Acceptance

**Files:**
- Modify only if a failing acceptance check reveals a root-cause defect.

**Interfaces:**
- Existing `/api/v2/admin/folders/:id/children`, folder mutation APIs, and `LibraryFolder` schema remain unchanged.

- [ ] **Step 1: Run folder backend invariants**

```powershell
pytest tests/backend/test_library_v2.py -k "folder" -q
```

Expected: depth/cycle, lazy children, subtree trash/restore, delete, and move tests pass.

- [ ] **Step 2: Run full frontend validation**

```powershell
pnpm.cmd --dir apps/web test
pnpm.cmd --dir apps/web lint
pnpm.cmd --dir apps/web build
```

Expected: all pass with no new warnings.

- [ ] **Step 3: Browser QA**

Use built app plus read-only mock folder data. Verify desktop and 390×844:

1. Page identity and nonblank render.
2. No framework overlay or console error/warning.
3. Rail defaults collapsed, expands, and survives reload.
4. Rail contains Slide library and Upload only.
5. Navigator contains Processing, Failed, Trash, folders, collections, saved views.
6. Theme switches Light, Dark, System from top-right.
7. Account and Sign out are top-right.
8. Folder Grid, List, and Table render and open child folder.
9. Empty and mixed folder/slide states remain correct.
10. `scrollWidth === clientWidth` at desktop and mobile.

- [ ] **Step 4: Final diff/security review**

```powershell
git diff origin/main...HEAD --check
git status --short
git diff origin/main...HEAD --stat
```

Confirm no API, migration, dependency, secret, workflow, or deployment file changed.

- [ ] **Step 5: Push and open draft PR**

```powershell
git push -u origin codex/compact-library-shell
gh pr create --draft --base main --head codex/compact-library-shell --title "Compact the library shell and add folder view modes" --body-file $prBody
```

PR body: root causes, shell changes, folder modes, folder audit, tests, browser evidence, and explicit “Not deployed.”
