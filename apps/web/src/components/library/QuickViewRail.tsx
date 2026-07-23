import { Bookmark, Clock3, Grid2X2 } from 'lucide-react'

import type { LibraryNavigation, LibrarySlide } from '../../types'

interface QuickViewRailProps {
  navigation: LibraryNavigation
  recent: LibrarySlide[]
  onLocation: (location: string) => void
  onOpen: (slide: LibrarySlide) => void
}

export function QuickViewRail({
  navigation,
  recent,
  onLocation,
  onOpen,
}: QuickViewRailProps) {
  return (
    <aside className="library-quick-rail" aria-label="Quick views">
      <header><p>Workspace</p><h2>Quick views</h2></header>
      <section>
        <h3><Grid2X2 /> Collections</h3>
        {navigation.collections.slice(0, 4).map((item) => (
          <button key={item.id} type="button" onClick={() => onLocation(`collection:${item.id}`)}>
            <span>{item.name}</span><strong>{item.itemCount}</strong>
          </button>
        ))}
      </section>
      <section>
        <h3><Bookmark /> Saved views</h3>
        {navigation.savedViews.slice(0, 4).map((item) => (
          <button key={item.id} type="button" onClick={() => onLocation(`saved:${item.id}`)}>
            <span>{item.name}</span>
          </button>
        ))}
      </section>
      <section>
        <h3><Clock3 /> Recent slides</h3>
        {recent.slice(0, 4).map((slide) => (
          <button key={slide.id} type="button" onClick={() => onOpen(slide)}>
            {slide.thumbnailUrl ? <img src={slide.thumbnailUrl} alt="" loading="lazy" /> : null}
            <span>{slide.displayName}</span>
          </button>
        ))}
      </section>
    </aside>
  )
}
