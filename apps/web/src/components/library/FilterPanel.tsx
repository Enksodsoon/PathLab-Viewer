import { X } from 'lucide-react'

import type { LibraryFacets } from '../../types'

export interface LibraryFilters {
  organ: string
  stain: string
  diagnosis: string
  course: string
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
      </div>
      <button type="button" className="filter-clear" onClick={onClear}>Clear filters</button>
    </section>
  )
}
