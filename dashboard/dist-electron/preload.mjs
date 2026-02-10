"use strict";
const electron = require("electron");
electron.contextBridge.exposeInMainWorld("ipcRenderer", {
  on(...args) {
    const [channel, listener] = args;
    return electron.ipcRenderer.on(channel, (event, ...args2) => listener(event, ...args2));
  },
  off(...args) {
    const [channel, ...omit] = args;
    return electron.ipcRenderer.off(channel, ...omit);
  },
  send(...args) {
    const [channel, ...omit] = args;
    return electron.ipcRenderer.send(channel, ...omit);
  },
  invoke(...args) {
    const [channel, ...omit] = args;
    return electron.ipcRenderer.invoke(channel, ...omit);
  }
});
electron.contextBridge.exposeInMainWorld("scraper", {
  startRun: (options) => electron.ipcRenderer.invoke("scraper:start", options),
  stopRun: () => electron.ipcRenderer.invoke("scraper:stop"),
  getPaths: (outDir) => electron.ipcRenderer.invoke("scraper:get-paths", outDir),
  readSummary: (path) => electron.ipcRenderer.invoke("scraper:read-summary", path),
  readState: (path) => electron.ipcRenderer.invoke("scraper:read-state", path),
  readExplorer: (path, limit) => electron.ipcRenderer.invoke("scraper:read-explorer", path, limit),
  clearResults: (options) => electron.ipcRenderer.invoke("scraper:clear-results", options),
  deleteOutput: (outDir) => electron.ipcRenderer.invoke("scraper:delete-output", outDir),
  getFolderSize: (outDir) => electron.ipcRenderer.invoke("scraper:folder-size", outDir),
  listRuns: (baseOutDir) => electron.ipcRenderer.invoke("scraper:list-runs", baseOutDir),
  openPolicyWindow: (url) => electron.ipcRenderer.invoke("scraper:open-policy-window", url),
  onEvent: (callback) => electron.ipcRenderer.on("scraper:event", (_evt, data) => callback(data)),
  onLog: (callback) => electron.ipcRenderer.on("scraper:log", (_evt, data) => callback(data)),
  onError: (callback) => electron.ipcRenderer.on("scraper:error", (_evt, data) => callback(data)),
  onExit: (callback) => electron.ipcRenderer.on("scraper:exit", (_evt, data) => callback(data))
});
