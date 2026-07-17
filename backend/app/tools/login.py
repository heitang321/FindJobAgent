"""浏览器登录脚本

用 subprocess 启动真实 Edge 浏览器（可见窗口），
用户手动登录招聘网站，登录态保存在本地目录，
后续 jd_fetcher 通过 CDP 连接同一 Edge 自动带登录态抓取。

为什么不用 Playwright 的 launch_persistent_context：
    Playwright 启动的 Chromium 会注入 --enable-automation 等标志，
    被 EdgeOne 检测为自动化浏览器。用 subprocess 启动真实 Edge 无此问题。
    另外，Chromium 和 Edge 的 cookie 加密密钥不同（绑定浏览器路径），
    用 Chromium 登录的 cookie，Edge 解不开，必须用同一个浏览器登录和抓取。

使用方式:
    cd backend
    python -m app.tools.login              # 登录智联招聘
    python -m app.tools.login --url <URL>  # 登录指定网站

流程:
1. 脚本用 subprocess 启动 Edge，导航到招聘网站
2. 你在 Edge 中手动完成登录（手机号验证码等）
3. 登录成功后，关闭 Edge 窗口
4. 登录态自动保存到 .browser_data/ 目录
5. 之后 jd_fetcher 通过 CDP 连接同一 Edge，自动带登录态
"""
import sys
import subprocess
from pathlib import Path

from app.tools._browser import BROWSER_DATA_DIR, EDGE_PATH


def login(site_url: str = "https://www.zhaopin.com/") -> None:
    """启动 Edge 让用户手动登录。

    Edge 窗口保持打开，直到用户关闭它。
    登录态（cookie、session）自动保存到 BROWSER_DATA_DIR。
    """
    BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not Path(EDGE_PATH).exists():
        raise FileNotFoundError(
            f"找不到 Edge 浏览器: {EDGE_PATH}\n"
            "请安装 Microsoft Edge 或修改 EDGE_PATH 路径"
        )

    proc = subprocess.Popen(
        [
            EDGE_PATH,
            f"--user-data-dir={BROWSER_DATA_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-session-crashed-bubble",  # 不显示"恢复页面"弹窗
            "--disable-features=Translate",      # 不显示翻译提示
            site_url,  # 直接打开登录页
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    print()
    print("=" * 50)
    print("Edge 浏览器已打开，请在浏览器中手动登录")
    print(f"当前网站: {site_url}")
    print()
    print("登录步骤:")
    print("  1. 在浏览器中点击「登录/注册」")
    print("  2. 使用手机号验证码或其他方式登录")
    print("  3. 登录成功后，直接关闭浏览器窗口")
    print()
    print("登录态将自动保存，后续 jd_fetcher 无需再次登录")
    print("=" * 50)
    print()

    # 等待用户关闭 Edge 窗口
    # proc.wait() 阻塞直到 Edge 进程退出
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()

    print("浏览器已关闭，登录态已保存。")
    print(f"数据目录: {BROWSER_DATA_DIR}")


if __name__ == "__main__":
    url = "https://www.zhaopin.com/"
    # 支持 --url 参数指定其他网站
    if "--url" in sys.argv:
        idx = sys.argv.index("--url")
        if idx + 1 < len(sys.argv):
            url = sys.argv[idx + 1]

    login(url)
