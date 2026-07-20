"""zhaopin 搜索结果页解析器。

从搜索页 HTML 中提取岗位卡片列表。每个卡片包含：
职位名、详情页 URL、薪资、技能标签、地点、经验、学历、公司名、公司类型/规模/行业。

CSS 选择器基于 zhaopin sou.zhaopin.com 搜索页真实 HTML 结构（2026-07 验证）。
核心选择器：
    - 卡片容器: .joblist-box__item
    - 职位名 + URL: .jobinfo__name (<a> 标签，href 是详情页 URL)
    - 薪资: .jobinfo__salary
    - 技能标签: .jobinfo__tag .joblist-box__item-tag (多个)
    - 其他信息(地点/经验/学历): .jobinfo__other-info-item (3 个)
    - 公司名: .companyinfo__name
    - 公司标签(类型/规模/行业): .companyinfo__tag .joblist-box__item-tag (多个)

设计：提供两种入口
    1. parse_from_page(page): 直接从 Playwright Page 对象提取（高效，浏览器端 JS 批量取）
    2. parse_from_html(html): 从 HTML 字符串提取（用 lxml，适合离线解析/测试）
"""

from __future__ import annotations

from typing import Any


# 岗位卡片结构（前端直接消费的 dict）
JobCard = dict[str, Any]


# zhaopin 搜索页卡片提取 JS（在浏览器端执行，返回 list[dict]）
# 用 querySelectorAll 遍历每个 .joblist-box__item，用嵌套 querySelector 取字段。
_EXTRACT_CARDS_JS = """
() => {
    const cards = [];
    const items = document.querySelectorAll('.joblist-box__item');
    for (const item of items) {
        try {
            // 职位名 + 详情页 URL
            const nameEl = item.querySelector('.jobinfo__name');
            const title = nameEl ? nameEl.textContent.trim() : '';
            const url = nameEl ? nameEl.href : '';

            // 薪资
            const salaryEl = item.querySelector('.jobinfo__salary');
            const salary = salaryEl ? salaryEl.textContent.trim() : '';

            // 技能标签
            const skillEls = item.querySelectorAll('.jobinfo__tag .joblist-box__item-tag');
            const skills = Array.from(skillEls).map(el => el.textContent.trim()).filter(Boolean);

            // 其他信息（地点/经验/学历）
            const otherEls = item.querySelectorAll('.jobinfo__other-info-item');
            const others = Array.from(otherEls).map(el => el.textContent.trim()).filter(Boolean);
            // 第一个含地点（带图片），第二个是经验，第三个是学历
            const location = others[0] || '';
            const experience = others[1] || '';
            const education = others[2] || '';

            // 公司名
            const companyEl = item.querySelector('.companyinfo__name');
            const company = companyEl ? companyEl.textContent.trim() : '';

            // 公司标签（类型/规模/行业）
            const compTagEls = item.querySelectorAll('.companyinfo__tag .joblist-box__item-tag');
            const compTags = Array.from(compTagEls).map(el => el.textContent.trim()).filter(Boolean);

            if (!title || !url) continue;  // 跳过无效卡片

            cards.push({
                title, url, salary, skills,
                location, experience, education,
                company, company_tags: compTags,
            });
        } catch (e) { continue; }
    }
    return cards;
}
"""


