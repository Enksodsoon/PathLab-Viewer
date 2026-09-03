interface LoaderProps {
  label: string
  size?: 'small' | 'medium' | 'large'
  inline?: boolean
  fullscreen?: boolean
}

export function Loader({
  label,
  size = 'medium',
  inline = false,
  fullscreen = false,
}: LoaderProps) {
  return (
    <span
      className={[
        'pathlab-loader',
        `pathlab-loader--${size}`,
        inline ? 'pathlab-loader--inline' : '',
        fullscreen ? 'pathlab-loader--fullscreen' : '',
      ].filter(Boolean).join(' ')}
      role="status"
      aria-live="polite"
    >
      <span className="pathlab-loader__indicator" aria-hidden="true" />
      <span className="pathlab-loader__label">{label}</span>
    </span>
  )
}
