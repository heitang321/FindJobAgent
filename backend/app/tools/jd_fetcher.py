"""JD 抓取工具

从招聘网站 URL 抓取职位描述（JD）文本。

设计思路：
1. 通过 CDP 连接真实 Edge 浏览器（非 Playwright 启动的 Chromium），
   绕过腾讯云 EdgeOne 的高级机器人检测
2. Edge 使用和 login 脚本相同的 BROWSER_DATA_DIR，自动带登录态
3. 提取页面可见文本（innerText），不做针对特定网站的 CSS 选择器解析
4. 后续由 LLM 从页面文本中提取 JD 正文（见 requirement_extractor）

为什么用 CDP 而不是 launch_persistent_context:
    Playwright 的 launch_persistent_context 会注入 --enable-automation 等
    CDP 自动化标志，EdgeOne 能检测到这些标志并返回验证页面。
    CDP 模式连接的是 subprocess 启动的真实 Edge，没有这些自动化标志。

前置条件：
    首次使用前，需先运行 `python -m app.tools.login` 登录招聘网站，
    登录态会保存在 .browser_data/ 目录，后续抓取自动复用。
"""
from __future__ import annotations

from app.tools._browser import (
    CDP_ENDPOINT,
    cleanup_browser,
    ensure_browser_running,
)


def fetch_jd_from_url(url: str, timeout: int = 15000, render_wait: int = 3000) -> str:
    """用 CDP 连接的真实 Edge 浏览器抓取 URL，返回页面文本。

    自动启动 Edge（如未运行），使用 BROWSER_DATA_DIR 中的登录态。
    抓取完成后自动关闭由本函数启动的 Edge 进程。

    Args:
        url: 招聘职位详情页 URL
        timeout: 页面加载超时（毫秒），默认 15 秒
        render_wait: DOM 加载后额外等待 JS 渲染的时间（毫秒），默认 3 秒。
            招聘网站常有持续的网络请求（广告、统计上报），
            会导致 networkidle 永远不触发，所以改用固定等待。

    Returns:
        页面的可见文本内容

    Raises:
        FileNotFoundError: Edge 未安装
        RuntimeError: Edge 启动失败
        Exception: 页面加载失败或超时
    """
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "抓取 JD URL 需要安装 Playwright：pip install playwright"
        ) from exc

    # 启动 Edge（如果 CDP 端口未就绪则自动启动，返回进程对象用于后续清理）
    proc = ensure_browser_running()

    try:
        with sync_playwright() as p:
            # 通过 CDP 连接到真实 Edge
            # connect_over_cdp 连接的是 subprocess 启动的真实浏览器，
            # 没有 Playwright 的 --enable-automation 等自动化标志
            browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)

            # 获取 Edge 已有的浏览器上下文（启动时自动创建）
            context = browser.contexts[0] if browser.contexts else browser.new_context()

            # 新开一个页面来抓取（不影响用户可能打开的其他页面）
            page = context.new_page()
            try:
                # domcontentloaded: 等 DOM 解析完成，不等所有资源
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                # 固定等待，让 JS 渲染职位内容
                page.wait_for_timeout(render_wait)
                # 提取页面可见文本
                text = page.inner_text("body")
                return text
            finally:
                page.close()
                # 不调用 browser.close() —— 那会关闭整个 Edge
                # sync_playwright 上下文退出时自动断开 CDP 连接
    finally:
        # 关闭我们启动的 Edge 进程（如果是我们启动的）
        cleanup_browser(proc)


if __name__ == "__main__":
    # 测试入口：抓取一个 URL 并打印前 2000 字符
    test_url = input("请输入招聘职位 URL: ").strip()
    if test_url:
        print(f"\n正在抓取: {test_url}")
        result = fetch_jd_from_url(test_url)
        print("\n=== 页面文本（前 2000 字符）===")
        print(result[:2000])
        print(f"\n=== 总字符数: {len(result)} ===")