async def parse_from_page(page) -> list[JobCard]:
    """从 Playwright Page 对象提取岗位卡片列表。

    在浏览器端用 JS 批量提取，比逐个 query_selector + inner_text 快得多。
    前置条件：页面已加载完成，卡片已渲染。

    Args:
        page: playwright.async_api.Page 对象

    Returns:
        岗位卡片列表，每项是 dict 含:
        title / url / salary / skills / location / experience /
        education / company / company_tags
    """
    cards = await page.eval_on_selector_all(
        ".joblist-box__item",
        """(items) => items.map(item => {
            try {
                const nameEl = item.querySelector('.jobinfo__name');
                const title = nameEl ? nameEl.textContent.trim() : '';
                const url = nameEl ? nameEl.href : '';
                const salaryEl = item.querySelector('.jobinfo__salary');
                const salary = salaryEl ? salaryEl.textContent.trim() : '';
                const skillEls = item.querySelectorAll('.jobinfo__tag .joblist-box__item-tag');
                const skills = Array.from(skillEls).map(el => el.textContent.trim()).filter(Boolean);
                const otherEls = item.querySelectorAll('.jobinfo__other-info-item');
                const others = Array.from(otherEls).map(el => el.textContent.trim()).filter(Boolean);
                const location = others[0] || '';
                const experience = others[1] || '';
                const education = others[2] || '';
                const companyEl = item.querySelector('.companyinfo__name');
                const company = companyEl ? companyEl.textContent.trim() : '';
                const compTagEls = item.querySelectorAll('.companyinfo__tag .joblist-box__item-tag');
                const compTags = Array.from(compTagEls).map(el => el.textContent.trim()).filter(Boolean);
                if (!title || !url) return null;
                return { title, url, salary, skills, location, experience, education, company, company_tags: compTags };
            } catch (e) { return null; }
        }).filter(x => x !== null)""",
    )
    print(f"[search_parser] 解析出 {len(cards)} 个岗位卡片", flush=True)
    return cards


def parse_from_sync_page(page) -> list[JobCard]:
    """从 Playwright 同步 Page 对象批量提取岗位卡片。

    Windows 服务端通过工作线程使用同步 Playwright，以避免异步事件循环
    无法创建驱动子进程；字段格式与 ``parse_from_page`` 完全一致。
    """
    cards = page.evaluate(_EXTRACT_CARDS_JS)
    print(f"[search_parser] 解析出 {len(cards)} 个岗位卡片", flush=True)
    return cards


def parse_from_html(html: str) -> list[JobCard]:
    """从 HTML 字符串提取岗位卡片列表（用 lxml）。

    适合离线解析或单元测试。在线场景优先用 parse_from_page（更高效）。

    Args:
        html: 搜索页 HTML 字符串

    Returns:
        岗位卡片列表（同 parse_from_page 格式）
    """
    try:
        from lxml import html as lxml_html
    except ImportError as exc:
        raise RuntimeError("解析 HTML 需要安装 lxml：pip install lxml") from exc

    tree = lxml_html.fromstring(html)
    cards: list[JobCard] = []
    for item in tree.cssselect(".joblist-box__item"):
        try:
            name_el = item.cssselect(".jobinfo__name")
            if not name_el:
                continue
            title = name_el[0].text_content().strip()
            url = name_el[0].get("href", "")
            if not title or not url:
                continue

            salary_el = item.cssselect(".jobinfo__salary")
            salary = salary_el[0].text_content().strip() if salary_el else ""

            skills = [
                el.text_content().strip()
                for el in item.cssselect(".jobinfo__tag .joblist-box__item-tag")
            ]
            skills = [s for s in skills if s]

            others = [
                el.text_content().strip()
                for el in item.cssselect(".jobinfo__other-info-item")
            ]
            others = [o for o in others if o]
            location = others[0] if len(others) > 0 else ""
            experience = others[1] if len(others) > 1 else ""
            education = others[2] if len(others) > 2 else ""

            company_el = item.cssselect(".companyinfo__name")
            company = company_el[0].text_content().strip() if company_el else ""

            comp_tags = [
                el.text_content().strip()
                for el in item.cssselect(".companyinfo__tag .joblist-box__item-tag")
            ]
            comp_tags = [t for t in comp_tags if t]

            cards.append(
                {
                    "title": title,
                    "url": url,
                    "salary": salary,
                    "skills": skills,
                    "location": location,
                    "experience": experience,
                    "education": education,
                    "company": company,
                    "company_tags": comp_tags,
                }
            )
        except Exception:
            continue

    print(f"[search_parser] 从 HTML 解析出 {len(cards)} 个岗位卡片", flush=True)
    return cards
