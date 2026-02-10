import { app, BrowserWindow, ipcMain } from 'electron'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import fs from 'node:fs'
import { spawn, ChildProcessWithoutNullStreams } from 'node:child_process'

const require = createRequire(import.meta.url)
const __dirname = path.dirname(fileURLToPath(import.meta.url))

// The built directory structure
//
// ├─┬─┬ dist
// │ │ └── index.html
// │ │
// │ ├─┬ dist-electron
// │ │ ├── main.js
// │ │ └── preload.mjs
// │
process.env.APP_ROOT = path.join(__dirname, '..')

// 🚧 Use ['ENV_NAME'] avoid vite:define plugin - Vite@2.x
export const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL']
export const MAIN_DIST = path.join(process.env.APP_ROOT, 'dist-electron')
export const RENDERER_DIST = path.join(process.env.APP_ROOT, 'dist')

process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL ? path.join(process.env.APP_ROOT, 'public') : RENDERER_DIST
const REPO_ROOT = path.resolve(process.env.APP_ROOT, '..')

let win: BrowserWindow | null
let scraperProcess: ChildProcessWithoutNullStreams | null = null
const policyWindows = new Set<BrowserWindow>()

type ScraperStartOptions = {
  topN?: number
  trancoDate?: string
  trackerRadarIndex?: string
  outDir?: string
  artifactsDir?: string
  runId?: string
  cruxFilter?: boolean
  cruxApiKey?: string
  skipHomeFailed?: boolean
  excludeSameEntity?: boolean
}

function sendToRenderer(channel: string, payload: unknown) {
  if (win && !win.isDestroyed()) {
    win.webContents.send(channel, payload)
  }
}

function defaultPaths(outDir?: string) {
  const root = outDir ? path.resolve(REPO_ROOT, outDir) : path.join(REPO_ROOT, 'outputs')
  return {
    outDir: root,
    resultsJsonl: path.join(root, 'results.jsonl'),
    summaryJson: path.join(root, 'results.summary.json'),
    stateJson: path.join(root, 'run_state.json'),
    explorerJsonl: path.join(root, 'explorer.jsonl'),
    artifactsDir: path.join(root, 'artifacts'),
  }
}

function parseJsonl(content: string, limit?: number) {
  const lines = content.split(/\r?\n/)
  const out: any[] = []
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) continue
    try {
      out.push(JSON.parse(trimmed))
      if (limit && out.length >= limit) break
    } catch (err) {
      out.push({ _error: 'invalid_json', raw: trimmed })
    }
  }
  return out
}

async function getDirectorySize(dirPath: string): Promise<number> {
  let total = 0
  const entries = await fs.promises.readdir(dirPath, { withFileTypes: true })
  for (const entry of entries) {
    const fullPath = path.join(dirPath, entry.name)
    if (entry.isDirectory()) {
      total += await getDirectorySize(fullPath)
    } else if (entry.isFile()) {
      try {
        const stat = await fs.promises.stat(fullPath)
        total += stat.size
      } catch {
        continue
      }
    }
  }
  return total
}

function createWindow() {
  win = new BrowserWindow({
    icon: path.join(process.env.VITE_PUBLIC, 'electron-vite.svg'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.mjs'),
    },
  })

  // Test active push message to Renderer-process.
  win.webContents.on('did-finish-load', () => {
    win?.webContents.send('main-process-message', (new Date).toLocaleString())
  })

  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL)
  } else {
    // win.loadFile('dist/index.html')
    win.loadFile(path.join(RENDERER_DIST, 'index.html'))
  }
}

