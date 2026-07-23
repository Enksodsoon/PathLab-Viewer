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
  deleteCollection,
  deleteLibrarySlide,
  deleteSavedView,
  getFolderChildren,
  getLibraryFacets,
  getLibraryItems,
  getLibraryNavigation,
  getLibrarySlide,
  getSlideStatuses,
  logout,
  mutateLibrarySlide,
  mutateFolder,
  mutateSlide,
  publishSlide,
  reserveUpload,
  removeCollectionSlides,
  updateCollection,
  updateFolder,
  updateSavedView,
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
import { PublishConfirmationDialog } from '../components/library/PublishConfirmationDialog'
import { ShareDialog } from '../components/library/ShareDialog'
import { SlideDetailsPanel } from '../components/library/SlideDetailsPanel'
import { SlideViews, type SlideAction } from '../components/library/SlideViews'
import type {
  AdminSlide,
  LibraryFacets,
  LibraryCollection,
  LibraryFolder,
  LibraryItemsPage,
  LibraryNavigation,
  LibrarySlide,
  LibrarySlideDetails,
  SavedView,
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
  tag: '',
  state: '',
  createdFrom: '',
  createdTo: '',
  updatedFrom: '',
  updatedTo: '',
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
  | 'edit'
  | 'delete'
  | 'edit-folder'
  | 'move-folder'
  | 'trash-folder'
  | 'edit-collection'
  | 'delete-collection'
  | 'edit-saved'
  | 'delete-saved'
  | 'publish'
  | 'share'
  | null

interface SlideEditForm {
  displayName: string
  description: string
  caseId: string
  organSite: string
  stain: string
  diagnosis: string
  course: string
  tags: string
  teachingNote: string
  adminNotes: string
}

const EMPTY_EDIT_FORM: SlideEditForm = {
  displayName: '',
  description: '',
  caseId: '',
  organSite: '',
  stain: '',
  diagnosis: '',
  course: '',
  tags: '',
  teachingNote: '',
  adminNotes: '',
}

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
    tag: url.get('tag') || '',
    state: url.get('state') || '',
    createdFrom: url.get('createdFrom') || '',
    createdTo: url.get('createdTo') || '',
    updatedFrom: url.get('updatedFrom') || '',
    updatedTo: url.get('updatedTo') || '',
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
  const [publishBusy, setPublishBusy] = useState(false)
  const [visible, setVisible] = useState(() => document.visibilityState !== 'hidden')
  const [formName, setFormName] = useState('')
  const [formDescription, setFormDescription] = useState('')
  const [moveTarget, setMoveTarget] = useState('')
  const [folderTarget, setFolderTarget] = useState<LibraryFolder | null>(null)
  const [collectionTarget, setCollectionTarget] = useState('')
  const [collectionEditTarget, setCollectionEditTarget] = useState<LibraryCollection | null>(null)
  const [savedEditTarget, setSavedEditTarget] = useState<SavedView | null>(null)
  const [tagValue, setTagValue] = useState('')
  const [editForm, setEditForm] = useState(EMPTY_EDIT_FORM)
  const [file, setFile] = useState<File | null>(null)
  const [uploadName, setUploadName] = useState('')
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)
  const selectionAnchor = useRef<number | null>(null)
  const authEpoch = useRef(0)

  const setUrlValues = useCallback((
    values: Record<string, string | null>,
    replace = true,
  ) => {
    setUrl((current) => {
      const next = new URLSearchParams(current)
      for (const [key, value] of Object.entries(values)) {
        if (!value) next.delete(key)
        else next.set(key, value)
      }
      return next
    }, { replace })
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
    tags: filters.tag ? [filters.tag] : undefined,
    state: filters.state,
    createdFrom: filters.createdFrom ? `${filters.createdFrom}T00:00:00Z` : undefined,
    createdTo: filters.createdTo ? `${filters.createdTo}T23:59:59Z` : undefined,
    updatedFrom: filters.updatedFrom ? `${filters.updatedFrom}T00:00:00Z` : undefined,
    updatedTo: filters.updatedTo ? `${filters.updatedTo}T23:59:59Z` : undefined,
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
      } catch {
        if (!cancelled) setError('Processing status could not refresh. Retrying automatically.')
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
      .catch((caught) => {
        if (!(caught instanceof DOMException && caught.name === 'AbortError')) {
          setError('Filters could not load. Close and try again.')
        }
      })
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
      const names: Array<{ label: string; location: string }> = []
      let current = foldersById.get(location.slice('folder:'.length))
      while (current) {
        names.unshift({ label: current.name, location: `folder:${current.id}` })
        current = current.parentId ? foldersById.get(current.parentId) : undefined
      }
      return [{ label: 'All slides', location: 'all' }, ...names]
    }
    if (location.startsWith('collection:')) {
      const collection = navigation.collections.find(
        (item) => item.id === location.slice('collection:'.length),
      )
      return [
        { label: 'Collections', location: 'all' },
        { label: collection?.name ?? 'Collection', location },
      ]
    }
    const labels: Record<string, string> = {
      all: 'All slides',
      unfiled: 'Unfiled',
      shared: 'Shared',
      processing: 'Processing',
      failed: 'Failed',
      trash: 'Trash',
    }
    return [{ label: labels[location] ?? 'Slides', location }]
  }, [foldersById, location, navigation.collections])

  const currentTitle = breadcrumbs.at(-1)?.label ?? 'Slides'
  const shareTarget = useMemo(() => {
    if (location.startsWith('folder:')) {
      return {
        type: 'folder' as const,
        id: location.slice('folder:'.length),
        name: currentTitle,
      }
    }
    if (location.startsWith('collection:')) {
      return {
        type: 'collection' as const,
        id: location.slice('collection:'.length),
        name: currentTitle,
      }
    }
    return null
  }, [currentTitle, location])
  const selectedSlides = page.items.filter((slide) => selected.has(slide.id))
  const selectedIds = selectedSlides.map((slide) => slide.id)

  function chooseLocation(nextLocation: string) {
    setUrlValues({ location: nextLocation === 'all' ? null : nextLocation }, false)
    setNavigatorOpen(false)
  }

  function runAction(task: () => Promise<unknown>, failure: string) {
    setError('')
    void task().catch(() => setError(`${failure} failed. Try again.`))
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

  async function openEditor(slide: LibrarySlide) {
    let full: LibrarySlideDetails
    try {
      full = await getLibrarySlide(slide.id)
    } catch {
      full = { ...slide, filename: '', adminNotes: '', metadata: null }
    }
    setSelected(new Set([slide.id]))
    setDetails(full)
    setEditForm({
      displayName: full.displayName,
      description: full.description,
      caseId: full.caseId,
      organSite: full.organSite,
      stain: full.stain,
      diagnosis: full.diagnosis,
      course: full.course,
      tags: full.tags.join(', '),
      teachingNote: full.teachingNote,
      adminNotes: full.adminNotes,
    })
    setDialog('edit')
  }

  async function actOnSlide(
    slide: LibrarySlide,
    action: SlideAction,
  ) {
    setError('')
    try {
      if (action === 'edit') {
        await openEditor(slide)
        return
      }
      if (action === 'copy-public') {
        await navigator.clipboard.writeText(
          new URL(`/s/${slide.publicId}`, window.location.origin).toString(),
        )
        setNotice('Public link copied.')
        return
      }
      setSelected(new Set([slide.id]))
      if (action === 'move') setDialog('move')
      else if (action === 'collection') setDialog('add-collection')
      else if (action === 'delete') setDialog('delete')
      else if (action === 'publish') {
        setDialog('publish')
        return
      } else if (action === 'unpublish' || action === 'retry') {
        const changed = await mutateSlide(slide.id, action)
        setPage((current) => ({
          ...current,
          items: current.items.map((item) => (
            item.id === slide.id ? { ...item, state: changed.state } : item
          )),
        }))
        setSelected(new Set())
        setNotice(action === 'retry'
          ? 'Conversion queued again.'
          : action === 'publish' ? 'Slide published.' : 'Slide unpublished.')
      } else if (action === 'trash' || action === 'restore') {
        await mutateLibrarySlide(slide.id, action)
        setPage((current) => ({
          ...current,
          items: current.items.filter((item) => item.id !== slide.id),
          total: Math.max(0, current.total - 1),
        }))
        setSelected(new Set())
        await refreshNavigation()
      }
    } catch {
      const label = action === 'retry' ? 'Retry' : `${action[0]?.toUpperCase()}${action.slice(1)}`
      setError(`${label} failed. Try again.`)
    }
  }

  async function refreshNavigation() {
    setNavigation(safeNavigation(await getLibraryNavigation()))
  }

  async function handleFolderAction(
    folder: LibraryFolder,
    action: 'rename' | 'move' | 'trash',
  ) {
    if (action === 'trash') {
      setFolderTarget(folder)
      setDialog('trash-folder')
      return
    }
    setFolderTarget(folder)
    setFormName(folder.name)
    setFormDescription(folder.description)
    setMoveTarget(folder.parentId ?? '')
    setDialog(action === 'rename' ? 'edit-folder' : 'move-folder')
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

  async function restoreSelected() {
    if (!selectedIds.length) return
    await Promise.all(selectedIds.map((id) => mutateLibrarySlide(id, 'restore')))
    setPage((current) => ({
      ...current,
      items: current.items.filter((slide) => !selected.has(slide.id)),
      total: Math.max(0, current.total - selected.size),
    }))
    setSelected(new Set())
    await refreshNavigation()
  }

  async function permanentlyDeleteSelected() {
    if (!selectedIds.length) return
    await Promise.all(selectedIds.map((id) => deleteLibrarySlide(id)))
    setPage((current) => ({
      ...current,
      items: current.items.filter((slide) => !selected.has(slide.id)),
      total: Math.max(0, current.total - selected.size),
    }))
    setSelected(new Set())
    setDialog(null)
    await refreshNavigation()
  }

  async function changeSelectedState(
    action: 'publish' | 'unpublish' | 'retry',
    eligibleState: SlideState,
  ) {
    const eligible = selectedSlides.filter((slide) => slide.state === eligibleState)
    const changed = await Promise.all(
      eligible.map((slide) => action === 'publish'
        ? publishSlide(slide.id)
        : mutateSlide(slide.id, action)),
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
    const skipped = selectedSlides.length - eligible.length
    const verb = action === 'retry' ? 'queued' : action === 'publish' ? 'published' : 'unpublished'
    setNotice(`${changed.length} slide${changed.length === 1 ? '' : 's'} ${verb}${
      skipped ? `; ${skipped} skipped because their state was not eligible.` : '.'
    }`)
  }

  async function removeSelectedFromCollection() {
    if (!location.startsWith('collection:') || !selectedIds.length) return
    const removed = await removeCollectionSlides(
      location.slice('collection:'.length),
      selectedIds,
    )
    const removedIds = new Set(removed)
    setPage((current) => ({
      ...current,
      items: current.items.filter((slide) => !removedIds.has(slide.id)),
      total: Math.max(0, current.total - removedIds.size),
    }))
    setSelected(new Set())
    setNotice(`${removed.length} slide${removed.length === 1 ? '' : 's'} removed from collection.`)
    await refreshNavigation()
  }

  const publishSelected = () => changeSelectedState('publish', 'ready_private')
  const unpublishSelected = () => changeSelectedState('unpublish', 'published')
  const retrySelected = () => changeSelectedState('retry', 'failed')

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
            ...(filters.tag ? { tags: [filters.tag] } : {}),
            ...(filters.state ? { state: filters.state } : {}),
            ...(filters.createdFrom ? { createdFrom: filters.createdFrom } : {}),
            ...(filters.createdTo ? { createdTo: filters.createdTo } : {}),
            ...(filters.updatedFrom ? { updatedFrom: filters.updatedFrom } : {}),
            ...(filters.updatedTo ? { updatedTo: filters.updatedTo } : {}),
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
    } else if (dialog === 'edit') {
      const changed = await batchUpdateSlides(selectedIds, {
        displayName: editForm.displayName.trim(),
        description: editForm.description.trim(),
        caseId: editForm.caseId.trim(),
        organSite: editForm.organSite.trim(),
        stain: editForm.stain.trim(),
        diagnosis: editForm.diagnosis.trim(),
        course: editForm.course.trim(),
        tags: editForm.tags.split(',').map((tag) => tag.trim()).filter(Boolean),
        teachingNote: editForm.teachingNote.trim(),
        adminNotes: editForm.adminNotes.trim(),
      })
      const changedById = new Map(changed.map((slide) => [slide.id, slide]))
      setPage((current) => ({
        ...current,
        items: current.items.map((slide) => changedById.get(slide.id) ?? slide),
      }))
      const edited = changed[0]
      if (edited) setDetails((current) => current?.id === edited.id ? { ...current, ...edited } : current)
    } else if (dialog === 'edit-folder' && folderTarget) {
      await updateFolder(folderTarget.id, {
        name: formName.trim(),
        description: formDescription.trim(),
      })
      await refreshNavigation()
    } else if (dialog === 'move-folder' && folderTarget) {
      await updateFolder(folderTarget.id, { parentId: moveTarget || null })
      await refreshNavigation()
    } else if (dialog === 'edit-collection' && collectionEditTarget) {
      await updateCollection(collectionEditTarget.id, {
        name: formName.trim(),
        description: formDescription.trim(),
      })
      await refreshNavigation()
    } else if (dialog === 'edit-saved' && savedEditTarget) {
      await updateSavedView(savedEditTarget.id, { name: formName.trim() })
      await refreshNavigation()
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
    setMoveTarget('')
    setCollectionTarget('')
    setTagValue('')
    setDialog(name)
  }

  async function trashFolder() {
    if (!folderTarget) return
    await mutateFolder(folderTarget.id, 'trash')
    if (location === `folder:${folderTarget.id}`) chooseLocation('all')
    setDialog(null)
    setFolderTarget(null)
    await refreshNavigation()
  }

  function handleCollectionAction(id: string, action: 'rename' | 'delete') {
    const target = navigation.collections.find((collection) => collection.id === id)
    if (!target) return
    setCollectionEditTarget(target)
    setFormName(target.name)
    setFormDescription(target.description)
    setDialog(action === 'rename' ? 'edit-collection' : 'delete-collection')
  }

  function handleSavedViewAction(id: string, action: 'rename' | 'delete') {
    const target = navigation.savedViews.find((viewItem) => viewItem.id === id)
    if (!target) return
    setSavedEditTarget(target)
    setFormName(target.name)
    setDialog(action === 'rename' ? 'edit-saved' : 'delete-saved')
  }

  async function deleteOrganizationTarget() {
    if (dialog === 'delete-collection' && collectionEditTarget) {
      await deleteCollection(collectionEditTarget.id)
      if (location === `collection:${collectionEditTarget.id}`) chooseLocation('all')
      setCollectionEditTarget(null)
    } else if (dialog === 'delete-saved' && savedEditTarget) {
      await deleteSavedView(savedEditTarget.id)
      if (location === `saved:${savedEditTarget.id}`) chooseLocation('all')
      setSavedEditTarget(null)
    }
    setDialog(null)
    await refreshNavigation()
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
          onExpandFolder={(folder) => runAction(
            () => expandFolder(folder),
            'Folder expansion',
          )}
          onLocation={chooseLocation}
          onNewFolder={() => openNamedDialog('folder')}
          onNewCollection={() => openNamedDialog('collection')}
          onNewSavedView={() => openNamedDialog('saved')}
          onDropSlides={(folderId, ids) => runAction(
            () => moveSlides(ids, folderId),
            'Move',
          )}
          onFolderAction={(folder, action) => runAction(
            () => handleFolderAction(folder, action),
            'Folder action',
          )}
          onCollectionAction={handleCollectionAction}
          onSavedViewAction={handleSavedViewAction}
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
          onForward={() => navigate(1)}
          onUp={() => {
            if (!location.startsWith('folder:')) return chooseLocation('all')
            const current = foldersById.get(location.slice('folder:'.length))
            chooseLocation(current?.parentId ? `folder:${current.parentId}` : 'all')
          }}
          onBreadcrumb={chooseLocation}
          onSearch={setSearchDraft}
          onSort={(value) => setUrlValues({ sort: value === 'updated_desc' ? null : value })}
          onView={(value) => setUrlValues({ view: value === 'grid' ? null : value })}
          onToggleFilters={() => setFiltersOpen((current) => !current)}
          onNewFolder={() => openNamedDialog('folder')}
          onNewCollection={() => openNamedDialog('collection')}
          onNewSavedView={() => openNamedDialog('saved')}
          onUpload={() => openNamedDialog('upload')}
          onShare={shareTarget ? () => openNamedDialog('share') : undefined}
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
                tag: next.tag || null,
                state: next.state || null,
                createdFrom: next.createdFrom || null,
                createdTo: next.createdTo || null,
                updatedFrom: next.updatedFrom || null,
                updatedTo: next.updatedTo || null,
              })
            }}
            onClear={() => {
              setFilters(EMPTY_FILTERS)
              setUrlValues({
                organ: null,
                stain: null,
                diagnosis: null,
                course: null,
                tag: null,
                state: null,
                createdFrom: null,
                createdTo: null,
                updatedFrom: null,
                updatedTo: null,
              })
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
          {notice && dialog === null ? (
            <div className="library-notice" role="status">{notice}</div>
          ) : null}
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
              onAction={(slide, action) => void actOnSlide(slide, action)}
            />
          ) : null}
          {page.nextCursor ? (
            <button
              type="button"
              className="load-more"
              disabled={loadingMore}
              onClick={() => runAction(loadMore, 'Load more')}
            >
              {loadingMore ? 'Loading…' : 'Load more slides'}
            </button>
          ) : null}
        </section>
        <SelectionActionBar
          count={selected.size}
          mode={location === 'trash' ? 'trash' : 'default'}
          onClear={() => setSelected(new Set())}
          onMove={() => openNamedDialog('move')}
          onCollection={() => openNamedDialog('add-collection')}
          onTags={() => openNamedDialog('tags')}
          onPublish={() => openNamedDialog('publish')}
          onUnpublish={() => runAction(unpublishSelected, 'Unpublish')}
          onRetry={() => runAction(retrySelected, 'Retry')}
          onRemoveCollection={() => runAction(
            removeSelectedFromCollection,
            'Remove from collection',
          )}
          onTrash={() => runAction(trashSelected, 'Move to Trash')}
          onRestore={() => runAction(restoreSelected, 'Restore')}
          onDelete={() => openNamedDialog('delete')}
          canPublish={selectedSlides.some((slide) => slide.state === 'ready_private')}
          canUnpublish={selectedSlides.some((slide) => slide.state === 'published')}
          canRetry={selectedSlides.some((slide) => slide.state === 'failed')}
          inCollection={location.startsWith('collection:')}
        />
      </main>
      {details ? (
        <SlideDetailsPanel
          slide={details}
          folderName={details.folderId
            ? foldersById.get(details.folderId)?.name
            : undefined}
          collectionNames={location.startsWith('collection:')
            ? [navigation.collections.find(
              (collection) => collection.id === location.slice('collection:'.length),
            )?.name].filter((name): name is string => Boolean(name))
            : []}
          onClose={() => setDetails(null)}
          onEdit={() => {
            void openEditor(details)
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

      <PublishConfirmationDialog
        open={dialog === 'publish'}
        count={selected.size}
        busy={publishBusy}
        onClose={() => setDialog(null)}
        onConfirm={() => {
          if (publishBusy) return
          setPublishBusy(true)
          setError('')
          void publishSelected()
            .then(() => setDialog(null))
            .catch(() => setError('Publish failed. Review deidentification and try again.'))
            .finally(() => setPublishBusy(false))
        }}
      />

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
          runAction(submitSimpleDialog, 'Create')
        }}>
          <label>Name<input autoFocus required value={formName} onChange={(event) => setFormName(event.target.value)} /></label>
          {dialog !== 'saved' ? (
            <label>Description<textarea value={formDescription} onChange={(event) => setFormDescription(event.target.value)} /></label>
          ) : <p>Current search and filters will be saved.</p>}
          <button type="submit" className="primary">Create</button>
        </form>
      </LibraryDialog>

      <LibraryDialog
        open={dialog === 'edit'}
        wide
        title="Edit slide details"
        description="Private administrator fields stay out of public manifests."
        onClose={() => setDialog(null)}
      >
        <form className="library-dialog-form metadata-form" onSubmit={(event) => {
          event.preventDefault()
          runAction(submitSimpleDialog, 'Save details')
        }}>
          <label>Display name
            <input
              required
              value={editForm.displayName}
              onChange={(event) => setEditForm((current) => ({
                ...current,
                displayName: event.target.value,
              }))}
            />
          </label>
          <label>Description
            <textarea
              value={editForm.description}
              onChange={(event) => setEditForm((current) => ({
                ...current,
                description: event.target.value,
              }))}
            />
          </label>
          <div className="metadata-form-grid">
            {([
              ['Case ID', 'caseId'],
              ['Organ / site', 'organSite'],
              ['Stain', 'stain'],
              ['Diagnosis', 'diagnosis'],
              ['Course', 'course'],
              ['Tags (comma separated)', 'tags'],
            ] as const).map(([label, field]) => (
              <label key={field}>{label}
                <input
                  value={editForm[field]}
                  onChange={(event) => setEditForm((current) => ({
                    ...current,
                    [field]: event.target.value,
                  }))}
                />
              </label>
            ))}
          </div>
          <label>Teaching note
            <textarea
              value={editForm.teachingNote}
              onChange={(event) => setEditForm((current) => ({
                ...current,
                teachingNote: event.target.value,
              }))}
            />
          </label>
          <label>Administrator note
            <textarea
              value={editForm.adminNotes}
              onChange={(event) => setEditForm((current) => ({
                ...current,
                adminNotes: event.target.value,
              }))}
            />
          </label>
          <button type="submit" className="primary">Save details</button>
        </form>
      </LibraryDialog>

      <LibraryDialog
        open={dialog === 'edit-folder'}
        title="Rename folder"
        onClose={() => setDialog(null)}
      >
        <form className="library-dialog-form" onSubmit={(event) => {
          event.preventDefault()
          runAction(submitSimpleDialog, 'Save folder')
        }}>
          <label>Name
            <input required value={formName} onChange={(event) => setFormName(event.target.value)} />
          </label>
          <label>Description
            <textarea value={formDescription} onChange={(event) => setFormDescription(event.target.value)} />
          </label>
          <button type="submit" className="primary">Save folder</button>
        </form>
      </LibraryDialog>

      <LibraryDialog
        open={dialog === 'move-folder'}
        title="Move folder"
        onClose={() => setDialog(null)}
      >
        <form className="library-dialog-form" onSubmit={(event) => {
          event.preventDefault()
          runAction(submitSimpleDialog, 'Move folder')
        }}>
          <label>Parent folder
            <select value={moveTarget} onChange={(event) => setMoveTarget(event.target.value)}>
              <option value="">Top level</option>
              {[...foldersById.values()]
                .filter((folder) => folder.id !== folderTarget?.id)
                .map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}
            </select>
          </label>
          <button type="submit" className="primary">Move folder</button>
        </form>
      </LibraryDialog>

      <LibraryDialog
        open={dialog === 'edit-collection' || dialog === 'edit-saved'}
        title={dialog === 'edit-collection' ? 'Rename collection' : 'Rename saved view'}
        onClose={() => setDialog(null)}
      >
        <form className="library-dialog-form" onSubmit={(event) => {
          event.preventDefault()
          runAction(submitSimpleDialog, 'Rename')
        }}>
          <label>Name
            <input required value={formName} onChange={(event) => setFormName(event.target.value)} />
          </label>
          {dialog === 'edit-collection' ? (
            <label>Description
              <textarea value={formDescription} onChange={(event) => setFormDescription(event.target.value)} />
            </label>
          ) : null}
          <button type="submit" className="primary">Save name</button>
        </form>
      </LibraryDialog>

      <LibraryDialog
        open={dialog === 'delete-collection' || dialog === 'delete-saved'}
        title={dialog === 'delete-collection' ? 'Delete collection' : 'Delete saved view'}
        description="Slides and stored files are not deleted."
        onClose={() => setDialog(null)}
      >
        <div className="library-dialog-form">
          <p>Delete “{dialog === 'delete-collection'
            ? collectionEditTarget?.name
            : savedEditTarget?.name}”?</p>
          <button
            type="button"
            className="primary danger"
            onClick={() => runAction(deleteOrganizationTarget, 'Delete')}
          >
            Delete
          </button>
        </div>
      </LibraryDialog>

      <LibraryDialog
        open={dialog === 'trash-folder'}
        title="Move folder to Trash"
        description="The complete folder subtree stays together and can be restored."
        onClose={() => setDialog(null)}
      >
        <div className="library-dialog-form">
          <p>Move “{folderTarget?.name}” and its contents to Trash?</p>
          <button
            type="button"
            className="primary danger"
            onClick={() => runAction(trashFolder, 'Move folder to Trash')}
          >
            Move folder to Trash
          </button>
        </div>
      </LibraryDialog>

      <LibraryDialog
        open={dialog === 'delete'}
        title="Delete permanently"
        description="This removes the selected slides and their stored files. This cannot be undone."
        onClose={() => setDialog(null)}
      >
        <div className="library-dialog-form">
          <p>{selected.size} slide{selected.size === 1 ? '' : 's'} selected.</p>
          <button
            type="button"
            className="primary danger"
            onClick={() => runAction(permanentlyDeleteSelected, 'Permanent deletion')}
          >
            Delete permanently
          </button>
        </div>
      </LibraryDialog>

      <LibraryDialog
        open={dialog === 'move'}
        title="Move slides"
        description={`${selected.size} selected`}
        onClose={() => setDialog(null)}
      >
        <form className="library-dialog-form" onSubmit={(event) => {
          event.preventDefault()
          runAction(submitSimpleDialog, 'Move')
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
          runAction(submitSimpleDialog, 'Add to collection')
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
          runAction(submitSimpleDialog, 'Save tags')
        }}>
          <label>Tags<input value={tagValue} onChange={(event) => setTagValue(event.target.value)} placeholder="Teaching, Adenocarcinoma" /></label>
          <button type="submit" className="primary">Save tags</button>
        </form>
      </LibraryDialog>

      {shareTarget ? (
        <ShareDialog
          open={dialog === 'share'}
          targetType={shareTarget.type}
          targetId={shareTarget.id}
          targetName={shareTarget.name}
          onClose={() => setDialog(null)}
        />
      ) : null}

      <AccountSecurityDialog
        open={securityOpen}
        onClose={() => setSecurityOpen(false)}
        onChanged={() => endSession('Password changed. Sign in again.')}
        onAuthenticationRequired={() => endSession('Session expired. Sign in again.')}
      />
    </div>
  )
}
