import { Books } from '@phosphor-icons/react'
import type { ComponentProps } from 'react'
import { getCourseIconOption, type CourseIconKey } from '../../assessment/courseIcons'

export function CourseIcon({ iconKey, ...props }: { iconKey: CourseIconKey } & ComponentProps<typeof Books>) {
  const option = getCourseIconOption(iconKey)
  return <option.Icon {...props} />
}
