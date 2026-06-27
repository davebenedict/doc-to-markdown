const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    selectFile: () => ipcRenderer.invoke('select-file'),
    selectFolder: () => ipcRenderer.invoke('select-folder'),
    openFile: (filePath) => ipcRenderer.invoke('open-file', filePath),
    revealFile: (filePath) => ipcRenderer.invoke('reveal-file', filePath),
    onFlaskReady: (callback) => ipcRenderer.on('flask-ready', callback)
});
