import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, expect, it, vi } from 'vitest'

import { parseAssessmentChoices } from '../assessment/choiceParser'
import type { AssessmentDocumentV2, DiagnosticSelection } from '../assessment/types'
import { AssessmentLearnerPreview } from '../components/assessment/AssessmentLearnerPreview'
import { AssessmentDiagnosticField } from '../components/AssessmentDiagnosticField'
import { AssessmentSectionCanvas } from '../components/assessment/AssessmentSectionCanvas'

vi.mock('../assessment/api', () => ({
  listEligibleAssessmentSlides: vi.fn().mockResolvedValue({
    items: [{
      id: 'slide-a',
      publicId: 'public-slide-a',
      displayName: 'Teaching slide A',
      tileSource: '/api/v2/slides/slide-a.dzi',
      thumbnail: 'data:image/png;base64,iVBORw0KGgo=',
    }, {
      id: 'slide-b',
      publicId: 'public-slide-b',
      displayName: 'Teaching slide B',
      tileSource: '/api/v2/slides/slide-b.dzi',
      thumbnail: 'data:image/png;base64,iVBORw0KGgo=',
    }],
  }),
}))

const fixture: AssessmentDocumentV2 = {
  schema: 'pathlab.assessment/2',
  title: 'Thoracic pathology',
  description: 'A sectioned diagnostic assessment.',
  presentation: { preset: 'standard', showProgress: true, showSectionTitles: true },
  settings: { mode: 'formative' },
  sections: [
    {
      id: 'section-a',
      title: 'Invasive tumours',
      description: 'Review the slide before answering.',
      items: [
        {
          id: 'question-a',
          type: 'multiple-choice',
          prompt: 'Which diagnosis best fits the glands?',
          required: true,
          points: '1',
          options: [
            { id: 'option-a', label: 'Adenocarcinoma' },
            { id: 'option-b', label: 'Reactive atypia' },
          ],
          answerKey: { optionIds: ['option-a'] },
        },
      ],
    },
  ],
}

function Harness() {
  const [document, setDocument] = useState(fixture)
  return <AssessmentSectionCanvas
    document={document}
    onDocumentChange={(update) => setDocument((current) => update(current))}
    onImport={vi.fn()}
    onPreview={vi.fn()}
  />
}

function DragHarness() {
  const [document, setDocument] = useState<AssessmentDocumentV2>({
    ...fixture,
    sections: [{
      ...fixture.sections[0],
      items: [
        ...fixture.sections[0].items,
        {
          ...fixture.sections[0].items[0],
          id: 'question-b',
          prompt: 'Which feature supports invasion?',
          options: [
            { id: 'option-c', label: 'Desmoplasia' },
            { id: 'option-d', label: 'Cilia' },
          ],
          answerKey: { optionIds: ['option-c'] },
        },
      ],
    }],
  })
  return <AssessmentSectionCanvas document={document} onDocumentChange={(update) => setDocument((current) => update(current))} onImport={vi.fn()} onPreview={vi.fn()} />
}

function dragDataTransfer() {
  const values = new Map<string, string>()
  return {
    effectAllowed: 'none',
    dropEffect: 'none',
    setData: (type: string, value: string) => values.set(type, value),
    getData: (type: string) => values.get(type) ?? '',
  }
}

afterEach(cleanup)

