import { Atom, Barbell, Bone, Books, Brain, Calculator, CirclesThreePlus, Dna, Drop, Ear, Eye, FirstAid, ForkKnife, GenderIntersex, HandPalm, Heartbeat, Microscope, PersonSimple, Pill, Plant, ShieldCheck, Stethoscope, TestTube, Tooth, Virus, Wind } from '@phosphor-icons/react'

export const COURSE_ICON_OPTIONS = [
  { key: 'general', label: 'General', Icon: Books },
  { key: 'integumentary', label: 'Integumentary system', Icon: HandPalm },
  { key: 'bone', label: 'Skeletal system', Icon: Bone },
  { key: 'muscular', label: 'Muscular system', Icon: Barbell },
  { key: 'neuroscience', label: 'Nervous system', Icon: Brain },
  { key: 'endocrine', label: 'Endocrine system', Icon: CirclesThreePlus },
  { key: 'cardiology', label: 'Cardiovascular system', Icon: Heartbeat },
  { key: 'immune', label: 'Lymphatic and immune system', Icon: ShieldCheck },
  { key: 'respiratory', label: 'Respiratory system', Icon: Wind },
  { key: 'digestive', label: 'Digestive system', Icon: ForkKnife },
  { key: 'urinary', label: 'Urinary system', Icon: Drop },
  { key: 'reproductive', label: 'Reproductive system', Icon: GenderIntersex },
  { key: 'anatomy', label: 'General anatomy', Icon: PersonSimple },
  { key: 'vision', label: 'Eye and vision', Icon: Eye },
  { key: 'hearing', label: 'Ear and hearing', Icon: Ear },
  { key: 'dental', label: 'Dental', Icon: Tooth },
  { key: 'microscope', label: 'Microscopy', Icon: Microscope },
  { key: 'laboratory', label: 'Laboratory', Icon: TestTube },
  { key: 'medicine', label: 'Medicine', Icon: Stethoscope },
  { key: 'pharmacology', label: 'Pharmacology', Icon: Pill },
  { key: 'first_aid', label: 'First aid', Icon: FirstAid },
  { key: 'genetics', label: 'Genetics and DNA', Icon: Dna },
  { key: 'microbiology', label: 'Microbiology', Icon: Virus },
  { key: 'science', label: 'Science', Icon: Atom },
  { key: 'botany', label: 'Plants and botany', Icon: Plant },
  { key: 'mathematics', label: 'Mathematics', Icon: Calculator },
] as const

export type CourseIconKey = typeof COURSE_ICON_OPTIONS[number]['key']

export function getCourseIconOption(iconKey: CourseIconKey) {
  return COURSE_ICON_OPTIONS.find((item) => item.key === iconKey) ?? COURSE_ICON_OPTIONS[0]
}
