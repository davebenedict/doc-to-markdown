const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const net = require('net');

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

    mainWindow.on('closed', () => {
        mainWindow = null;
        if (pythonProcess) {
            pythonProcess.kill();
        }
    });

    // Start Flask backend
    // Wait for Flask to start before loading
    startFlaskBackend()
        .then(port => {
            if (mainWindow) {
                mainWindow.loadURL(`http://127.0.0.1:${port}`);
            }
        })
        .catch(error => {
            console.error(`Flask startup failed: ${error.message}`);
            if (mainWindow) {
                dialog.showErrorBox('Backend startup failed', error.message);
            }
        });
}

async function startFlaskBackend() {
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

    const cwd = app.isPackaged ? path.join(process.resourcesPath, 'python') : path.join(__dirname, '../python');
    const port = await getAvailablePort();
    pythonProcess = spawn(pythonPath, [scriptPath], {
        cwd,
        env: { ...process.env, DOC2MD_PORT: String(port) }
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

    await waitForBackend(port, pythonProcess);
    return port;
}

function getAvailablePort() {
    return new Promise((resolve, reject) => {
        const server = net.createServer();
        server.once('error', reject);
        server.listen(0, '127.0.0.1', () => {
            const port = server.address().port;
            server.close(error => error ? reject(error) : resolve(port));
        });
    });
}

function waitForBackend(port, child) {
    return new Promise((resolve, reject) => {
        let attempts = 0;
        let settled = false;
        const fail = error => {
            if (!settled) {
                settled = true;
                reject(error);
            }
        };
        const retry = () => {
            if (settled) return;
            if (attempts >= 100) {
                fail(new Error('Flask backend did not become ready'));
            } else {
                attempts += 1;
                setTimeout(check, 300);
            }
        };
        const check = () => {
            if (settled) return;
            const request = http.get({ hostname: '127.0.0.1', port, path: '/supported-formats' }, response => {
                response.resume();
                if (response.statusCode === 200) {
                    settled = true;
                    resolve();
                } else {
                    retry();
                }
            });
            request.setTimeout(1000, () => request.destroy());
            request.on('error', retry);
        };

        child.once('error', fail);
        child.once('exit', code => fail(new Error(`Flask backend exited with code ${code}`)));
        check();
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
