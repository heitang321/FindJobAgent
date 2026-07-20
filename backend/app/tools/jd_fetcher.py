"""通过真实 Edge 的 CDP 接口抓取招聘页面。

公开入口保持异步，但完整的 Playwright 同步生命周期运行在工作线程中。
这是刻意的 Windows 兼容设计：部分 Uvicorn/asyncio 事件循环无法创建
Playwright 驱动所需的异步子进程，会直接抛出 ``NotImplementedError``。
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlencode

from app.tools._browser import (
    CDP_ENDPOINT,
    cleanup_browser,
    ensure_browser_running,
)


class NoSearchResultsError(RuntimeError):
    """搜索页正常打开，但当前关键词没有解析到岗位。"""


def _load_sync_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "浏览器抓取需要安装 Playwright：pip install playwright"
        ) from exc
    return sync_playwright


def _error_detail(exc: BaseException) -> str:
    """异常没有消息时也返回可诊断的文本。"""
    message = str(exc).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def _fetch_jd_from_url_sync(
    url: str,
    timeout: int,
    render_wait: int,
) -> str:
    """在线程中完成 Edge 启动、Playwright 连接和页面读取。"""
    sync_playwright = _load_sync_playwright()
    proc = ensure_browser_running()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(CDP_ENDPOINT)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                page.wait_for_timeout(render_wait)
                return page.inner_text("body")
            finally:
                page.close()
                # 不调用 browser.close()，避免关闭用户已打开的整个 Edge。
    except Exception as exc:
        raise RuntimeError(f"JD 页面抓取失败（{_error_detail(exc)}）") from exc
    finally:
        cleanup_browser(proc)


async def fetch_jd_from_url(
    url: str,
    timeout: int = 15000,
    render_wait: int = 3000,
) -> str:
    """抓取职位详情页可见文本，不阻塞 FastAPI 事件循环。"""
    return await asyncio.to_thread(
        _fetch_jd_from_url_sync,
        url,
        timeout,
        render_wait,
    )


def _fetch_search_page_sync(
    keywords: str,
    city: str,
    timeout: int,
    wait_selector: str,
    wait_timeout: int,
    max_results: int,
) -> list[dict]:
    """在线程中抓取并解析 zhaopin 搜索结果。"""
    sync_playwright = _load_sync_playwright()

    from app.tools.search_result_parser import parse_from_sync_page

    params = {"kw": keywords}
    if city:
        params["jl"] = city
    url = f"https://sou.zhaopin.com/?{urlencode(params)}"

    proc = ensure_browser_running()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(CDP_ENDPOINT)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                try:
                    page.wait_for_selector(wait_selector, timeout=wait_timeout)
                except Exception:
                    # 页面可能改版或仍在异步渲染，额外等待后交给解析器判断。
                    page.wait_for_timeout(5000)

                cards = parse_from_sync_page(page)
                if max_results:
                    cards = cards[:max_results]
                if not cards:
                    raise NoSearchResultsError(f"关键词“{keywords}”没有匹配到岗位")
                return cards
            finally:
                page.close()
    except NoSearchResultsError:
        raise
    except Exception as exc:
        raise RuntimeError(f"岗位搜索页抓取失败（{_error_detail(exc)}）") from exc
    finally:
        cleanup_browser(proc)


async def fetch_search_page(
    keywords: str,
    city: str = "",
    timeout: int = 30000,
    wait_selector: str = ".joblist-box__item",
    wait_timeout: int = 10000,
    max_results: int = 20,
) -> list[dict]:
    """搜索 zhaopin 岗位，不阻塞或依赖 FastAPI 的事件循环实现。"""
    return await asyncio.to_thread(
        _fetch_search_page_sync,
        keywords,
        city,
        timeout,
        wait_selector,
        wait_timeout,
        max_results,
    )


async def main() -> None:
    """命令行测试入口。"""
    test_url = input("请输入招聘职位 URL: ").strip()
    if test_url:
        print(f"\n正在抓取: {test_url}")
        result = await fetch_jd_from_url(test_url)
        print("\n=== 页面文本（前 2000 字符）===")
        print(result[:2000])
        print(f"\n=== 总字符数: {len(result)} ===")


if __name__ == "__main__":
    asyncio.run(main())
