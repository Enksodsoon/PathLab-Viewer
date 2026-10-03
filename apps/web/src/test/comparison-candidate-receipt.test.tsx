import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { ComparisonCandidateReceipt } from '../components/ComparisonCandidateReceipt'

it('shows actual recipe stages and reports missing calibrated errors without inventing units', () => {
  render(<ComparisonCandidateReceipt recipeIdentity="native-wsireg" stages={[{ engine: 'wsireg', buildVersion: '0.3.10', settingsDigest: 'frozen-settings', runtimeSeconds: 7.25, status: 'approximate', coordinateFrame: 'level-zero-reference' }]} measurements={{ coverage: 0.4, medianErrorUm: null, p95ErrorUm: null, qualified: false }} />)
  expect(screen.getByText(/wsireg · 0.3.10/)).toBeInTheDocument()
  expect(screen.getByText(/7.25 s/)).toBeInTheDocument()
  expect(screen.getByText('40.0%')).toBeInTheDocument()
  expect(screen.getByText('Unqualified')).toBeInTheDocument()
  expect(screen.getAllByText('Not measured')).toHaveLength(2)
})
