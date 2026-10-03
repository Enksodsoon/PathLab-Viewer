export function registrationEngineLabel(engine: string): string {
  if (engine === 'native-v12') return 'Native canonical · native-v12'
  if (engine === 'native-overview-v6') return 'Native bounded overview · native-overview-v6'
  return engine
}
