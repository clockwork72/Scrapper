import { baseResults } from '../../data/results'
import { ResultsMetrics } from '../../utils/results'

type ResultsViewProps = {
  hasRun: boolean
  progress: number
  topN: string
  metrics: ResultsMetrics
  summary?: any
  useCrux?: boolean
  postCruxCount?: number | null
}

export function ResultsView({
  hasRun,
  progress,
  topN,
  metrics,
  summary,
  useCrux,
  postCruxCount,
}: ResultsViewProps) {
  if (!hasRun) {
    return (
      <section className="card rounded-2xl p-6">
        <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">No results</p>
        <h2 className="text-lg font-semibold">There are no results yet</h2>
        <p className="mt-2 text-sm text-[var(--muted-text)]">
          Start a crawl from the Launcher tab to generate results.
        </p>
      </section>
    )
  }

  const statusCounts = summary?.status_counts || {}
  const statusOk = statusCounts.ok ?? metrics.statusOk
  const statusPolicyNotFound = statusCounts.policy_not_found ?? metrics.statusPolicyNotFound
  const statusNonBrowsable = statusCounts.non_browsable ?? metrics.statusNonBrowsable
  const statusHomeFailed = statusCounts.home_fetch_failed ?? metrics.statusHomeFailed
  const statusTotal = Math.max(1, statusOk + statusPolicyNotFound + statusNonBrowsable + statusHomeFailed)

  const thirdParty = summary?.third_party || {}
  const thirdPartyDetected =
    thirdParty.total ?? Math.max(0, metrics.radarMapped + metrics.radarUnmapped)
  const radarMapped = thirdParty.mapped ?? metrics.radarMapped
  const radarUnmapped = thirdParty.unmapped ?? metrics.radarUnmapped
  const radarNoPolicy = thirdParty.no_policy_url ?? metrics.radarNoPolicy
  const thirdPartyPoliciesFound = Math.max(0, thirdPartyDetected - radarNoPolicy)

  const mappedRatio = Math.round((radarMapped / Math.max(1, thirdPartyDetected)) * 100)
  const unmappedRatio = Math.round((radarUnmapped / Math.max(1, thirdPartyDetected)) * 100)
  const summaryCategories = summary?.categories || baseResults.categories
  const summaryEntities = summary?.entities || baseResults.entities
  const categoryMax = summaryCategories.reduce((max: number, cat: any) => Math.max(max, cat.count || 0), 1)
  const entityMax = summaryEntities.reduce((max: number, entity: any) => {
    const prev = entity.prevalence_max ?? entity.prevalence_avg ?? entity.prevalence ?? 0
    return Math.max(max, prev)
  }, 0.0001)
  const postCruxSites =
    typeof postCruxCount === 'number' ? postCruxCount : typeof summary?.total_sites === 'number' ? summary.total_sites : null
  const overviewStats = [
    { label: 'Sites processed', value: summary?.processed_sites ?? metrics.totalSitesProcessed },
    ...(useCrux ? [{ label: 'Post‑CrUX sites', value: postCruxSites }] : []),
    { label: 'Success rate', value: `${summary?.success_rate ?? metrics.successRate}%` },
    { label: '3P services detected', value: thirdPartyDetected },
    { label: '3P policies found', value: thirdPartyPoliciesFound },
    { label: 'Mapped in Tracker Radar', value: radarMapped },
  ]

  return (
    <>
      <section className="card rounded-2xl p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">Overview</p>
            <h2 className="text-lg font-semibold">Scrape summary</h2>
            <p className="text-xs text-[var(--muted-text)]">
              {progress < 100 ? `Partial results • ${progress.toFixed(0)}% complete` : 'Final results • 100% complete'}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="theme-chip rounded-full px-3 py-1 text-xs">Tranco Top {topN}</span>
            {useCrux && <span className="theme-chip rounded-full px-3 py-1 text-xs">CrUX filter on</span>}
          </div>
        </div>
        <div
          className={`mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 ${
            useCrux ? 'xl:grid-cols-6' : 'xl:grid-cols-5'
          }`}
        >
          {overviewStats.map((stat) => (
            <div key={stat.label} className="rounded-xl border border-[var(--border-soft)] bg-black/20 px-4 py-3">
              <p className="text-xs text-[var(--muted-text)]">{stat.label}</p>
              <p className="text-lg font-semibold">
                {stat.value === null || stat.value === undefined
                  ? '—'
                  : typeof stat.value === 'number'
                    ? stat.value.toLocaleString()
                    : stat.value}
              </p>
            </div>
          ))}
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-4 text-xs text-[var(--muted-text)]">
          <span className="theme-chip rounded-full px-3 py-1">ok {statusOk.toLocaleString()}</span>
          <span className="theme-chip rounded-full px-3 py-1">
            policy not found {statusPolicyNotFound.toLocaleString()}
          </span>
          <span className="theme-chip rounded-full px-3 py-1">
            non-browsable {statusNonBrowsable.toLocaleString()}
          </span>
          <span className="theme-chip rounded-full px-3 py-1">
            home failed {statusHomeFailed.toLocaleString()}
          </span>
        </div>
        <div className="mt-5">
          <div className="flex h-2 w-full overflow-hidden rounded-full bg-black/30">
            <div
              className="h-full bg-[var(--color-success)]"
              style={{ width: `${(statusOk / statusTotal) * 100}%` }}
            />
            <div
              className="h-full bg-[var(--color-warn)]"
              style={{ width: `${(statusPolicyNotFound / statusTotal) * 100}%` }}
            />
            <div
              className="h-full bg-[var(--color-danger)]"
              style={{ width: `${(statusNonBrowsable / statusTotal) * 100}%` }}
            />
            <div
              className="h-full bg-[var(--border-soft)]"
              style={{ width: `${(statusHomeFailed / statusTotal) * 100}%` }}
            />
          </div>
        </div>
      </section>

      <section className="card rounded-2xl p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">Coverage</p>
            <h3 className="text-lg font-semibold">Tracker Radar mapping</h3>
          </div>
          <span className="text-xs text-[var(--muted-text)]">
            mapped {metrics.mappedRatio}% • unmapped {metrics.unmappedRatio}%
          </span>
        </div>
        <div className="mt-4 grid gap-6 lg:grid-cols-[220px_1fr]">
          <div className="flex flex-col items-center justify-center gap-3">
            <div
              className="flex h-44 w-44 items-center justify-center rounded-full"
              style={{
                background: `conic-gradient(var(--color-primary) ${metrics.mappedRatio}%, var(--color-warn) ${
                  metrics.mappedRatio
                }% ${metrics.mappedRatio + metrics.unmappedRatio}%, var(--border-soft) ${
                  metrics.mappedRatio + metrics.unmappedRatio
                }% 100%)`,
              }}
            >
              <div className="flex h-28 w-28 flex-col items-center justify-center rounded-full bg-[var(--color-surface)] text-center">
                <span className="text-2xl font-semibold">{mappedRatio}%</span>
                <span className="text-xs text-[var(--muted-text)]">mapped</span>
              </div>
            </div>
            <div className="text-xs text-[var(--muted-text)]">
              {radarMapped.toLocaleString()} mapped • {radarUnmapped.toLocaleString()} unmapped •{' '}
              {radarNoPolicy.toLocaleString()} no policy URL
            </div>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">Categories</p>
            <div className="mt-3 space-y-3 text-xs">
              {summaryCategories.map((cat: any) => {
                const count = cat.count ?? 0
                return (
                  <div key={cat.name} className="flex items-center gap-4">
                    <span className="w-36 text-[var(--muted-text)]">{cat.name}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-black/30">
                      <div
                        className="h-full rounded-full bg-[var(--color-primary)]"
                        style={{
                          width: `${Math.min(100, (count / Math.max(1, categoryMax)) * 100)}%`,
                        }}
                      />
                    </div>
                    <span className="text-[var(--muted-text)]">{count.toLocaleString()}</span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </section>

      <section className="card rounded-2xl p-6">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">Entities</p>
          <h3 className="text-lg font-semibold">Entity prevalence distribution</h3>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {summaryEntities.map((entity: any) => {
            const prevalence =
              entity.prevalence_max ?? entity.prevalence_avg ?? entity.prevalence ?? entity.prevalence_avg ?? 0
            const countLabel = entity.count ? `${entity.count} occurrences` : '—'
            return (
              <div key={entity.name} className="rounded-xl border border-[var(--border-soft)] bg-black/20 px-4 py-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-semibold">{entity.name}</span>
                  <span className="text-xs text-[var(--muted-text)]">{(prevalence * 100).toFixed(2)}%</span>
                </div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-black/30">
                  <div
                    className="h-full rounded-full bg-[var(--color-primary)]"
                    style={{
                      width: `${Math.min(100, (prevalence / Math.max(0.0001, entityMax)) * 100)}%`,
                    }}
                  />
                </div>
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--muted-text)]">
                  <span>{entity.categories ? entity.categories.join(' • ') : '—'}</span>
                  <span>{entity.domains ? `${entity.domains} domains` : countLabel}</span>
                </div>
              </div>
            )
          })}
        </div>
      </section>
    </>
  )
}
