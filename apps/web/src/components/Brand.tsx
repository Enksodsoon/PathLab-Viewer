import { Microscope } from 'lucide-react'

export function Brand() {
  return (
    <div className="brand" aria-label="PathLab Viewer">
      <span className="brand-mark"><Microscope size={19} strokeWidth={2} /></span>
      <span>PathLab</span>
      <span className="brand-product">Viewer</span>
    </div>
  )
}
