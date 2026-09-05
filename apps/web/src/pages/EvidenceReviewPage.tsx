import { ArrowLeft, CheckCircle, ShieldCheck } from '@phosphor-icons/react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Brand } from '../components/Brand'
import { Loader } from '../components/Loader'
import {
  approveEvidence, getEvidenceForReview, listEvidenceForReview,
  type EvidenceReviewSummary,
} from '../study/api'
import { ThemeControl } from '../theme/ThemeControl'
import './EvidenceReviewPage.css'

type Detail = Awaited<ReturnType<typeof getEvidenceForReview>>

export function EvidenceReviewPage() {
  const [items, setItems] = useState<EvidenceReviewSummary[]>([])
  const [detail, setDetail] = useState<Detail | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    setBusy(true); setError('')
    try { setItems(await listEvidenceForReview()) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Evidence is unavailable.') }
    finally { setBusy(false) }
  }, [])
  useEffect(() => { void refresh() }, [refresh])

  const open = async (id: string) => {
    setBusy(true); setError('')
    try { setDetail(await getEvidenceForReview(id)) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Evidence detail is unavailable.') }
    finally { setBusy(false) }
  }
  const approve = async () => {
    if (!detail) return
    setBusy(true); setError('')
    try { await approveEvidence(detail.id, detail.manifestSha256); await refresh(); setDetail(await getEvidenceForReview(detail.id)) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Review could not be recorded.') }
    finally { setBusy(false) }
  }

  const manifest = detail?.manifest
  return <main className="evidence-review">
    <header><Brand product="Evidence review" /><nav><Link to="/admin/study"><ArrowLeft /> Study Coach</Link><ThemeControl /></nav></header>
    <section className="evidence-review-heading"><div><span>Faculty gate</span><h1>Review signed pathology evidence</h1><p>Approval binds this exact slide revision, pack, signer, qualification checksum, regions, QC, masks, and descriptive outputs.</p></div></section>
    {error ? <p role="alert" className="evidence-review-error">{error}</p> : null}
    {busy && !items.length ? <Loader label="Loading evidence…" /> : <div className="evidence-review-layout">
      <aside aria-label="Evidence bundles">{items.map((item) => <button type="button" key={item.id} className={detail?.id === item.id ? 'selected' : ''} onClick={() => void open(item.id)}>
        <strong>{item.packId} · {item.packVersion}</strong><span>{item.status} · {item.validationStatus}</span><code>{item.manifestSha256.slice(0, 16)}…</code>{item.reviewedAt ? <small><CheckCircle /> Reviewed</small> : <small>Awaiting review</small>}
      </button>)}</aside>
      <section className="evidence-review-detail" aria-live="polite">{detail && manifest ? <>
        <div className="evidence-review-status"><ShieldCheck /><div><strong>Research-only, non-diagnostic</strong><span>Checksum-bound faculty review is required before Study Pack use.</span></div></div>
        <dl>
          <div><dt>Slide</dt><dd>{String((manifest.source as Record<string, unknown> | undefined)?.slideSha256 ?? detail.slideId)}</dd></div>
          <div><dt>Revision</dt><dd>{String((manifest.source as Record<string, unknown> | undefined)?.revision ?? 'Unavailable')}</dd></div>
          <div><dt>Manifest</dt><dd>{detail.manifestSha256}</dd></div>
          <div><dt>Signer</dt><dd>{String((manifest.signature as Record<string, unknown> | undefined)?.keyId ?? 'Unavailable')}</dd></div>
          <div><dt>Qualification</dt><dd>{String(manifest.qualificationAttestationSha256 ?? (manifest.pack as Record<string, unknown> | undefined)?.validationStatus ?? 'Legacy evidence')}</dd></div>
        </dl>
        <EvidenceSection title="Pack and provenance" value={{ pack: manifest.pack, provenance: manifest.provenance }} />
        <EvidenceSection title="Quality control and uncertainty" value={manifest.qc} />
        <EvidenceSection title="Regions and bounded overlays" value={manifest.regions ?? manifest.evidence} />
        <EvidenceSection title="Cell instances and aggregates" value={{ cellInstances: manifest.cellInstances, cellAggregates: manifest.cellAggregates }} />
        <EvidenceSection title="IHC and stain descriptors" value={{ ihc: manifest.ihcDescriptors, specialStains: manifest.specialStainDescriptors, cytology: manifest.cytologyDescriptors }} />
        <button type="button" className="evidence-review-approve" disabled={busy || Boolean(detail.reviewedAt)} onClick={() => void approve()}><CheckCircle /> {detail.reviewedAt ? 'Exact manifest reviewed' : 'Approve exact manifest checksum'}</button>
      </> : <p>Select an evidence bundle to inspect every signed field before approval.</p>}</section>
    </div>}
  </main>
}

function EvidenceSection({ title, value }: { title: string; value: unknown }) {
  return <details><summary>{title}</summary><pre>{JSON.stringify(value ?? null, null, 2)}</pre></details>
}
