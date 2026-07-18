"""Tool 1.1: 确定性简历文件类型检测器。

纯函数，不调用 LLM。通过文件扩展名 + 文件头（magic bytes）双重判断，
输出 {"file_type": "pdf"|"docx"|"doc"|"unknown", "file_path": str}。
"""
from __future__ import annotations

from pathlib import Path


# 文件头签名（magic bytes）
_PDF_HEADER = b"%PDF"
# Office 2007+（docx / xlsx / pptx）是 ZIP 格式，以 PK 开头
_OOXML_HEADER = b"PK\x03\x04"
# Office 97-2003（doc / xls / ppt）使用 OLE2 复合文档格式
_OLE2_HEADER = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# 扩展名 → 类型映射
_EXTENSION_MAP: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "doc",
}


def _detect_by_header(header: bytes) -> str:
    """根据文件头签名判断文件类型。"""
    if header.startswith(_PDF_HEADER):
        return "pdf"
    if header.startswith(_OOXML_HEADER):
        # OOXML 格式无法仅凭头区分 docx/xlsx/pptx，需结合扩展名
        return "ooxml"
    if header.startswith(_OLE2_HEADER):
        return "doc"
    return ""


def file_type_detector(file_path: str) -> dict[str, str]:
    """检测简历文件类型。

    结合文件扩展名和文件头签名进行判断，返回::

        {"file_type": "pdf"|"docx"|"doc"|"unknown", "file_path": str}

    Parameters
    ----------
    file_path:
        简历文件的绝对或相对路径。

    Returns
    -------
    dict[str, str]
        ``file_type`` 为 ``"pdf"`` / ``"docx"`` / ``"doc"`` / ``"unknown"``，
        ``file_path`` 为规范化后的路径字符串。
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    # 读取文件头（前 8 字节即可覆盖所有已知签名）
    header = b""
    try:
        with path.open("rb") as f:
            header = f.read(8)
    except OSError:
        # 文件无法读取，只能靠扩展名兜底
        return {"file_type": _EXTENSION_MAP.get(suffix, "unknown"), "file_path": str(path)}

    header_type = _detect_by_header(header)

    # 优先使用文件头判断
    if header_type == "pdf":
        return {"file_type": "pdf", "file_path": str(path)}
    if header_type == "doc":
        return {"file_type": "doc", "file_path": str(path)}
    if header_type == "ooxml":
        # OOXML 需结合扩展名确认具体类型
        if suffix == ".docx":
            return {"file_type": "docx", "file_path": str(path)}
        # 如果是 OOXML 但扩展名不是 docx，仍然尝试用扩展名判断
        ext_type = _EXTENSION_MAP.get(suffix, "unknown")
        return {"file_type": ext_type, "file_path": str(path)}

    # 文件头无法识别时，用扩展名兜底
    return {"file_type": _EXTENSION_MAP.get(suffix, "unknown"), "file_path": str(path)}