function createPolicyWindow(url: string) {
  const policyWin = new BrowserWindow({
    width: 1200,
    height: 800,
    title: 'Policy Viewer',
    backgroundColor: '#0B0E14',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  policyWin.setMenuBarVisibility(false)
  policyWin.loadURL(url)
  policyWindows.add(policyWin)
  policyWin.on('closed', () => {
    policyWindows.delete(policyWin)
  })
  return policyWin
}

ipcMain.handle('scraper:get-paths', (_event, outDir?: string) => {
  return defaultPaths(outDir)
})

ipcMain.handle('scraper:read-summary', async (_event, filePath?: string) => {
  try {
    const target = filePath ? path.resolve(REPO_ROOT, filePath) : defaultPaths().summaryJson
    if (!fs.existsSync(target)) {
      return { ok: false, error: 'not_found', path: target }
    }
    const raw = await fs.promises.readFile(target, 'utf-8')
    return { ok: true, data: JSON.parse(raw), path: target }
  } catch (error) {
    return { ok: false, error: String(error) }
  }
})

ipcMain.handle('scraper:read-state', async (_event, filePath?: string) => {
  try {
    const target = filePath ? path.resolve(REPO_ROOT, filePath) : defaultPaths().stateJson
    if (!fs.existsSync(target)) {
      return { ok: false, error: 'not_found', path: target }
    }
    const raw = await fs.promises.readFile(target, 'utf-8')
    return { ok: true, data: JSON.parse(raw), path: target }
  } catch (error) {
    return { ok: false, error: String(error) }
  }
})

ipcMain.handle('scraper:read-explorer', async (_event, filePath?: string, limit?: number) => {
  try {
    const target = filePath ? path.resolve(REPO_ROOT, filePath) : defaultPaths().explorerJsonl
    if (!fs.existsSync(target)) {
      return { ok: false, error: 'not_found', path: target }
    }
    const raw = await fs.promises.readFile(target, 'utf-8')
    const data = target.endsWith('.jsonl') ? parseJsonl(raw, limit) : JSON.parse(raw)
    return { ok: true, data, path: target }
  } catch (error) {
    return { ok: false, error: String(error) }
  }
})

ipcMain.handle('scraper:folder-size', async (_event, outDir?: string) => {
  try {
    const target = outDir ? path.resolve(REPO_ROOT, outDir) : defaultPaths().outDir
    if (!fs.existsSync(target)) {
      return { ok: false, error: 'not_found', path: target }
    }
    const size = await getDirectorySize(target)
    return { ok: true, bytes: size, path: target }
  } catch (error) {
    return { ok: false, error: String(error) }
  }
})

ipcMain.handle('scraper:list-runs', async (_event, baseOutDir?: string) => {
  try {
    const root = baseOutDir ? path.resolve(REPO_ROOT, baseOutDir) : defaultPaths().outDir
    if (!fs.existsSync(root)) {
      return { ok: false, error: 'not_found', path: root }
    }
    const entries = await fs.promises.readdir(root, { withFileTypes: true })
    const runs: any[] = []
    for (const entry of entries) {
      if (!entry.isDirectory()) continue
      const dir = path.join(root, entry.name)
      const summaryPath = path.join(dir, 'results.summary.json')
      const statePath = path.join(dir, 'run_state.json')
      let summary: any = null
      let state: any = null
      if (fs.existsSync(summaryPath)) {
        try {
          summary = JSON.parse(await fs.promises.readFile(summaryPath, 'utf-8'))
        } catch {
          summary = null
        }
      }
      if (fs.existsSync(statePath)) {
        try {
          state = JSON.parse(await fs.promises.readFile(statePath, 'utf-8'))
        } catch {
          state = null
        }
      }
      if (!summary && !state && !entry.name.startsWith('output_')) {
        continue
      }
      let mtime = ''
      try {
        const stat = await fs.promises.stat(dir)
        mtime = stat.mtime.toISOString()
      } catch {
        mtime = ''
      }
      const runId = summary?.run_id || state?.run_id || entry.name.replace(/^output_/, '')
      runs.push({
        runId,
        folder: entry.name,
        outDir: path.relative(REPO_ROOT, dir),
        summary,
        state,
        updated_at: summary?.updated_at || state?.updated_at || mtime,
        started_at: summary?.started_at || state?.started_at || null,
      })
    }
    runs.sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')))
    return { ok: true, root, runs }
  } catch (error) {
    return { ok: false, error: String(error) }
  }
})

ipcMain.handle('scraper:start', async (_event, options: ScraperStartOptions = {}) => {
  if (scraperProcess) {
    return { ok: false, error: 'scraper_already_running' }
  }

  const paths = defaultPaths(options.outDir)
  const pythonCmd = process.env.PRIVACY_DATASET_PYTHON || 'python'
  const args: string[] = [
    '-m',
    'privacy_research_dataset.cli',
    '--out',
    paths.resultsJsonl,
    '--artifacts-dir',
    options.artifactsDir ? path.resolve(REPO_ROOT, options.artifactsDir) : paths.artifactsDir,
    '--emit-events',
    '--state-file',
    paths.stateJson,
    '--summary-out',
    paths.summaryJson,
    '--explorer-out',
    paths.explorerJsonl,
  ]

  if (options.topN) {
    args.push('--tranco-top', String(options.topN))
  }
  if (options.trancoDate) {
    args.push('--tranco-date', options.trancoDate)
  }
  if (options.trackerRadarIndex) {
    const trackerPath = path.resolve(REPO_ROOT, options.trackerRadarIndex)
    if (fs.existsSync(trackerPath)) {
      args.push('--tracker-radar-index', trackerPath)
    } else {
      sendToRenderer('scraper:error', { message: 'tracker_radar_index_not_found', path: trackerPath })
    }
  }
  if (options.runId) {
    args.push('--run-id', options.runId)
  }
  if (options.cruxFilter) {
    args.push('--crux-filter')
    if (options.cruxApiKey) {
      args.push('--crux-api-key', options.cruxApiKey)
    }
  }
  if (options.skipHomeFailed) {
    args.push('--skip-home-fetch-failed')
  }
  if (options.excludeSameEntity) {
    args.push('--exclude-same-entity')
  }

  try {
    scraperProcess = spawn(pythonCmd, args, {
      cwd: REPO_ROOT,
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
    })
  } catch (error) {
    scraperProcess = null
    return { ok: false, error: String(error) }
  }

  let stdoutBuffer = ''
  scraperProcess.stdout.on('data', (chunk) => {
    stdoutBuffer += chunk.toString()
    const lines = stdoutBuffer.split(/\r?\n/)
    stdoutBuffer = lines.pop() || ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue
      try {
        const evt = JSON.parse(trimmed)
        sendToRenderer('scraper:event', evt)
      } catch (error) {
        sendToRenderer('scraper:log', { message: trimmed })
      }
    }
  })

  scraperProcess.stderr.on('data', (chunk) => {
    sendToRenderer('scraper:error', { message: chunk.toString() })
  })

  scraperProcess.on('error', (error) => {
    sendToRenderer('scraper:error', { message: String(error) })
  })

  scraperProcess.on('close', (code, signal) => {
    sendToRenderer('scraper:exit', { code, signal })
    scraperProcess = null
  })

  return { ok: true, paths }
})

ipcMain.handle('scraper:stop', async () => {
  if (!scraperProcess) return { ok: false, error: 'not_running' }
  scraperProcess.kill()
  return { ok: true }
})

ipcMain.handle('scraper:open-policy-window', async (_event, url?: string) => {
  if (!url || typeof url !== 'string') {
    return { ok: false, error: 'invalid_url' }
  }
  try {
    const parsed = new URL(url)
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      return { ok: false, error: 'unsupported_protocol' }
    }
    createPolicyWindow(url)
    return { ok: true }
  } catch (error) {
    return { ok: false, error: String(error) }
  }
})

