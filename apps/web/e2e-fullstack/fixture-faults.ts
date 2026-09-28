import { execFileSync } from 'node:child_process'
import path from 'node:path'

export function fault(kind: 'quota-full' | 'quota-clear' | 'expire-session' | 'expire-share' | 'expire-assessment-cooldown', subject?: string) {
  execFileSync(process.env.PATHLAB_E2E_PYTHON!,
    [path.resolve('../../scripts/frontend_qa_fault.py'), kind, ...(subject ? [subject] : [])],
    { stdio: 'pipe' })
}
