import { useEffect, useMemo, useState } from 'react'

export type ReasoningSelection = {
  firstPartySite: string
  thirdPartyName: string
  firstPartyText: string
  thirdPartyText: string
  firstPartyExtractionMethod?: string | null
  thirdPartyExtractionMethod?: string | null
}

type Stage0Side = {
  after_text: string
  raw_chars: number
  clean_chars: number
  section_count: number
  clause_count: number
  sections: Array<{
    section_id: string
    title: string
    level: number
    section_path: string
    start_offset: number
    end_offset: number
  }>
}

type Stage0Preview = {
  first_party: Stage0Side
  third_party: Stage0Side
}

type ReasoningViewProps = {
  selection: ReasoningSelection | null
  onGoToConsistency: () => void
}

function formatExtractionMethod(value?: string | null) {
  if (!value) return 'Unknown'
  return value === 'trafilatura' ? 'Trafilatura' : 'Fallback'
}

function countWords(text: string) {
  const trimmed = text.trim()
  if (!trimmed) return 0
  return trimmed.split(/\s+/).length
}

function formatDelta(raw: number, cleaned: number) {
  const delta = raw - cleaned
  if (delta === 0) return 'No change'
  if (delta > 0) return `-${delta.toLocaleString()} chars`
  return `+${Math.abs(delta).toLocaleString()} chars`
}

function PolicyBeforeAfter({
  title,
  beforeText,
  after,
}: {
  title: string
  beforeText: string
  after: Stage0Side
}) {
  const beforeWords = useMemo(() => countWords(beforeText), [beforeText])
  const afterWords = useMemo(() => countWords(after.after_text), [after.after_text])
  return (
    <div className="rounded-2xl border border-[var(--border-soft)] bg-black/20 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">{title}</h3>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--muted-text)]">
          <span className="theme-chip rounded-full px-2 py-1">Chars: {after.raw_chars.toLocaleString()} → {after.clean_chars.toLocaleString()}</span>
          <span className="theme-chip rounded-full px-2 py-1">{formatDelta(after.raw_chars, after.clean_chars)}</span>
          <span className="theme-chip rounded-full px-2 py-1">Words: {beforeWords.toLocaleString()} → {afterWords.toLocaleString()}</span>
          <span className="theme-chip rounded-full px-2 py-1">Sections: {after.section_count.toLocaleString()}</span>
          <span className="theme-chip rounded-full px-2 py-1">Clauses: {after.clause_count.toLocaleString()}</span>
        </div>
      </div>

      <div className="mt-3 grid gap-4 xl:grid-cols-2">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">Before Stage 0</p>
          <pre className="mono mt-2 max-h-[320px] overflow-auto rounded-xl border border-[var(--border-soft)] bg-black/30 p-3 text-[11px] leading-relaxed whitespace-pre-wrap">
            {beforeText || 'No source text.'}
          </pre>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">After Stage 0</p>
          <pre className="mono mt-2 max-h-[320px] overflow-auto rounded-xl border border-[var(--border-soft)] bg-black/30 p-3 text-[11px] leading-relaxed whitespace-pre-wrap">
            {after.after_text || 'No cleaned text.'}
          </pre>
        </div>
      </div>

      <div className="mt-3">
        <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">Section Preview</p>
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          {after.sections.length === 0 && (
            <div className="rounded-lg border border-[var(--border-soft)] bg-black/30 px-3 py-2 text-xs text-[var(--muted-text)]">
              No sections detected.
            </div>
          )}
          {after.sections.map((section) => (
            <div key={section.section_id} className="rounded-lg border border-[var(--border-soft)] bg-black/30 px-3 py-2 text-xs">
              <div className="font-semibold">{section.title || 'Untitled section'}</div>
              <div className="text-[var(--muted-text)]">{section.section_path}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export function ReasoningView({ selection, onGoToConsistency }: ReasoningViewProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stage0Result, setStage0Result] = useState<Stage0Preview | null>(null)

  useEffect(() => {
    setError(null)
    setStage0Result(null)
  }, [selection?.firstPartySite, selection?.thirdPartyName])

  const runStage0 = async () => {
    if (!selection || !window.scraper?.runConsistencyStage0Preview) return
    setLoading(true)
    setError(null)
    const result = await window.scraper.runConsistencyStage0Preview({
      firstPartyText: selection.firstPartyText,
      thirdPartyText: selection.thirdPartyText,
    })
    if (!result.ok || !result.data) {
      setError(result.error || 'Stage 0 preview failed')
      setLoading(false)
      return
    }
    setStage0Result(result.data)
    setLoading(false)
  }

  if (!selection) {
    return (
      <section className="card rounded-2xl p-6">
        <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">Reasoning</p>
        <h2 className="text-lg font-semibold">No selected policy pair</h2>
        <p className="mt-2 text-sm text-[var(--muted-text)]">
          Open the Consistency checker, select a first-party and third-party policy, then send them to Reasoning.
        </p>
        <button className="focusable mt-4 rounded-xl border border-[var(--border-soft)] px-4 py-2 text-sm" onClick={onGoToConsistency}>
          Go to Consistency checker
        </button>
      </section>
    )
  }

  return (
    <>
      <section className="card rounded-2xl p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">Advanced consistency</p>
            <h2 className="text-lg font-semibold">Reasoning workflow</h2>
            <p className="text-xs text-[var(--muted-text)]">
              Current pair: <span className="text-[var(--color-text)]">{selection.firstPartySite}</span> vs{' '}
              <span className="text-[var(--color-text)]">{selection.thirdPartyName}</span>
            </p>
            <p className="mt-1 text-xs text-[var(--muted-text)]">
              Extraction methods: 1P {formatExtractionMethod(selection.firstPartyExtractionMethod)} • 3P{' '}
              {formatExtractionMethod(selection.thirdPartyExtractionMethod)}
            </p>
          </div>
          <button className="focusable rounded-xl border border-[var(--border-soft)] px-4 py-2 text-sm" onClick={onGoToConsistency}>
            Change selected policies
          </button>
        </div>
      </section>

      <section className="card rounded-2xl p-6">
        <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">Step by step</p>
        <div className="mt-3 rounded-2xl border border-[var(--border-soft)] bg-black/20 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">Stage 0: Ingest + Segment</h3>
              <p className="text-xs text-[var(--muted-text)]">
                Clean policy text, detect sections, and derive clause-level structure with provenance offsets.
              </p>
            </div>
            <button
              className="focusable rounded-xl border border-[var(--color-danger)] px-4 py-2 text-sm"
              disabled={loading}
              onClick={runStage0}
            >
              {loading ? 'Running…' : stage0Result ? 'Re-run Stage 0 preview' : 'Run Stage 0 preview'}
            </button>
          </div>
          {error && <div className="mt-3 rounded-xl border border-[var(--color-warn)] bg-black/20 px-3 py-2 text-xs text-[var(--color-warn)]">{error}</div>}
        </div>
      </section>

      {stage0Result && (
        <section className="card rounded-2xl p-6">
          <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">Stage 0 output</p>
          <div className="mt-3 grid gap-4">
            <PolicyBeforeAfter
              title={`First-party policy (${selection.firstPartySite})`}
              beforeText={selection.firstPartyText}
              after={stage0Result.first_party}
            />
            <PolicyBeforeAfter
              title={`Third-party policy (${selection.thirdPartyName})`}
              beforeText={selection.thirdPartyText}
              after={stage0Result.third_party}
            />
          </div>
        </section>
      )}
    </>
  )
}
