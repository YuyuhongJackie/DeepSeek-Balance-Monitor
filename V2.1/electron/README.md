# Electron 工程（V2.1）—— 可运行状态

## 当前状态（2026-09-05）

- 已内置免安装 Node.js（`.nodejs` 同级目录），已安装 Electron 33.4。
- 主进程、预加载桥接、托盘、单实例、余额接口、配置读写均已实现并通过冒烟测试
  （渲染器就绪、桥接可用、配置读写正常）。
- 界面直接复用旧版 `balance-widget.html`（放入 `ui/`），功能延续：
  余额圆环、差额统计、多账号、置顶钉子、窗口边缘缩放与拖动移动。

## 运行

双击 `start.bat`，或命令行执行：

```bash
cd V2.1/electron
..\.nodejs\node-v22.23.2-win-x64\npm start     # 或直接 node_modules/.bin/electron .
```

> 本目录的 `.nodejs` 位于 `V2.1/` 下（不在本目录内）。
> 若把本仓库克隆到别处：先下载 Node 放到 `V2.1/.nodejs`（或系统安装 Node 后直接 `npm start`）。

## 数据与日志

- 配置：`%APPDATA%\DeepSeek余额监控\config.json`
- 日志：`%APPDATA%\DeepSeek余额监控\electron.log`

## 后续

- 打包免安装版/安装包：接入 electron-builder。
- 可选打磨：真正透明的圆角悬浮窗、开机自启、桌面通知。