import { useEffect, useMemo, useRef } from 'react'

const logLines = [
 ''
]

type LauncherViewProps = {
  steps: string[]
  currentSite?: string
  topN: string
  onTopNChange: (value: string) => void
  onStart: () => void
  onStop?: () => void
  hasRun: boolean
  running: boolean
  progress: number
  stepIndex: number
  resultsReady: boolean
  onViewResults: () => void
  logs?: string[]
  errorMessage?: string
  etaText?: string
  useCrux?: boolean
  onToggleCrux?: (next: boolean) => void
  cruxApiKey?: string
  onCruxKeyChange?: (value: string) => void
  excludeSameEntity?: boolean
  onToggleExcludeSameEntity?: (next: boolean) => void
  postCruxCount?: number | null
}

export function LauncherView({
  topN,
  onTopNChange,
  onStart,
  onStop,
  hasRun,
  running,
  progress,
  stepIndex,
  resultsReady,
  onViewResults,
  logs,
  errorMessage,
  etaText,
  useCrux,
  onToggleCrux,
  cruxApiKey,
  onCruxKeyChange,
  excludeSameEntity,
  onToggleExcludeSameEntity,
  postCruxCount,
  steps,
  currentSite,
}: LauncherViewProps) {
  const logRef = useRef<HTMLDivElement | null>(null)
  const visibleLogs = useMemo(() => {
    if (logs && logs.length > 0) return logs.slice(-120)
    if (!hasRun) return []
    if (progress >= 100) return logLines
    return logLines.slice(0, Math.min(logLines.length, stepIndex + 2))
  }, [hasRun, progress, stepIndex, logs])

  useEffect(() => {
    if (!logRef.current) return
    logRef.current.scrollTop = logRef.current.scrollHeight
  }, [visibleLogs])

  return (
    <>
      <section className="card rounded-2xl p-6">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">Launch</p>
              <h2 className="text-lg font-semibold">Tranco Top-N</h2>
              <p className="text-xs text-[var(--muted-text)]">
                Choose how many sites to crawl. Press <span className="kbd">Enter</span> to start.
              </p>
            </div>
            <button
              className="focusable rounded-full bg-[var(--color-primary)] px-4 py-2 text-xs font-semibold text-white"
              onClick={onStart}
            >
              Start run
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--muted-text)]">
            <button
              className={`focusable rounded-full border px-4 py-2 text-xs ${
                running ? 'border-[var(--color-danger)] text-white' : 'border-[var(--border-soft)] text-[var(--muted-text)]'
              }`}
              onClick={onStop}
              disabled={!running}
            >
              Stop run
            </button>
            {running && <span>Stopping will keep partial results.</span>}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <input
              type="number"
              min={1}
              value={topN}
              onChange={(event) => onTopNChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') onStart()
              }}
              className="focusable w-40 rounded-xl border border-[var(--border-soft)] bg-black/20 px-4 py-2 text-sm text-white"
              placeholder="1000"
            />
            <span className="text-xs text-[var(--muted-text)]">sites from Tranco list</span>
            <button
              className={`focusable rounded-full border px-3 py-1 text-xs ${
                useCrux ? 'border-[var(--color-danger)] text-white' : 'border-[var(--border-soft)] text-[var(--muted-text)]'
              }`}
              onClick={() => onToggleCrux?.(!useCrux)}
            >
              CrUX {useCrux ? 'on' : 'off'}
            </button>
            <button
              className={`focusable rounded-full border px-3 py-1 text-xs ${
                excludeSameEntity
                  ? 'border-[var(--color-danger)] text-white'
                  : 'border-[var(--border-soft)] text-[var(--muted-text)]'
              }`}
              onClick={() => onToggleExcludeSameEntity?.(!excludeSameEntity)}
            >
              Exclude same-entity {excludeSameEntity ? 'on' : 'off'}
            </button>
            {useCrux && (
              <span className="text-xs text-[var(--muted-text)]">
                Post‑CrUX sites: {postCruxCount ?? '—'}
              </span>
            )}
            {useCrux && (
              <input
                type="password"
                className="focusable w-64 rounded-xl border border-[var(--border-soft)] bg-black/20 px-4 py-2 text-sm text-white"
                placeholder="CrUX API key"
                value={cruxApiKey || ''}
                onChange={(event) => onCruxKeyChange?.(event.target.value)}
              />
            )}
          </div>
        </div>
      </section>

      <section
        className={`overflow-hidden transition-all duration-700 ${
          hasRun ? 'max-h-[520px] opacity-100' : 'max-h-0 opacity-0'
        }`}
      >
        <div className="card rounded-2xl p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">Progress</p>
              <h3 className="text-lg font-semibold">Active crawl</h3>
              <p className="text-xs text-[var(--muted-text)]">
                {currentSite ? `Current site: ${currentSite}` : 'Waiting for site...'}
              </p>
              <p className="text-xs text-[var(--muted-text)]">
                Step: {steps[Math.min(Math.max(stepIndex, 0), steps.length - 1)]}
              </p>
            </div>
            <div className="text-xs text-[var(--muted-text)]">
              {running ? 'Running' : progress >= 100 ? 'Completed' : 'Ready'}
            </div>
          </div>

          <div className="mt-4">
            <div className="h-2 w-full overflow-hidden rounded-full bg-black/30">
              <div
                className="h-full rounded-full bg-[var(--color-primary)] transition-all duration-700"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="mt-2 flex flex-wrap justify-between gap-2 text-xs text-[var(--muted-text)]">
              <span>{progress.toFixed(0)}% complete</span>
              <span>{etaText ? `ETA ${etaText}` : 'ETA --'}</span>
              <span>{topN} sites</span>
            </div>
          </div>

          <div className="mt-6 flex flex-col gap-4">
            <div className="flex items-center gap-3">
              {steps.map((label, index) => (
                <div key={label} className="flex flex-1 items-center gap-3">
                  <div
                    className={`flex h-8 w-8 items-center justify-center rounded-full border text-xs font-semibold ${
                      index <= stepIndex
                        ? 'border-[var(--color-primary)] text-white'
                        : 'border-[var(--border-soft)] text-[var(--muted-text)]'
                    }`}
                    style={{
                      background:
                        index <= stepIndex
                          ? 'color-mix(in srgb, var(--color-primary) 25%, transparent)'
                          : 'transparent',
                    }}
                  >
                    {index + 1}
                  </div>
                  {index < steps.length - 1 && (
                    <div
                      className={`h-1 flex-1 rounded-full ${
                        index < stepIndex ? 'bg-[var(--color-primary)]' : 'bg-black/30'
                      }`}
                    />
                  )}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-4 gap-3 text-xs text-[var(--muted-text)]">
              {steps.map((label, index) => (
                <span
                  key={label}
                  className={index === stepIndex ? 'text-[var(--color-text)]' : 'text-[var(--muted-text)]'}
                >
                  {label}
                </span>
              ))}
            </div>
            <div className="flex justify-end">
              <button
                className={`focusable rounded-full border px-4 py-2 text-xs ${
                  resultsReady
                    ? 'border-[var(--color-danger)] text-white'
                    : 'border-[var(--border-soft)] text-[var(--muted-text)]'
                }`}
                onClick={onViewResults}
                disabled={!resultsReady}
              >
                View results
              </button>
            </div>
          </div>
        </div>
      </section>

      <section
        className={`overflow-hidden transition-all duration-700 ${
          hasRun ? 'max-h-[420px] opacity-100' : 'max-h-0 opacity-0'
        }`}
      >
        <div className="card rounded-2xl p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">Logs</p>
              <h3 className="text-lg font-semibold">Run details</h3>
            </div>
            <span className="text-xs text-[var(--muted-text)]">tail -f</span>
          </div>
          <div className="mt-4 space-y-2 text-xs">
            {errorMessage && (
              <div className="rounded-lg border border-[var(--color-danger)] bg-black/20 px-3 py-2 text-[var(--color-danger)]">
                {errorMessage}
              </div>
            )}
            <div
              ref={logRef}
              className="mono max-h-[420px] overflow-y-auto rounded-xl border border-[var(--border-soft)] bg-black/30 p-3 text-[11px] leading-relaxed text-[var(--muted-text)]"
            >
              {visibleLogs.length === 0 && <div>Launch a run to see logs.</div>}
              {visibleLogs.map((line, index) => (
                <div key={`${line}-${index}`} className="flex gap-2">
                  <span className="text-[var(--muted-text)]">{String(index + 1).padStart(2, '0')}</span>
                  <span className="text-[var(--color-text)]">{line}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
