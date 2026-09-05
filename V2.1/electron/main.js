// ============================================================
// DeepSeek 余额监控 · Electron 主进程（V2.1）
// 职责：窗口、托盘、单实例、余额接口、配置持久化、窗口控制 IPC
// ============================================================
const { app, BrowserWindow, Tray, Menu, ipcMain, nativeImage, screen } = require('electron');
const path = require('path');
const fs = require('fs');
const https = require('https');

const API_URL = 'https://api.deepseek.com/user/balance';
let mainWindow = null;
let tray = null;
let dragState = null;
let config = null;
let pinOn = false;             // 置顶状态权威变量（主进程自己维护，不依赖查询结果）
let lastPinTime = 0;           // 防抖：同一瞬间的重复请求只处理一次
const cfgPath = () => path.join(app.getPath('userData'), 'config.json');

const DEFAULT_CONFIG = { accounts: [], activeId: null, reference: 100, baselines: {}, onTop: false };

function loadConfig() {
  try {
    const raw = fs.readFileSync(cfgPath(), 'utf-8');
    const data = JSON.parse(raw);
    return Object.assign({}, DEFAULT_CONFIG, data);
  } catch (e) {
    return Object.assign({}, DEFAULT_CONFIG);
  }
}
function saveConfig(cfg) {
  config = Object.assign({}, DEFAULT_CONFIG, cfg || {});
  try { fs.mkdirSync(path.dirname(cfgPath()), { recursive: true }); fs.writeFileSync(cfgPath(), JSON.stringify(config, null, 2), 'utf-8'); } catch (e) {}
  return true;
}
function logLine(msg) {
  const line = '[' + new Date().toLocaleString('zh-CN') + '] ' + msg;
  try {
    const logPath = path.join(app.getPath('userData'), 'electron.log');
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    fs.appendFileSync(logPath, line + '\n', 'utf-8');
  } catch (e) {}
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 420,
    height: 404,
    minWidth: 320,
    minHeight: 360,
    frame: false,
    thickFrame: true,      // 无边框但保留系统边缘缩放（原生、跟手、无追赶）
    resizable: true,
    show: false,           // 就绪后再显示，避免空白闪烁
    backgroundColor: '#0d1226',
    icon: path.join(__dirname, 'app_icon.ico'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: false,
      nodeIntegration: false,
      sandbox: false
    }
  });

  mainWindow.loadFile(path.join(__dirname, 'ui', 'balance-widget.html'), { hash: 'app' });
  mainWindow.once('ready-to-show', () => {
    try { mainWindow.show(); mainWindow.focus(); mainWindow.moveTop(); } catch (e) {}
  });
  // 页面加载完成后把当前置顶状态推给界面，保证按钮显示与真实状态一致
  mainWindow.webContents.on('did-finish-load', () => {
    try { mainWindow.webContents.send('pin-state', pinOn); } catch (e) {}
  });

  // 渲染进程崩溃/被杀时自动重载，尽量避免“未响应”后无动作
  mainWindow.webContents.on('render-process-gone', (e, details) => {
    logLine('render-process-gone: ' + (details && details.reason));
    setTimeout(() => { try { mainWindow.reload(); } catch (err) {} }, 800);
  });
  mainWindow.webContents.on('unresponsive', () => {
    logLine('webContents unresponsive, reloading');
    try { mainWindow.reload(); } catch (e) {}
  });

  mainWindow.on('closed', () => { mainWindow = null; });

  // 恢复上次置顶状态（明确层级 floating）
  pinOn = !!(config && config.onTop);
  if (pinOn) mainWindow.setAlwaysOnTop(true, 'screen-saver');
}

function setupTray() {
  try {
    const img = nativeImage.createFromPath(path.join(__dirname, 'app_icon.ico'));
    tray = new Tray(img);
    tray.setToolTip('DeepSeek 余额监控');
    tray.setContextMenu(Menu.buildFromTemplate([
      { label: '显示主界面', click: () => { if (mainWindow) { mainWindow.show(); mainWindow.focus(); } } },
      { label: '隐藏到托盘', click: () => { if (mainWindow) mainWindow.hide(); } },
      { type: 'separator' },
      { label: '退出', click: () => app.quit() }
    ]));
    // 单击托盘图标 = 唤起窗口（不再做“再点一次隐藏”，避免误以为窗口丢失）
    tray.on('click', () => { if (mainWindow) { mainWindow.show(); mainWindow.focus(); } });
  } catch (e) {
    logLine('tray error: ' + e);
  }
}

