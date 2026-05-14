const { app, BrowserWindow, screen } = require('electron');

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
