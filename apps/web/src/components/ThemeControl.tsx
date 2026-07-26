import { Desktop, Moon, Sun } from '@phosphor-icons/react'

import { useTheme } from '../theme'
import type { ThemePreference } from '../theme'

const OPTIONS: Array<{
  Icon: typeof Sun
  label: string
  value: ThemePreference
}> = [
  { Icon: Sun, label: 'Light', value: 'light' },
  { Icon: Moon, label: 'Dark', value: 'dark' },
  { Icon: Desktop, label: 'System', value: 'system' },
]

export function ThemeControl() {
  const { preference, setPreference } = useTheme()

  return (
    <fieldset className="theme-control">
      <legend className="visually-hidden">Color theme</legend>
      {OPTIONS.map(({ Icon, label, value }) => (
        <span className="theme-option" key={value}>
          <input
            checked={preference === value}
            id={`theme-${value}`}
            name="color-theme"
            onChange={() => setPreference(value)}
            type="radio"
            value={value}
          />
          <label htmlFor={`theme-${value}`}>
            <Icon aria-hidden="true" size={16} weight={preference === value ? 'fill' : 'regular'} />
            <span>{label}</span>
          </label>
        </span>
      ))}
    </fieldset>
  )
}
