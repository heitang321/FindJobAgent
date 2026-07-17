"""JD 正文提取工具

从 jd_fetcher 返回的页面文本中提取纯 JD 正文。
去除导航栏、操作按钮、相似职位、公司介绍、页脚等噪音。

设计思路：
1. 用文本标记定位 JD 内容边界（不依赖 CSS 选择器，通用性强）
   - 起点标记: "职位描述" / "岗位职责"
   - 终点标记: "工作地点" / "公司信息"
2. 向上回溯获取职位元信息（职位名、薪资、地点等）
   - 过滤掉操作按钮（收藏、投递、分享等）和导航链接
3. 如果找不到标记，返回原文（交给后续 LLM 处理）

为什么不用 CSS 选择器：
    CSS 选择器依赖网站的 DOM 结构，网站改版会导致提取失效。
    文本标记是各招聘网站的通用约定（"职位描述"、"工作地点" 等），
    不受 DOM 结构变化影响。

为什么不用 LLM 做这步：
    LLM 提取成本高（每次调用都要发 token），文本标记提取快速、免费、可靠。
    LLM 留给后续的结构化步骤（requirement_extractor）。
"""
from __future__ import annotations

# JD 正文起点标记（各大招聘网站通用）
_JD_START_MARKERS = (
    "职位描述",
    "岗位职责",
    "Job Description",
    "job description",
)

# JD 正文终点标记
_JD_END_MARKERS = (
    "工作地点",
    "公司信息",
    "Work Location",
    "Company Info",
    "公司基本信息",
)

# 操作按钮和噪音关键词（向上回溯时过滤掉）
_NOISE_KEYWORDS = (
    "收藏", "投递", "分享", "举报", "更新时间",
    "微信", "扫码", "APP", "刷新", "下载",
    "立即", "查看", "更多",
    "点评", "标签", "好评", "中评",
)


def _find_marker_line(
    lines: list[str], markers: tuple[str, ...], start_from: int = 0
) -> int | None:
    """在 lines 中从 start_from 开始查找第一个匹配 markers 的行索引。

    匹配规则：行文本（去除首尾空白后）等于某个 marker，或以某个 marker 开头。
    """
    for i in range(start_from, len(lines)):
        line = lines[i].strip()
        for marker in markers:
            if line == marker or line.startswith(marker):
                return i
    return None


def _is_noise_line(line: str) -> bool:
    """判断一行是否是操作按钮或噪音"""
    line = line.strip()
    if not line or len(line) <= 1:
        return True
    return any(kw in line for kw in _NOISE_KEYWORDS)


def extract_jd_text(page_text: str, context_lines: int = 15) -> str:
    """从页面文本中提取 JD 正文。

    提取范围：
    - 正文：从"职位描述"到"工作地点"（不含终点行）
    - 元信息：从"职位描述"向上回溯 context_lines 行，过滤噪音后保留
      （用于抓取职位名、薪资、地点等元信息）

    如果找不到起点标记，返回原文（交给 LLM 处理）。

    Args:
        page_text: jd_fetcher 返回的页面完整文本
        context_lines: 向上回溯的行数（抓取职位名、薪资等元信息），默认 12 行

    Returns:
        提取后的 JD 文本（元信息 + 正文），去除了导航栏、相似职位、公司介绍等噪音
    """
    lines = page_text.split("\n")

    # 1. 找 JD 正文起点
    start_idx = _find_marker_line(lines, _JD_START_MARKERS)
    if start_idx is None:
        # 找不到标记，返回原文（交给 LLM 处理）
        return page_text.strip()

    # 2. 找 JD 正文终点
    end_idx = _find_marker_line(lines, _JD_END_MARKERS, start_from=start_idx + 1)
    if end_idx is None:
        end_idx = len(lines)

    # 3. 向上回溯获取职位元信息
    #    从 start_idx 往上看 context_lines 行，过滤掉操作按钮等噪音
    metadata_lines: list[str] = []
    for i in range(start_idx - 1, max(start_idx - context_lines, -1), -1):
        line = lines[i]
        if _is_noise_line(line):
            continue
        metadata_lines.insert(0, line.strip())

    # 4. 组合：元信息 + JD 正文
    jd_lines = [line.strip() for line in lines[start_idx:end_idx]]
    result = "\n".join(metadata_lines + jd_lines).strip()

    return result


if __name__ == "__main__":
    # 测试入口：抓取 URL → 提取 JD 正文 → 对比压缩比
    from app.tools.jd_fetcher import fetch_jd_from_url

    test_url = input("请输入招聘职位 URL: ").strip()
    if test_url:
        print(f"\n正在抓取: {test_url}")
        page_text = fetch_jd_from_url(test_url)
        print(f"\n=== 原始页面文本: {len(page_text)} 字符 ===")

        jd_text = extract_jd_text(page_text)
        print(f"\n=== 提取后 JD 正文: {len(jd_text)} 字符 ===")
        print(jd_text)
        print(
            f"\n=== 压缩比: {len(jd_text)}/{len(page_text)} "
            f"= {len(jd_text) / len(page_text) * 100:.1f}% ==="
        )
