const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

let mainWindow;
let pythonProcess;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1000,
        height: 700,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js')
        },
        title: 'Doc to Markdown Converter v2.0'
    });

    // Start Flask backend
    startFlaskBackend();

    // Wait for Flask to start before loading
    setTimeout(() => {
        mainWindow.loadURL('http://localhost:5000');
    }, 2000);

    mainWindow.on('closed', () => {
        mainWindow = null;
        if (pythonProcess) {
            pythonProcess.kill();
        }
    });
}

function startFlaskBackend() {
    // Determine Python path and script path based on whether we're in development or production
    let pythonPath, scriptPath;

    if (app.isPackaged) {
        // Production: Python and scripts are in the resources directory
        pythonPath = process.platform === 'win32' ? 'python.exe' : 'python3';
        const resourcesPath = process.resourcesPath;
        scriptPath = path.join(resourcesPath, 'python', 'web_app.py');
    } else {
        // Development: Use local paths
        pythonPath = process.platform === 'win32' ? 'python' : 'python3';
        scriptPath = path.join(__dirname, '../python/web_app.py');
    }

    pythonProcess = spawn(pythonPath, [scriptPath], {
        cwd: app.isPackaged ? path.join(process.resourcesPath, 'python') : path.join(__dirname, '../python')
    });

    pythonProcess.stdout.on('data', (data) => {
        console.log(`Flask: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`Flask Error: ${data}`);
    });

    pythonProcess.on('close', (code) => {
        console.log(`Flask process exited with code ${code}`);
    });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});

// IPC handlers for native file dialogs
ipcMain.handle('select-file', async () => {
    const { dialog } = require('electron');
    const result = await dialog.showOpenDialog({
        properties: ['openFile'],
        filters: [
            { name: 'All Files', extensions: ['*'] },
            { name: 'PDF', extensions: ['pdf'] },
            { name: 'Word', extensions: ['docx', 'doc'] },
            { name: 'HTML', extensions: ['html', 'htm'] },
            { name: 'Text', extensions: ['txt', 'md', 'csv', 'json', 'xml'] }
        ]
    });
    return result;
});

ipcMain.handle('select-folder', async () => {
    const { dialog } = require('electron');
    const result = await dialog.showOpenDialog({
        properties: ['openDirectory']
    });
    return result;
});

ipcMain.handle('open-file', async (event, filePath) => {
    const { shell } = require('electron');
    try {
        await shell.openPath(filePath);
        return { success: true };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

ipcMain.handle('reveal-file', async (event, filePath) => {
    const { shell } = require('electron');
    try {
        await shell.showItemInFolder(filePath);
        return { success: true };
    } catch (error) {
        return { success: false, error: error.message };
    }
});
