const path = require('path');
const { spawnSync } = require('child_process');

const pythonCommand = process.platform === 'win32' ? 'py' : 'python3';
const pythonArgs = process.platform === 'win32' ? ['-3'] : [];
const backendDir = path.resolve(__dirname, '../python');
const result = spawnSync(pythonCommand, [...pythonArgs, '-m', 'PyInstaller', '--noconfirm', 'backend.spec'], {
    cwd: backendDir,
    stdio: 'inherit'
});

if (result.error) {
    console.error(`Could not run PyInstaller: ${result.error.message}`);
    process.exitCode = 1;
} else {
    process.exitCode = result.status ?? 1;
}
