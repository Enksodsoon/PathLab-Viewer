import {
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  BookmarkPlus,
  ChevronRight,
  Filter,
  FolderPlus,
  Grid2X2,
  Grid2X2Plus,
  List,
  Plus,
  Search,
  Share2,
  Table2,
  Upload,
} from 'lucide-react'
import { ContextMenu } from './ContextMenu'

export type LibraryViewMode = 'grid' | 'list' | 'table'
export interface BreadcrumbItem {
  label: string
  location: string
}

interface LibraryToolbarProps {
  breadcrumbs: BreadcrumbItem[]
  search: string
  sort: string
  view: LibraryViewMode
  filtersOpen: boolean
  onBack: () => void
  onForward: () => void
  onUp: () => void
  onBreadcrumb: (location: string) => void
  onSearch: (value: string) => void
  onSort: (value: string) => void
  onView: (view: LibraryViewMode) => void
  onToggleFilters: () => void
  onNewFolder: () => void
  onNewCollection: () => void
  onNewSavedView: () => void
  onUpload: () => void
  onShare?: () => void
}

export function LibraryToolbar({
  breadcrumbs,
  search,
  sort,
  view,
  filtersOpen,
  onBack,
  onForward,
  onUp,
  onBreadcrumb,
  onSearch,
  onSort,
  onView,
  onToggleFilters,
  onNewFolder,
  onNewCollection,
  onNewSavedView,
  onUpload,
  onShare,
}: LibraryToolbarProps) {
  return (
    <header className="library-toolbar">
      <div className="library-breadcrumb-row">
        <button type="button" aria-label="Back" onClick={onBack}><ArrowLeft /></button>
        <button type="button" aria-label="Forward" onClick={onForward}><ArrowRight /></button>
        <button type="button" aria-label="Up one level" onClick={onUp}><ArrowUp /></button>
        <nav aria-label="Breadcrumb">
          {breadcrumbs.map((crumb, index) => (
            <span key={`${crumb.location}-${index}`}>
              {index ? <ChevronRight aria-hidden="true" /> : null}
              {index === breadcrumbs.length - 1 ? (
                <span aria-current="page">{crumb.label}</span>
              ) : (
                <button type="button" onClick={() => onBreadcrumb(crumb.location)}>
                  {crumb.label}
                </button>
              )}
            </span>
          ))}
        </nav>
      </div>
      <div className="library-command-row">
        <label className="library-search">
          <Search aria-hidden="true" />
          <span className="visually-hidden">Search slides</span>
          <input
            type="search"
            role="searchbox"
            value={search}
            placeholder="Search slides, cases, diagnoses, tags"
            onChange={(event) => onSearch(event.target.value)}
          />
        </label>
        <div className="library-command-actions">
          <button
            type="button"
            className={filtersOpen ? 'active' : ''}
            aria-expanded={filtersOpen}
            onClick={onToggleFilters}
          >
            <Filter /> <span>Filters</span>
          </button>
          <label className="toolbar-select">
            <span className="visually-hidden">Sort slides</span>
            <select value={sort} onChange={(event) => onSort(event.target.value)}>
              <option value="updated_desc">Sort: Updated</option>
              <option value="updated_asc">Sort: Oldest update</option>
              <option value="created_desc">Sort: Newest</option>
              <option value="created_asc">Sort: Oldest created</option>
              <option value="name_asc">Sort: Name A–Z</option>
              <option value="name_desc">Sort: Name Z–A</option>
            </select>
          </label>
          <label className="mobile-view-select">
            <span className="visually-hidden">View slides</span>
            <select value={view} onChange={(event) => onView(event.target.value as LibraryViewMode)}>
              <option value="grid">Grid</option>
              <option value="list">List</option>
              <option value="table">Table</option>
            </select>
          </label>
          <div className="view-switcher" aria-label="View mode">
            <button
              type="button"
              className={view === 'grid' ? 'active' : ''}
              aria-label="Grid view"
              onClick={() => onView('grid')}
            ><Grid2X2 /></button>
            <button
              type="button"
              className={view === 'list' ? 'active' : ''}
              aria-label="List view"
              onClick={() => onView('list')}
            ><List /></button>
            <button
              type="button"
              className={view === 'table' ? 'active' : ''}
              aria-label="Table view"
              onClick={() => onView('table')}
            ><Table2 /></button>
          </div>
          <div className="toolbar-create">
            <ContextMenu label="Create" buttonContent={<><Plus /> <span>Create</span></>}>
              {(close) => (
                <>
                <button type="button" role="menuitem" onClick={() => { close(); onNewFolder() }}>
                  <FolderPlus /> New folder
                </button>
                <button type="button" role="menuitem" onClick={() => { close(); onNewCollection() }}>
                  <Grid2X2Plus /> New collection
                </button>
                <button type="button" role="menuitem" onClick={() => { close(); onNewSavedView() }}>
                  <BookmarkPlus /> New saved view
                </button>
                </>
              )}
            </ContextMenu>
          </div>
          {onShare ? (
            <button type="button" aria-label="Share" onClick={onShare}>
              <Share2 /> <span>Share</span>
            </button>
          ) : null}
          <button
            type="button"
            className="library-upload-button"
            aria-label="Upload"
            onClick={onUpload}
          >
            <Upload /> <span>Upload</span>
          </button>
        </div>
      </div>
    </header>
  )
}
