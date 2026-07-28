import { Desktop, Moon, Sun } from '@phosphor-icons/react'

import { useTheme } from './ThemeProvider'
import type { ThemePreference } from './theme'

export type ThemeControlProps = {
  compact?: boolean
  className?: string
}

const themeOptions: ReadonlyArray<{
  value: ThemePreference
  label: string
  Icon: typeof Sun
}> = [
  { value: 'light', label: 'Light', Icon: Sun },
  { value: 'dark', label: 'Dark', Icon: Moon },
  { value: 'system', label: 'System', Icon: Desktop },
]

export function ThemeControl({ compact = false, className }: ThemeControlProps) {
  const { preference, setPreference } = useTheme()
  const classes = ['theme-control', compact ? 'theme-control--compact' : '', className ?? '']
    .filter(Boolean)
    .join(' ')

  return (
    <fieldset className={classes}>
      <legend className="visually-hidden">Theme preference</legend>
      {themeOptions.map(({ value, label, Icon }) => (
        <label className="theme-control__option" key={value}>
          <input
            checked={preference === value}
            name="pathlab-theme"
            onChange={() => setPreference(value)}
            type="radio"
            value={value}
          />
          <Icon aria-hidden="true" size={18} weight="regular" />
          <span className="theme-control__label">{label}</span>
        </label>
      ))}
    </fieldset>
  )
}
