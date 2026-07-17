"""Playwright 浏览器共享配置

jd_fetcher 和 login 脚本共用这些常量和工具函数。

两种浏览器连接模式：
1. launch_persistent_context（旧模式）: Playwright 启动自带的 Chromium
   - 会注入 --enable-automation 等 CDP 自动化标志
   - 腾讯云 EdgeOne 能检测到，返回验证页面
   - 适用于不限制自动化的网站，或开发调试

2. CDP 连接真实 Edge（新模式）: 用 subprocess 启动系统 Edge，Playwright 通过 connect_over_cdp 连接
   - 真实浏览器没有自动化标志，EdgeOne 检测不到
   - 适用于有高级反爬检测的网站（如 jobs.zhaopin.com）
   - 不需要 stealth 脚本，因为 Edge 本身就是真实浏览器
"""
import socket
import subprocess
import time
from pathlib import Path

# ========== 反检测脚本（仅 launch_persistent_context 模式需要）==========
# CDP 模式连接真实 Edge 时不需要此脚本，真实浏览器没有自动化特征。
# 保留此脚本供 login.py 等仍用 persistent_context 的场景使用。

STEALTH_SCRIPT = """
// 隐藏 webdriver 标志（headless 浏览器这个值为 true）
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
// 模拟真实的插件列表
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
// 模拟真实的语言列表
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
// 添加 window.chrome 对象（正常浏览器有，headless 没有）
window.chrome = { runtime: {} };
// 模拟真实的平台信息
Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
"""

# 真实浏览器的 User-Agent（仅 launch_persistent_context 模式需要覆盖）
# CDP 模式下 Edge 自带真实 UA，不需要覆盖
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# ========== 持久化数据目录 ==========
# 保存 cookie、session 等登录态
# 路径: backend/.browser_data/  （已加入 .gitignore）
BROWSER_DATA_DIR = Path(__file__).resolve().parent.parent.parent / ".browser_data"

# ========== CDP 模式配置 ==========
# 用 CDP 连接真实 Edge 浏览器，而非 Playwright 自带的 Chromium
# 真实浏览器没有 --enable-automation 等自动化标志，
# 能绕过腾讯云 EdgeOne 的高级机器人检测

CDP_PORT = 9222
CDP_ENDPOINT = f"http://localhost:{CDP_PORT}"

# 系统安装的 Edge 浏览器路径（Chromium 内核，和 Chrome 行为一致）
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def _is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    """检查端口是否可连接"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _wait_for_port(port: int, timeout: int = 10) -> bool:
    """等待端口可用，返回是否在超时前就绪"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_port_open(port):
            return True
        time.sleep(0.3)
    return False


def ensure_browser_running() -> "subprocess.Popen | None":
    """确保 Edge 带 remote debugging port 运行中。

    如果 CDP 端口已就绪（Edge 已在运行），直接返回 None。
    否则用 subprocess 启动 Edge，--user-data-dir 指向 BROWSER_DATA_DIR，
    自动加载之前通过 login 脚本保存的登录态。

    关键区别（为什么不用 Playwright 的 launch_persistent_context）：
        Playwright 启动浏览器时会加 --enable-automation 等 CDP 标志，
        EdgeOne 检测到这些标志就返回验证页面。
        subprocess 启动的 Edge 没有这些标志，EdgeOne 认为它是真实用户。

    Returns:
        subprocess.Popen | None: 新启动的进程对象（用完需 cleanup_browser 关闭），
                                  或 None（端口已就绪，Edge 已在运行）

    Raises:
        FileNotFoundError: Edge 未安装
        RuntimeError: Edge 启动后端口未就绪
    """
    if _is_port_open(CDP_PORT):
        return None  # Edge 已经在运行

    if not Path(EDGE_PATH).exists():
        raise FileNotFoundError(
            f"找不到 Edge 浏览器: {EDGE_PATH}\n"
            "请安装 Microsoft Edge 或修改 EDGE_PATH 路径"
        )

    BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        [
            EDGE_PATH,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={BROWSER_DATA_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-session-crashed-bubble",  # 不显示"恢复页面"弹窗
            "--disable-features=Translate",      # 不显示翻译提示
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if not _wait_for_port(CDP_PORT, timeout=10):
        proc.kill()
        raise RuntimeError(
            f"Edge 启动后端口 {CDP_PORT} 未就绪\n"
            "可能原因: .browser_data 目录被其他进程锁定，或 Edge 版本不兼容"
        )

    return proc


def cleanup_browser(proc: "subprocess.Popen | None") -> None:
    """关闭由 ensure_browser_running() 启动的浏览器进程。

    如果 proc 为 None（Edge 是外部启动的），不做任何操作。
    """
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
