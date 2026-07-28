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
