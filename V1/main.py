# -*- coding: utf-8 -*-
"""DeepSeek 余额监控 - 桌面版入口

界面为 balance-widget.html（Edge WebView2 渲染），本文件提供：
- 真实余额接口调用（避免浏览器跨域问题）
- 账号 / 基准额度的本地持久化（%APPDATA%\\DeepSeekBalanceMonitor\\config.json）
- 无边框窗口、窗口拖动、置顶切换、退出
"""

import json
import os
import sys
import subprocess
import threading
import time
import traceback
import urllib.error
import urllib.request
import ctypes
from ctypes import wintypes

import webview

# 稳定性关键项：禁用 WebView2 硬件加速。
# 本机 GPU/显卡驱动不稳会导致渲染进程卡死、窗口无响应（AppHang）。
os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--disable-gpu --disable-gpu-compositing --disable-accelerated-2d-canvas")


APP_TITLE = "DeepSeek 余额监控"
BALANCE_API = "https://api.deepseek.com/user/balance"
MUTEX_NAME = "Local\\DeepSeekBalanceMonitor.SingleInstance"
_mutex_handle = None
_main_hwnd = None
_app_ready = threading.Event()   # 页面启动完成信号（供看门狗判定）
_user_exit = False               # 用户主动退出标志（避免误触发自动重启）


def resource_path(rel):
    """开发模式取项目目录；打包后取 PyInstaller 解包目录。"""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, rel)


def widget_url():
    """返回打包内 HTML 的本地地址（#app 用于前端识别桌面模式）。"""
    path = resource_path("balance-widget.html")
    return "file:///" + path.replace("\\", "/") + "#app"


def set_window_icon(window):
    """运行窗口/任务栏图标：WinForms 默认取 exe 图标，这里显式设置一次兜底。"""
    try:
        ico = None
        for _ in range(40):
            try:
                # .NET 运行时由 pywebview 启动后加载，这里等待它就绪再导入
                from System.Drawing import Icon
                if ico is None:
                    ico = Icon(resource_path("app_icon.ico"))
                form = window.native.FindForm()
                if form is not None:
                    form.Icon = ico
                    debug_log("window icon applied")
                    return
            except Exception:
                time.sleep(0.5)
        debug_log("window icon skipped (runtime unavailable)")
    except Exception as e:
        debug_log("window icon failed: %s" % e)


def config_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    directory = os.path.join(base, "DeepSeekBalanceMonitor")
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, "config.json")


def debug_log(msg):
    """写入调试日志，便于排查打包后启动问题。"""
    try:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        directory = os.path.join(base, "DeepSeekBalanceMonitor")
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, "debug.log"), "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _find_app_hwnd():
    """按窗口标题查找本程序主窗口（返回第一个匹配句柄）。"""
    user32 = ctypes.windll.user32
    found = []
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value == APP_TITLE:
                found.append(hwnd)
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return found[0] if found else None


def _show_existing_window():
    """找到已运行实例的窗口，从托盘恢复到前台。"""
    try:
        hwnd = _find_app_hwnd()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW（隐藏窗口也能唤出）
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass



def _native_set_visible(show):
    """用 Win32 API 直接显示/隐藏主窗口。

    绕过 pywebview 的 hide()/show()：实测其 show() 在"启动即隐藏"场景下
    无法把窗口重新显示出来，ShowWindow 是最底层可靠的方案。
    """
    global _main_hwnd
    hwnd = _main_hwnd or _find_app_hwnd()
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    if show:
        user32.ShowWindow(hwnd, 5)  # SW_SHOW
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
    else:
        user32.ShowWindow(hwnd, 0)  # SW_HIDE
    return True


def ensure_single_instance():
    """通过命名互斥锁保证只有一个实例；重复启动时唤起已有窗口并退出。"""
    global _mutex_handle
    kernel32 = ctypes.windll.kernel32
    _mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        debug_log("another instance already running, restoring it")
        _show_existing_window()
        return False
    return True


