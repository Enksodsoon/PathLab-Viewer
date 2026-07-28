import {
  CheckCircle,
  Info,
  WarningCircle,
  XCircle,
} from '@phosphor-icons/react'
import type { HTMLAttributes, ReactNode } from 'react'

type StatusTone = 'info' | 'success' | 'warning' | 'error'

interface StatusMessageProps extends Omit<HTMLAttributes<HTMLDivElement>, 'children'> {
  children: ReactNode
  label?: string
  tone?: StatusTone
}

const toneDefaults: Record<StatusTone, { label: string; icon: typeof Info }> = {
  info: { label: 'Update', icon: Info },
  success: { label: 'Complete', icon: CheckCircle },
  warning: { label: 'Review', icon: WarningCircle },
  error: { label: 'Attention', icon: XCircle },
}

export function StatusMessage({
  children,
  className = '',
  label,
  role,
  tone = 'info',
  ...props
}: StatusMessageProps) {
  const fallback = toneDefaults[tone]
  const Icon = fallback.icon
  const semanticRole = role ?? (tone === 'error' ? 'alert' : 'status')

  return (
    <div
      {...props}
      className={`pathlab-status-message pathlab-status-message--${tone} ${className}`.trim()}
      role={semanticRole}
    >
      <span className="pathlab-status-message__badge" aria-hidden="true">
        <Icon weight="bold" />
        {label ?? fallback.label}
      </span>
      <span className="pathlab-status-message__copy">{children}</span>
    </div>
  )
}
