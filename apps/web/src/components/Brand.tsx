import { Microscope } from '@phosphor-icons/react'

interface BrandProps {
  variant?: 'default' | 'library'
  product?: string
}

export function Brand({ variant = 'default', product = 'Viewer' }: BrandProps) {
  return (
    <div className={`brand${variant === 'library' ? ' brand-library' : ''}`} aria-label="PathLab Viewer">
      <span className={`brand-mark${variant === 'library' ? ' brand-mark-layers' : ''}`}>
        <Microscope
          aria-hidden="true"
          color="currentColor"
          data-testid="pathlab-microscope-mark"
          weight="duotone"
        />
      </span>
      <span>PathLab</span>
      <span className="brand-product">{product}</span>
    </div>
  )
}