class Api:
    """暴露给前端 JavaScript 的桥接方法。"""

    def __init__(self):
        self._cfg_path = config_path()
        self.config = self._load_config()
        # 注意：必须是私有属性（_ 开头）。pywebview 注入 API 时会递归展开公开属性，
        # 如果把 Window 对象挂在公开属性上，展开会极慢甚至卡死（详见 issue 噪音日志）
        self._window = None
        debug_log(
            "config loaded, accounts=%d active=%s reference=%s"
            % (
                len(self.config.get("accounts", [])),
                self.config.get("activeId"),
                self.config.get("reference"),
            )
        )

    def _load_config(self):
        default = {"accounts": [], "activeId": None, "reference": 100, "baselines": {}}

        try:
            with open(self._cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return default

    def get_config(self):
        debug_log(
            "get_config called, returning accounts=%d"
            % len(self.config.get("accounts", []))
        )
        return self.config

    def save_config(self, cfg):
        try:
            self.config = cfg if isinstance(cfg, dict) else {}
            debug_log(
                "save_config called, accounts=%d"
                % (len(self.config.get("accounts", [])) if isinstance(self.config, dict) else -1)
            )
            with open(self._cfg_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def log(self, msg):
        """前端 JS 侧调试日志。"""
        debug_log("JS: %s" % msg)
        return True

    def get_balance(self, key):
        key = (key or "").strip()
        req = urllib.request.Request(
            BALANCE_API,
            headers={
                "Accept": "application/json",
                "Authorization": "Bearer " + key,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError("HTTP " + str(e.code))
        except Exception as e:
            raise RuntimeError("网络请求失败：" + str(e))

        infos = data.get("balance_infos") or []
        if not infos:
            raise RuntimeError("接口响应格式异常")
        info = next((b for b in infos if b.get("currency") == "CNY"), infos[0])
        try:
            amount = float(info.get("total_balance", 0))
        except (TypeError, ValueError):
            raise RuntimeError("余额字段缺失")
        return {"amount": amount, "currency": info.get("currency", "CNY")}

    def toggle_top(self):
        if self._window is None:
            return False
        self._window.on_top = not self._window.on_top
        return self._window.on_top

    def minimize(self):
        """最小化到托盘（隐藏窗口）。"""
        try:
            if _native_set_visible(False):
                return True
            if self._window is not None:
                self._window.hide()
                return True
        except Exception:
            pass
        return False

    def show(self):
        try:
            if _native_set_visible(True):
                return True
            if self._window is not None:
                self._window.show()
                return True
        except Exception:
            pass
        return False

    def ready(self):
        """前端页面完成启动后调用，供启动看门狗确认应用正常。"""
        _app_ready.set()
        return True

    def exit(self):
        global _user_exit
        _user_exit = True
        if self._window is not None:
            self._window.destroy()


# ===================== 自定义 Win32 系统托盘（替代 pystray） =====================
# pystray 的右键菜单在部分 Windows 环境失效（菜单句柄未被创建导致右键无反应），
# 这里直接用 Shell_NotifyIcon 实现：单击/双击图标显示窗口，右键弹出"显示主界面/退出"。

_WM_TRAY_CALLBACK = 0x0400 + 233
_NIM_ADD = 0
_NIM_DELETE = 2
_NIF_MESSAGE = 1
_NIF_ICON = 2
_NIF_TIP = 4
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010
_WM_LBUTTONUP = 0x0202
_WM_LBUTTONDBLCLK = 0x0203
_WM_RBUTTONUP = 0x0205
_WM_QUIT = 0x0012
_MF_STRING = 0
_MF_SEPARATOR = 0x0800
_TPM_RETURNCMD = 0x0100
_TPM_RIGHTALIGN = 0x0008
_TPM_BOTTOMALIGN = 0x0020
_CMD_SHOW = 1
_CMD_QUIT = 2


class _NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HANDLE),
        ("szTip", ctypes.c_wchar * 128),
    ]


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


if not hasattr(wintypes, 'LRESULT'):
    wintypes.LRESULT = ctypes.c_longlong  # Python 3.9 的 wintypes 缺少 LRESULT

_WNDPROC = ctypes.WINFUNCTYPE(
    wintypes.LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_shell32 = ctypes.windll.shell32

_user32.RegisterClassW.restype = wintypes.ATOM
_user32.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASSW)]
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HANDLE, wintypes.HINSTANCE, wintypes.LPVOID,
]
_user32.LoadImageW.restype = wintypes.HANDLE
_user32.LoadImageW.argtypes = [
    wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
_user32.AppendMenuW.restype = wintypes.BOOL
_user32.AppendMenuW.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
_user32.TrackPopupMenuEx.restype = wintypes.UINT
_user32.TrackPopupMenuEx.argtypes = [
    wintypes.HANDLE, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.LPVOID,
]
_user32.DestroyMenu.restype = wintypes.BOOL
_user32.DestroyMenu.argtypes = [wintypes.HANDLE]
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.GetCursorPos.restype = wintypes.BOOL
_user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
_user32.DestroyIcon.restype = wintypes.BOOL
_user32.DestroyIcon.argtypes = [wintypes.HANDLE]
_user32.DestroyWindow.restype = wintypes.BOOL
_user32.DestroyWindow.argtypes = [wintypes.HWND]
_user32.PostMessageW.restype = wintypes.BOOL
_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.DefWindowProcW.restype = wintypes.LRESULT
_user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.CreatePopupMenu.restype = wintypes.HANDLE
_user32.CreatePopupMenu.argtypes = []

_shell32.Shell_NotifyIconW.restype = wintypes.BOOL
_shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(_NOTIFYICONDATA)]


