import { expect, it } from 'vitest'

import { ROSTER_COLUMNS, rowsToCsv } from '../assessment/rosterFiles'

it('defines the required structured roster columns and preserves Thai Unicode', () => {
  expect(ROSTER_COLUMNS.filter((column) => column.required).map((column) => column.key)).toEqual(['student_id', 'first_name'])
  expect(rowsToCsv([
    ROSTER_COLUMNS.map((column) => column.key),
    ['66001234', 'กัญญา', 'วัฒนกุล', 'Year 3', 'Lab A', 'Exchange student'],
  ])).toContain('66001234,กัญญา,วัฒนกุล,Year 3,Lab A,Exchange student')
  expect(ROSTER_COLUMNS.at(-1)?.key).toBe('other_information')
})

it('quotes spreadsheet values containing commas and line breaks', () => {
  expect(rowsToCsv([['S1', 'Ana, María', 'Line 1\nLine 2']])).toBe('S1,"Ana, María","Line 1\nLine 2"')
})
