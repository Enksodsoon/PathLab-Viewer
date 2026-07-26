interface BrandProps {
  variant?: 'default' | 'library'
}

export function Brand({ variant = 'default' }: BrandProps) {
  return (
    <div className={`brand${variant === 'library' ? ' brand-library' : ''}`} aria-label="PathLab Viewer">
      <span className={`brand-mark${variant === 'library' ? ' brand-mark-layers' : ''}`}>
        <svg
          aria-hidden="true"
          data-testid="pathlab-tissue-mark"
          fill="none"
          viewBox="0 0 32 32"
        >
          <path data-tissue-layer d="M4.5 10.1 16 4.4l11.5 5.7L16 15.8 4.5 10.1Z" fill="currentColor" opacity=".34" />
          <path data-tissue-layer d="m4.5 15.9 11.5 5.7 11.5-5.7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" />
          <path data-tissue-layer d="m4.5 21.7 11.5 5.7 11.5-5.7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" />
        </svg>
      </span>
      <span>PathLab</span>
      <span className="brand-product">Viewer</span>
    </div>
  )
}
