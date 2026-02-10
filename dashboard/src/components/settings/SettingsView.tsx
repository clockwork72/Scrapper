import { Theme } from '../../types'

type SettingsViewProps = {
  theme: Theme
  onThemeChange: (theme: Theme) => void
}

export function SettingsView({ theme, onThemeChange }: SettingsViewProps) {
  return (
    <>
      <section className="card rounded-2xl p-6">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">Theme</p>
          <h2 className="text-lg font-semibold">Appearance</h2>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
          <button
            className={`focusable rounded-full border px-4 py-2 text-xs ${
              theme === 'dark'
                ? 'border-[var(--color-danger)] text-white'
                : 'border-[var(--border-soft)] text-[var(--muted-text)]'
            }`}
            onClick={() => onThemeChange('dark')}
          >
            Dark
          </button>
          <button
            className={`focusable rounded-full border px-4 py-2 text-xs ${
              theme === 'vscode-red'
                ? 'border-[var(--color-danger)] text-white'
                : 'border-[var(--border-soft)] text-[var(--muted-text)]'
            }`}
            onClick={() => onThemeChange('vscode-red')}
          >
            Red
          </button>
          <button
            className={`focusable rounded-full border px-4 py-2 text-xs ${
              theme === 'academia'
                ? 'border-[var(--color-danger)] text-white'
                : 'border-[var(--border-soft)] text-[var(--muted-text)]'
            }`}
            onClick={() => onThemeChange('academia')}
          >
            Academia
          </button>
        </div>
      </section>

      <section className="card rounded-2xl p-6">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted-text)]">Preferences</p>
          <h3 className="text-lg font-semibold">Defaults</h3>
        </div>
        <div className="mt-4 space-y-2 text-sm">
          <div className="flex items-center justify-between rounded-xl border border-[var(--border-soft)] bg-black/20 px-4 py-3">
            <span className="text-xs text-[var(--muted-text)]">Prefilter websites</span>
            <span className="text-xs">Enabled</span>
          </div>
          <div className="flex items-center justify-between rounded-xl border border-[var(--border-soft)] bg-black/20 px-4 py-3">
            <span className="text-xs text-[var(--muted-text)]">Engine</span>
            <span className="text-xs">crawl4ai</span>
          </div>
        </div>
      </section>
    </>
  )
}
