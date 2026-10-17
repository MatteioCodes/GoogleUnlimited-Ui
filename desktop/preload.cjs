const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld(
  "desktop",
  Object.freeze({
    selectFolders: () => ipcRenderer.invoke("folders:select"),
    connectAccount: () => ipcRenderer.invoke("account:connect"),
    setStartup: (enabled) => ipcRenderer.invoke("startup:set", enabled),
    openDataFolder: () => ipcRenderer.invoke("data:open"),
    revealFile: (identifier) => ipcRenderer.invoke("file:reveal", identifier),
    openExternal: (url) => ipcRenderer.invoke("external:open", url),
    importSetup: () => ipcRenderer.invoke("setup:import"),
    getVersion: () => ipcRenderer.invoke("app:version"),
  }),
);
