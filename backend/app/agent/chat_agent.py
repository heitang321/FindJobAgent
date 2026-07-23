"""智能问答 Agent。

根据用户问题关键词路由到不同回答逻辑：
- 岗位搜索 → 调用 zhaopin 搜索岗位
- 简历优化 → 修改建议 + 引导
- 图表 → LLM 生成 ECharts option JSON
- 数据分析 → LLM 分析回答
- 面试 → 面试技巧
- 薪资 → 薪资分析
- 默认 → 通用问答

支持多轮对话记忆（history 参数）。
流式输出由 route 层的 chat.py 直接调用 chat_completion_stream 实现。
"""
from __future__ import annotations

import json
import re

from app.model.openai_compatible import chat_completion


# 可流式输出的类型（文本类，逐 token 返回）
STREAMABLE_TYPES = {"qa", "analysis", "interview", "salary", "resume_advice"}


class ChatAgent:
    """智能问答路由 Agent。"""

    # ===== 关键词路由规则 =====
    # 岗位搜索用两段匹配：搜索动词 + 岗位名词
    SEARCH_VERBS = (
        "搜索", "搜", "查找", "查询", "查", "找", "推荐", "列出", "有哪些",
        "帮忙找", "帮我找", "看", "看看",
    )
    JOB_NOUNS = ("岗位", "职位", "工作", "招聘")
    # 简单关键词路由（非两段匹配）
    JOB_SEARCH_KEYWORDS = ("招聘", "岗位列表", "岗位推荐")
    RESUME_KEYWORDS = (
        "优化简历", "改简历", "修改简历", "简历优化", "简历改写",
        "简历修改", "简历怎么改", "完善简历", "简历建议",
        "简历点评", "简历评估", "我的简历",
    )
    CHART_KEYWORDS = (
        "图表", "画图", "柱状图", "折线图", "饼图", "散点图",
        "雷达图", "echarts", "可视化", "画一个",
    )
    ANALYSIS_KEYWORDS = (
        "数据分析", "分析一下", "统计分析", "数据趋势",
        "数据对比", "指标分析",
    )
    INTERVIEW_KEYWORDS = (
        "面试", "面经", "面试题", "面试技巧", "自我介绍",
        "面试问题", "怎么面试", "面试准备",
    )
    SALARY_KEYWORDS = (
        "薪资", "工资", "薪酬", "待遇", "多少钱",
        "薪水", "收入",
    )

    def route(self, question: str) -> str:
        """只判断路由类型，不执行回答逻辑。供流式路由层调用。"""
        q = question.strip()
        # 岗位搜索：两段匹配（动词 + 名词）或简单关键词
        if self._is_job_search(q):
            return "job_search"
        if any(kw in q for kw in self.RESUME_KEYWORDS):
            return "resume_advice"
        if any(kw in q for kw in self.CHART_KEYWORDS):
            return "chart"
        if any(kw in q for kw in self.ANALYSIS_KEYWORDS):
            return "analysis"
        if any(kw in q for kw in self.INTERVIEW_KEYWORDS):
            return "interview"
        if any(kw in q for kw in self.SALARY_KEYWORDS):
            return "salary"
        return "qa"

    def get_system_prompt(self, route_type: str) -> str:
        """返回指定路由类型的 system prompt（流式输出时用）。"""
        prompts = {
            "qa": (
                "你是 FindJobAgent 智能助手，专注于求职辅助领域。"
                "你可以回答简历优化、面试技巧、职业规划、SQL 技术问题等。"
                "回答简洁、专业，可以使用 markdown 格式。"
            ),
            "analysis": (
                "你是一个数据分析专家。请根据用户的问题进行数据分析，"
                "给出有逻辑、有条理的分析结论。"
                "可以使用 markdown 格式（标题、列表、表格、加粗等）增强可读性。"
            ),
            "interview": (
                "你是一个资深面试官和求职导师。请根据用户的问题给出专业的面试建议。\n"
                "可以涵盖：自我介绍模板、常见面试题及答题思路、项目经验描述（STAR 法则）、"
                "技术面试准备、HR 面应对、薪资谈判技巧等。\n"
                "回答使用 markdown 格式，结构清晰，实用性强。"
            ),
            "salary": (
                "你是一个薪资分析专家，熟悉中国互联网/IT 行业的薪酬体系。"
                "请根据用户的问题给出薪资分析和建议。\n"
                "可以涵盖：不同城市/岗位/经验级别的薪资范围、薪资构成（base+奖金+股票）、"
                "谈薪技巧、跳槽涨薪幅度参考等。\n"
                "回答使用 markdown 格式，数据合理，注明仅供参考。"
            ),
            "resume_advice": (
                "你是 FindJobAgent 的简历优化顾问。用户提到了简历相关需求，请：\n"
                "1. 如果用户描述了具体的简历问题，给出针对性的修改建议（用 markdown 格式）。\n"
                "2. 如果用户只是泛泛地提到简历，询问用户是否需要优化简历，"
                "并建议用户前往「简历优化」页面上传简历，系统会自动进行结构化分析和 AI 优化。\n"
                "3. 可以涵盖：简历结构、内容表达、STAR 法则、技能描述、项目经历写法等。\n"
                "4. 回答简洁专业，控制在 300 字以内。"
            ),
        }
        return prompts.get(route_type, prompts["qa"])

    def answer(self, question: str, user_id: str = "", history: list[dict] | None = None) -> dict:
        """同步一次性回答（非流式），保留给非 SSE 场景使用。"""
        q = question.strip()
        route_type = self.route(q)
        if route_type == "job_search":
            return self._handle_job_search(q, user_id)
        if route_type == "chart":
            return self._handle_chart(q, history)
        # 文本类
        system = self.get_system_prompt(route_type)
        result = chat_completion(q, system_prompt=system, json_mode=False, history=history)
        if route_type == "resume_advice":
            result += "\n\n---\n💡 **提示**：前往「简历优化」页面上传简历，可获取完整的 AI 结构化分析和自动优化。"
        return {"type": route_type, "data": result}

    # ===== 图表分支（修复：不用 json_mode，自然语言提取 JSON） =====
    def _handle_chart(self, question: str, history: list[dict] | None = None) -> dict:
        """LLM 生成 ECharts option JSON。

        修复空白问题：不使用 json_mode（DashScope 对复杂 JSON 强制模式可能返回空），
        改为自然语言模式 + 从文本中提取 JSON。
        """
        system = (
            "你是一个 ECharts 图表配置专家。根据用户描述生成一个完整的 ECharts option JSON 对象。\n"
            "严格要求：\n"
            "1. 只输出 JSON 对象，以 { 开头，以 } 结尾。\n"
            "2. 不要包含 markdown 代码块标记（```json```）或任何说明文字。\n"
            "3. JSON 必须可以直接被 JSON.parse 解析。\n"
            "4. 必须包含以下字段：\n"
            '   - title: {"text": "图表标题", "left": "center"}\n'
            "   - tooltip: {\"trigger\": \"axis\"} (柱状图/折线图) 或 {\"trigger\": \"item\"} (饼图)\n"
            "   - xAxis: {\"type\": \"category\", \"data\": [\"标签1\", \"标签2\", ...]} (饼图不需要)\n"
            "   - yAxis: {\"type\": \"value\"} (饼图不需要)\n"
            '   - series: [{"name": "系列名", "type": "bar"|"line"|"pie", "data": [数值1, 数值2, ...]}]\n'
            "5. 数据点 5-8 个，数值为正整数。\n"
            "6. series 中的 data 数组长度必须和 xAxis.data 长度一致。\n\n"
            "示例（柱状图）：\n"
            '{"title":{"text":"编程语言流行度","left":"center"},'
            '"tooltip":{"trigger":"axis"},'
            '"legend":{"bottom":0},'
            '"xAxis":{"type":"category","data":["Python","Java","JavaScript","Go","C++"]},'
            '"yAxis":{"type":"value"},'
            '"series":[{"name":"热度","type":"bar","data":[95,85,90,75,70]}]}'
        )
        # 用 json_mode=False（自然语言），从响应中提取 JSON
        raw = chat_completion(question, system_prompt=system, json_mode=False, history=history)

        # 尝试直接解析
        option = None
        try:
            option = json.loads(raw)
        except json.JSONDecodeError:
            option = self._extract_json(raw)

        # 验证 option 有效性
        if isinstance(option, dict) and option.get("series"):
            option = self._normalize_echarts_option(option)
            return {"type": "chart", "data": json.dumps(option, ensure_ascii=False)}

        # 二次尝试：更简短的 prompt
        print(f"  [chart] 第一次解析失败，重试。raw 前 200 字: {raw[:200]}", flush=True)
        system_retry = (
            "请直接输出一个 ECharts option 的 JSON 对象，不要包含任何其他文字。\n"
            "格式：{\"title\":{\"text\":\"标题\",\"left\":\"center\"},"
            "\"tooltip\":{\"trigger\":\"axis\"},"
            "\"xAxis\":{\"type\":\"category\",\"data\":[...]},"
            "\"yAxis\":{\"type\":\"value\"},"
            "\"series\":[{\"name\":\"名\",\"type\":\"bar\",\"data\":[...]}]}\n"
            "数据 5-8 个，数值为整数。"
        )
        raw2 = chat_completion(question, system_prompt=system_retry, json_mode=False, history=history)
        try:
            option = json.loads(raw2)
        except json.JSONDecodeError:
            option = self._extract_json(raw2)

        if isinstance(option, dict) and option.get("series"):
            option = self._normalize_echarts_option(option)
            return {"type": "chart", "data": json.dumps(option, ensure_ascii=False)}

        # 都失败了，返回错误提示
        return {
            "type": "qa",
            "data": f"抱歉，图表生成失败。模型返回的内容无法解析为有效的 ECharts 配置。\n\n原始返回：\n```\n{raw[:500]}\n```\n\n请尝试更具体的描述，例如：'帮我画一个柱状图展示编程语言流行度'。",
        }

    # ===== 岗位搜索分支 =====
    def _handle_job_search(self, question: str, user_id: str) -> dict:
        """调用 zhaopin 搜索岗位。"""
        keywords = self._extract_job_keywords(question)
        if not keywords or len(keywords) < 2:
            return {
                "type": "qa",
                "data": "请告诉我你想搜索什么岗位，例如：'搜索 Python 后端岗位' 或 '推荐上海 Java 开发岗位'。",
            }

        try:
            import asyncio

            from app.tools.jd_fetcher import NoSearchResultsError, fetch_search_page

            cards = asyncio.run(
                fetch_search_page(keywords=keywords, city="", max_results=10)
            )

            if not cards:
                return {
                    "type": "qa",
                    "data": f"未找到与「{keywords}」相关的岗位，请尝试其他关键词。",
                }

            return {
                "type": "job_search",
                "data": json.dumps(cards, ensure_ascii=False),
                "keywords": keywords,
            }

        except NoSearchResultsError:
            return {
                "type": "qa",
                "data": f"未找到与「{keywords}」相关的岗位，请尝试其他关键词。",
            }
        except Exception as exc:
            error_msg = str(exc).strip() or type(exc).__name__
            return {
                "type": "qa",
                "data": f"岗位搜索暂时不可用：{error_msg}。请稍后重试，或前往简历优化页面使用自动推荐功能。",
            }

    # 指代词列表：如果问题中包含这些词 + 岗位名词，说明用户在问已有结果，不是要搜索
    _REFERENCE_WORDS = (
        "这些", "这个", "上面", "刚才", "前面", "之前的",
        "列表", "卡片", "哪个", "第几个", "几个",
    )

    @classmethod
    def _is_job_search(cls, question: str) -> bool:
        """两段匹配：问题中同时包含搜索动词和岗位名词。

        但如果包含指代词（这些/上面/刚才等），说明用户在询问已有结果，不算新搜索。
        """
        has_reference = any(w in question for w in cls._REFERENCE_WORDS)
        has_verb = any(v in question for v in cls.SEARCH_VERBS)
        has_noun = any(n in question for n in cls.JOB_NOUNS)
        has_keyword = any(kw in question for kw in cls.JOB_SEARCH_KEYWORDS)
        # 包含指代词时，不触发新搜索（即使有动词+名词）
        if has_reference:
            return False
        return has_keyword or (has_verb and has_noun)

    @staticmethod
    def _extract_job_keywords(question: str) -> str:
        """从用户问题中提取岗位搜索关键词。

        示例：
        - "搜索 Python 后端岗位" → "Python 后端"
        - "查询北京的 agent 开发岗位" → "北京 agent 开发"
        - "推荐上海 Java 开发岗位" → "上海 Java 开发"
        """
        cleaned = question
        # 去掉搜索动词前缀
        for prefix in ("帮忙搜索", "帮我搜索", "帮我找", "帮忙找",
                       "搜索", "查找", "查询", "推荐", "有哪些", "列出", "看一下", "看看",
                       "搜", "查", "找"):
            while cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
        # 去掉岗位名词后缀
        for suffix in ("的岗位", "的职位", "的工作", "的招聘信息", "的招聘",
                       "岗位", "职位", "工作", "招聘信息", "招聘"):
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)]
                break
        return cleaned.strip(" ，。、！？?的")

    # ===== 上下文继承 =====
    # 常见中国城市名（用于判断关键词中是否包含地点）
    _CITIES = (
        "北京", "上海", "广州", "深圳", "成都", "杭州", "南京", "武汉",
        "西安", "重庆", "苏州", "天津", "长沙", "青岛", "大连", "厦门",
        "福州", "无锡", "合肥", "郑州", "济南", "沈阳", "哈尔滨", "昆明",
        "贵阳", "南宁", "兰州", "太原", "石家庄", "呼和浩特", "乌鲁木齐",
        "宁波", "东莞", "佛山", "珠海", "中山", "惠州",
    )
    # 岗位类型限定词（追加到已有关键词后面）
    _JOB_TYPE_QUALIFIERS = (
        "实习", "全职", "兼职", "远程", "校招", "社招",
        "应届", "秋招", "春招",
    )

    @classmethod
    def _resolve_search_keywords(
        cls,
        current_keywords: str,
        prev_keywords: str = "",
        prev_city: str = "",
    ) -> tuple[str, str]:
        """根据上次搜索上下文补全当前搜索关键词。

        示例：
        - prev="成都agent开发", current="实习" → ("成都agent开发实习", "")
        - prev="上海Java", current="Python后端" → ("上海Python后端", "")
        - prev="北京Python", current="北京Python" → ("北京Python", "")  # 相同不补全

        返回 (resolved_keywords, city) 二元组。
        """
        if not prev_keywords:
            return current_keywords, prev_city

        # 如果当前关键词已经包含上次的核心内容，直接返回
        if current_keywords and prev_keywords in current_keywords:
            return current_keywords, prev_city

        # 提取上次搜索中的城市
        prev_city_in_kw = ""
        prev_core = prev_keywords
        for city in cls._CITIES:
            if city in prev_keywords:
                prev_city_in_kw = city
                prev_core = prev_keywords.replace(city, "").strip()
                break

        # 提取当前关键词中的城市
        current_has_city = any(city in current_keywords for city in cls._CITIES)

        # 如果当前关键词不含城市，且上次有城市 → 补全城市
        if prev_city_in_kw and not current_has_city:
            # 判断当前关键词是否是限定词（实习/全职等）
            is_qualifier = any(q in current_keywords for q in cls._JOB_TYPE_QUALIFIERS)
            if is_qualifier:
                # 限定词直接追加到上次完整关键词后面
                resolved = f"{prev_keywords}{current_keywords}"
            else:
                # 非限定词：城市 + 当前关键词 + 上次核心词
                resolved = f"{prev_city_in_kw}{current_keywords}"
                # 如果当前关键词不包含上次核心词，追加
                if prev_core and prev_core not in current_keywords:
                    resolved = f"{prev_city_in_kw}{current_keywords}{prev_core}"
            return resolved.strip(), prev_city_in_kw

        return current_keywords, prev_city_in_kw or prev_city

    # ===== 工具方法 =====
    @staticmethod
    def _extract_json(text: str) -> dict:
        """从可能包含 markdown 代码块的文本中提取 JSON。"""
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        return {}

    @staticmethod
    def _normalize_echarts_option(option: dict) -> dict:
        """补齐 ECharts option 的标准字段。"""
        title = option.get("title")
        if isinstance(title, str):
            option["title"] = {"text": title, "left": "center"}
        elif isinstance(title, dict):
            if "left" not in title:
                title["left"] = "center"
        elif title is None:
            option["title"] = {"text": "", "left": "center"}

        tooltip = option.get("tooltip")
        if tooltip is None:
            option["tooltip"] = (
                {"trigger": "axis"} if "xAxis" in option else {"trigger": "item"}
            )

        if "toolbox" not in option:
            option["toolbox"] = {
                "show": True,
                "feature": {"saveAsImage": {"show": True}},
            }

        series = option.get("series")
        if isinstance(series, dict):
            option["series"] = [series]

        return option


# 单例
_chat_agent: ChatAgent | None = None


def get_chat_agent() -> ChatAgent:
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = ChatAgent()
    return _chat_agent
