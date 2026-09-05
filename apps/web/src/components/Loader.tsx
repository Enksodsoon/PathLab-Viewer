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
      <svg
        className="pathlab-loader__container"
        viewBox="0 0 50 50"
        aria-hidden="true"
      >
        <rect
          className="pathlab-loader__boxes"
          x="0"
          y="0"
          width="50"
          height="50"
        />
      </svg>
      <span className="pathlab-loader__label">{label}</span>
    </span>
  )
}
