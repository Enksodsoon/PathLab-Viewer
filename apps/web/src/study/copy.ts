import type { StudyAction, StudyReason } from './types'

export type StudyLocale = 'en' | 'th'

const reasonCopy: Record<StudyLocale, Record<StudyReason, string>> = {
  en: {
    CONTINUE_PRACTICE: 'Continue while this material is fresh.',
    HINT_SUPPORT: 'A faculty-written hint may help with this step.',
    CHECK_CONFIDENCE: 'Pause to compare confidence with the feedback.',
    VERIFY_SOURCE: 'Open the faculty source and verify the explanation.',
    REVIEW_PREVIOUS: 'Retrieve the previous concept once more.',
    TAKE_BREAK: 'A short pause may reduce effort before continuing.',
    MODEL_SUGGESTION: 'The local model selected this optional study step.',
  },
  th: {
    CONTINUE_PRACTICE: 'เรียนต่อขณะที่เนื้อหายังสดใหม่',
    HINT_SUPPORT: 'คำใบ้ที่อาจารย์เขียนอาจช่วยในขั้นตอนนี้',
    CHECK_CONFIDENCE: 'หยุดสักครู่เพื่อเปรียบเทียบความมั่นใจกับผลตอบกลับ',
    VERIFY_SOURCE: 'เปิดแหล่งข้อมูลของอาจารย์เพื่อตรวจสอบคำอธิบาย',
    REVIEW_PREVIOUS: 'ทบทวนแนวคิดก่อนหน้านี้อีกครั้ง',
    TAKE_BREAK: 'พักสั้น ๆ ก่อนเรียนต่อ',
    MODEL_SUGGESTION: 'โมเดลภายในอุปกรณ์เลือกขั้นตอนเสริมนี้',
  },
}

const actionCopy: Record<StudyLocale, Record<StudyAction, string>> = {
  en: {
    continue: 'Continue practice', offer_hint: 'Open a hint', ask_confidence: 'Check confidence',
    ask_source_check: 'Verify the source', retrieve: 'Review the previous task', pause: 'Take a short break',
  },
  th: {
    continue: 'เรียนต่อ', offer_hint: 'เปิดคำใบ้', ask_confidence: 'ตรวจสอบความมั่นใจ',
    ask_source_check: 'ตรวจสอบแหล่งข้อมูล', retrieve: 'ทบทวนคำถามก่อนหน้า', pause: 'พักสั้น ๆ',
  },
}

export function studyReasonCopy(locale: StudyLocale, reason: StudyReason): string {
  return reasonCopy[locale][reason]
}

export function studyActionCopy(locale: StudyLocale, action: StudyAction): string {
  return actionCopy[locale][action]
}
