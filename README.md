# DeepSeek 余额监控（桌面小组件）

一个运行在 Windows 桌面的小工具：显示你的 **DeepSeek API 账户余额**，
余额低于设定值时圆环变红预警；支持多个账号（多个 API Key）一键切换；
每次刷新会显示“相比上次刷新消耗/增加了多少钱”。

## 下载 / 直接使用

**只想用，不想编译**：去 [Releases](https://github.com/YuyuhongJackie/DeepSeek-Balance-Monitor/releases) 下载 `DeepSeekBalanceMonitor-2.2.0-portable.exe`，双击即用，免安装。

**想看源码**：往下读。仓库里只有源码和文档——可执行文件、依赖目录和打包产物都不入库，原因写在 `.gitignore` 的注释里。

## 给第一次接触项目的人

- **DeepSeek**：一家 AI 服务商。用户充值后调用它的接口会扣余额。
- **API Key**：相当于账号的钥匙，程序用它在余额查询接口上获取余额，只存在使用者自己电脑的配置里。
- **满格金额**：由用户设定“多少钱算 100%”，圆环百分比 = 当前余额 ÷ 满格金额。
- **系统托盘**：Windows 右下角时钟旁边的一排小图标区域，程序可以常驻在那里。
- **免安装（便携版）**：一个 exe 双击即用，无需安装。

## 仓库结构 / 版本地图

| 目录 | 技术方案 | 状态 | 一句话 |
|---|---|---|---|
| `V1/` | Python + pywebview（旧路线） | ✅ 完成可用（不再维护） | 稳定版：界面、托盘、差额统计都正常 |
| `V2/` | Python + pywebview（旧路线） | ⛔ 废案 | 尝试加“钉子/缩放/拖动”的一整条线，最终因稳定性问题废弃 |
| `V2.1/` | Electron（新路线）开发版 | ✅ 源码（已被 V2.2 打包） | main.js/preload/界面全部实现 |
| `V2.2/` | **Electron 打包发布版** | ✅ 可分发 | 免安装单 exe，自带渲染内核，双击即用 |

每个版本目录内都有一份 `版本日志.md`，说明：实现了什么、改了什么、出过什么错、完成度如何。

## 为什么换技术路线（重要背景）

旧路线使用 Python 的 pywebview（底层是 Windows 自带的 WebView2 渲染内核）。
在开发者的这台电脑上，WebView2 渲染层会**间歇性卡死**（程序“未响应”），
尝试过关闭 GPU 加速、屏蔽遮挡计算、启动自动重启、运行时心跳自愈等手段，
仍无法彻底消除，且影响操作。因此 V2 整条线被判定为废案，
转入 V2.1 的 Electron 方案（进程模型更成熟、可控性更强）。

## 更新日志与版本标签

- **[CHANGELOG.md](CHANGELOG.md)** —— 所有版本的汇总时间线，建议从这里看起
- 分册：[V1](V1/版本日志.md)　[V2（废案）](V2/版本日志.md)　[V2.1](V2.1/版本日志.md)　[V2.2](V2.2/版本日志.md)

Git 历史里每个版本对应一个提交和一个标签，可以直接切过去看当时的代码：

| 标签 | 目录 | 说明 |
|---|---|---|
| `v1.0` | `V1/` | Python + pywebview 稳定版 |
| `v1.0-verify` | `V1-对外验证版/` | V1 的对外验证包 |
| `v2.0-abandoned` | `V2/` | 交互试验线，已废弃 |
| `v2.1` | `V2.1/` | Electron 开发版 |
| `v2.2` | `V2.2/` | Electron 打包发布版 |

```bash
git checkout v1.0     # 回到当初的 V1
git checkout main     # 回到最新
```

## 运行方式

- **想直接用**：从 [Releases](https://github.com/YuyuhongJackie/DeepSeek-Balance-Monitor/releases) 下载 `DeepSeekBalanceMonitor-2.2.0-portable.exe`，双击即用。
- **V1（Python 路线）**：需要 Python 3 + `pywebview` + `pystray`，或用 `DeepSeekBalanceMonitor.spec` 自行打包。
- **V2.1（Electron 路线）**：进入 `V2.1/electron/`，先 `npm install` 装依赖，再 `npm start` 启动；`npm run dist` 打包成免安装 exe。原开发环境用的是内置的免安装 Node.js（`V2.1/.nodejs`，未入库）。
