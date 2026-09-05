import { Component, type ErrorInfo, type ReactNode } from 'react'

import { Brand } from './Brand'

interface ApplicationErrorBoundaryProps {
  children: ReactNode
  resetKey: string
  reload?: () => void
}

interface ApplicationErrorBoundaryState {
  error: Error | null
}

export class ApplicationErrorBoundary extends Component<
  ApplicationErrorBoundaryProps,
  ApplicationErrorBoundaryState
> {
  state: ApplicationErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ApplicationErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('PathLab application render failed', error, info.componentStack)
  }

  componentDidUpdate(previousProps: ApplicationErrorBoundaryProps) {
    if (this.state.error && previousProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null })
    }
  }

  private retry = () => {
    this.setState({ error: null })
  }

  private reload = () => {
    if (this.props.reload) this.props.reload()
    else window.location.reload()
  }

  render() {
    if (!this.state.error) return this.props.children
    return <main className="viewer-message" role="alert">
      <Brand />
      <div>
        <h1>PathLab could not open this page</h1>
        <p>A page component failed to load. Reload the page to check your saved work.</p>
        <div className="application-recovery-actions">
          <button className="button primary" type="button" onClick={this.retry}>Try again</button>
          <button className="button" type="button" onClick={this.reload}>Reload app</button>
          <a className="button" href="/admin">Go to library</a>
        </div>
      </div>
    </main>
  }
}
