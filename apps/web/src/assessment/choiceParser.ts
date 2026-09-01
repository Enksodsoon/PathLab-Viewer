const PREFIX = /^\s*(?:(?:[-*•‣▪◦])|(?:\(?\d{1,3}\)?[.)\-:])|(?:\(?[a-zA-Z]\)?[.)\-:]))\s+/

export function parseAssessmentChoices(input: string, limit = 10): string[] {
  const normalized = input.replace(/\r\n?/g, '\n').trim()
  if (!normalized) return []
  let parts = normalized.split('\n')
  if (parts.length === 1) {
    const separator = /[\t;|]/.test(normalized) ? /\s*(?:\t+|;|\|)\s*/ : /\s*,\s*/
    parts = normalized.split(separator)
  }
  const seen = new Set<string>()
  const choices: string[] = []
  for (const part of parts) {
    const label = part.replace(PREFIX, '').trim().replace(/^['"]|['"]$/g, '').trim()
    const key = label.toLocaleLowerCase()
    if (!label || seen.has(key)) continue
    seen.add(key)
    choices.push(label.slice(0, 1000))
    if (choices.length === limit) break
  }
  return choices
}
