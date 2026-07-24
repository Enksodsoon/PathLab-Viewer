import { Layers3, Microscope } from 'lucide-react'

interface BrandProps {
  variant?: 'default' | 'library'
}

export function Brand({ variant = 'default' }: BrandProps) {
  const Mark = variant === 'library' ? Layers3 : Microscope

  return (
    <div className={`brand${variant === 'library' ? ' brand-library' : ''}`} aria-label="PathLab Viewer">
      <span className={`brand-mark${variant === 'library' ? ' brand-mark-layers' : ''}`}>
        <Mark size={19} strokeWidth={2} aria-hidden="true" />
      </span>
      <span>PathLab</span>
      <span className="brand-product">Viewer</span>
    </div>
  )
}
