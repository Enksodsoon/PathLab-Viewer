import { PathLabProductRail } from '@pathlab/viewer-ui'
import type { Ref } from 'react'

import type { LibraryNavigation } from '../../types'

interface AppRailProps {
  expanded: boolean
  isInert: boolean
  navigatorOpen: boolean
  navigatorButtonRef: Ref<HTMLButtonElement>
  storage: LibraryNavigation['storage']
  onToggleExpanded: () => void
  onNavigator: () => void
  onUpload: () => void
  onSecurity: () => void
  onSignOut: () => void
}

export function AppRail({
  expanded,
  isInert,
  navigatorOpen,
  navigatorButtonRef,
  storage,
  onToggleExpanded,
  onNavigator,
  onUpload,
  onSecurity,
  onSignOut,
}: AppRailProps) {
  return (
    <PathLabProductRail
      productName="Viewer"
      expanded={expanded}
      isInert={isInert}
      navigatorOpen={navigatorOpen}
      navigatorButtonRef={navigatorButtonRef}
      storage={storage}
      onToggleExpanded={onToggleExpanded}
      onNavigator={onNavigator}
      onUpload={onUpload}
      onSecurity={onSecurity}
      onSignOut={onSignOut}
    />
  )
}
