import type { AssessmentItem, DiagnosticSelection } from '../../assessment/types'
import { AssessmentDiagnosticField } from '../AssessmentDiagnosticField'

interface Props {
  item: AssessmentItem
  value: Record<string, unknown>
  onChange?: (response: Record<string, unknown>) => void
  assets?: Record<string, string>
  mobilePanel?: 'slide' | 'answer'
  readOnly?: boolean
}

const ratingSymbol = (item: AssessmentItem, value: number) => item.rating?.style === 'stars'
  ? '★'
  : item.rating?.style === 'hearts'
    ? '♥'
    : item.rating?.style === 'thumbs-up' ? '👍' : String(value)

export function AssessmentLearnerQuestion({ item, value, onChange = () => undefined, assets = {}, mobilePanel = 'answer', readOnly = false }: Props) {
  const selected = (value.optionIds as string[] | undefined) ?? []
  const tileSource = item.slideId ? assets[item.slideId] : undefined
  const diagnosticSelections = value.selection ? [value.selection as DiagnosticSelection] : []
  if (item.type === 'section-information' || item.type === 'information') {
    return <section className="assessment-student-question assessment-information-block"><h2>{item.prompt}</h2>{item.helpText ? <p>{item.helpText}</p> : null}</section>
  }
  return <section className="assessment-student-question" data-question-type={item.type}>
    <h2>{item.prompt}</h2>
    {item.helpText ? <p className="assessment-question-help">{item.helpText}</p> : null}
    {item.type === 'dropdown' ? <label>Answer<select aria-label="Answer" disabled={readOnly} value={String(value.optionId ?? '')} onChange={(event) => onChange({ optionId: event.target.value })}><option value="">Select an answer</option>{item.options?.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label> : null}
    {item.type === 'multiple-choice' || item.type === 'checkboxes' ? <div className="assessment-learner-options">{item.options?.map((option) => <label key={option.id}><input disabled={readOnly} type={item.type === 'checkboxes' ? 'checkbox' : 'radio'} name={item.id} aria-label={option.label} checked={item.type === 'checkboxes' ? selected.includes(option.id) : value.optionId === option.id} onChange={() => item.type === 'checkboxes' ? onChange({ optionIds: selected.includes(option.id) ? selected.filter((id) => id !== option.id) : [...selected, option.id] }) : onChange({ optionId: option.id })} /><span>{option.label}</span></label>)}{item.allowOther ? <label><input disabled={readOnly} type="checkbox" aria-label="Other" checked={value.other !== undefined} onChange={(event) => onChange({ ...value, other: event.target.checked ? '' : undefined })} /><span>Other</span></label> : null}{item.allowOther && value.other !== undefined ? <input aria-label="Other response" disabled={readOnly} value={String(value.other)} onChange={(event) => onChange({ ...value, other: event.target.value })} /> : null}</div> : null}
    {item.type === 'rating' ? <fieldset className="assessment-learner-rating"><legend>Rating</legend>{Array.from({ length: item.rating?.max ?? 5 }, (_, index) => index + 1).map((rating) => <label key={rating}><input disabled={readOnly} type="radio" name={item.id} aria-label={`Rating ${rating}`} checked={Number(value.value) === rating} onChange={() => onChange({ value: rating })} /><span>{ratingSymbol(item, rating)}</span></label>)}</fieldset> : null}
    {['short-answer', 'paragraph'].includes(item.type) ? <textarea aria-label="Answer" disabled={readOnly} value={String(value.text ?? '')} minLength={item.validation?.minimumLength} maxLength={item.validation?.maximumLength} onChange={(event) => onChange({ text: event.target.value })} /> : null}
    {item.type === 'diagnostic-field' && tileSource ? <div className="assessment-slide-panel" data-active={mobilePanel === 'slide'}><AssessmentDiagnosticField label="Diagnostic slide" tileSource={tileSource} selections={diagnosticSelections} onCommit={(selection) => !readOnly && onChange({ ...value, selection })} onClear={() => !readOnly && onChange({ ...value, selection: undefined })} /></div> : null}
    {item.type === 'diagnostic-field' ? <div className="assessment-answer-panel" data-active={mobilePanel === 'answer'}><label>Diagnosis<input disabled={readOnly} value={String(value.diagnosis ?? '')} onChange={(event) => onChange({ ...value, diagnosis: event.target.value })} /></label></div> : null}
  </section>
}
