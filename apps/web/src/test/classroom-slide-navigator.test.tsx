import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ClassroomSlideNavigator } from '../classroom/ClassroomSlideNavigator'
import type { ClassroomSlide } from '../classroom/api'

const slides: ClassroomSlide[] = [
  {
    id: 'slide-1',
    position: 0,
    displayName: 'Colon overview',
    assetVersion: 'v1',
    tileSource: '/slide-1.dzi',
    width: 1000,
    height: 800,
    tileSize: 512,
    format: 'jpg',
    folderPath: ['GI', 'Colon'],
  },
  {
    id: 'slide-2',
    position: 1,
    displayName: 'Liver overview',
    assetVersion: 'v1',
    tileSource: '/slide-2.dzi',
    width: 1000,
    height: 800,
    tileSize: 512,
    format: 'jpg',
    folderPath: ['GI', 'Liver'],
  },
]

describe('ClassroomSlideNavigator', () => {
  it('keeps the session folder structure and selects a slide', () => {
    const select = vi.fn()
    render(<ClassroomSlideNavigator activeId="slide-1" slides={slides} onSelect={select} />)

    fireEvent.click(screen.getByRole('button', { name: /Colon overview/ }))
    expect(screen.getByRole('dialog', { name: 'Classroom slide navigator' })).toBeInTheDocument()
    expect(screen.getByText('GI')).toBeInTheDocument()
    expect(screen.getByText('Colon')).toBeInTheDocument()
    expect(screen.getByText('Liver')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Liver overview/ }))
    expect(select).toHaveBeenCalledWith('slide-2')
    expect(screen.queryByRole('dialog', { name: 'Classroom slide navigator' })).not.toBeInTheDocument()
  })
})
