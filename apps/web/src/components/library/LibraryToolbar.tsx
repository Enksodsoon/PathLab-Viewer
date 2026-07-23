import {
  ArrowLeft,
  ArrowUp,
  ChevronRight,
  Filter,
  FolderPlus,
  Grid2X2,
  List,
  Search,
  Table2,
  Upload,
} from 'lucide-react'

export type LibraryViewMode = 'grid' | 'list' | 'table'

interface LibraryToolbarProps {
  breadcrumbs: string[]
  search: string
  sort: string
  view: LibraryViewMode
  filtersOpen: boolean
  onBack: () => void
  onUp: () => void
  onSearch: (value: string) => void
  onSort: (value: string) => void
  onView: (view: LibraryViewMode) => void
  onToggleFilters: () => void
  onNewFolder: () => void
  onUpload: () => void
}

export function LibraryToolbar({
  breadcrumbs,
  search,
  sort,
  view,
  filtersOpen,
  onBack,
  onUp,
  onSearch,
  onSort,
  onView,
  onToggleFilters,
  onNewFolder,
  onUpload,
}: LibraryToolbarProps) {
  return (
    <header className="library-toolbar">
      <div className="library-breadcrumb-row">
        <button type="button" aria-label="Back" onClick={onBack}><ArrowLeft /></button>
        <button type="button" aria-label="Up one level" onClick={onUp}><ArrowUp /></button>
        <nav aria-label="Breadcrumb">
          {breadcrumbs.map((crumb, index) => (
            <span key={`${crumb}-${index}`}>
              {index ? <ChevronRight aria-hidden="true" /> : null}
              {crumb}
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
        <button
          type="button"
          className={filtersOpen ? 'active' : ''}
          aria-expanded={filtersOpen}
          onClick={onToggleFilters}
        >
          <Filter /> Filters
        </button>
        <label className="toolbar-select">
          <span className="visually-hidden">Sort slides</span>
          <select value={sort} onChange={(event) => onSort(event.target.value)}>
            <option value="updated_desc">Sort: Updated</option>
            <option value="created_desc">Sort: Newest</option>
            <option value="name_asc">Sort: Name A–Z</option>
            <option value="name_desc">Sort: Name Z–A</option>
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
        <button type="button" onClick={onNewFolder}><FolderPlus /> New folder</button>
        <button type="button" className="library-upload-button" onClick={onUpload}>
          <Upload /> Upload
        </button>
      </div>
    </header>
  )
}
