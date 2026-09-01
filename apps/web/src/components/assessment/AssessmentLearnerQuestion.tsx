import { assessmentQuestionMedia, type AssessmentItem, type AssessmentQuestionMedia, type DiagnosticSelection } from '../../assessment/types'
import { AssessmentDiagnosticField } from '../AssessmentDiagnosticField'

interface Props {
  item: AssessmentItem
  value: Record<string, unknown>
  onChange?: (response: Record<string, unknown>) => void
  assets?: Record<string, string>
  mobilePanel?: 'slide' | 'answer'
  readOnly?: boolean
  dropdownPresentation?: 'select' | 'choices'
}

const ratingSymbol = (item: AssessmentItem, value: number) => item.rating?.style === 'stars'
  ? '★'
  : item.rating?.style === 'hearts'
    ? '♥'
    : item.rating?.style === 'thumbs-up' ? '👍' : String(value)

function answerMedia(option: NonNullable<AssessmentItem['options']>[number]) {
  return [...(option.media ? [option.media] : []), ...(option.mediaItems ?? [])].slice(0, 3)
}

function answerMediaSource(media: AssessmentQuestionMedia, assets: Record<string, string>) {
  return media.capturedImage?.assetPath ?? media.assetPath ?? (media.slideId && assets[media.slideId]
    ? assets[media.slideId].replace(/\/slide\.dzi$/, '/thumbnail.jpg')
    : undefined)
}

function LearnerQuestionMedia({ media, assets }: { media: AssessmentQuestionMedia; assets: Record<string, string> }) {
  const source = media.capturedImage?.assetPath ?? (media.kind === 'uploaded-image'
    ? media.assetPath
    : media.slideId && assets[media.slideId]
      ? assets[media.slideId].replace(/\/slide\.dzi$/, '/thumbnail.jpg')
      : media.assetPath)
  if (!source) return null
  const capture = media.capture
  const scale = media.capturedImage ? 1 : capture
    ? Math.min(1 / capture.width, 1 / capture.height)
    : media.viewport?.scale ?? 1
  const origin = media.capturedImage ? '50% 50%' : capture
    ? `${(capture.x + capture.width / 2) * 100}% ${(capture.y + capture.height / 2) * 100}%`
    : `${media.viewport?.x ?? 50}% ${media.viewport?.y ?? 50}%`
  return <figure className="assessment-learner-media"><div><img src={source} alt={media.alt || ''} style={{ transform: `scale(${scale})`, transformOrigin: origin }} />{capture ? media.marks?.map((mark, index) => {
    if (mark.kind === 'point') return <span key={index} className="assessment-learner-media-point" style={{ left: `${((mark.x - capture.x) / capture.width) * 100}%`, top: `${((mark.y - capture.y) / capture.height) * 100}%` }}>{mark.label ? <em>{mark.label}</em> : null}</span>
    if (mark.kind === 'rectangle') return <span key={index} className="assessment-learner-media-rectangle" style={{ left: `${((mark.x - capture.x) / capture.width) * 100}%`, top: `${((mark.y - capture.y) / capture.height) * 100}%`, width: `${(mark.width / capture.width) * 100}%`, height: `${(mark.height / capture.height) * 100}%` }}>{mark.label ? <em>{mark.label}</em> : null}</span>
    const first = mark.points[0]
    return <span key={index} className="assessment-learner-media-freehand"><svg viewBox={`0 0 ${capture.width} ${capture.height}`} preserveAspectRatio="none" aria-hidden="true"><polyline points={mark.points.map((point) => `${point.x - capture.x},${point.y - capture.y}`).join(' ')} /></svg>{mark.label && first ? <em style={{ left: `${((first.x - capture.x) / capture.width) * 100}%`, top: `${((first.y - capture.y) / capture.height) * 100}%` }}>{mark.label}</em> : null}</span>
  }) : null}</div>{media.alt ? <figcaption>{media.alt}</figcaption> : null}</figure>
}

