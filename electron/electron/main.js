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
        icon: path.join(__dirname, process.platform === 'win32' ? 'app-icon.ico' : 'app-icon.png'),
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
                dialog.showErrorBox('Backend startup failed', backendStartupMessage(error));
            }
        });
}

async function startFlaskBackend() {
    // Select the bundled backend for packaged builds or Python for development.
    let backendCommand, backendArgs, cwd;

    if (app.isPackaged) {
        // Production: the bundled backend is in the resources directory
        cwd = path.join(process.resourcesPath, 'backend');
        backendCommand = path.join(cwd, process.platform === 'win32' ? 'doc2md-backend.exe' : 'doc2md-backend');
        backendArgs = [];
    } else {
        // Development: Use local paths
        const scriptPath = path.join(__dirname, '../python/web_app.py');
        backendCommand = process.platform === 'win32' ? 'py' : 'python3';
        backendArgs = process.platform === 'win32' ? ['-3', scriptPath] : [scriptPath];
        cwd = path.join(__dirname, '../python');
    }

    const port = await getAvailablePort();
    pythonProcess = spawn(backendCommand, backendArgs, {
        cwd,
        env: { ...process.env, DOC2MD_PORT: String(port) },
        windowsHide: process.platform === 'win32'
    });

    let backendStderr = '';
    pythonProcess.stdout.on('data', (data) => {
        console.log(`Flask: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        const text = data.toString();
        backendStderr = `${backendStderr}${text}`.slice(-4000);
        console.error(`Flask Error: ${text}`);
    });

    pythonProcess.on('close', (code) => {
        console.log(`Flask process exited with code ${code}`);
    });

    await waitForBackend(port, pythonProcess, () => backendStderr);
    return port;
}

function backendStartupMessage(error) {
    const message = error.message || String(error);
    const missingModule = message.match(/No module named ['\"]([^'\"]+)['\"]/);
    const details = message.split(/\r?\n/).filter(Boolean).pop();
    if (app.isPackaged) {
        if (missingModule) {
            return `The bundled backend is missing '${missingModule[1]}'. The installed bundle is incomplete; install a corrected release.`;
        }
        return `The bundled conversion backend could not start. Reinstall the app or download a corrected build. Details: ${details || 'No additional details were reported.'}`;
    }
    if (error.code === 'ENOENT' || /spawn (?:py|python3?)(?:\.exe)? ENOENT/i.test(message)) {
        return 'Python 3 was not found. Install Python 3.9 or later and ensure py/python3 is on PATH.';
    }
    if (missingModule) {
        const pipCommand = process.platform === 'win32' ? 'py -3' : 'python3';
        return `The development backend is missing '${missingModule[1]}'. Install dependencies with ${pipCommand} -m pip install -r electron/python/requirements.txt, then restart.`;
    }
    return `The development backend could not start. Check Python and electron/python/requirements.txt. Details: ${details || 'No additional details were reported.'}`;
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

function waitForBackend(port, child, getErrorOutput) {
    return new Promise((resolve, reject) => {
        let attempts = 0;
        let settled = false;
        const fail = error => {
            if (!settled) {
                settled = true;
                const output = getErrorOutput().trim();
                if (output) {
                    error.message = `${error.message}\n${output}`;
                }
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