class TrayIcon:
    """原生系统托盘：单击/双击显示窗口，右键弹出（显示主界面/退出）菜单。"""

    def __init__(self, icon_path, tip, on_show, on_quit):
        self._icon_path = icon_path
        self._tip = tip
        self._on_show = on_show
        self._on_quit = on_quit
        self._hwnd = None
        self._hicon = None
        self._thread = None
        self._nid = None
        self._wndproc = _WNDPROC(self._proc)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="tray-thread")
        self._thread.start()

    def stop(self):
        if self._hwnd:
            try:
                _user32.PostMessageW(self._hwnd, _WM_QUIT, 0, 0)
            except Exception:
                pass

    def _run(self):
        hinst = _kernel32.GetModuleHandleW(None)
        wc = _WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p)
        wc.hInstance = hinst
        wc.lpszClassName = "DeepSeekBalanceTrayWnd"
        atom = _user32.RegisterClassW(ctypes.byref(wc))
        if atom == 0 and _kernel32.GetLastError() != 1410:  # 1410 = 类已存在
            debug_log("tray: RegisterClass failed")
            return

        self._hwnd = _user32.CreateWindowExW(
            0, "DeepSeekBalanceTrayWnd", "", 0,
            0, 0, 0, 0, None, None, hinst, None,
        )
        if not self._hwnd:
            debug_log("tray: CreateWindow failed")
            return

        self._hicon = _user32.LoadImageW(
            None, self._icon_path, _IMAGE_ICON, 32, 32, _LR_LOADFROMFILE
        )
        if not self._hicon:
            debug_log("tray: LoadImage failed path=%s" % self._icon_path)

        nid = _NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(_NOTIFYICONDATA)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = _NIF_MESSAGE | _NIF_ICON | _NIF_TIP
        nid.uCallbackMessage = _WM_TRAY_CALLBACK
        nid.hIcon = self._hicon
        nid.szTip = self._tip[:127]
        self._nid = nid
        _shell32.Shell_NotifyIconW(_NIM_ADD, ctypes.byref(nid))
        debug_log("tray icon added (custom win32)")

        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

        try:
            _shell32.Shell_NotifyIconW(_NIM_DELETE, ctypes.byref(nid))
        except Exception:
            pass
        if self._hicon:
            _user32.DestroyIcon(self._hicon)
        _user32.DestroyWindow(self._hwnd)
        debug_log("tray thread ended")

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == _WM_TRAY_CALLBACK:
            if lparam == _WM_LBUTTONUP or lparam == _WM_LBUTTONDBLCLK:
                self._safe_show()
            elif lparam == _WM_RBUTTONUP:
                self._show_menu()
        return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _safe_show(self):
        try:
            debug_log("tray click: show")
            self._on_show()
        except Exception as e:
            debug_log("tray show callback error: %s" % e)

    def _show_menu(self):
        if not self._hwnd:
            return
        try:
            _user32.SetForegroundWindow(self._hwnd)
            pt = wintypes.POINT()
            _user32.GetCursorPos(ctypes.byref(pt))
            hmenu = _user32.CreatePopupMenu()
            _user32.AppendMenuW(hmenu, _MF_STRING, _CMD_SHOW, "显示主界面")
            _user32.AppendMenuW(hmenu, _MF_SEPARATOR, 0, None)
            _user32.AppendMenuW(hmenu, _MF_STRING, _CMD_QUIT, "退出")
            cmd = _user32.TrackPopupMenuEx(
                hmenu,
                _TPM_RETURNCMD | _TPM_RIGHTALIGN | _TPM_BOTTOMALIGN,
                pt.x, pt.y, self._hwnd, None,
            )
            _user32.DestroyMenu(hmenu)
            if cmd == _CMD_SHOW:
                self._safe_show()
            elif cmd == _CMD_QUIT:
                debug_log("tray menu: quit")
                self._on_quit()
        except Exception as e:
            debug_log("tray menu error: %s" % e)