export function AssessmentLearnerQuestion({ item, value, onChange = () => undefined, assets = {}, mobilePanel = 'answer', readOnly = false, dropdownPresentation = 'select' }: Props) {
  const selected = (value.optionIds as string[] | undefined) ?? []
  const tileSource = item.slideId ? assets[item.slideId] : undefined
  const media = assessmentQuestionMedia(item)
  const diagnosticSelections = value.selection ? [value.selection as DiagnosticSelection] : []
  if (item.type === 'section-information' || item.type === 'information') {
    return <section className="assessment-student-question assessment-information-block" aria-label="Description"><p className="assessment-information-copy">{item.prompt}</p>{item.helpText ? <p>{item.helpText}</p> : null}</section>
  }
  return <section className="assessment-student-question" data-question-type={item.type}>
    <h2>{item.prompt}</h2>
    {media.length ? <div className="assessment-learner-media-gallery">{media.map((entry, index) => <LearnerQuestionMedia key={`${entry.kind}-${entry.slideId ?? entry.fileName ?? index}-${index}`} media={entry} assets={assets} />)}</div> : null}
    {item.helpText ? <p className="assessment-question-help">{item.helpText}</p> : null}
    {item.type === 'dropdown' && dropdownPresentation === 'select' ? <><label>Answer<select aria-label="Answer" disabled={readOnly} value={String(value.optionId ?? '')} onChange={(event) => onChange({ optionId: event.target.value })}><option value="">Select an answer</option>{item.options?.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>{item.options?.some((option) => answerMedia(option).some((entry) => answerMediaSource(entry, assets))) ? <div className="assessment-learner-dropdown-media" aria-label="Answer choice media">{item.options.flatMap((option) => answerMedia(option).map((entry, index) => { const source = answerMediaSource(entry, assets); return source ? <figure key={`${option.id}-${index}`}><img src={source} alt={entry.alt || ''} /><figcaption>{option.label}</figcaption></figure> : null }))}</div> : null}</> : null}
    {item.type === 'dropdown' && dropdownPresentation === 'choices' ? <div className="assessment-learner-options assessment-learner-options--dropdown" role="radiogroup" aria-label="Answer">{item.options?.map((option) => { const optionMedia = answerMedia(option); return <label key={option.id}><input disabled={readOnly} type="radio" name={item.id} aria-label={option.label} checked={value.optionId === option.id} onChange={() => onChange({ optionId: option.id })} />{optionMedia.length ? <span className="assessment-learner-option-media-group">{optionMedia.map((entry, index) => { const source = answerMediaSource(entry, assets); return source ? <img key={index} className="assessment-learner-option-media" src={source} alt={entry.alt || ''} /> : null })}</span> : null}<span>{option.label}</span></label>})}</div> : null}
    {item.type === 'multiple-choice' || item.type === 'checkboxes' ? <div className="assessment-learner-options">{item.options?.map((option) => { const optionMedia = answerMedia(option); return <label key={option.id}><input disabled={readOnly} type={item.type === 'checkboxes' ? 'checkbox' : 'radio'} name={item.id} aria-label={option.label} checked={item.type === 'checkboxes' ? selected.includes(option.id) : value.optionId === option.id} onChange={() => item.type === 'checkboxes' ? onChange({ optionIds: selected.includes(option.id) ? selected.filter((id) => id !== option.id) : [...selected, option.id] }) : onChange({ optionId: option.id })} />{optionMedia.length ? <span className="assessment-learner-option-media-group">{optionMedia.map((entry, index) => { const source = answerMediaSource(entry, assets); return source ? <img key={index} className="assessment-learner-option-media" src={source} alt={entry.alt || ''} /> : null })}</span> : null}<span>{option.label}</span></label>})}{item.allowOther ? <label><input disabled={readOnly} type="checkbox" aria-label="Other" checked={value.other !== undefined} onChange={(event) => onChange({ ...value, other: event.target.checked ? '' : undefined })} /><span>Other</span></label> : null}{item.allowOther && value.other !== undefined ? <input aria-label="Other response" disabled={readOnly} value={String(value.other)} onChange={(event) => onChange({ ...value, other: event.target.value })} /> : null}</div> : null}
    {item.type === 'rating' ? <fieldset className="assessment-learner-rating"><legend>Rating</legend>{Array.from({ length: item.rating?.max ?? 5 }, (_, index) => index + 1).map((rating) => <label key={rating}><input disabled={readOnly} type="radio" name={item.id} aria-label={`Rating ${rating}`} checked={Number(value.value) === rating} onChange={() => onChange({ value: rating })} /><span>{ratingSymbol(item, rating)}</span></label>)}</fieldset> : null}
    {['short-answer', 'paragraph'].includes(item.type) ? <label className="assessment-text-response"><span>Answer</span><textarea aria-label="Answer" rows={5} placeholder="Type a short or long response" disabled={readOnly} value={String(value.text ?? '')} minLength={item.validation?.minimumLength} maxLength={item.validation?.maximumLength} onChange={(event) => onChange({ text: event.target.value })} /></label> : null}
    {item.type === 'diagnostic-field' && tileSource ? <div className="assessment-slide-panel" data-active={mobilePanel === 'slide'}><AssessmentDiagnosticField label="Diagnostic slide" tileSource={tileSource} selections={diagnosticSelections} onCommit={(selection) => !readOnly && onChange({ ...value, selection })} onClear={() => !readOnly && onChange({ ...value, selection: undefined })} /></div> : null}
    {item.type === 'diagnostic-field' ? <div className="assessment-answer-panel" data-active={mobilePanel === 'answer'}><label>Diagnosis<input disabled={readOnly} value={String(value.diagnosis ?? '')} onChange={(event) => onChange({ ...value, diagnosis: event.target.value })} /></label></div> : null}
  </section>
}