ipcMain.handle('scraper:clear-results', async (_event, options?: { includeArtifacts?: boolean; outDir?: string }) => {
  if (scraperProcess) {
    return { ok: false, error: 'scraper_running' }
  }

  const paths = defaultPaths(options?.outDir)
  const targets = [paths.resultsJsonl, paths.summaryJson, paths.stateJson, paths.explorerJsonl]
  const removed: string[] = []
  const missing: string[] = []
  const errors: string[] = []

  for (const target of targets) {
    try {
      if (fs.existsSync(target)) {
        await fs.promises.rm(target, { force: true })
        removed.push(target)
      } else {
        missing.push(target)
      }
    } catch (error) {
      errors.push(`${target}: ${String(error)}`)
    }
  }

  if (options?.includeArtifacts) {
    try {
      if (fs.existsSync(paths.artifactsDir)) {
        await fs.promises.rm(paths.artifactsDir, { recursive: true, force: true })
        removed.push(paths.artifactsDir)
      }
    } catch (error) {
      errors.push(`${paths.artifactsDir}: ${String(error)}`)
    }
  }

  return { ok: errors.length === 0, removed, missing, errors, paths }
})

ipcMain.handle('scraper:delete-output', async (_event, outDir?: string) => {
  try {
    const target = outDir ? path.resolve(REPO_ROOT, outDir) : defaultPaths().outDir
    if (!fs.existsSync(target)) {
      return { ok: false, error: 'not_found', path: target }
    }
    await fs.promises.rm(target, { recursive: true, force: true })
    return { ok: true, path: target }
  } catch (error) {
    return { ok: false, error: String(error) }
  }
})

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
    win = null
  }
})

app.on('activate', () => {
  // On OS X it's common to re-create a window in the app when the
  // dock icon is clicked and there are no other windows open.
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})

app.whenReady().then(createWindow)
