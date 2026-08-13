import { CaretDown, FolderSimple, List, X } from '@phosphor-icons/react'
import { memo, useEffect, useMemo, useState } from 'react'

import type { ClassroomSlide } from './api'
import { classroomSlideThumbnail } from './classroomThumbnail'

interface FolderNode {
  key: string
  name: string
  slides: ClassroomSlide[]
  children: FolderNode[]
}

function pathKey(path: string[]) {
  return JSON.stringify(path)
}

function buildTree(slides: ClassroomSlide[]): FolderNode {
  const root: FolderNode = { key: 'root', name: 'Classroom slides', slides: [], children: [] }
  const nodes = new Map<string, FolderNode>([[pathKey([]), root]])
  const ensurePath = (path: string[]) => {
    let parent = root
    for (let depth = 1; depth <= path.length; depth += 1) {
      const currentPath = path.slice(0, depth)
      const key = pathKey(currentPath)
      let node = nodes.get(key)
      if (!node) {
        node = { key, name: currentPath.at(-1) ?? '', slides: [], children: [] }
        nodes.set(key, node)
        parent.children.push(node)
      }
      parent = node
    }
    return parent
  }
  slides.forEach((slide) => ensurePath(slide.folderPath ?? []).slides.push(slide))
  nodes.forEach((node) => node.children.sort((left, right) => left.name.localeCompare(right.name)))
  return root
}

function descendantCount(node: FolderNode): number {
  return node.slides.length
    + node.children.reduce((total, child) => total + descendantCount(child), 0)
}

const SlideButton = memo(function SlideButton({
  activeId,
  onSelect,
  slide,
}: {
  activeId: string
  onSelect: (slideId: string) => void
  slide: ClassroomSlide
}) {
  return <button
    className={slide.id === activeId ? 'is-active' : ''}
    type="button"
    onClick={() => onSelect(slide.id)}
  >
    <img src={classroomSlideThumbnail(slide)} alt="" loading="lazy" />
    <span><small>Slide {slide.position + 1}</small><strong>{slide.displayName}</strong></span>
  </button>
})

const FolderBranch = memo(function FolderBranch({
  activeId,
  node,
  onSelect,
}: {
  activeId: string
  node: FolderNode
  onSelect: (slideId: string) => void
}) {
  return <details className="classroom-folder-node" open>
    <summary>
      <FolderSimple aria-hidden="true" />
      <span>{node.name}</span>
      <small>{descendantCount(node)}</small>
    </summary>
    <div className="classroom-folder-contents">
      {node.slides.map((slide) => <SlideButton
        key={slide.id}
        activeId={activeId}
        onSelect={onSelect}
        slide={slide}
      />)}
      {node.children.map((child) => <FolderBranch
        key={child.key}
        activeId={activeId}
        node={child}
        onSelect={onSelect}
      />)}
    </div>
  </details>
})

export function ClassroomSlideNavigator({
  activeId,
  onSelect,
  slides,
}: {
  activeId: string
  onSelect: (slideId: string) => void
  slides: ClassroomSlide[]
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const active = slides.find((slide) => slide.id === activeId) ?? slides[0]
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase()
    if (!normalized) return slides
    return slides.filter((slide) => (
      `${slide.displayName} ${(slide.folderPath ?? []).join(' ')}`
        .toLocaleLowerCase()
        .includes(normalized)
    ))
  }, [query, slides])
  const tree = useMemo(() => buildTree(filtered), [filtered])

  useEffect(() => {
    if (!open) return
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [open])

  const select = (slideId: string) => {
    onSelect(slideId)
    setOpen(false)
  }

  return <div className={`classroom-slide-navigator${open ? ' is-open' : ''}`}>
    <button
      className="classroom-slide-trigger"
      type="button"
      aria-expanded={open}
      aria-haspopup="dialog"
      onClick={() => setOpen((current) => !current)}
    >
      <List aria-hidden="true" />
      <span>{active ? `${active.position + 1}. ${active.displayName}` : 'Choose a slide'}</span>
      <CaretDown aria-hidden="true" />
    </button>
    {open ? <>
      <button className="classroom-slide-backdrop" type="button" aria-label="Close slide navigator" onClick={() => setOpen(false)} />
      <section className="classroom-slide-popover" role="dialog" aria-label="Classroom slide navigator">
        <header>
          <div><p>Teaching set</p><h2>Classroom slides</h2></div>
          <button type="button" aria-label="Close slide navigator" onClick={() => setOpen(false)}><X /></button>
        </header>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search this class"
          aria-label="Search classroom slides"
        />
        <div className="classroom-slide-tree">
          {tree.slides.map((slide) => <SlideButton key={slide.id} activeId={activeId} onSelect={select} slide={slide} />)}
          {tree.children.map((child) => <FolderBranch key={child.key} activeId={activeId} node={child} onSelect={select} />)}
          {!filtered.length ? <p>No matching slides</p> : null}
        </div>
      </section>
    </> : null}
  </div>
}
