// ============================================================
// 预加载脚本：把 IPC 包装成 window.pywebview.api
// 让复用的界面代码（原本面向 pywebview）无需改动即可工作
// ============================================================
const { ipcRenderer } = require('electron');

const api = {
  get_config: () => ipcRenderer.invoke('cfg:get'),
  save_config: (cfg) => ipcRenderer.invoke('cfg:save', cfg),
  get_balance: (key) => ipcRenderer.invoke('balance:get', key),
  toggle_top: () => ipcRenderer.invoke('win:top'),
  pin: () => ipcRenderer.invoke('win:pin'),
  onPin: (cb) => { ipcRenderer.on('pin-state', (e, v) => { try { cb(!!v); } catch (err) {} }); },
  minimize: () => ipcRenderer.invoke('win:minimize'),
  exit: () => ipcRenderer.invoke('win:exit'),
  get_window_geometry: () => ipcRenderer.invoke('win:geometry'),
  move_window: (x, y) => ipcRenderer.invoke('win:move', x, y),
  resize_window: (w, h) => ipcRenderer.invoke('win:resize', w, h),
  resize: (w, h) => ipcRenderer.invoke('win:resize', w, h),
  drag_start: (mode) => ipcRenderer.invoke('win:drag-start', mode),
  drag_end: () => ipcRenderer.invoke('win:drag-end'),
  log: (msg) => ipcRenderer.invoke('app:log', msg),
  ready: () => ipcRenderer.invoke('app:ready')
};

window.pywebview = { api: api };