function setupIPC() {
  ipcMain.handle('cfg:get', () => config);
  ipcMain.handle('cfg:save', (e, cfg) => saveConfig(cfg));

  ipcMain.handle('balance:get', (e, key) => new Promise((resolve, reject) => {
    const req = https.request(API_URL, {
      method: 'GET',
      headers: { Accept: 'application/json', Authorization: 'Bearer ' + String(key || '').trim() },
      timeout: 15000
    }, (res) => {
      let body = '';
      res.on('data', (c) => { body += c; });
      res.on('end', () => {
        try {
          if (res.statusCode !== 200) return reject(new Error('HTTP ' + res.statusCode));
          const data = JSON.parse(body);
          const infos = data && data.balance_infos;
          if (!Array.isArray(infos) || !infos.length) return reject(new Error('接口响应格式异常'));
          const info = infos.find((b) => b.currency === 'CNY') || infos[0];
          const amount = parseFloat(info.total_balance);
          if (isNaN(amount)) return reject(new Error('余额字段缺失'));
          resolve({ amount: amount, currency: info.currency });
        } catch (err) { reject(err); }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(new Error('网络请求超时')); });
    req.end();
  }));

  // 置顶：用 Windows 最高的置顶层级 screen-saver，确保钉在真正的最上层；
  // 置顶后再强制 moveTop 一次，避免被其他置顶/全屏程序压住。
  function applyPin(on) {
    pinOn = !!on;
    if (!mainWindow) return pinOn;
    try {
      if (pinOn) {
        mainWindow.setAlwaysOnTop(true, 'screen-saver');
        mainWindow.moveTop();
        setTimeout(() => { try { if (mainWindow && pinOn) mainWindow.moveTop(); } catch (e3) {} }, 80);
      } else {
        mainWindow.setAlwaysOnTop(false);
      }
      logLine('pin -> ' + pinOn + ' (level=' + (pinOn ? 'screen-saver' : 'off') + ')');
      try { mainWindow.webContents.send('pin-state', pinOn); } catch (e2) {}
      if (config) { config.onTop = pinOn; saveConfig(config); }
    } catch (e) { logLine('pin error: ' + e); }
    return pinOn;
  }
  ipcMain.handle('win:top', () => {
    const now = Date.now();
    if (now - lastPinTime < 300) return pinOn;   // 防抖：300ms 内重复请求忽略
    lastPinTime = now;
    return applyPin(!pinOn);
  });
  ipcMain.handle('win:pin', () => {
    const now = Date.now();
    if (now - lastPinTime < 300) return pinOn;
    lastPinTime = now;
    return applyPin(!pinOn);
  });
  ipcMain.handle('win:minimize', () => { logLine('win:minimize (hide to tray)'); if (mainWindow) mainWindow.hide(); return true; });
  ipcMain.handle('win:exit', () => { logLine('win:exit'); app.quit(); });
  ipcMain.handle('win:geometry', () => {
    if (!mainWindow) return null;
    const b = mainWindow.getBounds();
    return { x: b.x, y: b.y, width: b.width, height: b.height };
  });
  ipcMain.handle('win:move', (e, x, y) => {
    if (!mainWindow) return false;
    const b = mainWindow.getBounds();
    mainWindow.setBounds({ x: Math.round(x), y: Math.round(y), width: b.width, height: b.height });
    return true;
  });
  ipcMain.handle('win:resize', (e, w, h) => {
    if (!mainWindow) return false;
    const b = mainWindow.getBounds();
    mainWindow.setBounds({ x: b.x, y: b.y, width: Math.max(320, Math.round(w)), height: Math.max(360, Math.round(h)) });
    return true;
  });
  // —— 原生级拖拽循环：按下即开始，主进程按屏幕坐标逐帧改窗口，松手结束 ——
  ipcMain.handle('win:drag-start', (e, mode) => {
    if (!mainWindow || dragState) return false;
    try {
      const b = mainWindow.getBounds();
      const c = screen.getCursorScreenPoint();
      dragState = { mode: String(mode || 'move'), b: b, c: c };
      dragState.timer = setInterval(() => {
        const s = dragState;
        if (!s || !mainWindow) return;
        const cur = screen.getCursorScreenPoint();
        const dx = cur.x - s.c.x, dy = cur.y - s.c.y;
        let x = s.b.x, y = s.b.y, w = s.b.width, h = s.b.height;
        if (s.mode === 'move') {
          x = s.b.x + dx; y = s.b.y + dy;
        } else {
          if (s.mode.indexOf('e') >= 0) w = Math.max(320, s.b.width + dx);
          if (s.mode.indexOf('s') >= 0) h = Math.max(360, s.b.height + dy);
          if (s.mode.indexOf('w') >= 0) { w = Math.max(320, s.b.width - dx); x = s.b.x + (s.b.width - w); }
          if (s.mode.indexOf('n') >= 0) { h = Math.max(360, s.b.height - dy); y = s.b.y + (s.b.height - h); }
        }
        mainWindow.setBounds({ x: Math.round(x), y: Math.round(y), width: Math.round(w), height: Math.round(h) });
      }, 15);
      return true;
    } catch (err) {
      return false;
    }
  });
  ipcMain.handle('win:drag-end', () => {
    if (dragState) { clearInterval(dragState.timer); dragState = null; }
    return true;
  });

  ipcMain.handle('app:log', (e, msg) => logLine('renderer: ' + msg));
  ipcMain.handle('app:ready', () => { logLine('renderer ready'); return true; });
}

// 单实例：重复打开时唤出已有窗口
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) { try { mainWindow.show(); mainWindow.focus(); mainWindow.moveTop(); } catch (e) {} }
  });

  app.whenReady().then(() => {
    config = loadConfig();
    setupIPC();
    createWindow();
    setupTray();
    app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
  });

  app.on('window-all-closed', () => { app.quit(); });
}