import { registrationEngineLabel } from '../registrationEngineLabel'
import type { RegistrationBenchmarkMeasurements, RegistrationStageReceipt } from '../types'

export function ComparisonCandidateReceipt({ recipeIdentity, stages = [], measurements }: { recipeIdentity?: string; stages?: RegistrationStageReceipt[]; measurements?: RegistrationBenchmarkMeasurements }) {
  if (!stages.length && !measurements && !recipeIdentity) return null
  const measured = (value: number | null | undefined, unit: string) => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? `${value.toFixed(2)} ${unit}` : 'Not measured'
  return <details className="comparison-candidate-receipt"><summary>Method and measurements</summary>
    {recipeIdentity ? <p>Recipe: {recipeIdentity}</p> : null}
    {stages.length ? <ol>{stages.map((stage, index) => <li key={`${index}-${stage.engine}`}><strong>{registrationEngineLabel(stage.engine)} · {stage.buildVersion}</strong><span>{stage.status} · {measured(stage.runtimeSeconds, 's')}</span><small>Original reference pixels · settings {stage.settingsDigest}</small></li>)}</ol> : null}
    {measurements ? <dl>
      <div><dt>Qualification</dt><dd>{measurements.qualified === true ? 'Qualified' : measurements.qualified === false ? 'Unqualified' : 'Not evaluated'}</dd></div>
      <div><dt>Median error</dt><dd>{measured(measurements.medianErrorUm, 'µm')}</dd></div>
      <div><dt>95th percentile error</dt><dd>{measured(measurements.p95ErrorUm, 'µm')}</dd></div>
      {typeof measurements.coverage === 'number' && Number.isFinite(measurements.coverage) ? <div><dt>Coverage</dt><dd>{(measurements.coverage * 100).toFixed(1)}%</dd></div> : null}
      {measurements.runtimeSeconds !== undefined ? <div><dt>Total runtime</dt><dd>{measured(measurements.runtimeSeconds, 's')}</dd></div> : null}
      {measurements.peakMemoryBytes !== undefined ? <div><dt>Peak memory</dt><dd>{measured(measurements.peakMemoryBytes / 1024 ** 2, 'MiB')}</dd></div> : null}
    </dl> : null}
  </details>
}
