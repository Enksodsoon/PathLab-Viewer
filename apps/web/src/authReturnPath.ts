export function safeAdminReturnPath(value: string | null | undefined): string | null {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) {
    return null
  }
  try {
    const parsed = new URL(value, window.location.origin)
    if (parsed.origin !== window.location.origin) return null
    if (parsed.pathname !== '/admin' && !parsed.pathname.startsWith('/admin/')) return null
    return `${parsed.pathname}${parsed.search}${parsed.hash}`
  } catch {
    return null
  }
}

export function adminSignInPath(returnTo: string): string {
  const safeReturnTo = safeAdminReturnPath(returnTo)
  return safeReturnTo ? `/admin?returnTo=${encodeURIComponent(safeReturnTo)}` : '/admin'
}
