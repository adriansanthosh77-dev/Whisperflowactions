const { app, BrowserWindow, screen, ipcMain } = require('electron');
const path = require('path');

let win;

function createWindow() {
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width, height } = primaryDisplay.workAreaSize;

  win = new BrowserWindow({
    width: 300,
    height: 300,
    x: width - 340,
    y: height - 360,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    visibleOnAllWorkspaces: true,
    focusable: false,
    resizable: false,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    }
  });

  win.loadFile('index.html');

  win.setAlwaysOnTop(true, 'screen-saver');
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.setIgnoreMouseEvents(true, { forward: true });

  ipcMain.on('hud-resize', (event, mode) => {
    if (mode === 'fullscreen') {
      win.setBounds({ width, height, x: 0, y: 0 });
      win.setIgnoreMouseEvents(true, { forward: true });
    } else {
      win.setBounds({ width: 300, height: 300, x: width - 340, y: height - 360 });
      win.setIgnoreMouseEvents(true, { forward: true });
    }
  });

  // Hide on Escape (keeps process running for wake)
  ipcMain.on('hud-hide', () => {
    win.hide();
  });

  // Show on wake (from overlay)
  ipcMain.on('hud-show', () => {
    if (win.isMinimized()) win.restore();
    win.show();
    win.focus();
    win.setIgnoreMouseEvents(true, { forward: true });
  });

  win.on('closed', () => {
    app.quit();
  });
}

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
