"""Pydantic contracts for Agent 2 job analysis."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings


def validate_job_url(value: str) -> str:
    """只允许受信任招聘站点的 HTTP(S) 详情页 URL。"""
    candidate = value.strip()
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").casefold().rstrip(".")
    allowed = tuple(item.casefold().lstrip(".") for item in settings.JOB_ALLOWED_HOSTS)
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("JD URL 必须是有效的 HTTP(S) 地址")
    if not any(host == item or host.endswith(f".{item}") for item in allowed):
        raise ValueError(f"仅支持招聘站点域名：{', '.join(settings.JOB_ALLOWED_HOSTS)}")
    return candidate


class JobAnalysisRequest(BaseModel):
    """前端提交 JD URL 的请求体。"""

    jd_url: str = Field(
        ...,
        description="招聘职位详情页 URL，例如 https://www.zhaopin.com/jobdetail/CC....htm",
    )

    _validate_jd_url = field_validator("jd_url")(validate_job_url)


class JobAnalysisResponse(BaseModel):
    """Agent 2 跑完返回的匹配结果和 gap 报告。"""

    task_id: str
    current_stage: str
    error: str | None = None
    jd_raw_text: str = ""
    job_requirements: dict[str, Any] = Field(default_factory=dict)
    match_result: dict[str, Any] = Field(default_factory=dict)
    gap_report: dict[str, Any] = Field(default_factory=dict)


class JobCardItem(BaseModel):
    """搜索结果中的单个岗位卡片（前端用 el-card 展示）。"""

    title: str = Field(..., description="职位名，如 'Python 后端开发工程师'")
    url: str = Field(
        ..., description="详情页 URL，如 https://www.zhaopin.com/jobdetail/CC....htm"
    )
    salary: str = Field("", description="薪资，如 '1.5-3万·15薪'")
    skills: list[str] = Field(
        default_factory=list, description="技能标签，如 ['Python', 'MySQL']"
    )
    location: str = Field("", description="地点，如 '上海·杨浦·新江湾城'")
    experience: str = Field("", description="经验要求，如 '1-3年' / '经验不限'")
    education: str = Field("", description="学历要求，如 '本科' / '大专'")
    company: str = Field("", description="公司名")
    company_tags: list[str] = Field(
        default_factory=list,
        description="公司标签，如 ['合资', '10000人以上', '软件/IT服务']",
    )


class JobSearchRequest(BaseModel):
    """前端请求自动检索岗位的请求体。

    keywords 留空时，后端从 state["structured_resume"] 自动推导（取 skills 前 3 + 职位方向）。
    筛选条件（experience/education/keyword）由后端对已抓取结果做服务端过滤。
    """

    keywords: str | None = Field(
        None, description="搜索关键词，留空则从简历 skills 自动推导"
    )
    city: str = Field("", description="城市筛选，空字符串表示全国")
    max_results: int = Field(30, description="从源站抓取的最大岗位数", ge=1, le=50)

    # 服务端筛选
    filter_city: str = Field("", description="城市后端过滤，如 '北京'")
    filter_experience: str = Field("", description="经验要求筛选，如 '1-3年'")
    filter_education: str = Field("", description="学历要求筛选，如 '本科'")
    filter_keyword: str = Field("", description="职位/公司/技能关键词模糊搜索")

    # 分页
    page: int = Field(1, description="页码，从 1 开始", ge=1)
    page_size: int = Field(10, description="每页条数", ge=1, le=30)


class JobSearchResponse(BaseModel):
    """岗位检索接口返回。"""

    task_id: str
    current_stage: str
    error: str | None = None
    keywords: str = Field(..., description="实际使用的搜索关键词（自动推导或用户传入）")
    job_search_results: list[JobCardItem] = Field(
        default_factory=list, description="当前页的岗位卡片列表"
    )
    total: int = Field(0, description="筛选后总岗位数")
    page: int = Field(1, description="当前页码")
    page_size: int = Field(10, description="每页条数")
    total_pages: int = Field(1, description="总页数")
