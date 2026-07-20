"""浏览器抓取的 Windows 事件循环兼容性回归测试。"""

from __future__ import annotations

import threading

import pytest

from app.tools import jd_fetcher
from app.tools.search_result_parser import parse_from_sync_page


@pytest.mark.asyncio
async def test_search_runs_complete_playwright_work_in_worker_thread(monkeypatch):
    caller_thread = threading.get_ident()
    worker_threads: list[int] = []

    def fake_sync_fetch(
        keywords,
        city,
        timeout,
        wait_selector,
        wait_timeout,
        max_results,
    ):
        worker_threads.append(threading.get_ident())
        assert keywords == "RAG FAISS"
        assert city == "上海"
        assert max_results == 5
        return [{"title": "AI 工程师", "url": "https://jobs.zhaopin.com/demo"}]

    monkeypatch.setattr(jd_fetcher, "_fetch_search_page_sync", fake_sync_fetch)

    cards = await jd_fetcher.fetch_search_page(
        "RAG FAISS",
        city="上海",
        max_results=5,
    )

    assert cards[0]["title"] == "AI 工程师"
    assert worker_threads
    assert worker_threads[0] != caller_thread


def test_sync_page_parser_uses_synchronous_playwright_api():
    expected = [{"title": "Python 工程师", "url": "https://example.test/job"}]

    class FakePage:
        def evaluate(self, script):
            assert ".joblist-box__item" in script
            return expected

    assert parse_from_sync_page(FakePage()) == expected
