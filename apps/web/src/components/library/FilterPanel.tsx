import { X } from 'lucide-react'

import type { LibraryFacets } from '../../types'

export interface LibraryFilters {
  organ: string
  stain: string
  diagnosis: string
  course: string
  tag: string
  state: string
  createdFrom: string
  createdTo: string
  updatedFrom: string
  updatedTo: string
}

interface FilterPanelProps {
  filters: LibraryFilters
  facets: LibraryFacets | null
  loading: boolean
  onChange: (filters: LibraryFilters) => void
  onClear: () => void
  onClose: () => void
}

export function FilterPanel({
  filters,
  facets,
  loading,
  onChange,
  onClear,
  onClose,
}: FilterPanelProps) {
  const fields = [
    ['organ', 'Organ / site', facets?.organ ?? []],
    ['stain', 'Stain', facets?.stain ?? []],
    ['diagnosis', 'Diagnosis', facets?.diagnosis ?? []],
    ['course', 'Course', facets?.course ?? []],
  ] as const
  return (
    <section className="library-filter-panel" aria-label="Library filters">
      <div className="filter-panel-heading">
        <h2>Filters</h2>
        <button type="button" aria-label="Close filters" onClick={onClose}><X /></button>
      </div>
      {loading ? <p role="status">Loading filter values…</p> : null}
      <div className="filter-grid">
        {fields.map(([key, label, options]) => (
          <label key={key}>
            <span>{label}</span>
            <select
              value={filters[key]}
              onChange={(event) => onChange({ ...filters, [key]: event.target.value })}
            >
              <option value="">All</option>
              {options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.value} ({option.count})
                </option>
              ))}
            </select>
          </label>
        ))}
        <label>
          <span>Tag</span>
          <input
            value={filters.tag}
            placeholder="Exact tag"
            onChange={(event) => onChange({ ...filters, tag: event.target.value })}
          />
        </label>
        <label>
          <span>Processing state</span>
          <select
            value={filters.state}
            onChange={(event) => onChange({ ...filters, state: event.target.value })}
          >
            <option value="">All</option>
            <option value="uploading">Uploading</option>
            <option value="queued">Queued</option>
            <option value="validating">Validating</option>
            <option value="converting">Processing</option>
            <option value="ready_private">Ready private</option>
            <option value="published">Published</option>
            <option value="failed">Failed</option>
          </select>
        </label>
        {([
          ['createdFrom', 'Created from'],
          ['createdTo', 'Created to'],
          ['updatedFrom', 'Updated from'],
          ['updatedTo', 'Updated to'],
        ] as const).map(([key, label]) => (
          <label key={key}>
            <span>{label}</span>
            <input
              type="date"
              value={filters[key]}
              onChange={(event) => onChange({ ...filters, [key]: event.target.value })}
            />
          </label>
        ))}
      </div>
      <button type="button" className="filter-clear" onClick={onClear}>Clear filters</button>
    </section>
  )
}
