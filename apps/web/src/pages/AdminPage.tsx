import {
  ChevronLeft,
  Menu,
  Plus,
  Upload,
} from 'lucide-react'
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import {
  ApiError,
  addCollectionSlides,
  batchMoveSlides,
  batchUpdateSlides,
  createCollection,
  createFolder,
  createSavedView,
  getFolderChildren,
  getLibraryFacets,
  getLibraryItems,
  getLibraryNavigation,
  getLibrarySlide,
  getSlideStatuses,
  logout,
  mutateLibrarySlide,
  mutateSlide,
  reserveUpload,
} from '../api'
import { AccountSecurityDialog, AuthPanel } from '../components/AuthPanels'
import { AppRail } from '../components/library/AppRail'
import {
  FilterPanel,
  type LibraryFilters,
} from '../components/library/FilterPanel'
import { LibraryDialog } from '../components/library/LibraryDialog'
import { LibraryNavigator } from '../components/library/LibraryNavigator'
import {
  LibraryToolbar,
  type LibraryViewMode,
} from '../components/library/LibraryToolbar'
import { SelectionActionBar } from '../components/library/SelectionActionBar'
import { QuickViewRail } from '../components/library/QuickViewRail'
import { SlideDetailsPanel } from '../components/library/SlideDetailsPanel'
import { SlideViews } from '../components/library/SlideViews'
import type {
  AdminSlide,
  LibraryFacets,
  LibraryFolder,
  LibraryItemsPage,
  LibraryNavigation,
  LibrarySlide,
  LibrarySlideDetails,
  SlideState,
} from '../types'
import { startTusUpload } from '../upload'
import '../library.css'

const EMPTY_NAVIGATION: LibraryNavigation = {
  counts: { all: 0, unfiled: 0, shared: 0, processing: 0, failed: 0, trash: 0 },
  folders: [],
  collections: [],
  savedViews: [],
}
const EMPTY_PAGE: LibraryItemsPage = { items: [], nextCursor: null, total: 0 }
const EMPTY_FILTERS: LibraryFilters = {
  organ: '',
  stain: '',
  diagnosis: '',
  course: '',
}
const ACTIVE_STATES = new Set<SlideState>([
  'uploading',
  'queued',
  'validating',
  'converting',
  'deleting',
])

type DialogName =
  | 'upload'
  | 'folder'
  | 'collection'
  | 'saved'
  | 'move'
  | 'add-collection'
  | 'tags'
  | null

function safeNavigation(value: LibraryNavigation): LibraryNavigation {
  if (!value || Array.isArray(value) || !value.counts) return EMPTY_NAVIGATION
  return value
}

function safePage(value: LibraryItemsPage): LibraryItemsPage {
  if (!value || Array.isArray(value) || !Array.isArray(value.items)) return EMPTY_PAGE
  return value
}

function uploadSlide(slide: AdminSlide, folderId: string | null): LibrarySlide {
  return {
    id: slide.id,
    publicId: slide.publicId,
    displayName: slide.displayName,
    description: '',
    folderId,
    caseId: '',
    organSite: '',
    stain: '',
    diagnosis: '',
    course: '',
    tags: [],
    teachingNote: '',
    sourceBytes: slide.sourceBytes,
    derivativeBytes: 0,
    state: slide.state,
    errorCode: slide.errorCode,
    createdAt: slide.createdAt,
    updatedAt: slide.createdAt,
    trashedAt: null,
    thumbnailUrl: null,
  }
}

