const { app, BrowserWindow, screen } = require('electron');

// Watch for parent Python process to exit (passed via --parent-pid arg)
const parentPid = parseInt(process.argv.find(a => a.startsWith('--parent-pid='))?.split('=')[1] || '0', 10);
if (parentPid > 0) {
  const pollInterval = setInterval(() => {
    try {
      // process.kill(pid, 0) checks if the process exists without killing it
      process.kill(parentPid, 0);
    } catch {
      // Parent process no longer exists — close the HUD
      clearInterval(pollInterval);
      app.quit();
    }
  }, 2000);
}

app.whenReady().then(() => {
  const { width, height } = screen.getPrimaryDisplay().size;
  const win = new BrowserWindow({
    width, height, x: 0, y: 0,
    transparent: true, frame: false, alwaysOnTop: true,
    skipTaskbar: true, focusable: false, resizable: false,
    webPreferences: { nodeIntegration: true, contextIsolation: false }
  });
  win.loadFile('index.html');
  win.setAlwaysOnTop(true, 'screen-saver');
  win.setIgnoreMouseEvents(true, { forward: true });
  win.on('closed', () => app.quit());
});
