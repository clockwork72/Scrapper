import { ipcRenderer, contextBridge } from 'electron'

// --------- Expose some API to the Renderer process ---------
contextBridge.exposeInMainWorld('ipcRenderer', {
  on(...args: Parameters<typeof ipcRenderer.on>) {
    const [channel, listener] = args
    return ipcRenderer.on(channel, (event, ...args) => listener(event, ...args))
  },
  off(...args: Parameters<typeof ipcRenderer.off>) {
    const [channel, ...omit] = args
    return ipcRenderer.off(channel, ...omit)
  },
  send(...args: Parameters<typeof ipcRenderer.send>) {
    const [channel, ...omit] = args
    return ipcRenderer.send(channel, ...omit)
  },
  invoke(...args: Parameters<typeof ipcRenderer.invoke>) {
    const [channel, ...omit] = args
    return ipcRenderer.invoke(channel, ...omit)
  },
})

contextBridge.exposeInMainWorld('scraper', {
  startRun: (options: any) => ipcRenderer.invoke('scraper:start', options),
  stopRun: () => ipcRenderer.invoke('scraper:stop'),
  getPaths: (outDir?: string) => ipcRenderer.invoke('scraper:get-paths', outDir),
  readSummary: (path?: string) => ipcRenderer.invoke('scraper:read-summary', path),
  readState: (path?: string) => ipcRenderer.invoke('scraper:read-state', path),
  readExplorer: (path?: string, limit?: number) => ipcRenderer.invoke('scraper:read-explorer', path, limit),
  readArtifactText: (options?: { outDir?: string; relativePath?: string }) =>
    ipcRenderer.invoke('scraper:read-artifact-text', options),
  clearResults: (options?: { includeArtifacts?: boolean; outDir?: string }) =>
    ipcRenderer.invoke('scraper:clear-results', options),
  deleteOutput: (outDir?: string) => ipcRenderer.invoke('scraper:delete-output', outDir),
  getFolderSize: (outDir?: string) => ipcRenderer.invoke('scraper:folder-size', outDir),
  listRuns: (baseOutDir?: string) => ipcRenderer.invoke('scraper:list-runs', baseOutDir),
  openLogWindow: (content: string, title?: string) => ipcRenderer.invoke('scraper:open-log-window', { content, title }),
  openPolicyWindow: (url: string) => ipcRenderer.invoke('scraper:open-policy-window', url),
  onEvent: (callback: (event: any) => void) => ipcRenderer.on('scraper:event', (_evt, data) => callback(data)),
  onLog: (callback: (event: any) => void) => ipcRenderer.on('scraper:log', (_evt, data) => callback(data)),
  onError: (callback: (event: any) => void) => ipcRenderer.on('scraper:error', (_evt, data) => callback(data)),
  onExit: (callback: (event: any) => void) => ipcRenderer.on('scraper:exit', (_evt, data) => callback(data)),
})