it('keeps learner preview focused and numbering contiguous around information blocks', async () => {
  const user = userEvent.setup()
  render(<AssessmentLearnerPreview document={{
    ...fixture,
    sections: [{
      ...fixture.sections[0],
      items: [
        fixture.sections[0].items[0],
        { id: 'information-a', type: 'section-information' as const, prompt: 'Review this teaching note.' },
        { ...fixture.sections[0].items[0], id: 'question-b', prompt: 'Which pattern is present?' },
      ],
    }],
  }} seed="preview-test" />)

  const navigator = screen.getByRole('complementary', { name: 'Preview question navigator' })
  expect(within(navigator).getByText('Question 1')).toBeVisible()
  expect(within(navigator).getByText('Section information')).toBeVisible()
  expect(within(navigator).getByText('Question 2')).toBeVisible()
  expect(within(navigator).queryByText('Question 3')).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Which diagnosis best fits the glands?' })).toBeVisible()
  expect(screen.queryByText('Review this teaching note.')).not.toBeInTheDocument()

  await user.click(within(navigator).getByRole('button', { name: /Section information/ }))
  expect(screen.getByText('Review this teaching note.')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Continue' }))
  expect(screen.getByRole('heading', { name: 'Which pattern is present?' })).toBeVisible()
})

it('authors, reorders, duplicates, deletes, and restores true sections', async () => {
  const user = userEvent.setup()
  render(<Harness />)

  expect(screen.getByRole('heading', { name: 'Questions' })).toBeVisible()
  expect(screen.getByText('1 sections · 1 questions · Ready to review')).toBeVisible()
  expect(screen.getByRole('checkbox', { name: 'Required question 1' })).toBeChecked()
  expect(screen.getByText('Section 1', { selector: '.assessment-section-kicker' })).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Collapse question 1' }))
  expect(screen.queryByRole('textbox', { name: 'Question' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Expand question 1' }))
  expect(screen.getByRole('textbox', { name: 'Question' })).toBeVisible()

  await user.click(screen.getByRole('button', { name: 'Add section' }))
  expect(screen.getByRole('textbox', { name: 'Section 2 title' })).toHaveValue('Section 2')
  await user.clear(screen.getByRole('textbox', { name: 'Section 2 title' }))
  await user.type(screen.getByRole('textbox', { name: 'Section 2 title' }), 'Clinical correlation')

  await user.click(screen.getByRole('button', { name: 'Duplicate section 1' }))
  expect(screen.getByDisplayValue('Invasive tumours copy')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Delete section 2' }))
  expect(screen.queryByDisplayValue('Invasive tumours copy')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Undo' }))
  expect(screen.getByDisplayValue('Invasive tumours copy')).toBeVisible()

  const reorder = screen.getByRole('button', { name: 'Reorder section 1' })
  reorder.focus()
  fireEvent.keyDown(reorder, { key: 'ArrowDown', altKey: true })
  expect(screen.getByRole('textbox', { name: 'Section 1 title' })).toHaveValue('Invasive tumours copy')
})

it('provides complete stable choice editing and section search', async () => {
  const user = userEvent.setup()
  render(<Harness />)

  const navigator = screen.getByRole('complementary', { name: 'Question navigator' })
  await user.type(within(navigator).getByPlaceholderText('Search sections and questions'), 'glands')
  expect(within(navigator).getByText('Which diagnosis best fits the glands?')).toBeVisible()

  await user.click(screen.getByRole('button', { name: 'Duplicate option 1' }))
  expect(screen.getByDisplayValue('Adenocarcinoma copy')).toBeVisible()
  expect(screen.getAllByRole('radio')).toHaveLength(3)
  await user.click(screen.getByRole('button', { name: 'Delete option 1' }))
  expect(screen.queryByDisplayValue('Adenocarcinoma')).not.toBeInTheDocument()
  await user.click(screen.getByRole('checkbox', { name: 'Allow Other' }))
  expect(screen.getByTestId('other-choice-preview')).toHaveTextContent('Other')
  expect(screen.getByTestId('other-choice-preview')).toHaveTextContent('Learner enters their own response')
  await user.click(screen.getByRole('button', { name: 'Remove Other choice' }))
  expect(screen.queryByTestId('other-choice-preview')).not.toBeInTheDocument()
  expect(screen.getByRole('checkbox', { name: 'Allow Other' })).not.toBeChecked()
  await user.click(screen.getByRole('checkbox', { name: 'Allow Other' }))
  await user.click(screen.getByRole('checkbox', { name: 'Shuffle choices' }))
  expect(screen.getByRole('checkbox', { name: 'Allow Other' })).toBeChecked()
  expect(screen.getByRole('checkbox', { name: 'Shuffle choices' })).toBeChecked()

  const firstChoice = screen.getByRole('textbox', { name: 'Option 1' })
  fireEvent.paste(firstChoice, { clipboardData: { getData: () => 'Solid growth\nLepidic growth\nAcinar growth' } })
  expect(screen.getByDisplayValue('Solid growth')).toBeVisible()
  expect(screen.getByDisplayValue('Lepidic growth')).toBeVisible()
  expect(screen.getByDisplayValue('Acinar growth')).toBeVisible()
  const optionGrip = screen.getByRole('button', { name: 'Reorder option 1' })
  const thirdOption = screen.getByRole('textbox', { name: 'Option 3' }).closest('.assessment-option')!
  fireEvent.mouseDown(optionGrip, { button: 0 })
  fireEvent.mouseEnter(thirdOption)
  fireEvent.mouseUp(thirdOption)
  expect(screen.getByRole('textbox', { name: 'Option 1' })).toHaveValue('Lepidic growth')
  expect(screen.getByRole('textbox', { name: 'Option 3' })).toHaveValue('Solid growth')
  expect(screen.queryByRole('button', { name: 'Move option 2 up' })).not.toBeInTheDocument()
  expect(screen.queryByText('Help text')).not.toBeInTheDocument()
  expect(screen.queryByText('Stable option IDs preserve keys, routing, and deterministic shuffle.')).not.toBeInTheDocument()
  expect(screen.getByText('Question', { selector: 'label' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Add choice' })).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Add option' })).not.toBeInTheDocument()
})

it('creates a reusable template and opens assessment import from one hub', async () => {
  const user = userEvent.setup()
  const createTemplate = vi.fn().mockResolvedValue({ id: 'template-1', name: 'Lung case review', document: fixture })
  const listTemplates = vi.fn().mockResolvedValue([])
  const openImport = vi.fn()
  render(<AssessmentSectionCanvas
    document={fixture}
    onDocumentChange={vi.fn()}
    onImport={openImport}
    onPreview={vi.fn()}
    onCreateTemplate={createTemplate}
    onListTemplates={listTemplates}
  />)

  await user.click(screen.getByRole('button', { name: 'Templates & import' }))
  const hub = screen.getByRole('region', { name: 'Templates and assessment import' })
  await user.type(within(hub).getByRole('textbox', { name: 'Template name' }), 'Lung case review')
  await user.click(within(hub).getByRole('button', { name: 'Save template' }))
  expect(createTemplate).toHaveBeenCalledWith('Lung case review')
  expect(await within(hub).findByRole('status')).toHaveTextContent('Lung case review is ready')
  expect(within(hub).getByRole('button', { name: /Lung case review/ })).toBeVisible()
  expect(within(hub).queryByText('Built-in templates')).not.toBeInTheDocument()
  expect(within(hub).queryByText('Paste questions in bulk')).not.toBeInTheDocument()

  await user.click(within(hub).getByRole('button', { name: 'Choose assessment' }))
  expect(openImport).toHaveBeenCalledOnce()
  expect(screen.queryByRole('region', { name: 'Templates and assessment import' })).not.toBeInTheDocument()
})

it('parses common copied-list formats and adds the result as choices', async () => {
  expect(parseAssessmentChoices('A) Solid growth; B) Lepidic growth | C) Acinar growth')).toEqual([
    'Solid growth',
    'Lepidic growth',
    'Acinar growth',
  ])
  expect(parseAssessmentChoices('• Solid growth\n- lepidic growth\n3. Acinar growth')).toEqual([
    'Solid growth',
    'lepidic growth',
    'Acinar growth',
  ])

  render(<Harness />)
  fireEvent.paste(screen.getByRole('textbox', { name: 'Option 1' }), { clipboardData: { getData: () => 'A) Solid growth; B) Lepidic growth | C) Acinar growth' } })
  expect(screen.getByRole('textbox', { name: 'Option 1' })).toHaveValue('Solid growth')
  expect(screen.getByRole('textbox', { name: 'Option 2' })).toHaveValue('Lepidic growth')
  expect(screen.getByRole('textbox', { name: 'Option 3' })).toHaveValue('Acinar growth')
  expect(screen.queryByText('Paste choices')).not.toBeInTheDocument()
})

it('keeps trackpad scrolling inside the question navigator', () => {
  render(<DragHarness />)
  const outline = screen.getByRole('complementary', { name: 'Question navigator' }).querySelector('.assessment-section-outline') as HTMLOListElement
  Object.defineProperty(outline, 'scrollHeight', { configurable: true, value: 800 })
  Object.defineProperty(outline, 'clientHeight', { configurable: true, value: 240 })
  outline.scrollTop = 0
  fireEvent.wheel(outline, { deltaY: 96 })
  expect(outline.scrollTop).toBe(96)
})

it('opens media in a modal and supports upload, alt text, removal, and keyboard close', async () => {
  const user = userEvent.setup()
  render(<Harness />)
  expect(screen.queryByRole('dialog', { name: 'Add question media' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Add media for question 1' }))
  expect(screen.getByRole('dialog', { name: 'Add question media' })).toBeVisible()
  await user.click(screen.getByRole('tab', { name: 'Upload image' }))
  const upload = within(screen.getByRole('tabpanel', { name: 'Upload image' })).getByLabelText('Upload images') as HTMLInputElement
  expect(upload).toHaveAttribute('multiple')
  await user.upload(upload, new File(['image-data'], 'teaching-image.png', { type: 'image/png' }))
  expect(await screen.findByAltText('Question media preview')).toBeVisible()
  await user.type(screen.getByRole('textbox', { name: 'Image 1 description' }), 'Glandular teaching image')
  expect(screen.getByAltText('Glandular teaching image')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Remove this media' })).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Remove this media' }))
  expect(screen.getByText('No media selected')).toBeVisible()
  fireEvent.keyDown(document, { key: 'Escape' })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Add media for question 1' })).toBeVisible()
})

it('supports WSI media selection, capture and annotation tools, and invalid upload feedback', async () => {
  const user = userEvent.setup()
  render(<Harness />)
  await user.click(screen.getByRole('button', { name: 'Add media for question 1' }))
  expect(screen.queryByRole('button', { name: 'Select slide' })).not.toBeInTheDocument()
  expect(screen.getByRole('tab', { name: 'Class slides' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.queryByText('Select one or several')).not.toBeInTheDocument()
  expect(screen.queryByText('Add several at once')).not.toBeInTheDocument()
  expect(screen.getByText('this lesson slides')).toBeVisible()
  expect(screen.queryByText('Only privacy-passed slides attached to this class or lesson appear here.')).not.toBeInTheDocument()
  const slideCard = await screen.findByRole('listitem', { name: 'Select slide Teaching slide A' })
  expect(slideCard).toBeVisible()
  await user.click(slideCard)
  expect(screen.getByRole('region', { name: 'Question WSI media editor' })).toBeVisible()
  expect(screen.getByRole('toolbar', { name: 'Question media annotation tools' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Capture current view' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Add point' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Draw rectangle' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Draw freehand' })).toBeVisible()
  expect(screen.queryByRole('combobox', { name: 'Loading mode' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Pan or zoom' })).toHaveTextContent('')
  fireEvent.keyDown(screen.getByRole('region', { name: 'Question WSI media editor' }), { key: 'p' })
  expect(screen.getByRole('button', { name: 'Add point' })).toHaveAttribute('aria-pressed', 'true')
  fireEvent.keyDown(screen.getByRole('region', { name: 'Question WSI media editor' }), { key: 'f' })
  expect(screen.getByRole('button', { name: 'Draw freehand' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.queryByRole('button', { name: 'Place selected annotation at center' })).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Keyboard shortcuts')).not.toBeInTheDocument()
  expect(within(screen.getByRole('region', { name: 'Question WSI media editor' })).getByRole('status', { hidden: true })).toHaveClass('visually-hidden')
  await user.clear(screen.getByRole('textbox', { name: 'Image 1 description' }))
  await user.type(screen.getByRole('textbox', { name: 'Image 1 description' }), 'Selected slide crop')
  expect(screen.getByRole('textbox', { name: 'Image 1 description' })).toHaveValue('Selected slide crop')

  await user.click(screen.getByRole('tab', { name: 'Class slides' }))
  await user.click(screen.getByRole('listitem', { name: 'Select slide Teaching slide B' }))
  expect(screen.getByText('2 / 10')).toBeVisible()
  expect(screen.getByRole('listitem', { name: 'Deselect slide Teaching slide A' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('listitem', { name: 'Deselect slide Teaching slide B' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('button', { name: 'Remove media 2: Teaching slide B' })).toBeVisible()

  await user.click(screen.getByRole('listitem', { name: 'Deselect slide Teaching slide A' }))
  expect(screen.getByText('1 / 10')).toBeVisible()
  await user.click(screen.getByRole('listitem', { name: 'Select slide Teaching slide A' }))
  expect(screen.getByText('2 / 10')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Remove media 2: Teaching slide A' }))
  expect(screen.getByText('1 / 10')).toBeVisible()
  await user.click(screen.getByRole('listitem', { name: 'Select slide Teaching slide A' }))
  expect(screen.getByText('2 / 10')).toBeVisible()

  await user.click(screen.getByRole('tab', { name: 'Upload image' }))
  const upload = within(screen.getByRole('tabpanel', { name: 'Upload image' })).getByLabelText('Upload images') as HTMLInputElement
  fireEvent.change(upload, { target: { files: [new File(['not-an-image'], 'notes.txt', { type: 'text/plain' })] } })
  expect(await screen.findByText('One or more images could not be prepared. Use JPG, PNG, or WebP files up to 100 MB each.')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Done' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Edit media for question 1' })).toBeVisible()
  expect(screen.getAllByLabelText('Question media preview')).toHaveLength(2)
}, 15_000)

it('edits point labels and supports cross-platform annotation shortcuts', async () => {
  const user = userEvent.setup()
  function LabeledPointHarness() {
    const [selections, setSelections] = useState<DiagnosticSelection[]>([{ kind: 'point', x: 0.4, y: 0.5 }])
    return <AssessmentDiagnosticField label="Labeled slide" tileSource="/slide.dzi" selections={selections} onCommit={(selection) => setSelections((current) => [...current, selection])} onClear={() => setSelections([])} onUpdateSelection={(index, selection) => setSelections((current) => current.map((candidate, candidateIndex) => candidateIndex === index ? selection : candidate))} onDeleteSelection={(index) => setSelections((current) => current.filter((_, candidateIndex) => candidateIndex !== index))} />
  }
  render(<LabeledPointHarness />)
  const workspace = screen.getByRole('region', { name: 'Labeled slide' })
  await user.type(screen.getByRole('textbox', { name: 'Point 1 label' }), 'Tumour focus')
  expect(screen.getByRole('textbox', { name: 'Point 1 label' })).toHaveValue('Tumour focus')
  fireEvent.keyDown(workspace, { key: 'r' })
  expect(screen.getByRole('button', { name: 'Draw rectangle' })).toHaveAttribute('aria-pressed', 'true')
  fireEvent.keyDown(workspace, { key: 'c', ctrlKey: true })
  fireEvent.keyDown(workspace, { key: 'v', ctrlKey: true })
  expect(screen.getByRole('textbox', { name: 'Point 2 label' })).toHaveValue('Tumour focus')
  fireEvent.keyDown(workspace, { key: 'z', ctrlKey: true })
  expect(screen.queryByRole('textbox', { name: 'Point 2 label' })).not.toBeInTheDocument()
  fireEvent.keyDown(workspace, { key: 'z', ctrlKey: true, shiftKey: true })
  expect(screen.getByRole('textbox', { name: 'Point 2 label' })).toBeVisible()
  fireEvent.keyDown(workspace, { key: 'x', metaKey: true })
  expect(screen.queryByRole('textbox', { name: 'Point 2 label' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Erase all annotations' })).toBeEnabled()
})

it('reorders questions by dragging navigator grips and omits the old drag guide', () => {
  render(<DragHarness />)
  const navigator = screen.getByRole('complementary', { name: 'Question navigator' })
  expect(within(navigator).queryByText('Drag or use Alt + arrows')).not.toBeInTheDocument()

  const source = within(navigator).getByRole('button', { name: /Which diagnosis best fits the glands/ })
  const target = within(navigator).getByRole('button', { name: /Which feature supports invasion/ })
  fireEvent.mouseDown(source.querySelector('.assessment-outline-drag')!, { button: 0 })
  fireEvent.mouseEnter(target.closest('li')!)
  fireEvent.mouseUp(target.closest('li')!)

  const cards = document.querySelectorAll('[data-question-id]')
  expect(cards[0]).toHaveAttribute('data-question-id', 'question-b')
  expect(cards[1]).toHaveAttribute('data-question-id', 'question-a')
})

it('collapses and restores the question navigator without losing its search', async () => {
  const user = userEvent.setup()
  render(<Harness />)
  const navigator = screen.getByRole('complementary', { name: 'Question navigator' })
  const search = within(navigator).getByPlaceholderText('Search sections and questions')

  await user.type(search, 'glands')
  await user.click(within(navigator).getByRole('button', { name: 'Collapse question navigator' }))

  expect(navigator).toHaveClass('is-collapsed')
  expect(within(navigator).getByRole('button', { name: 'Expand question navigator' })).toBeVisible()
  expect(within(navigator).getByText('Question navigator')).toBeVisible()
  expect(screen.queryByPlaceholderText('Search sections and questions')).not.toBeInTheDocument()

  await user.click(within(navigator).getByRole('button', { name: 'Expand question navigator' }))

  expect(navigator).not.toHaveClass('is-collapsed')
  expect(within(navigator).getByPlaceholderText('Search sections and questions')).toHaveValue('glands')
})

it('reorders questions between the canvas and navigator using one drag payload', () => {
  render(<DragHarness />)
  const navigator = screen.getByRole('complementary', { name: 'Question navigator' })
  const firstCanvasCard = document.querySelector('[data-question-id="question-a"]')!
  const secondNavigatorItem = within(navigator).getByRole('button', { name: /Which feature supports invasion/ }).closest('li')!
  const canvasToNavigator = dragDataTransfer()

  fireEvent.dragStart(firstCanvasCard, { dataTransfer: canvasToNavigator })
  fireEvent.drop(secondNavigatorItem, { dataTransfer: canvasToNavigator })
  expect(Array.from(document.querySelectorAll('[data-question-id]')).map((node) => node.getAttribute('data-question-id'))).toEqual(['question-b', 'question-a'])

  const navigatorSource = within(navigator).getByRole('button', { name: /Which diagnosis best fits the glands/ }).closest('li')!
  const canvasTarget = document.querySelector('[data-question-id="question-b"]')!
  const navigatorToCanvas = dragDataTransfer()
  fireEvent.dragStart(navigatorSource, { dataTransfer: navigatorToCanvas })
  fireEvent.drop(canvasTarget, { dataTransfer: navigatorToCanvas })
  expect(Array.from(document.querySelectorAll('[data-question-id]')).map((node) => node.getAttribute('data-question-id'))).toEqual(['question-a', 'question-b'])
})

it('shows completion status and adds up to three media items to an answer choice', async () => {
  const user = userEvent.setup()
  render(<Harness />)

  await user.click(screen.getByText('Feedback'))
  expect(screen.queryByText('Feedback & validation')).not.toBeInTheDocument()
  expect(screen.queryByText('Response guidance and scoring rules')).not.toBeInTheDocument()
  expect(screen.queryByText('Validation message')).not.toBeInTheDocument()
  await user.type(screen.getByRole('textbox', { name: 'Correct response' }), 'Well done')
  expect(screen.getByText('Added')).toBeVisible()

  await user.click(screen.getByLabelText('Add media for option 1'))
  expect(screen.getByRole('dialog', { name: 'Edit answer 1 media' })).toBeVisible()
  await user.click(await screen.findByRole('listitem', { name: 'Select slide Teaching slide A' }))
  expect(screen.getByRole('region', { name: 'Answer WSI media editor' })).toBeVisible()
  expect(screen.getByRole('toolbar', { name: 'Answer media annotation tools' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Capture current view' })).toBeVisible()
  expect(screen.getByRole('textbox', { name: 'Answer image 1 description' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Edit answer media 1: Teaching slide A' })).toBeVisible()
  await user.click(screen.getByRole('listitem', { name: 'Select slide Teaching slide B' }))
  expect(screen.getByText('2 / 3')).toBeVisible()
  await user.click(screen.getByRole('tab', { name: 'Upload images' }))
  fireEvent.change(screen.getByLabelText('Upload images for option 1'), { target: { files: [new File(['image'], 'choice.png', { type: 'image/png' })] } })
  expect(await screen.findByText('3 / 3')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Done' }))
  expect(screen.getAllByText(/Teaching slide/, { selector: '.assessment-option-media-thumb small' })).toHaveLength(2)
  expect(screen.getByLabelText('Edit media for option 1')).toBeVisible()

  const header = screen.getByRole('button', { name: 'Collapse question 1' }).closest('header')!
  expect(Array.from(header.children).indexOf(screen.getByRole('button', { name: 'Collapse question 1' }))).toBeGreaterThan(Array.from(header.children).indexOf(screen.getByText('•••').closest('details')!))
})

it('adds rating items with the approved rating controls', async () => {
  const user = userEvent.setup()
  render(<Harness />)

  await user.selectOptions(screen.getByRole('combobox', { name: 'Question type for section 1' }), 'rating')
  await user.click(screen.getByRole('button', { name: 'Add selected question to section 1' }))
  expect(screen.getByRole('combobox', { name: 'Display style' })).toHaveValue('stars')
  await user.selectOptions(screen.getByRole('combobox', { name: 'Maximum choices' }), '10')
  await user.selectOptions(screen.getByRole('combobox', { name: 'Display style' }), 'hearts')
  expect(screen.getAllByText('♥')).toHaveLength(10)
})

it('offers one text response type and highlights configured keywords', async () => {
  const user = userEvent.setup()
  render(<Harness />)

  const typePicker = screen.getByRole('combobox', { name: 'Question type for section 1' })
  expect(within(typePicker).queryByRole('option', { name: 'Dropdown' })).not.toBeInTheDocument()
  expect(within(typePicker).queryByRole('option', { name: 'Paragraph' })).not.toBeInTheDocument()
  expect(within(typePicker).getByRole('option', { name: 'Text response' })).toBeVisible()

  await user.selectOptions(typePicker, 'short-answer')
  await user.click(screen.getByRole('button', { name: 'Add selected question to section 1' }))
  await user.click(screen.getByText('Answer key & keywords'))
  await user.type(screen.getByRole('textbox', { name: 'Answer keywords' }), 'atypia, invasion')
  await user.type(screen.getByRole('textbox', { name: 'Keyword match preview' }), 'Marked atypia supports invasion.')
  expect(screen.getByText('atypia', { selector: 'mark' })).toBeVisible()
  expect(screen.getByText('invasion', { selector: 'mark' })).toBeVisible()
  expect(screen.getByText('2 of 2 keywords matched')).toBeVisible()
})