export function AdminPage() {
  const navigate = useNavigate()
  const [url, setUrl] = useSearchParams()
  const location = url.get('location') || 'all'
  const sort = url.get('sort') || 'updated_desc'
  const view = (url.get('view') as LibraryViewMode | null) || 'grid'
  const [authorized, setAuthorized] = useState<boolean | null>(null)
  const [navigation, setNavigation] = useState(EMPTY_NAVIGATION)
  const [page, setPage] = useState(EMPTY_PAGE)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [searchDraft, setSearchDraft] = useState(url.get('q') || '')
  const [search, setSearch] = useState(url.get('q') || '')
  const [filters, setFilters] = useState<LibraryFilters>({
    organ: url.get('organ') || '',
    stain: url.get('stain') || '',
    diagnosis: url.get('diagnosis') || '',
    course: url.get('course') || '',
  })
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [facets, setFacets] = useState<LibraryFacets | null>(null)
  const [facetsLoading, setFacetsLoading] = useState(false)
  const [folderChildren, setFolderChildren] = useState(
    () => new Map<string, LibraryFolder[]>(),
  )
  const [expandedFolders, setExpandedFolders] = useState(() => new Set<string>())
  const [selected, setSelected] = useState(() => new Set<string>())
  const [details, setDetails] = useState<LibrarySlideDetails | LibrarySlide | null>(null)
  const [dialog, setDialog] = useState<DialogName>(null)
  const [securityOpen, setSecurityOpen] = useState(false)
  const [navigatorOpen, setNavigatorOpen] = useState(false)
  const [notice, setNotice] = useState('')
  const [authNotice, setAuthNotice] = useState('')
  const [signingOut, setSigningOut] = useState(false)
  const [visible, setVisible] = useState(() => document.visibilityState !== 'hidden')
  const [formName, setFormName] = useState('')
  const [formDescription, setFormDescription] = useState('')
  const [moveTarget, setMoveTarget] = useState('')
  const [collectionTarget, setCollectionTarget] = useState('')
  const [tagValue, setTagValue] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [uploadName, setUploadName] = useState('')
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)
  const selectionAnchor = useRef<number | null>(null)
  const authEpoch = useRef(0)

  const setUrlValues = useCallback((values: Record<string, string | null>) => {
    setUrl((current) => {
      const next = new URLSearchParams(current)
      for (const [key, value] of Object.entries(values)) {
        if (!value) next.delete(key)
        else next.set(key, value)
      }
      return next
    }, { replace: true })
  }, [setUrl])

  const loadNavigation = useCallback(async () => {
    const epoch = authEpoch.current
    try {
      const value = safeNavigation(await getLibraryNavigation())
      if (epoch !== authEpoch.current) return
      setNavigation(value)
      setAuthorized(true)
    } catch (caught) {
      if (epoch !== authEpoch.current) return
      if (caught instanceof ApiError && caught.status === 401) {
        setAuthorized(false)
        setNavigation(EMPTY_NAVIGATION)
        setPage(EMPTY_PAGE)
      } else {
        setError('Library navigation could not load.')
      }
    }
  }, [])

  useEffect(() => {
    void loadNavigation()
  }, [loadNavigation])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchDraft.trim())
      setUrlValues({ q: searchDraft.trim() || null })
    }, 250)
    return () => window.clearTimeout(timer)
  }, [searchDraft, setUrlValues])

  const query = useMemo(() => ({
    location,
    q: search,
    organ: filters.organ,
    stain: filters.stain,
    diagnosis: filters.diagnosis,
    course: filters.course,
    sort,
    limit: 48,
  }), [filters, location, search, sort])

  useEffect(() => {
    if (!authorized) return
    const controller = new AbortController()
    setLoading(true)
    setError('')
    void getLibraryItems({ ...query, signal: controller.signal })
      .then((value) => {
        setPage(safePage(value))
        setSelected(new Set())
        selectionAnchor.current = null
      })
      .catch((caught) => {
        if (caught instanceof DOMException && caught.name === 'AbortError') return
        if (caught instanceof ApiError && caught.status === 401) {
          authEpoch.current += 1
          setAuthorized(false)
          return
        }
        setError('Slides could not load. Try again.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [authorized, query])

  useEffect(() => {
    const handler = () => setVisible(document.visibilityState !== 'hidden')
    document.addEventListener('visibilitychange', handler)
    return () => document.removeEventListener('visibilitychange', handler)
  }, [])

  const activeIdsKey = useMemo(
    () => page.items
      .filter((slide) => ACTIVE_STATES.has(slide.state))
      .map((slide) => slide.id)
      .join(','),
    [page.items],
  )
  const activeIds = useMemo(
    () => activeIdsKey ? activeIdsKey.split(',') : [],
    [activeIdsKey],
  )

  useEffect(() => {
    if (!authorized || !visible || activeIds.length === 0) return
    let cancelled = false
    let cycles = 0
    let timer = 0
    const poll = async () => {
      try {
        const statuses = await getSlideStatuses(activeIds)
        if (cancelled) return
        const byId = new Map(statuses.map((item) => [item.id, item]))
        setPage((current) => ({
          ...current,
          items: current.items.map((slide) => {
            const statusItem = byId.get(slide.id)
            return statusItem
              ? { ...slide, state: statusItem.state, errorCode: statusItem.errorCode }
              : slide
          }),
        }))
      } finally {
        cycles += 1
        if (!cancelled) timer = window.setTimeout(poll, cycles < 3 ? 4000 : 15_000)
      }
    }
    timer = window.setTimeout(poll, 4000)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [activeIds, activeIdsKey, authorized, visible])

  useEffect(() => {
    if (!filtersOpen || !authorized) return
    const controller = new AbortController()
    setFacetsLoading(true)
    void getLibraryFacets(location, search, controller.signal)
      .then(setFacets)
      .finally(() => {
        if (!controller.signal.aborted) setFacetsLoading(false)
      })
    return () => controller.abort()
  }, [authorized, filtersOpen, location, search])

  const foldersById = useMemo(() => {
    const map = new Map<string, LibraryFolder>()
    navigation.folders.forEach((folder) => map.set(folder.id, folder))
    folderChildren.forEach((children) => {
      children.forEach((folder) => map.set(folder.id, folder))
    })
    return map
  }, [folderChildren, navigation.folders])

  const breadcrumbs = useMemo(() => {
    if (location.startsWith('folder:')) {
      const names: string[] = []
      let current = foldersById.get(location.slice('folder:'.length))
      while (current) {
        names.unshift(current.name)
        current = current.parentId ? foldersById.get(current.parentId) : undefined
      }
      return ['All slides', ...names]
    }
    if (location.startsWith('collection:')) {
      const collection = navigation.collections.find(
        (item) => item.id === location.slice('collection:'.length),
      )
      return ['Collections', collection?.name ?? 'Collection']
    }
    const labels: Record<string, string> = {
      all: 'All slides',
      unfiled: 'Unfiled',
      shared: 'Shared',
      processing: 'Processing',
      failed: 'Failed',
      trash: 'Trash',
    }
    return [labels[location] ?? 'Slides']
  }, [foldersById, location, navigation.collections])

  const currentTitle = breadcrumbs.at(-1) ?? 'Slides'
  const selectedSlides = page.items.filter((slide) => selected.has(slide.id))
  const selectedIds = selectedSlides.map((slide) => slide.id)

  function chooseLocation(nextLocation: string) {
    setUrlValues({ location: nextLocation === 'all' ? null : nextLocation })
    setNavigatorOpen(false)
  }

  async function expandFolder(folder: LibraryFolder) {
    if (expandedFolders.has(folder.id)) {
      setExpandedFolders((current) => {
        const next = new Set(current)
        next.delete(folder.id)
        return next
      })
      return
    }
    if (!folderChildren.has(folder.id)) {
      const children = await getFolderChildren(folder.id)
      setFolderChildren((current) => new Map(current).set(folder.id, children))
    }
    setExpandedFolders((current) => new Set(current).add(folder.id))
  }

  function selectSlide(slideId: string, index: number, shift: boolean) {
    setSelected((current) => {
      const next = new Set(current)
      if (shift && selectionAnchor.current !== null) {
        const start = Math.min(selectionAnchor.current, index)
        const end = Math.max(selectionAnchor.current, index)
        for (let candidate = start; candidate <= end; candidate += 1) {
          const item = page.items[candidate]
          if (item) next.add(item.id)
        }
      } else if (next.has(slideId)) {
        next.delete(slideId)
      } else {
        next.add(slideId)
      }
      return next
    })
    selectionAnchor.current = index
  }

  async function openDetails(slide: LibrarySlide) {
    setDetails(slide)
    try {
      setDetails(await getLibrarySlide(slide.id))
    } catch {
      // Card metadata remains a safe fallback.
    }
  }

  async function refreshNavigation() {
    setNavigation(safeNavigation(await getLibraryNavigation()))
  }

  async function moveSlides(ids: string[], folderId: string | null) {
    if (!ids.length) return
    const changed = await batchMoveSlides(ids, folderId)
    if (location.startsWith('folder:') && folderId !== location.slice('folder:'.length)) {
      setPage((current) => ({
        ...current,
        items: current.items.filter((slide) => !ids.includes(slide.id)),
        total: Math.max(0, current.total - ids.length),
      }))
    } else {
      const changedById = new Map(changed.map((slide) => [slide.id, slide]))
      setPage((current) => ({
        ...current,
        items: current.items.map((slide) => changedById.get(slide.id) ?? slide),
      }))
    }
    setSelected(new Set())
    setDialog(null)
    await refreshNavigation()
  }

  async function trashSelected() {
    if (!selectedIds.length) return
    await Promise.all(selectedIds.map((id) => mutateLibrarySlide(id, 'trash')))
    setPage((current) => ({
      ...current,
      items: current.items.filter((slide) => !selected.has(slide.id)),
      total: Math.max(0, current.total - selected.size),
    }))
    setSelected(new Set())
    await refreshNavigation()
  }

  async function publishSelected() {
    const changed = await Promise.all(
      selectedSlides
        .filter((slide) => slide.state === 'ready_private')
        .map((slide) => mutateSlide(slide.id, 'publish')),
    )
    const changedById = new Map(changed.map((slide) => [slide.id, slide]))
    setPage((current) => ({
      ...current,
      items: current.items.map((slide) => {
        const item = changedById.get(slide.id)
        return item ? { ...slide, state: item.state } : slide
      }),
    }))
    setSelected(new Set())
  }

  async function loadMore() {
    if (!page.nextCursor || loadingMore) return
    setLoadingMore(true)
    try {
      const next = safePage(await getLibraryItems({
        ...query,
        cursor: page.nextCursor,
      }))
      setPage((current) => ({
        items: [...current.items, ...next.items],
        nextCursor: next.nextCursor,
        total: next.total,
      }))
    } finally {
      setLoadingMore(false)
    }
  }

  async function submitSimpleDialog() {
    if (dialog === 'folder') {
      const parentId = location.startsWith('folder:')
        ? location.slice('folder:'.length)
        : null
      const folder = await createFolder({
        name: formName,
        description: formDescription,
        parentId,
      })
      if (parentId) {
        setFolderChildren((current) => {
          const next = new Map(current)
          next.set(parentId, [...(next.get(parentId) ?? []), folder])
          return next
        })
      }
      await refreshNavigation()
    } else if (dialog === 'collection') {
      await createCollection({ name: formName, description: formDescription })
      await refreshNavigation()
    } else if (dialog === 'saved') {
      await createSavedView({
        name: formName,
        definition: {
          version: 1,
          filters: {
            ...(search ? { q: search } : {}),
            ...(filters.organ ? { organ: [filters.organ] } : {}),
            ...(filters.stain ? { stain: [filters.stain] } : {}),
            ...(filters.diagnosis ? { diagnosis: [filters.diagnosis] } : {}),
            ...(filters.course ? { course: [filters.course] } : {}),
          },
        },
        sort,
      })
      await refreshNavigation()
    } else if (dialog === 'move') {
      await moveSlides(selectedIds, moveTarget || null)
      return
    } else if (dialog === 'add-collection') {
      if (collectionTarget) await addCollectionSlides(collectionTarget, selectedIds)
    } else if (dialog === 'tags') {
      const tags = tagValue.split(',').map((tag) => tag.trim()).filter(Boolean)
      const changed = await batchUpdateSlides(selectedIds, { tags })
      const changedById = new Map(changed.map((slide) => [slide.id, slide]))
      setPage((current) => ({
        ...current,
        items: current.items.map((slide) => changedById.get(slide.id) ?? slide),
      }))
    }
    setDialog(null)
    setFormName('')
    setFormDescription('')
    setSelected(new Set())
  }

  async function startUpload() {
    if (!file) return
    if (!/\.ome\.tiff?$/i.test(file.name)) {
      setNotice('Choose a file ending in .ome.tif or .ome.tiff.')
      return
    }
    const folderId = location.startsWith('folder:')
      ? location.slice('folder:'.length)
      : null
    setNotice('Preparing resumable upload…')
    try {
      const reservation = await reserveUpload(
        file,
        uploadName.trim() || file.name.replace(/\.ome\.tiff?$/i, ''),
        folderId,
      )
      setPage((current) => ({
        ...current,
        items: [uploadSlide(reservation.slide, folderId), ...current.items],
        total: current.total + 1,
      }))
      setUploadProgress(0)
      setNotice('Upload prepared — it will resume automatically if interrupted.')
      await startTusUpload(file, reservation.uploadUrl, reservation.uploadToken, {
        progress: setUploadProgress,
        success: () => {
          setUploadProgress(100)
          setNotice('Upload complete. Processing is queued.')
        },
        error: (message) => setNotice(`Upload paused: ${message}`),
      })
    } catch {
      setNotice('Upload could not start. Check the file and available storage.')
    }
  }

  function endSession(message = '') {
    authEpoch.current += 1
    setAuthNotice(message)
    setAuthorized(false)
    setNavigation(EMPTY_NAVIGATION)
    setPage(EMPTY_PAGE)
    setSecurityOpen(false)
  }

  async function signOut() {
    if (signingOut) return
    setSigningOut(true)
    try {
      await logout()
      endSession()
    } catch {
      setError('Sign-out failed. Try again.')
    } finally {
      setSigningOut(false)
    }
  }

  function openNamedDialog(name: DialogName) {
    setFormName('')
    setFormDescription('')
    setNotice('')
    setDialog(name)
  }

  if (signingOut) return <div className="center-state dark">Signing out…</div>
  if (authorized === false) {
    return (
      <AuthPanel
        notice={authNotice}
        onSuccess={() => {
          setAuthNotice('')
          setAuthorized(null)
          void loadNavigation()
        }}
      />
    )
  }
  if (authorized === null) return <div className="center-state dark">Loading secure library…</div>

  return (
    <div className={`library-shell ${navigatorOpen ? 'navigator-open' : ''}`}>
      <AppRail
        location={location}
        onLocation={chooseLocation}
        onUpload={() => openNamedDialog('upload')}
        onSecurity={() => setSecurityOpen(true)}
        onSignOut={() => void signOut()}
      />
      <button
        type="button"
        className="mobile-navigator-toggle"
        aria-label="Open library navigator"
        onClick={() => setNavigatorOpen(true)}
      ><Menu /></button>
      <div className="mobile-navigator-backdrop" onClick={() => setNavigatorOpen(false)} />
      <div className="library-navigator-wrap">
        <button
          type="button"
          className="mobile-navigator-close"
          aria-label="Close library navigator"
          onClick={() => setNavigatorOpen(false)}
        ><ChevronLeft /></button>
        <LibraryNavigator
          navigation={navigation}
          location={location}
          folderChildren={folderChildren}
          expandedFolders={expandedFolders}
          onExpandFolder={(folder) => void expandFolder(folder)}
          onLocation={chooseLocation}
          onNewFolder={() => openNamedDialog('folder')}
          onNewCollection={() => openNamedDialog('collection')}
          onNewSavedView={() => openNamedDialog('saved')}
          onDropSlides={(folderId, ids) => void moveSlides(ids, folderId)}
        />
      </div>
      <main className="library-main">
        <LibraryToolbar
          breadcrumbs={breadcrumbs}
          search={searchDraft}
          sort={sort}
          view={view}
          filtersOpen={filtersOpen}
          onBack={() => navigate(-1)}
          onUp={() => {
            if (!location.startsWith('folder:')) return chooseLocation('all')
            const current = foldersById.get(location.slice('folder:'.length))
            chooseLocation(current?.parentId ? `folder:${current.parentId}` : 'all')
          }}
          onSearch={setSearchDraft}
          onSort={(value) => setUrlValues({ sort: value === 'updated_desc' ? null : value })}
          onView={(value) => setUrlValues({ view: value === 'grid' ? null : value })}
          onToggleFilters={() => setFiltersOpen((current) => !current)}
          onNewFolder={() => openNamedDialog('folder')}
          onUpload={() => openNamedDialog('upload')}
        />
        {filtersOpen ? (
          <FilterPanel
            filters={filters}
            facets={facets}
            loading={facetsLoading}
            onChange={(next) => {
              setFilters(next)
              setUrlValues({
                organ: next.organ || null,
                stain: next.stain || null,
                diagnosis: next.diagnosis || null,
                course: next.course || null,
              })
            }}
            onClear={() => {
              setFilters(EMPTY_FILTERS)
              setUrlValues({ organ: null, stain: null, diagnosis: null, course: null })
            }}
            onClose={() => setFiltersOpen(false)}
          />
        ) : null}
        <section className="library-content">
          <div className="library-content-heading">
            <div>
              <h2>{currentTitle}</h2>
              <span>{page.total} slides</span>
            </div>
            <label className="select-visible">
              <input
                type="checkbox"
                checked={page.items.length > 0 && selected.size === page.items.length}
                onChange={(event) => setSelected(
                  event.target.checked
                    ? new Set(page.items.map((slide) => slide.id))
                    : new Set(),
                )}
              />
              Select visible
            </label>
          </div>
          {error ? <div className="library-error" role="alert">{error}</div> : null}
          {loading ? <div className="library-loading" role="status">Loading slides…</div> : null}
          {!loading && page.items.length === 0 ? (
            <div className="library-empty">
              <Plus />
              <h3>No slides here</h3>
              <p>Upload a slide or choose another location.</p>
              <button type="button" onClick={() => openNamedDialog('upload')}>
                <Upload /> Upload slide
              </button>
            </div>
          ) : null}
          {!loading && page.items.length ? (
            <SlideViews
              view={view}
              slides={page.items}
              selected={selected}
              onSelect={selectSlide}
              onOpen={(slide) => void openDetails(slide)}
            />
          ) : null}
          {page.nextCursor ? (
            <button
              type="button"
              className="load-more"
              disabled={loadingMore}
              onClick={() => void loadMore()}
            >
              {loadingMore ? 'Loading…' : 'Load more slides'}
            </button>
          ) : null}
        </section>
        <SelectionActionBar
          count={selected.size}
          onClear={() => setSelected(new Set())}
          onMove={() => openNamedDialog('move')}
          onCollection={() => openNamedDialog('add-collection')}
          onTags={() => openNamedDialog('tags')}
          onPublish={() => void publishSelected()}
          onTrash={() => void trashSelected()}
        />
      </main>
      {details ? (
        <SlideDetailsPanel
          slide={details}
          onClose={() => setDetails(null)}
          onEdit={() => {
            setSelected(new Set([details.id]))
            setTagValue(details.tags.join(', '))
            openNamedDialog('tags')
          }}
        />
      ) : (
        <QuickViewRail
          navigation={navigation}
          recent={page.items}
          onLocation={chooseLocation}
          onOpen={(slide) => void openDetails(slide)}
        />
      )}

      <LibraryDialog
        open={dialog === 'upload'}
        title="Upload OME-TIFF"
        description={location.startsWith('folder:') ? `Target: ${currentTitle}` : 'Target: Unfiled'}
        onClose={() => setDialog(null)}
      >
        <div className="library-dialog-form">
          <label className="upload-drop">
            <Upload />
            <strong>{file?.name ?? 'Choose OME-TIFF'}</strong>
            <span>Up to 5 GiB · resumable</span>
            <input
              type="file"
              accept=".ome.tif,.ome.tiff,image/tiff"
              aria-label="Choose OME-TIFF"
              onChange={(event) => {
                const next = event.target.files?.[0] ?? null
                setFile(next)
                if (next) setUploadName(next.name.replace(/\.ome\.tiff?$/i, ''))
              }}
            />
          </label>
          <label>Display name<input value={uploadName} onChange={(event) => setUploadName(event.target.value)} /></label>
          {uploadProgress !== null ? (
            <div className="library-upload-progress"><span style={{ width: `${uploadProgress}%` }} /></div>
          ) : null}
          {notice ? <p role="status">{notice}</p> : null}
          <button type="button" className="primary" disabled={!file} onClick={() => void startUpload()}>
            Upload slide
          </button>
        </div>
      </LibraryDialog>

      <LibraryDialog
        open={['folder', 'collection', 'saved'].includes(dialog ?? '')}
        title={dialog === 'folder' ? 'New folder' : dialog === 'collection' ? 'New collection' : 'New saved view'}
        onClose={() => setDialog(null)}
      >
        <form className="library-dialog-form" onSubmit={(event) => {
          event.preventDefault()
          void submitSimpleDialog()
        }}>
          <label>Name<input autoFocus required value={formName} onChange={(event) => setFormName(event.target.value)} /></label>
          {dialog !== 'saved' ? (
            <label>Description<textarea value={formDescription} onChange={(event) => setFormDescription(event.target.value)} /></label>
          ) : <p>Current search and filters will be saved.</p>}
          <button type="submit" className="primary">Create</button>
        </form>
      </LibraryDialog>

      <LibraryDialog
        open={dialog === 'move'}
        title="Move slides"
        description={`${selected.size} selected`}
        onClose={() => setDialog(null)}
      >
        <form className="library-dialog-form" onSubmit={(event) => {
          event.preventDefault()
          void submitSimpleDialog()
        }}>
          <label>Destination
            <select value={moveTarget} onChange={(event) => setMoveTarget(event.target.value)}>
              <option value="">Unfiled</option>
              {[...foldersById.values()].map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}
            </select>
          </label>
          <button type="submit" className="primary">Move</button>
        </form>
      </LibraryDialog>

      <LibraryDialog
        open={dialog === 'add-collection'}
        title="Add to collection"
        description={`${selected.size} selected`}
        onClose={() => setDialog(null)}
      >
        <form className="library-dialog-form" onSubmit={(event) => {
          event.preventDefault()
          void submitSimpleDialog()
        }}>
          <label>Collection
            <select required value={collectionTarget} onChange={(event) => setCollectionTarget(event.target.value)}>
              <option value="">Choose collection</option>
              {navigation.collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}
            </select>
          </label>
          <button type="submit" className="primary">Add slides</button>
        </form>
      </LibraryDialog>

      <LibraryDialog
        open={dialog === 'tags'}
        title="Edit tags"
        description={`${selected.size} selected`}
        onClose={() => setDialog(null)}
      >
        <form className="library-dialog-form" onSubmit={(event) => {
          event.preventDefault()
          void submitSimpleDialog()
        }}>
          <label>Tags<input value={tagValue} onChange={(event) => setTagValue(event.target.value)} placeholder="Teaching, Adenocarcinoma" /></label>
          <button type="submit" className="primary">Save tags</button>
        </form>
      </LibraryDialog>

      <AccountSecurityDialog
        open={securityOpen}
        onClose={() => setSecurityOpen(false)}
        onChanged={() => endSession('Password changed. Sign in again.')}
        onAuthenticationRequired={() => endSession('Session expired. Sign in again.')}
      />
    </div>
  )
}