def main():
    if not ensure_single_instance():
        return

    debug_log("--- app start (attempt %s) ---" % os.environ.get("DS_ATTEMPT", "1"))
    debug_log("frozen=%s _MEIPASS=%s" % (getattr(sys, "frozen", False), getattr(sys, "_MEIPASS", None)))
    html = resource_path("balance-widget.html")
    debug_log("html=%s exists=%s" % (html, os.path.exists(html)))
    debug_log("url=%s" % widget_url())

    api = Api()
    window = webview.create_window(
        APP_TITLE,
        url=widget_url(),
        js_api=api,
        width=420,
        height=404,
        frameless=True,
        resizable=False,
        background_color="#0d1226",
    )
    api._window = window

    def on_loaded():
        # 不再在加载回调里同步 evaluate_js，避免渲染进程卡住时阻塞主线程
        debug_log("page loaded (webview args=%s)" % os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"))
        # 捕获原生窗口句柄，供托盘显示/隐藏使用（不依赖 pywebview 的 hide/show）
        global _main_hwnd
        try:
            _main_hwnd = window.native.Handle.ToInt32()
            debug_log("native hwnd captured=%s" % _main_hwnd)

        except Exception as e:
            debug_log("hwnd capture failed: %s" % e)
        # 双击 exe 启动后直接显示窗口（不再自动隐藏到托盘；最小化按钮仍可进托盘）
        debug_log("window shown on start")


    window.events.loaded += on_loaded

    # 系统托盘：自定义 Win32 托盘（单击/双击显示，右键菜单含显示与退出）
    _tray = None

    def _tray_show():
        debug_log("tray action: show")
        try:
            if not _native_set_visible(True):
                window.show()
        except Exception as e:
            debug_log("tray show error: %s" % e)

    def _tray_quit():
        global _user_exit
        _user_exit = True
        debug_log("tray action: quit")
        try:
            window.destroy()
        except Exception as e:
            debug_log("tray quit error: %s" % e)

    try:
        _tray = TrayIcon(
            icon_path=resource_path("app_icon.ico"),
            tip=APP_TITLE,
            on_show=_tray_show,
            on_quit=_tray_quit,
        )
        _tray.start()
        debug_log("tray started (custom win32)")
    except Exception:
        debug_log("tray failed:\n%s" % traceback.format_exc())
        _tray = None

    def _watchdog(win):
        # 页面 12 秒内未就绪则结束本轮，主流程随后自动重启（应对本机 WebView2 间歇性卡死）
        if not _app_ready.wait(12):
            debug_log("watchdog: app not ready in 12s, forcing restart")
            try:
                win.destroy()
            except Exception as e:
                debug_log("watchdog destroy error: %s" % e)

    threading.Thread(target=_watchdog, args=(window,), daemon=True, name="watchdog").start()

    try:
        # private_mode=True（默认）：每次运行使用全新 WebView2 临时目录，
        # 避免持久化用户数据目录损坏后导致桥接注入挂起（账号存在 Python 配置里，不依赖它）
        threading.Thread(target=set_window_icon, args=(window,), daemon=True).start()
        webview.start(debug=False)
        debug_log("start returned (window closed)")
    except Exception:
        debug_log("start error:\n%s" % traceback.format_exc())

    if _tray is not None:
        try:
            _tray.stop()
        except Exception:
            pass

    # 看门狗判定启动超时且不是用户主动退出时：自动重启（最多 3 次）
    if not _app_ready.is_set() and not _user_exit:
        attempt = int(os.environ.get("DS_ATTEMPT", "1"))
        if attempt < 3:
            next_attempt = attempt + 1
            debug_log("relaunching (attempt %d -> %d)" % (attempt, next_attempt))
            try:
                env = dict(os.environ)
                env["DS_ATTEMPT"] = str(next_attempt)
                if getattr(sys, "frozen", False):
                    cmd = [sys.executable]
                else:
                    cmd = [sys.executable, os.path.abspath(__file__)]
                subprocess.Popen(
                    cmd,
                    env=env,
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                    close_fds=True,
                )
            except Exception as e:
                debug_log("relaunch error: %s" % e)
        else:
            debug_log("max relaunch attempts reached")
    else:
        debug_log("exit clean (ready=%s user_exit=%s)" % (_app_ready.is_set(), _user_exit))


if __name__ == "__main__":
    main()
